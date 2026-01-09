import time
import re
import os
import json
import math
import random
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- ASETUKSET ---
SHEET_NAME = 'Potwell Data'

STORES_TO_CHECK = {
    "Espoo (Iso Omena)": "k-citymarket-espoo-iso-omena",
    "Jyväskylä (Seppälä)": "k-citymarket-jyvaskyla-seppala",
    "Kuopio (Päiväranta)": "k-citymarket-kuopio-paivaranta",
    "Pirkkala": "k-citymarket-pirkkala",
    "Rovaniemi": "k-citymarket-rovaniemi",
    "Seinäjoki (Päivölä)": "k-citymarket-seinajoki-paivola",
    "Turku (Kupittaa)": "k-citymarket-turku-kupittaa",
    "Vaasa (Kivihaka)": "k-citymarket-vaasa-kivihaka",
    "Helsinki (KM Erottaja)": "k-market-erottaja",
    "Lappeenranta (KM Kourula)": "k-market-kourula",
    "Kuopio (KM Neulamuikku)": "k-market-neulamuikku",
    "Turku (KM PikkuKippari)": "k-market-pikkukippari",
    "Oulu (KM Pitkäkangas)": "k-market-pitkakangas",
    "Vantaa (KM Ruusu)": "k-market-ruusu",
    "Turku (KM Tampereentie)": "k-market-tampereentie",
    "Turku (SM Kivikukkaro)": "k-supermarket-kivikukkaro",
    "Tampere (SM Kuninkaankulma)": "k-supermarket-kuninkaankulma",
    "Jyväskylä (SM Länsiväylä)": "k-supermarket-lansivayla",
    "Espoo (SM Mankkaa)": "k-supermarket-mankkaa",
    "Kuopio (SM Matkus)": "k-supermarket-matkus",
    "Salo (SM Perniö)": "k-supermarket-pernio",
    "Lappeenranta (SM Rakuuna)": "k-supermarket-rakuuna",
    "Rovaniemi (SM Rinteenkulma)": "k-supermarket-rinteenkulma",
    "Helsinki (SM Saari)": "k-supermarket-saari"
}

SEARCH_QUERIES = [
    "6410405093080", "6410405041937", "6410402024469", "6410402008933", 
    "6410402024445", "6410405330727", "6415350002804", "2000623600005", 
    "6410405152305", "6410405039910", "6410405195746", "6410405149510", 
    "6410402008919", "6410402023479", "6410402023455", "6410402028634", 
    "6410402008896", "2000610500004", "6410405318183", "6410405174277", 
    "6410402017195", "6410405082725", "6410405174253", "6410405196651", 
    "6410402008773", "6410402022953", "6410405097248"
]

EXCLUDE_KEYWORDS = [
    "lastu", "salaatti", "pakaste", "gnocchi", "ranskan", "lohko", "muusi", 
    "kuorittu", "viipale", "suikale", "kroket", "kermaperuna", "valkosipuliperuna", 
    "sose", "kuutio", "biola"        
]

def clean_text(text):
    if not text: return ""
    text = text.replace('\u2212', '-').replace('–', '-').replace(',', '.').replace('€', '').strip()
    return text.encode('ascii', 'ignore').decode('ascii').strip()

def get_google_creds():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    json_creds = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if json_creds:
        creds_dict = json.loads(json_creds)
        return ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    if os.path.exists("service_account.json"):
        return ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
    raise Exception("Virhe: Google-tunnuksia ei löytynyt.")

def save_to_sheet(data_list):
    if not data_list: 
        print("⚠️ Lista tyhjä, mitään ei tallenneta.")
        return

    try:
        creds = get_google_creds()
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).sheet1
    except Exception as e:
        print(f"❌ VIRHE: Sheets-yhteys: {e}")
        return

    if not sheet.get_all_values():
        sheet.append_row(["pvm", "kauppa", "tuote", "ean", "hinta"])

    try: existing_records = sheet.get_all_records()
    except: existing_records = []

    existing_keys = set()
    for row in existing_records:
        key = f"{row.get('pvm')}_{row.get('kauppa')}_{row.get('ean')}"
        existing_keys.add(key)
        
    new_rows = []
    for item in data_list:
        key = f"{item['Pvm']}_{item['Kaupunki/Kauppa']}_{item['Hakusana']}"
        if key not in existing_keys:
            raw_price = str(item['Hinta (EUR)']).replace(',', '.')
            try: price_float = float(raw_price)
            except: price_float = 0.0
            new_rows.append([item['Pvm'], item['Kaupunki/Kauppa'], item['Tuote'], item['Hakusana'], price_float])

    if new_rows:
        sheet.append_rows(new_rows)
        print(f"✅ Tallennettu {len(new_rows)} uutta riviä.")
    else:
        print("ℹ️ Ei uusia tietoja tallennettavaksi.")

