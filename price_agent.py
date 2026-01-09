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
            print(f"     -> {item['Tuote'][:50]}... ({price_float} €)")

    if new_rows:
        sheet.append_rows(new_rows)
        print(f"✅ Tallennettu {len(new_rows)} uutta riviä.")
    else:
        print("ℹ️ Ei uusia tietoja tallennettavaksi.")

def fetch_store_data_simple(store_name, store_slug, product_list):
    """Simple, reliable scraping approach"""
    print(f"\n🏪 {store_name}...")
    store_results = []
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    with sync_playwright() as p:
        # Launch browser
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
            ]
        )
        
        # Create context
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        )
        
        page = context.new_page()
        page.set_default_timeout(30000)
        
        try:
            # First, let's see what the site looks like
            store_url = f"https://www.k-ruoka.fi/kauppa/{store_slug}"
            print(f"  📍 Menossa: {store_url}")
            
            # Try to load the store page
            response = page.goto(store_url, wait_until="domcontentloaded", timeout=30000)
            print(f"  📄 Status: {response.status if response else 'N/A'}")
            
            # Wait a bit
            time.sleep(3)
            
            # Take a screenshot for debugging
            screenshot_path = f"debug_{store_slug}.png"
            page.screenshot(path=screenshot_path)
            print(f"  📸 Screenshot saved: {screenshot_path}")
            
            # Get page content for analysis
            html = page.content()
            with open(f"debug_{store_slug}.html", "w", encoding="utf-8") as f:
                f.write(html[:5000])  # Save first 5000 chars
            
            # Look for search box
            print(f"  🔍 Etsitään hakukenttää...")
            search_selectors = [
                'input[type="search"]',
                'input[placeholder*="etsi"]',
                'input[placeholder*="hae"]',
                '[data-testid*="search"]',
                '#search',
                '.search-input'
            ]
            
            search_box = None
            for selector in search_selectors:
                try:
                    element = page.locator(selector).first
                    if element.count() > 0 and element.is_visible():
                        search_box = element
                        print(f"  ✅ Löytyi hakukenttä: {selector}")
                        break
                except:
                    continue
            
            if not search_box:
                print(f"  ❌ Hakukenttää ei löytynyt")
                # Try direct search URL instead
                print(f"  🔄 Kokeillaan suoraa hakua...")
                
                for i, ean in enumerate(product_list, 1):
                    print(f"    [{i}/{len(product_list)}] {ean}...", end=" ")
                    
                    try:
                        # Try direct search URL
                        search_url = f"https://www.k-ruoka.fi/kauppa/{store_slug}/haku?q={ean}"
                        page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
                        time.sleep(2)
                        
                        # Look for products on the page
                        product_selectors = [
                            '.product',
                            '[class*="product"]',
                            '.search-result',
                            '.item',
                            'article',
                            '.card'
                        ]
                        
                        found_product = False
                        for selector in product_selectors:
                            try:
                                products = page.locator(selector)
                                count = products.count()
                                if count > 0:
                                    # Check first product
                                    for j in range(min(count, 3)):
                                        try:
                                            product = products.nth(j)
                                            product_text = product.inner_text(timeout=2000)
                                            
                                            # Simple parsing
                                            lines = [l.strip() for l in product_text.split('\n') if l.strip()]
                                            if not lines:
                                                continue
                                            
                                            # Get name (longest line is usually the product name)
                                            name = max(lines, key=len)
                                            clean_name = clean_text(name)
                                            
                                            # Skip excluded
                                            if any(bad in clean_name.lower() for bad in EXCLUDE_KEYWORDS):
                                                continue
                                            
                                            # Find price
                                            price = None
                                            for line in lines:
                                                price_match = re.search(r'(\d+[\.,]\d+)\s*€?', line)
                                                if price_match:
                                                    try:
                                                        price_str = price_match.group(1).replace(',', '.')
                                                        price = float(price_str)
                                                        break
                                                    except:
                                                        continue
                                            
                                            if price:
                                                store_results.append({
                                                    "Pvm": current_date,
                                                    "Kaupunki/Kauppa": store_name,
                                                    "Hakusana": ean,
                                                    "Tuote": clean_name[:100],
                                                    "Hinta (EUR)": price
                                                })
                                                print(f"✅ {price}€")
                                                found_product = True
                                                break
                                                
                                        except:
                                            continue
                                    
                                    if found_product:
                                        break
                                        
                            except:
                                continue
                        
                        if not found_product:
                            print("❌")
                        
                        # Delay between searches
                        if i < len(product_list):
                            time.sleep(random.uniform(1, 2))
                            
                    except Exception as e:
                        print(f"⚠️ {str(e)[:30]}")
                        continue
                
                browser.close()
                return store_results
            
            # If we found search box, use it
            print(f"  ⌨️  Käytetään hakukenttää...")
            
            for i, ean in enumerate(product_list, 1):
                print(f"    [{i}/{len(product_list)}] {ean}...", end=" ")
                
                try:
                    # Clear and fill search
                    search_box.fill("")
                    search_box.fill(ean)
                    search_box.press("Enter")
                    
                    # Wait for results
                    time.sleep(2)
                    
                    # Look for products
                    found_product = False
                    
                    # Try different product selectors
                    product_selectors = [
                        '.product-card',
                        '[data-testid="product-card"]',
                        '.search-result-item',
                        'article',
                        '.product-item'
                    ]
                    
                    for selector in product_selectors:
                        try:
                            products = page.locator(selector)
                            count = products.count()
                            if count > 0:
                                # Get first product
                                product = products.first
                                product_text = product.inner_text(timeout=2000)
                                
                                # Parse product info
                                lines = [l.strip() for l in product_text.split('\n') if l.strip()]
                                if not lines:
                                    continue
                                
                                # Find product name
                                name = lines[0]
                                if len(name) < 3 and len(lines) > 1:
                                    name = lines[1]
                                
                                clean_name = clean_text(name)
                                
                                # Skip excluded
                                if any(bad in clean_name.lower() for bad in EXCLUDE_KEYWORDS):
                                    continue
                                
                                # Find price
                                price = None
                                for line in lines:
                                    price_match = re.search(r'(\d+[\.,]\d+)\s*€?', line)
                                    if price_match:
                                        try:
                                            price_str = price_match.group(1).replace(',', '.')
                                            price = float(price_str)
                                            break
                                        except:
                                            continue
                                
                                if price:
                                    store_results.append({
                                        "Pvm": current_date,
                                        "Kaupunki/Kauppa": store_name,
                                        "Hakusana": ean,
                                        "Tuote": clean_name[:100],
                                        "Hinta (EUR)": price
                                    })
                                    print(f"✅ {price}€")
                                    found_product = True
                                    break
                                    
                        except:
                            continue
                    
                    if not found_product:
                        print("❌")
                    
                    # Clear search for next product
                    search_box.fill("")
                    time.sleep(random.uniform(1, 2))
                    
                except Exception as e:
                    print(f"⚠️ {str(e)[:30]}")
                    continue
            
            browser.close()
            return store_results
            
        except Exception as e:
            print(f"  ❌ Virhe: {str(e)}")
            browser.close()
            return store_results

