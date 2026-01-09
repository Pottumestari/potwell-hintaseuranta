import time
import re
import os
import json
import math
import random
from datetime import datetime
from playwright.sync_api import sync_playwright
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

def laske_kilohinta_nimesta(tuote_nimi, paketti_hinta):
    if not paketti_hinta or not tuote_nimi: return None
    try:
        match = re.search(r'(\d+(?:,\d+)?)\s*(kg|g|l|dl)', tuote_nimi.lower())
        if match:
            maara = float(match.group(1).replace(',', '.'))
            yksikko = match.group(2)
            if yksikko == 'g': maara = maara / 1000
            elif yksikko == 'dl': maara = maara / 10
            if maara > 0:
                return round(paketti_hinta / maara, 2)
    except: pass
    return None

def save_to_sheet(data_list):
    print(f"💾 save_to_sheet kutsuttu. Rivejä listassa: {len(data_list)}")
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
            print(f"   -> {item['Tuote']} ({price_float} €)")

    if new_rows:
        sheet.append_rows(new_rows)
        print(f"✅ Tallennettu {len(new_rows)} uutta riviä.")

def fetch_prices_from_store(page, store_name, store_slug, product_list):
    print(f"\n🏪 {store_name}...", end=" ", flush=True)
    store_url = f"https://www.k-ruoka.fi/kauppa/{store_slug}"
    store_results = []
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    try:
        # First, let's test if we can even access the store
        response = page.goto(store_url, timeout=60000, wait_until="networkidle")
        
        # Debug: Check response status
        print(f"[Status: {response.status if response else 'No response'}]", end=" ")
        
        # Take screenshot for debugging (optional)
        # page.screenshot(path=f"debug_{store_slug}.png")
        
        # Wait for page to be more interactive
        time.sleep(3)
        
        # Check for Cloudflare or blocking
        page_content = page.content()[:2000].lower()
        if "cloudflare" in page_content or "challenge" in page_content or "just a moment" in page_content:
            print(f"\n⛔ Cloudflare detected on {store_name}")
            return []
        
        # Try to accept cookies if present
        try:
            cookie_selectors = [
                "button:has-text('Hyväksy')",
                "button:has-text('Accept')", 
                "button:has-text('OK')",
                "[id*='cookie'] button",
                "[class*='cookie'] button"
            ]
            
            for selector in cookie_selectors:
                try:
                    cookie_btn = page.locator(selector).first
                    if cookie_btn.is_visible(timeout=2000):
                        cookie_btn.click()
                        time.sleep(1)
                        break
                except:
                    continue
        except:
            pass
        
        # Search for products
        for search_term in product_list:
            try:
                # Try multiple search URL patterns
                search_urls = [
                    f"https://www.k-ruoka.fi/kauppa/{store_slug}/haku?search={search_term}",
                    f"https://www.k-ruoka.fi/kauppa/{store_slug}/search?q={search_term}",
                    f"https://www.k-ruoka.fi/kauppa/{store_slug}/tuotehaku?term={search_term}"
                ]
                
                found_product = False
                for search_url in search_urls:
                    try:
                        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                        time.sleep(2)
                        
                        # Check for blocking
                        current_content = page.content()[:1000].lower()
                        if "verify" in current_content or "challenge" in current_content:
                            print("!", end="", flush=True)
                            break
                        
                        # Try multiple selectors for products
                        selectors_to_try = [
                            "[data-testid='product-card']",
                            ".product-card",
                            "article[class*='product']",
                            "div[class*='product']",
                            ".search-result-item",
                            "li[class*='product']",
                            ".product-item",
                            "[class*='ProductCard']"
                        ]
                        
                        for selector in selectors_to_try:
                            try:
                                cards = page.locator(selector)
                                count = cards.count()
                                if count > 0:
                                    # Check first few items
                                    for i in range(min(count, 3)):
                                        try:
                                            card = cards.nth(i)
                                            
                                            # Try to get product name
                                            name = ""
                                            name_selectors = [
                                                "h2", "h3", "h4",
                                                "[class*='name']",
                                                "[class*='title']",
                                                "[data-testid*='name']",
                                                "[data-testid*='title']"
                                            ]
                                            
                                            for name_selector in name_selectors:
                                                try:
                                                    name_elem = card.locator(name_selector).first
                                                    if name_elem.count() > 0:
                                                        name = name_elem.inner_text()
                                                        break
                                                except:
                                                    continue
                                            
                                            if not name:
                                                name = card.inner_text().split('\n')[0]
                                            
                                            name_clean = clean_text(name)
                                            if not name_clean or len(name_clean) < 2:
                                                continue
                                            
                                            # Skip excluded keywords
                                            if any(bad in name_clean.lower() for bad in EXCLUDE_KEYWORDS):
                                                continue
                                            
                                            # Try to get price
                                            price = None
                                            price_selectors = [
                                                "[class*='price']",
                                                "[data-testid*='price']",
                                                "[class*='Price']",
                                                ".price",
                                                ".Price"
                                            ]
                                            
                                            for price_selector in price_selectors:
                                                try:
                                                    price_elem = card.locator(price_selector).first
                                                    if price_elem.count() > 0:
                                                        price_text = price_elem.inner_text()
                                                        price_match = re.search(r"(\d+[\.,]\d+)", price_text)
                                                        if price_match:
                                                            price = float(price_match.group(1).replace(',', '.'))
                                                            break
                                                except:
                                                    continue
                                            
                                            # If no structured price found, try to extract from text
                                            if price is None:
                                                card_text = card.inner_text()
                                                price_match = re.search(r"(\d+[\.,]\d+)\s*€?", card_text)
                                                if price_match:
                                                    price = float(price_match.group(1).replace(',', '.'))
                                            
                                            if price is not None:
                                                store_results.append({
                                                    "Pvm": current_date,
                                                    "Kaupunki/Kauppa": store_name,
                                                    "Hakusana": search_term,
                                                    "Tuote": name_clean[:200],
                                                    "Hinta (EUR)": price
                                                })
                                                
                                                found_product = True
                                                print(".", end="", flush=True)
                                                break
                                                
                                        except Exception as e:
                                            continue
                                    
                                    if found_product:
                                        break
                                        
                            except:
                                continue
                        
                        if found_product:
                            break
                            
                    except Exception as e:
                        print("!", end="", flush=True)
                        continue
                
                if not found_product:
                    print("x", end="", flush=True)
                    
            except Exception as e:
                print(f"! ({search_term[:8]})", end="", flush=True)
                continue
                
        print("") 
        return store_results
        
    except Exception as e:
        print(f"\n⚠️ Virhe {store_name}: {str(e)[:100]}")
        return []