def get_proxy():
    """Get proxy from environment or use free proxy list"""
    # Try environment variable first
    proxy_url = os.environ.get("PROXY_URL")
    if proxy_url:
        return {"server": proxy_url}
    
    # Free proxy list (public proxies - may be unreliable)
    free_proxies = [
        # Add some free proxies here if needed
    ]
    
    if free_proxies:
        return {"server": random.choice(free_proxies)}
    
    return None

def create_stealth_browser(playwright, use_proxy=False):
    """Create a stealth browser with anti-detection"""
    
    launch_args = {
        "headless": True,
        "args": [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--window-size=1920,1080",
            "--start-maximized",
            "--disable-web-security",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-domain-reliability",
            "--disable-client-side-phishing-detection",
            "--disable-default-apps",
            "--disable-sync",
            "--disable-translate",
            "--metrics-recording-only",
            "--no-first-run",
            "--no-default-browser-check",
            "--no-zygote",
            "--disable-accelerated-2d-canvas",
            "--disable-accelerated-jpeg-decoding",
            "--disable-accelerated-mjpeg-decode",
            "--disable-app-list-dismiss-on-blur",
            "--disable-accelerated-video-decode",
            "--allow-running-insecure-content",
            "--autoplay-policy=user-gesture-required",
            "--disable-component-extensions-with-background-pages",
            "--disable-features=AudioServiceOutOfProcess,TranslateUI,BlinkGenPropertyTrees",
            "--disable-ipc-flooding-protection",
            "--disable-notifications",
            "--disable-offer-store-unmasked-wallet-cards",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            "--disable-speech-api",
            "--disable-print-preview",
            "--disable-hang-monitor",
            "--disable-extensions",
            "--mute-audio",
            "--disable-breakpad",
            "--disable-crash-reporter",
            "--disable-logging",
            "--disable-device-discovery-notifications",
            "--disable-background-networking",
        ]
    }
    
    if use_proxy:
        proxy = get_proxy()
        if proxy:
            launch_args["proxy"] = proxy
            print(f"🔒 Using proxy: {proxy['server']}")
    
    browser = playwright.chromium.launch(**launch_args)
    
    # Create context with stealth
    context = browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        locale='fi-FI',
        timezone_id='Europe/Helsinki',
        geolocation={'latitude': 60.1699, 'longitude': 24.9384},  # Helsinki
        permissions=['geolocation'],
        color_scheme='light',
        java_script_enabled=True,
        has_touch=False,
        is_mobile=False,
        device_scale_factor=1,
        screen={'width': 1920, 'height': 1080},
    )
    
    # Add stealth scripts
    context.add_init_script("""
        // Overwrite navigator properties
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );

        // Mock plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });

        // Mock languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['fi-FI', 'fi', 'en-US', 'en'],
        });

        // Mock webdriver
        Object.defineProperty(navigator, 'webdriver', {
            get: () => false,
        });

        // Mock chrome
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };

        // Mock permissions
        const originalPermissions = navigator.permissions;
        Object.defineProperty(navigator, 'permissions', {
            value: {
                ...originalPermissions,
                query: (parameters) => {
                    if (parameters.name === 'notifications') {
                        return Promise.resolve({ state: 'denied' });
                    }
                    return originalPermissions.query(parameters);
                }
            }
        });

        // Hide automation
        Object.defineProperty(document, 'hidden', { value: false });
        Object.defineProperty(document, 'visibilityState', { value: 'visible' });
    """)
    
    return browser, context