def main():
    print("🤖 Potwell Matrix-Robotti (Simple Scraper)")
    print(f"⏰ Aloitusaika: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")
    
    bot_id = int(os.environ.get("BOT_ID", 1))
    total_bots = int(os.environ.get("TOTAL_BOTS", 1))
    
    # For testing, just do one store
    TEST_MODE = True  # Set to False for production
    
    if TEST_MODE:
        print("🔧 TESTI-TILA - Käydään vain yksi kauppa läpi")
        my_stores = {"Espoo (Iso Omena)": "k-citymarket-espoo-iso-omena"}
        product_list = SEARCH_QUERIES[:3]  # Test with 3 products
    else:
        all_stores = list(STORES_TO_CHECK.items())
        chunk_size = math.ceil(len(all_stores) / total_bots)
        start_index = (bot_id - 1) * chunk_size
        end_index = start_index + chunk_size
        my_stores = dict(all_stores[start_index:end_index])
        product_list = SEARCH_QUERIES
    
    print(f"👷 Robotti {bot_id}/{total_bots}")
    print(f"📋 Kaupat: {', '.join(my_stores.keys())}")
    print(f"📦 Tuotteita: {len(product_list)}")
    print(f"{'=' * 60}")
    
    all_data = []
    
    for i, (store_name, store_slug) in enumerate(my_stores.items(), 1):
        print(f"\n{'=' * 60}")
        print(f"[{i}/{len(my_stores)}] KÄSITTELLÄÄN: {store_name}")
        print(f"{'=' * 60}")
        
        start_time = time.time()
        
        try:
            store_data = fetch_store_data_simple(store_name, store_slug, product_list)
            
            if store_data:
                all_data.extend(store_data)
                print(f"  ✅ Löytyi {len(store_data)} tuotetta")
                
                # Save after each store
                save_to_sheet(store_data)
            else:
                print(f"  ⚠️ Ei tuotteita löytynyt")
            
            elapsed = time.time() - start_time
            print(f"  ⏱️  Aikaa kului: {elapsed:.1f}s")
            
        except Exception as e:
            print(f"  ❌ Poikkeus: {str(e)}")
        
        # Delay between stores
        if i < len(my_stores):
            delay = random.uniform(5, 10)
            print(f"  ⏳ Odotetaan {delay:.1f}s...")
            time.sleep(delay)
    
    # Summary
    print(f"\n{'=' * 60}")
    print("📊 YHTEENVETO:")
    print(f"{'=' * 60}")
    print(f"✅ Kaikki kaupat käsitelty: {len(my_stores)}")
    print(f"✅ Tuotteita yhteensä: {len(all_data)}")
    print(f"📈 Onnistumisprosentti: {(len(all_data) / (len(my_stores) * len(product_list)) * 100):.1f}%")
    
    if all_data:
        print(f"\n💾 Tallennetaan loput tiedot...")
        save_to_sheet(all_data)
    
    print(f"\n{'=' * 60}")
    print(f"🏁 Robotti {bot_id} valmis!")
    print(f"⏰ Päättymisaika: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()
