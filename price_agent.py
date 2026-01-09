import time
import re
import os
import json
from datetime import datetime
from playwright.sync_api import sync_playwright
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- ASETUKSET ---
SHEET_NAME = 'Potwell Data'       # Google Sheetin nimi

# 1. KAUPPALISTA
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

# 2. EAN-KOODIT
SEARCH_QUERIES = [
    "6410405093080", "6410405041937", "6410402024469", "6410402008933", 
    "6410402024445", "6410405330727", "6415350002804", "2000623600005", 
    "6410405152305", "6410405039910", "6410405195746", "6410405149510", 
    "6410402008919", "6410402023479", "6410402023455", "6410402028634", 
    "6410402008896", "2000610500004", "6410405318183", "6410405174277", 
    "6410402017195", "6410405082725", "6410405174253", "6410405196651", 
    "6410402008773", "6410402022953", "6410405097248"
]

# KIELTOLISTA
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
    """Hakee Google-tunnukset joko tiedostosta tai ympäristömuuttujasta (GitHub Actions)"""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # 1. Kokeillaan lukea GitHubin salaisuuksista (Ympäristömuuttuja)
    json_creds = os.environ.get("GCP_SERVICE_ACCOUNT_JSON")
    if json_creds:
        print("🔑 Käytetään GitHub Secrets -tunnuksia.")
        creds_dict = json.loads(json_creds)
        return ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    # 2. Jos ei löydy, kokeillaan paikallista tiedostoa (Kotikone)
    if os.path.exists("service_account.json"):
        return ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
    
    raise Exception("Virhe: Google-tunnuksia ei löytynyt (ei env-muuttujaa eikä tiedostoa).")

def laske_kilohinta_nimesta(tuote_nimi, paketti_hinta):
    """VARAJÄRJESTELMÄ: Laskee kilohinnan, jos sivulta ei löydy suoraa mainintaa."""
    if not paketti_hinta or not tuote_nimi: return None
    try:
        match = re.search(r'(\d+(?:,\d+)?)\s*(kg|g|l|dl)', tuote_nimi.lower())
        if match:
            maara = float(match.group(1).replace(',', '.'))
            yksikko = match.group(2)
            
            if yksikko == 'g': maara = maara / 1000
            elif yksikko == 'dl': maara = maara / 10
            
            if maara > 0:
                laskettu = paketti_hinta / maara
                print(f"     (Laskettiin itse: {paketti_hinta}€ / {maara}kg = {laskettu:.2f}€/kg)")
                return round(laskettu, 2)
    except: pass
    return None

def save_to_sheet(data_list):
    """Tallentaa haetut tiedot Google Sheetsiin."""
    if not data_list: return
    
    print("☁️  Yhdistetään Google Sheetsiin...")
    try:
        creds = get_google_creds()
        client = gspread.authorize(creds)
        sheet = client.open(SHEET_NAME).sheet1
    except Exception as e:
        print(f"❌ VIRHE: Ei saatu yhteyttä Sheetsiin. {e}")
        return

    # 1. Tarkistetaan onko otsikot olemassa, jos sheet on tyhjä
    if not sheet.get_all_values():
        sheet.append_row(["pvm", "kauppa", "tuote", "ean", "hinta"])

    # 2. Haetaan olemassa oleva data duplikaattien tarkistusta varten
    try:
        existing_records = sheet.get_all_records()
    except:
        existing_records = []

    # Luodaan "avain" (pvm + kauppa + ean) nopeaa tarkistusta varten
    existing_keys = set()
    for row in existing_records:
        pvm = str(row.get('pvm', ''))
        kauppa = str(row.get('kauppa', ''))
        ean = str(row.get('ean', ''))
        key = f"{pvm}_{kauppa}_{ean}"
        existing_keys.add(key)
        
    new_rows = []
    
    for item in data_list:
        key = f"{item['Pvm']}_{item['Kaupunki/Kauppa']}_{item['Hakusana']}"
        
        if key not in existing_keys:
            # Varmistetaan että hinta on float eikä string, korvataan pilkku pisteellä
            raw_price = str(item['Hinta (EUR)']).replace(',', '.')
            try:
                price_float = float(raw_price)
            except:
                price_float = 0.0

            # Rakenne: [pvm, kauppa, tuote, ean, hinta]
            row = [
                item['Pvm'],
                item['Kaupunki/Kauppa'],
                item['Tuote'],
                item['Hakusana'], # EAN
                price_float       # Hinta numerona
            ]
            new_rows.append(row)
            print(f"    Tallennettu puskuriin: {item['Tuote']} ({price_float} €)")
        else:
            pass 

    # 3. Lähetetään uudet rivit pilveen yhtenä pakettina
    if new_rows:
        print(f"📤 Lähetetään {len(new_rows)} uutta riviä pilveen...")
        sheet.append_rows(new_rows)
        print("✅ Tallennus valmis!")
    else:
        print("    (Ei uusia hintoja, kaikki löytyi jo pilvestä.)")


