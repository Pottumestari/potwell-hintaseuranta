import time
import re
import os
import json
import math
import random
import requests
from datetime import datetime
from typing import Optional, Dict, List
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from bs4 import BeautifulSoup

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

class KRuokaScraper:
    def __init__(self):
        self.session = requests.Session()
        self.setup_headers()
        self.base_url = "https://www.k-ruoka.fi"
        
    def setup_headers(self):
        """Set up realistic browser headers"""
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'fi-FI,fi;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
        })
        
    def get_with_retry(self, url, max_retries=3, delay=2):
        """Get URL with retry logic"""
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=30, allow_redirects=True)
                
                # Check if we got blocked
                if response.status_code == 403 or response.status_code == 429:
                    print(f"  ⚠️ Blocked (Status {response.status_code}), retry {attempt + 1}/{max_retries}")
                    time.sleep(delay * (attempt + 1))
                    continue
                    
                return response
                
            except requests.exceptions.Timeout:
                print(f"  ⚠️ Timeout, retry {attempt + 1}/{max_retries}")
                time.sleep(delay * (attempt + 1))
            except Exception as e:
                print(f"  ⚠️ Error: {str(e)[:50]}, retry {attempt + 1}/{max_retries}")
                time.sleep(delay * (attempt + 1))
        
        return None
    
    def find_store_id(self, store_slug: str) -> Optional[str]:
        """Try to find store ID from various sources"""
        print(f"  🔍 Looking for store ID...")
        
        # Try different approaches
        approaches = [
            # Approach 1: Try to get store page and extract ID
            lambda: self._extract_id_from_store_page(store_slug),
            
            # Approach 2: Try to find in sitemap or robots.txt
            lambda: self._find_id_from_robots(store_slug),
            
            # Approach 3: Try known patterns
            lambda: self._try_known_patterns(store_slug),
        ]
        
        for approach in approaches:
            try:
                store_id = approach()
                if store_id:
                    print(f"  ✅ Found store ID: {store_id}")
                    return store_id
            except:
                continue
        
        print(f"  ❌ Could not find store ID")
        return None
    
    def _extract_id_from_store_page(self, store_slug: str) -> Optional[str]:
        """Extract store ID from store page HTML"""
        store_url = f"{self.base_url}/kauppa/{store_slug}"
        response = self.get_with_retry(store_url)
        
        if response and response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for store ID in various places
            # 1. In meta tags
            meta_tags = soup.find_all('meta')
            for tag in meta_tags:
                content = tag.get('content', '')
                if 'store' in content.lower() and any(char.isdigit() for char in content):
                    # Extract numbers
                    numbers = re.findall(r'\d+', content)
                    if numbers:
                        return numbers[0]
            
            # 2. In script tags with JSON data
            script_tags = soup.find_all('script')
            for script in script_tags:
                if script.string and 'store' in script.string.lower() and 'id' in script.string.lower():
                    # Try to parse as JSON or extract ID
                    id_match = re.search(r'"storeId"\s*:\s*["\']?(\d+)["\']?', script.string)
                    if id_match:
                        return id_match.group(1)
                    
                    id_match = re.search(r'"id"\s*:\s*["\']?(\d+)["\']?', script.string)
                    if id_match and 'store' in script.string.lower():
                        return id_match.group(1)
            
            # 3. In data attributes
            body = soup.find('body')
            if body:
                data_store = body.get('data-store')
                if data_store:
                    numbers = re.findall(r'\d+', data_store)
                    if numbers:
                        return numbers[0]
        
        return None
    
    def _find_id_from_robots(self, store_slug: str) -> Optional[str]:
        """Try to find store ID from robots.txt or sitemap"""
        # This is a placeholder - might need to be adjusted
        return None
    
    def _try_known_patterns(self, store_slug: str) -> Optional[str]:
        """Try known store ID patterns"""
        # Some store slugs might map to IDs
        store_patterns = {
            "k-citymarket-espoo-iso-omena": "001",
            "k-citymarket-jyvaskyla-seppala": "002",
            # Add more if known
        }
        
        return store_patterns.get(store_slug)
    
    def search_product(self, store_slug: str, ean: str, store_name: str) -> Optional[Dict]:
        """Search for a product using EAN code"""
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        print(f"    Searching EAN {ean}...", end=" ")
        
        # Try multiple search methods
        search_methods = [
            self._search_via_direct_url,
            self._search_via_api,
            self._search_via_html_parsing,
        ]
        
        for method in search_methods:
            try:
                result = method(store_slug, ean, store_name, current_date)
                if result:
                    price = result.get('Hinta (EUR)', 0)
                    print(f"✅ {price}€")
                    return result
            except Exception as e:
                continue
        
        print("❌")
        return None
    
    def _search_via_direct_url(self, store_slug: str, ean: str, store_name: str, current_date: str) -> Optional[Dict]:
        """Search via direct search URL"""
        search_url = f"{self.base_url}/kauppa/{store_slug}/haku"
        params = {'q': ean}
        
        response = self.get_with_retry(search_url, params=params)
        if not response or response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for product cards
        product_selectors = [
            '.product-card',
            '[data-testid="product-card"]',
            '.search-result-item',
            '.product-item',
            'article',
        ]
        
        for selector in product_selectors:
            products = soup.select(selector)
            if products:
                # Take first product
                product = products[0]
                
                # Extract name
                name_elements = product.select('h2, h3, h4, [class*="name"], [class*="title"]')
                name = name_elements[0].get_text(strip=True) if name_elements else product.get_text(strip=True)[:100]
                
                # Skip excluded
                if any(bad in name.lower() for bad in EXCLUDE_KEYWORDS):
                    return None
                
                # Extract price
                price_elements = product.select('[class*="price"], [data-testid*="price"]')
                price_text = price_elements[0].get_text(strip=True) if price_elements else ""
                
                # Find price in text
                price_match = re.search(r'(\d+[\.,]\d+)\s*€?', price_text)
                if not price_match:
                    # Try in entire product text
                    all_text = product.get_text()
                    price_match = re.search(r'(\d+[\.,]\d+)\s*€?', all_text)
                
                if price_match:
                    price = float(price_match.group(1).replace(',', '.'))
                    
                    return {
                        "Pvm": current_date,
                        "Kaupunki/Kauppa": store_name,
                        "Hakusana": ean,
                        "Tuote": clean_text(name)[:100],
                        "Hinta (EUR)": price
                    }
        
        return None
    
    def _search_via_api(self, store_slug: str, ean: str, store_name: str, current_date: str) -> Optional[Dict]:
        """Try to find product via API calls"""
        # First get store ID
        store_id = self.find_store_id(store_slug)
        if not store_id:
            return None
        
        # Try different API endpoints
        api_endpoints = [
            f"{self.base_url}/api/v1/stores/{store_id}/products?search={ean}",
            f"{self.base_url}/api/products?ean={ean}&storeId={store_id}",
            f"{self.base_url}/kr-api/search?q={ean}&store={store_slug}",
        ]
        
        for endpoint in api_endpoints:
            try:
                response = self.session.get(endpoint, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    
                    # Parse different response formats
                    products = []
                    
                    if isinstance(data, list):
                        products = data
                    elif isinstance(data, dict) and 'products' in data:
                        products = data['products']
                    elif isinstance(data, dict) and 'items' in data:
                        products = data['items']
                    
                    for product in products[:3]:  # Check first 3
                        if not isinstance(product, dict):
                            continue
                        
                        name = product.get('name', product.get('productName', ''))
                        if not name:
                            continue
                        
                        # Skip excluded
                        if any(bad in name.lower() for bad in EXCLUDE_KEYWORDS):
                            continue
                        
                        price = product.get('price', product.get('currentPrice'))
                        if price:
                            return {
                                "Pvm": current_date,
                                "Kaupunki/Kauppa": store_name,
                                "Hakusana": ean,
                                "Tuote": clean_text(name)[:100],
                                "Hinta (EUR)": price
                            }
                            
            except:
                continue
        
        return None
    
    def _search_via_html_parsing(self, store_slug: str, ean: str, store_name: str, current_date: str) -> Optional[Dict]:
        """Fallback: Parse HTML directly"""
        # This is a simple fallback if other methods fail
        search_url = f"{self.base_url}/kauppa/{store_slug}/haku?q={ean}"
        
        response = self.get_with_retry(search_url)
        if not response or response.status_code != 200:
            return None
        
        # Simple regex search for products in HTML
        html = response.text
        
        # Look for product patterns
        product_patterns = [
            r'<h[2-4][^>]*>([^<]+)</h[2-4]>.*?(\d+[\.,]\d+)\s*€',
            r'class="[^"]*product[^"]*"[^>]*>.*?<span[^>]*>([^<]+)</span>.*?(\d+[\.,]\d+)',
            r'data-product-name="([^"]+)"[^>]*data-product-price="([^"]+)"',
        ]
        
        for pattern in product_patterns:
            matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
            for match in matches:
                if len(match) >= 2:
                    name = match[0].strip()
                    price_str = match[1].strip()
                    
                    # Skip excluded
                    if any(bad in name.lower() for bad in EXCLUDE_KEYWORDS):
                        continue
                    
                    # Clean price
                    price_match = re.search(r'(\d+[\.,]\d+)', price_str)
                    if price_match:
                        price = float(price_match.group(1).replace(',', '.'))
                        
                        return {
                            "Pvm": current_date,
                            "Kaupunki/Kauppa": store_name,
                            "Hakusana": ean,
                            "Tuote": clean_text(name)[:100],
                            "Hinta (EUR)": price
                        }
        
        return None

def main():
    print("🤖 Potwell Matrix-Robotti (Requests-Based Approach)")
    print(f"⏰ Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")
    
    # Test with minimal setup
    TEST_MODE = True
    TEST_STORE_NAME = "Espoo (Iso Omena)"
    TEST_STORE_SLUG = "k-citymarket-espoo-iso-omena"
    TEST_PRODUCTS = SEARCH_QUERIES[:3]  # Just 3 for testing
    
    if TEST_MODE:
        print("🔧 TEST MODE - Testing one store with 3 products")
        stores_to_process = [(TEST_STORE_NAME, TEST_STORE_SLUG)]
        products_per_store = TEST_PRODUCTS
    else:
        bot_id = int(os.environ.get("BOT_ID", 1))
        total_bots = int(os.environ.get("TOTAL_BOTS", 1))
        
        all_stores = list(STORES_TO_CHECK.items())
        chunk_size = math.ceil(len(all_stores) / total_bots)
        start_index = (bot_id - 1) * chunk_size
        end_index = start_index + chunk_size
        stores_to_process = list(dict(all_stores[start_index:end_index]).items())
        products_per_store = SEARCH_QUERIES
    
    print(f"📋 Stores to process: {len(stores_to_process)}")
    print(f"📦 Products per store: {len(products_per_store)}")
    print(f"{'=' * 60}")
    
    all_data = []
    
    # Initialize scraper
    scraper = KRuokaScraper()
    
    for store_name, store_slug in stores_to_process:
        print(f"\n{'=' * 60}")
        print(f"🛒 PROCESSING: {store_name}")
        print(f"{'=' * 60}")
        
        start_time = time.time()
        store_data = []
        
        # First, test if we can access the store
        print(f"  Testing store access...", end=" ")
        test_url = f"https://www.k-ruoka.fi/kauppa/{store_slug}"
        response = scraper.get_with_retry(test_url)
        
        if response:
            print(f"✅ Status: {response.status_code}")
            
            # Check if we got actual content or redirect/block
            if response.status_code == 200 and len(response.text) > 1000:
                print(f"  ✅ Store accessible")
                
                # Process products
                for i, ean in enumerate(products_per_store, 1):
                    print(f"  [{i}/{len(products_per_store)}] ", end="")
                    
                    # Add delay between requests
                    if i > 1:
                        time.sleep(random.uniform(1, 2))
                    
                    product_data = scraper.search_product(store_slug, ean, store_name)
                    if product_data:
                        store_data.append(product_data)
                
                if store_data:
                    all_data.extend(store_data)
                    print(f"  ✅ Found {len(store_data)} products")
                    
                    # Save store data
                    save_to_sheet(store_data)
                else:
                    print(f"  ⚠️ No products found in this store")
                    
            else:
                print(f"  ❌ Store not accessible (Status: {response.status_code})")
                print(f"  📄 Response preview: {response.text[:200]}")
        else:
            print(f"❌ Could not connect to store")
        
        elapsed = time.time() - start_time
        print(f"  ⏱️ Time taken: {elapsed:.1f}s")
        
        # Delay between stores
        if len(stores_to_process) > 1:
            delay = random.uniform(5, 10)
            print(f"  ⏳ Waiting {delay:.1f}s before next store...")
            time.sleep(delay)
    
    # Final summary
    print(f"\n{'=' * 60}")
    print("📊 FINAL SUMMARY")
    print(f"{'=' * 60}")
    print(f"✅ Total stores processed: {len(stores_to_process)}")
    print(f"✅ Total products found: {len(all_data)}")
    
    if all_data:
        print(f"\n💾 Saving all data...")
        save_to_sheet(all_data)
    
    print(f"\n{'=' * 60}")
    print(f"🏁 Script completed!")
    print(f"⏰ End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()
