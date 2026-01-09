import time
import re
import os
import json
import math
import random
import requests
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

# FALLBACK: Try to use K-Ruoka API directly (might be more reliable)
def try_api_search(store_slug, search_term):
    """Try to fetch product data via K-Ruoka API"""
    try:
        api_url = f"https://www.k-ruoka.fi/kr-api/elastic/v3/stores/{store_slug}/search"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'fi-FI,fi;q=0.9,en;q=0.8',
            'Origin': 'https://www.k-ruoka.fi',
            'Referer': f'https://www.k-ruoka.fi/kauppa/{store_slug}',
        }
        
        params = {
            'query': search_term,
            'size': 10,
            'from': 0
        }
        
        response = requests.get(api_url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'hits' in data and 'hits' in data['hits']:
                products = data['hits']['hits']
                if products:
                    # Return first product
                    product = products[0]['_source']
                    return {
                        'name': product.get('name', ''),
                        'price': product.get('price', {}).get('current', 0),
                        'unitPrice': product.get('price', {}).get('unitPrice', 0)
                    }
    except Exception as e:
        print(f"[API Error: {str(e)[:50]}]")
    return None

def fetch_prices_from_store(page, store_name, store_slug, product_list):
    print(f"\n🏪 {store_name} ({store_slug})...")
    store_results = []
    current_date = datetime.now().strftime("%Y-%m-%d")
    successes = 0
    
    try:
        # Try to load store page with multiple strategies
        strategies = [
            lambda: page.goto(f"https://www.k-ruoka.fi/kauppa/{store_slug}", 
                            timeout=45000, wait_until="commit"),
            lambda: page.goto(f"https://www.k-ruoka.fi/kauppa/{store_slug}", 
                            timeout=45000, wait_until="domcontentloaded"),
            lambda: page.goto(f"https://www.k-ruoka.fi/kauppa/{store_slug}?no-cache=1", 
                            timeout=45000, wait_until="domcontentloaded"),
        ]
        
        page_loaded = False
        for i, strategy in enumerate(strategies):
            try:
                strategy()
                time.sleep(3)
                
                # Check if page loaded
                if page.title() and "404" not in page.title():
                    page_loaded = True
                    print(f"  ✅ Sivu ladattu (strategia {i+1})")
                    break
            except:
                continue
        
        if not page_loaded:
            print(f"  ❌ Sivun lataus epäonnistui kaikilla strategioilla")
            return []
        
        # Handle cookies if present
        try:
            cookie_buttons = [
                "button:has-text('Hyväksy')",
                "button:has-text('Accept')",
                "#onetrust-accept-btn-handler",
                ".cookie-consent__accept"
            ]
            
            for button_selector in cookie_buttons:
                try:
                    button = page.locator(button_selector).first
                    if button.is_visible(timeout=2000):
                        button.click()
                        time.sleep(1)
                        print("  ✅ Evästeet hyväksytty")
                        break
                except:
                    continue
        except:
            pass
        
        # Process each search term
        for search_index, search_term in enumerate(product_list):
            print(f"  [{search_index+1}/{len(product_list)}] Etsitään {search_term}...", end=" ", flush=True)
            
            try:
                # First try direct search URL
                search_url = f"https://www.k-ruoka.fi/kauppa/{store_slug}/haku?q={search_term}"
                
                try:
                    page.goto(search_url, timeout=20000, wait_until="domcontentloaded")
                    time.sleep(2)
                except PlaywrightTimeoutError:
                    # If timeout, try reloading
                    page.reload(timeout=20000, wait_until="domcontentloaded")
                    time.sleep(2)
                
                # Wait for products to appear
                product_found = False
                start_time = time.time()
                
                while time.time() - start_time < 10 and not product_found:  # Wait up to 10 seconds
                    # Try multiple selectors for products
                    selectors = [
                        "[data-testid='product-card']",
                        ".product-card",
                        "article",
                        ".product-item",
                        ".search-result-item",
                        "div[class*='product']"
                    ]
                    
                    for selector in selectors:
                        try:
                            products = page.locator(selector)
                            count = products.count()
                            
                            if count > 0:
                                # Check first product
                                for i in range(min(count, 3)):
                                    try:
                                        product = products.nth(i)
                                        product_text = product.inner_text(timeout=2000)
                                        
                                        if not product_text or len(product_text.strip()) < 10:
                                            continue
                                        
                                        lines = [l.strip() for l in product_text.split('\n') if l.strip()]
                                        if not lines:
                                            continue
                                        
                                        # Get product name
                                        product_name = lines[0]
                                        for line in lines:
                                            if len(line) > len(product_name) and len(line) < 100:
                                                product_name = line
                                                break
                                        
                                        clean_name = clean_text(product_name)
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
                                                    break
                                                except:
                                                    continue
                                        
                                        if price is not None:
                                            store_results.append({
                                                "Pvm": current_date,
                                                "Kaupunki/Kauppa": store_name,
                                                "Hakusana": search_term,
                                                "Tuote": clean_name[:150],
                                                "Hinta (EUR)": price
                                            })
                                            successes += 1
                                            product_found = True
                                            print(f"✅ {price}€")
                                            break
                                            
                                    except Exception as e:
                                        continue
                                
                                if product_found:
                                    break
                                    
                        except:
                            continue
                    
                    if not product_found:
                        time.sleep(0.5)  # Wait a bit and try again
                
                if not product_found:
                    # Try API as fallback
                    print("(API fallback)", end=" ", flush=True)
                    api_result = try_api_search(store_slug, search_term)
                    if api_result and api_result['name']:
                        price_to_use = api_result.get('unitPrice') or api_result.get('price')
                        if price_to_use:
                            store_results.append({
                                "Pvm": current_date,
                                "Kaupunki/Kauppa": store_name,
                                "Hakusana": search_term,
                                "Tuote": api_result['name'][:150],
                                "Hinta (EUR)": price_to_use
                            })
                            successes += 1
                            print(f"✅ API: {price_to_use}€")
                        else:
                            print("❌ (ei hintaa)")
                    else:
                        print("❌")
                
                # Random delay between searches
                if search_index < len(product_list) - 1:
                    delay = random.uniform(1.5, 3.5)
                    time.sleep(delay)
                    
            except Exception as e:
                print(f"⚠️ Virhe: {str(e)[:50]}")
                continue
        
        print(f"  📊 {store_name}: {successes}/{len(product_list)} tuotetta löytyi")
        return store_results
        
    except Exception as e:
        print(f"  ❌ Vakava virhe {store_name}: {str(e)}")
        return []

def main():
    print("🤖 Potwell Matrix-Robotti (GitHub Actions Optimized)")
    print(f"⏰ Aloitusaika: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    bot_id = int(os.environ.get("BOT_ID", 1))
    total_bots = int(os.environ.get("TOTAL_BOTS", 1))
    
    all_stores = list(STORES_TO_CHECK.items())
    chunk_size = math.ceil(len(all_stores) / total_bots)
    start_index = (bot_id - 1) * chunk_size
    end_index = start_index + chunk_size
    my_stores = dict(all_stores[start_index:end_index])
    
    print(f"👷 Robotti {bot_id}/{total_bots}")
    print(f"📋 Minulle kuuluu {len(my_stores)} kauppaa:")
    for name in my_stores.keys():
        print(f"   • {name}")
    
    total_results = 0
    failed_stores = []
    
    with sync_playwright() as p:
        # Launch browser for GitHub Actions/Cloud environment
        browser = p.chromium.launch(
            headless=True,  # Must be True for GitHub Actions
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-zygote",
                "--single-process" if os.getenv('IS_DOCKER') else "",
            ]
        )
        
        # Create context optimized for cloud
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale="fi-FI",
            timezone_id="Europe/Helsinki",
            permissions=['geolocation'],
            geolocation={'latitude': 60.1699, 'longitude': 24.9384},
            color_scheme='light'
        )
        
        # Add anti-detection
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['fi-FI', 'fi', 'en-US', 'en'] });
        """)
        
        page = context.new_page()
        
        # Set reasonable timeouts
        page.set_default_timeout(30000)
        page.set_default_navigation_timeout(45000)
        
        # Process each store
        for i, (name, slug) in enumerate(my_stores.items(), 1):
            print(f"\n{'='*60}")
            print(f"[{i}/{len(my_stores)}] ALKU: {name}")
            print(f"{'='*60}")
            
            start_time = time.time()
            
            try:
                data = fetch_prices_from_store(page, name, slug, SEARCH_QUERIES)
                
                if data:
                    total_results += len(data)
                    save_to_sheet(data)
                    print(f"  ✅ {len(data)} hintaa tallennettu")
                else:
                    failed_stores.append(name)
                    print(f"  ⚠️ Ei dataa saatu")
                
                elapsed = time.time() - start_time
                print(f"  ⏱️  Kesti: {elapsed:.1f}s")
                
            except Exception as e:
                failed_stores.append(name)
                print(f"  ❌ Poikkeus: {str(e)[:100]}")
            
            # Delay between stores (longer for cloud)
            if i < len(my_stores):
                delay = random.uniform(5, 10)
                print(f"  ⏳ Odotetaan {delay:.1f}s...")
                time.sleep(delay)
        
        # Cleanup
        print(f"\n{'='*60}")
        print("📊 YHTEENVETO:")
        print(f"{'='*60}")
        print(f"✅ Onnistuneet kaupat: {len(my_stores) - len(failed_stores)}/{len(my_stores)}")
        print(f"✅ Yhteensä hintatietoja: {total_results}")
        
        if failed_stores:
            print(f"⚠️  Epäonnistuneet kaupat: {', '.join(failed_stores)}")
        
        print(f"\n🧹 Suljetaan selain...")
        browser.close()
    
    print(f"\n{'='*60}")
    print(f"🏁 Robotti {bot_id} valmis!")
    print(f"⏰ Päättymisaika: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
