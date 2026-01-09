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
        # STRATEGIA: Käytetään mobiilinäkymää ja URL-parametreja
        page.goto(store_url, timeout=60000, wait_until="domcontentloaded")
        time.sleep(4) # Odotetaan latausta
        
        # --- DIAGNOSTIIKKA ---
        title = page.title()
        print(f"[Otsikko: {title}]", end=" ", flush=True)
        
        # Jos otsikko viittaa estoon, lopetetaan heti
        if "Just a moment" in title or "Access denied" in title or "Challenge" in title:
            print("\n⛔ CLOUDFLARE ESTO PÄÄLLÄ. IP-osoite estetty.", end="", flush=True)
            return []

        # Tuhotaan evästeet ja häiriöt
        page.add_style_tag(content="""
            #onetrust-banner-sdk, .onetrust-pc-dark-filter, div[id^="onetrust-"],
            .k-ruoka-cookie-consent, .chat-widget, iframe { 
                display: none !important; visibility: hidden !important; 
            }
        """)

        # Käydään tuotteet läpi suorilla URL-hauilla (Mobiilissa tämä on luotettavinta)
        for search_term in product_list:
            try:
                # Rakennetaan suora URL hakuun
                direct_url = f"https://www.k-ruoka.fi/kauppa/{store_slug}/haku?q={search_term}"
                page.goto(direct_url, wait_until="domcontentloaded")
                time.sleep(1.5) # Annetaan mobiilisivun ladata

                # Etsitään kortit (Mobiilin selektorit voivat olla erilaisia)
                cards = page.locator("[data-testid='product-card']").all()
                if not cards: cards = page.locator("article").all()
                # Mobiililayoutin fallback:
                if not cards: cards = page.locator(".product-card").all()
                
                if not cards:
                    # Tarkistetaan onko meillä "Verify" tekstiä sivulla
                    body_text = page.locator("body").inner_text()[:200]
                    if "Verify" in body_text or "human" in body_text:
                        print("!", end="", flush=True) # Cloudflare iski kesken kaiken
                    else:
                        print("x", end="", flush=True)
                    continue

                found = False 
                for card in cards:
                    try:
                        text = card.inner_text()
                        lines = text.split('\n')
                        
                        # Mobiilinäkymässä teksti voi rivittyä eri tavalla
                        if not lines: continue
                        name = lines[0].strip()
                        
                        if len(name) < 3 or name[0].isdigit():
                            if len(lines) > 1: name = lines[1].strip()
                            
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
    print("🤖 Aloitetaan Potwell Matrix-Robotti (MOBILE STEALTH)...")
    
    bot_id = int(os.environ.get("BOT_ID", 1))
    total_bots = int(os.environ.get("TOTAL_BOTS", 1))
    
    all_stores = list(STORES_TO_CHECK.items())
    chunk_size = math.ceil(len(all_stores) / total_bots)
    start_index = (bot_id - 1) * chunk_size
    end_index = start_index + chunk_size
    my_stores = dict(all_stores[start_index:end_index])
    
    print(f"👷 Olen robotti {bot_id}/{total_bots}. Minulle kuuluu {len(my_stores)} kauppaa.")
    
    with sync_playwright() as p:
        # MÄÄRITETÄÄN ANDROID-PUHELIN
        pixel_5 = p.devices['Pixel 5']
        
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--headless=new", # Uusi headless-tila
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )
        
        # Käytetään valmista mobiiliprofiilia (User-Agent, näyttökoko, kosketusnäyttö)
        context = browser.new_context(
            **pixel_5,
            locale="fi-FI",
            timezone_id="Europe/Helsinki"
        )
        
        page = context.new_page()
        
        for i, (name, slug) in enumerate(my_stores.items(), 1):
            print(f"[{i}/{len(my_stores)}] Robotti {bot_id} työssä...")
            data = fetch_prices_from_store(page, name, slug, SEARCH_QUERIES)
            save_to_sheet(data)
            
        browser.close()
    
    print(f"\n✅ Robotti {bot_id} valmis!")

if __name__ == "__main__":
    main()