def fetch_with_stealth(store_name, store_slug, ean_list):
    """Fetch prices with maximum stealth"""
    print(f"\n🏪 {store_name} - Advanced Stealth Mode")
    print(f"  {'─' * 50}")
    
    results = []
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    with sync_playwright() as p:
        try:
            # Try with proxy first
            browser, context = create_stealth_browser(p, use_proxy=True)
            page = context.new_page()
            
            # Set longer timeouts
            page.set_default_timeout(60000)
            page.set_default_navigation_timeout(60000)
            
            # Navigate to store with human-like behavior
            store_url = f"https://www.k-ruoka.fi/kauppa/{store_slug}"
            print(f"  📍 Navigating to: {store_url}")
            
            # Add random mouse movements before navigation
            page.mouse.move(random.randint(100, 500), random.randint(100, 500))
            
            # Navigate with referrer
            page.goto(store_url, wait_until="networkidle", timeout=60000)
            
            # Check for blocking
            page_content = page.content()
            if "403" in page_content or "Forbidden" in page_content or "Cloudflare" in page_content:
                print(f"  ⚠️ Blocked! Trying without proxy...")
                browser.close()
                
                # Try without proxy
                browser, context = create_stealth_browser(p, use_proxy=False)
                page = context.new_page()
                page.set_default_timeout(60000)
                page.goto(store_url, wait_until="networkidle", timeout=60000)
            
            # Wait and simulate human behavior
            time.sleep(random.uniform(3, 5))
            
            # Scroll randomly
            page.evaluate(f"window.scrollBy(0, {random.randint(100, 500)})")
            time.sleep(random.uniform(1, 2))
            
            # Check page title
            title = page.title()
            print(f"  📄 Page title: {title}")
            
            if "404" in title or "Not Found" in title:
                print(f"  ❌ Store not found")
                browser.close()
                return results
            
            # Try to find search functionality
            print(f"  🔍 Looking for search functionality...")
            
            # Method 1: Try search box
            search_found = False
            search_selectors = [
                'input[type="search"]',
                'input[placeholder*="etsi"]',
                'input[placeholder*="hae"]',
                '[data-testid*="search"]',
                '#search',
                '.search-input',
                'input[name="q"]'
            ]
            
            for selector in search_selectors:
                try:
                    search_box = page.locator(selector).first
                    if search_box.count() > 0:
                        print(f"  ✅ Found search box: {selector}")
                        search_found = True
                        
                        # Process each EAN
                        for i, ean in enumerate(ean_list, 1):
                            print(f"    [{i}/{len(ean_list)}] {ean}...", end=" ")
                            
                            try:
                                # Clear and type slowly like a human
                                search_box.fill("")
                                for char in ean:
                                    search_box.type(char, delay=random.uniform(50, 150))
                                    time.sleep(random.uniform(0.05, 0.1))
                                
                                # Press Enter
                                search_box.press("Enter")
                                
                                # Wait for results
                                time.sleep(random.uniform(2, 4))
                                
                                # Look for products
                                product = extract_product_info(page, ean)
                                
                                if product:
                                    results.append({
                                        "Pvm": current_date,
                                        "Kaupunki/Kauppa": store_name,
                                        "Hakusana": ean,
                                        "Tuote": product['name'][:100],
                                        "Hinta (EUR)": product['price']
                                    })
                                    print(f"✅ {product['price']}€")
                                else:
                                    print("❌")
                                
                                # Clear search
                                search_box.fill("")
                                time.sleep(random.uniform(1, 2))
                                
                            except Exception as e:
                                print(f"⚠️ Error: {str(e)[:30]}")
                                continue
                        
                        break
                        
                except:
                    continue
            
            if not search_found:
                print(f"  ⚠️ No search box found, trying direct URLs...")
                
                # Method 2: Direct search URLs
                for i, ean in enumerate(ean_list, 1):
                    print(f"    [{i}/{len(ean_list)}] {ean}...", end=" ")
                    
                    try:
                        search_url = f"https://www.k-ruoka.fi/kauppa/{store_slug}/haku?q={ean}"
                        
                        # Navigate with human-like delay
                        time.sleep(random.uniform(1, 2))
                        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                        time.sleep(random.uniform(2, 3))
                        
                        # Extract product info
                        product = extract_product_info(page, ean)
                        
                        if product:
                            results.append({
                                "Pvm": current_date,
                                "Kaupunki/Kauppa": store_name,
                                "Hakusana": ean,
                                "Tuote": product['name'][:100],
                                "Hinta (EUR)": product['price']
                            })
                            print(f"✅ {product['price']}€")
                        else:
                            print("❌")
                            
                    except Exception as e:
                        print(f"⚠️ {str(e)[:30]}")
                        continue
            
            browser.close()
            
            print(f"  {'─' * 50}")
            print(f"  📊 Found {len(results)}/{len(ean_list)} products")
            
            return results
            
        except Exception as e:
            print(f"  ❌ Fatal error: {str(e)}")
            return results