def main():
    print("🤖 Aloitetaan Potwell Matrix-Robotti (ENHANCED STEALTH)...")
    
    bot_id = int(os.environ.get("BOT_ID", 1))
    total_bots = int(os.environ.get("TOTAL_BOTS", 1))
    
    all_stores = list(STORES_TO_CHECK.items())
    chunk_size = math.ceil(len(all_stores) / total_bots)
    start_index = (bot_id - 1) * chunk_size
    end_index = start_index + chunk_size
    my_stores = dict(all_stores[start_index:end_index])
    
    print(f"👷 Olen robotti {bot_id}/{total_bots}. Minulle kuuluu {len(my_stores)} kauppaa.")
    
    with sync_playwright() as p:
        # Use desktop mode instead of mobile for better compatibility
        browser = p.chromium.launch(
            headless=True,  # Set to False for debugging
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-site-isolation-trials"
            ]
        )
        
        # Create desktop context with realistic settings
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale="fi-FI",
            timezone_id="Europe/Helsinki",
            # Add random mouse movements and other human-like behaviors
            permissions=['geolocation'],
            geolocation={'latitude': 60.1699, 'longitude': 24.9384},  # Helsinki coordinates
            color_scheme='light'
        )
        
        # Add extra stealth measures
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            window.chrome = {
                runtime: {}
            };
            
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            Object.defineProperty(navigator, 'languages', {
                get: () => ['fi-FI', 'fi', 'en-US', 'en']
            });
        """)
        
        page = context.new_page()
        
        # Set random viewport scroll to mimic human behavior
        page.evaluate("""
            window.scrollTo({
                top: Math.random() * 500,
                behavior: 'smooth'
            });
        """)
        
        for i, (name, slug) in enumerate(my_stores.items(), 1):
            print(f"\n[{i}/{len(my_stores)}] Robotti {bot_id} työssä...")
            data = fetch_prices_from_store(page, name, slug, SEARCH_QUERIES)
            save_to_sheet(data)
            
            # Add random delay between stores to avoid detection
            if i < len(my_stores):
                delay = random.uniform(2, 5)
                time.sleep(delay)
        
        browser.close()
    
    print(f"\n✅ Robotti {bot_id} valmis!")

if __name__ == "__main__":
    main()
