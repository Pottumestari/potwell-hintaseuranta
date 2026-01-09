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
        # STEALTH: Hidas lataus ja odotus
        page.goto(store_url, timeout=60000, wait_until="domcontentloaded")
        time.sleep(3) 

        # STEALTH: Satunnainen hiiren heilautus (simuloitu)
        try: page.mouse.move(100, 100)
        except: pass

        # Evästeet
        try:
            cookie_btn = page.locator("button:has-text('Hyväksy'), button:has-text('Hyväksy kaikki')")
            if cookie_btn.count() > 0:
                cookie_btn.first.click(timeout=4000)
                time.sleep(1)
        except: pass

        # Haku auki
        try:
            search_icon = page.locator("a[aria-label='Haku'], button[aria-label='Haku']")
            if search_icon.count() > 0 and search_icon.first.is_visible():
                search_icon.first.click(timeout=4000)
                time.sleep(1)
        except: pass

        search_input_sel = "input[type='search'], input[type='text'][placeholder*='Hae']"
        
        # Varmistetaan että hakukenttä löytyy
        try:
            page.wait_for_selector(search_input_sel, state="visible", timeout=10000)
        except:
            print(f"\n❌ Hakukenttä ei auennut (Estetty/Piilotettu).")
            return []

        for search_term in product_list:
            try:
                page.fill(search_input_sel, search_term)
                time.sleep(0.2) # Ihmismäinen viive
                page.keyboard.press("Enter")
                time.sleep(2) # Odotetaan tuloksia
                
                cards = page.locator("[data-testid='product-card']").all()
                if not cards: cards = page.locator("article").all()
                
                if not cards:
                    print("x", end="", flush=True)
                    continue

                found = False 
                for card in cards:
                    try:
                        text = card.inner_text()
                        lines = text.split('\n')
                        name = lines[0].strip()
                        if len(name) < 3 or name[0].isdigit() or "hinta" in name.lower():
                            if len(lines) > 1: name = lines[1].strip()
                        if "hinta" in name.lower() or name[0].isdigit(): continue
                        name_clean = clean_text(name)
                        if any(bad in name_clean.lower() for bad in EXCLUDE_KEYWORDS): continue 
                        
                        final_price = None
                        try:
                            unit_el = card.locator("[data-testid='product-unit-price']")
                            if unit_el.count() > 0:
                                val = unit_el.inner_text().replace('/kg', '').replace('/l', '').replace(' ', '').replace(',', '.').strip()
                                final_price = float(val)
                        except: pass
                        
                        if final_price is None:
                            match = re.search(r"(\d+,\d+)", text)
                            if match:
                                pkg_price = float(match.group(1).replace(',', '.'))
                                final_price = laske_kilohinta_nimesta(name_clean, pkg_price)

                        if final_price is not None:
                            store_results.append({
                                "Pvm": current_date, "Kaupunki/Kauppa": store_name, 
                                "Hakusana": search_term, "Tuote": name_clean, "Hinta (EUR)": final_price
                            })
                            found = True
                            print(".", end="", flush=True) 
                            break 
                    except: continue
                
                if not found: print("o", end="", flush=True) 
            except: 
                print("!", end="", flush=True) 
                continue
        print("") 
        return store_results
    except Exception as e: 
        print(f"\n⚠️ Virhe: {e}")
        return []

def main():
    print("🤖 Aloitetaan Potwell Matrix-Robotti (STEALTH CLOUD MODE)...")
    
    bot_id = int(os.environ.get("BOT_ID", 1))
    total_bots = int(os.environ.get("TOTAL_BOTS", 1))
    
    all_stores = list(STORES_TO_CHECK.items())
    chunk_size = math.ceil(len(all_stores) / total_bots)
    start_index = (bot_id - 1) * chunk_size
    end_index = start_index + chunk_size
    my_stores = dict(all_stores[start_index:end_index])
    
    print(f"👷 Olen robotti {bot_id}/{total_bots}. Minulle kuuluu {len(my_stores)} kauppaa.")
    
    with sync_playwright() as p:
        # --- TÄMÄ ON SE TÄRKEIN OSA PILVEÄ VARTEN ---
        # 1. Käytetään "New Headless" tilaa (se näyttää enemmän oikealta selaimelta)
        # 2. Asetetaan oikea User-Agent
        # 3. Asetetaan ikkunan koko (ettei ole 0x0)
        
        browser = p.chromium.launch(
            headless=True,  # Pilvessä pakko olla True
            args=[
                "--headless=new",  # The magic switch
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-size=1920,1080",
                "--start-maximized"
            ]
        )
        
        # Luodaan konteksti, joka näyttää suomalaiselta kotikoneelta
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="fi-FI",
            timezone_id="Europe/Helsinki",
            screen={"width": 1920, "height": 1080}
        )
        
        # Poistetaan "webdriver" ominaisuus kokonaan JavaScriptillä
        page = context.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        for i, (name, slug) in enumerate(my_stores.items(), 1):
            print(f"[{i}/{len(my_stores)}] Robotti {bot_id} työssä...")
            data = fetch_prices_from_store(page, name, slug, SEARCH_QUERIES)
            save_to_sheet(data)
            
        browser.close()
    
    print(f"\n✅ Robotti {bot_id} valmis!")

if __name__ == "__main__":
    main()