def extract_product_info(page, ean):
    """Extract product information from page"""
    try:
        # Try multiple selectors for products
        product_selectors = [
            '[data-testid="product-card"]',
            '.product-card',
            '.product-item',
            '.search-result-item',
            'article',
            '.product',
            '[class*="productCard"]',
            '.card'
        ]
        
        for selector in product_selectors:
            try:
                products = page.locator(selector)
                count = products.count()
                
                if count > 0:
                    # Check first 3 products
                    for i in range(min(count, 3)):
                        try:
                            product = products.nth(i)
                            
                            # Get all text
                            text = product.inner_text(timeout=3000)
                            lines = [line.strip() for line in text.split('\n') if line.strip()]
                            
                            if not lines:
                                continue
                            
                            # Find product name (usually the longest text)
                            name = max(lines, key=len)
                            clean_name = clean_text(name)
                            
                            # Skip excluded
                            if any(bad in clean_name.lower() for bad in EXCLUDE_KEYWORDS):
                                continue
                            
                            # Find price
                            price = None
                            for line in lines:
                                # Look for price patterns
                                price_match = re.search(r'(\d+[\.,]\d+)\s*€?', line)
                                if price_match:
                                    try:
                                        price_str = price_match.group(1).replace(',', '.')
                                        price = float(price_str)
                                        
                                        # Additional validation: price should be reasonable
                                        if 0.1 <= price <= 100:  # Assuming reasonable price range
                                            return {
                                                'name': clean_name,
                                                'price': price
                                            }
                                    except:
                                        continue
                            
                        except:
                            continue
                            
            except:
                continue
        
        return None
        
    except Exception as e:
        return None

def main():
    print("🤖 Potwell Matrix-Robotti (Ultimate Stealth Mode)")
    print(f"⏰ Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")
    
    # Test mode - only one store
    TEST_MODE = True
    TEST_STORE = "Espoo (Iso Omena)"
    TEST_SLUG = "k-citymarket-espoo-iso-omena"
    TEST_PRODUCTS = SEARCH_QUERIES[:5]  # Test with 5 products
    
    if TEST_MODE:
        print("🔧 TEST MODE - Testing one store only")
        my_stores = {TEST_STORE: TEST_SLUG}
        products_to_check = TEST_PRODUCTS
    else:
        bot_id = int(os.environ.get("BOT_ID", 1))
        total_bots = int(os.environ.get("TOTAL_BOTS", 1))
        
        all_stores = list(STORES_TO_CHECK.items())
        chunk_size = math.ceil(len(all_stores) / total_bots)
        start_index = (bot_id - 1) * chunk_size
        end_index = start_index + chunk_size
        my_stores = dict(all_stores[start_index:end_index])
        products_to_check = SEARCH_QUERIES
    
    print(f"📋 Stores to process: {len(my_stores)}")
    print(f"📦 Products per store: {len(products_to_check)}")
    print(f"{'=' * 60}")
    
    all_data = []
    
    for store_name, store_slug in my_stores.items():
        print(f"\n{'=' * 60}")
        print(f"🛒 PROCESSING: {store_name}")
        print(f"{'=' * 60}")
        
        start_time = time.time()
        
        try:
            store_data = fetch_with_stealth(store_name, store_slug, products_to_check)
            
            if store_data:
                all_data.extend(store_data)
                print(f"✅ Found {len(store_data)} products")
                
                # Save immediately
                save_to_sheet(store_data)
            else:
                print(f"⚠️ No products found")
            
            elapsed = time.time() - start_time
            print(f"⏱️ Time taken: {elapsed:.1f}s")
            
        except Exception as e:
            print(f"❌ Store failed: {str(e)}")
        
        # Long delay between stores
        if len(my_stores) > 1:
            delay = random.uniform(10, 20)
            print(f"⏳ Waiting {delay:.1f}s before next store...")
            time.sleep(delay)
    
    # Final summary
    print(f"\n{'=' * 60}")
    print("📊 FINAL SUMMARY")
    print(f"{'=' * 60}")
    print(f"✅ Total stores processed: {len(my_stores)}")
    print(f"✅ Total products found: {len(all_data)}")
    
    if all_data:
        print(f"\n💾 Saving final data...")
        save_to_sheet(all_data)
    
    print(f"\n{'=' * 60}")
    print(f"🏁 Script completed!")
    print(f"⏰ End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()