def fetch_prices_from_store(page, store_name, store_slug, product_list):
    print(f"\n[KAUPPA] {store_name}...")
    store_url = f"https://www.k-ruoka.fi/kauppa/{store_slug}"
    store_results = []
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    try:
        # TÄRKEÄ: headless=True pilvessä ajamista varten. Timeout asetettu 60s.
        page.goto(store_url, timeout=60000)
        
        # Cloudflare / Evästeet
        try:
            time.sleep(2)
            if page.locator("text=Verify you are human").count() > 0:
                print("    Cloudflare havaittu! Odota hetki...")
                time.sleep(5)
        except: pass

        try:
            page.wait_for_selector("button:has-text('Hyväksy')", timeout=3000)
            page.click("button:has-text('Hyväksy')")
        except: pass
        
        # Avataan haku
        try:
            if page.is_visible("a[aria-label='Haku']"): 
                page.click("a[aria-label='Haku']")
                time.sleep(1)
        except: pass

        for search_term in product_list:
            try:
                # 1. Tyhjennetään ja haetaan
                search_input = "input[type='search'], input[type='text']"
                page.click(search_input)
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                
                page.fill(search_input, search_term)
                page.keyboard.press("Enter")
                
                time.sleep(3) # Odotus
                
                # 2. Etsitään kortit
                cards = page.locator("[data-testid='product-card']").all()
                if not cards: cards = page.locator("article").all()
                
                found_for_this_ean = False 

                for card in cards:
                    try:
                        full_text = card.inner_text()
                        lines = full_text.split('\n')
                        
                        name = lines[0].strip()
                        if len(name) < 3 or "etu" in name.lower() or "%" in name or "hinta" in name.lower() or name[0].isdigit():
                            if len(lines) > 1: name = lines[1].strip()
                        
                        if "hinta" in name.lower() or name[0].isdigit():
                            continue
                        
                        name_clean = clean_text(name)
                        
                        if any(bad_word in name_clean.lower() for bad_word in EXCLUDE_KEYWORDS): 
                            print(f"    ❌ Ohitettu kielletty sana: {name_clean}")
                            continue 
                        
                        final_kg_price = None
                        
                        try:
                            unit_price_el = card.locator("[data-testid='product-unit-price']")
                            if unit_price_el.count() > 0:
                                raw_unit_text = unit_price_el.inner_text()
                                clean_unit_text = raw_unit_text.replace('/kg', '').replace('/l', '').replace(' ', '').replace(',', '.').strip()
                                final_kg_price = float(clean_unit_text)
                        except: pass
                        
                        if final_kg_price is None:
                            price_match = re.search(r"(\d+,\d+)", full_text)
                            if price_match:
                                package_price = float(price_match.group(1).replace(',', '.'))
                                final_kg_price = laske_kilohinta_nimesta(name_clean, package_price)

                        if final_kg_price is not None:
                            store_results.append({
                                "Pvm": current_date, 
                                "Kaupunki/Kauppa": store_name, 
                                "Hakusana": search_term, 
                                "Tuote": name_clean, 
                                "Hinta (EUR)": final_kg_price
                            })
                            found_for_this_ean = True
                            break 
                            
                    except Exception as e: continue
                
                if not found_for_this_ean:
                    print(f"    ⚠️  Ei löytynyt tuotetta haulla: {search_term}")

            except Exception as e: continue

        return store_results
    except Exception as e: 
        print(f"    Virhe kaupassa: {e}")
        return []

def main():
    print("🤖 Aloitetaan Potwell Hintarobotti (Cloud Edition)...")
    
    with sync_playwright() as p:
        # TÄRKEÄ: headless=True pilvessä ajamista varten
        browser = p.chromium.launch(
            headless=True, 
            slow_mo=50, 
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        for name, slug in STORES_TO_CHECK.items():
            data = fetch_prices_from_store(page, name, slug, SEARCH_QUERIES)
            # TALLENNETAAN PILVEEN
            save_to_sheet(data)
            
        browser.close()
    
    print("\n✅ Haku valmis! Kaikki tiedot päivitetty pilveen.")

if __name__ == "__main__":
    main()
