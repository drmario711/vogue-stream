import os
import sys
import time
import re
import difflib # Knihovna pro porovnávání podobnosti textů
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
import requests

app = Flask(__name__, template_folder='templates')
CORS(app)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'cs,en-US;q=0.7,en;q=0.3',
}

def get_chrome_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    paths = [
        "/opt/render/project/.render/chrome/opt/google/chrome/google-chrome",
        "/opt/render/project/src/.render/chrome/opt/google/chrome/google-chrome"
    ]
    
    for path in paths:
        if os.path.exists(path):
            chrome_options.binary_location = path
            break
    
    service = Service()
    return webdriver.Chrome(service=service, options=chrome_options)

def parse_size_mb(text):
    """Najde v textu velikost (např. 1.5 GB) a převede na MB"""
    try:
        # Hledáme vzor: číslo následované GB nebo MB
        match = re.search(r'(\d+[.,]?\d*)\s*(GB|MB)', text, re.IGNORECASE)
        if not match:
            return 0
        
        number = float(match.group(1).replace(',', '.'))
        unit = match.group(2).upper()
        
        if unit == 'GB':
            return number * 1024
        return number # MB
    except:
        return 0

def get_direct_video_url(page_url):
    driver = None
    try:
        print(f"DEBUG: Selenium otevírá: {page_url}", file=sys.stderr)
        driver = get_chrome_driver()
        driver.get(page_url)
        time.sleep(5) 
        
        # Pokus 1: ID
        try:
            video = driver.find_element("id", "content_video_html5_api")
            src = video.get_attribute("src")
            if src: return src
        except:
            pass

        # Pokus 2: Source tagy
        sources = driver.find_elements("tag name", "source")
        for s in sources:
            src = s.get_attribute("src")
            if src and "mp4" in src:
                return src
        return None
    except Exception as e:
        print(f"ERROR SELENIUM: {e}", file=sys.stderr)
        return None
    finally:
        if driver: driver.quit()

def find_movie(query):
    base = "https://prehrajto.cz/hledej/"
    search_url = base + query.replace(" ", "+")
    
    try:
        print(f"DEBUG: Requests hledá: {search_url}", file=sys.stderr)
        r = requests.get(search_url, headers=HEADERS)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        candidates = []
        
        # Projdeme všechny odkazy na stránce
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            
            # Základní filtr: Musí to být interní odkaz a mít nějaký text
            if href.startswith('/') and len(text) > 3:
                
                # 1. FUZZY MATCHING (Podobnost)
                # Spočítáme, jak moc je text podobný dotazu (0.0 až 1.0)
                similarity = difflib.SequenceMatcher(None, query.lower(), text.lower()).ratio()
                
                # Pokud je shoda menší než 30%, je to pravděpodobně reklama nebo menu -> ignorujeme
                if similarity < 0.3:
                    continue
                
                # 2. VELIKOST (Kvalita)
                # Zkusíme najít velikost v textu odkazu nebo v jeho okolí (rodičovský prvek)
                # Často je velikost napsaná hned vedle názvu
                full_text_context = text
                if a.parent:
                    full_text_context = a.parent.get_text(strip=True)
                
                size_mb = parse_size_mb(full_text_context)
                
                candidates.append({
                    'title': text,
                    'link': "https://prehrajto.cz" + href,
                    'similarity': similarity,
                    'size_mb': size_mb
                })

        print(f"DEBUG: Nalezeno {len(candidates)} kandidátů nad 30% shody.", file=sys.stderr)

        if not candidates:
            return {"error": "Nenalezen žádný soubor s podobným názvem."}

        # 3. SEŘAZENÍ (To je to kouzlo)
        # Seřadíme to primárně podle VELIKOSTI (největší první)
        # Sekundárně podle PODOBNOSTI
        candidates.sort(key=lambda x: (x['size_mb'], x['similarity']), reverse=True)

        best = candidates[0]
        print(f"DEBUG: VÍTĚZ: '{best['title']}' (Velikost: {best['size_mb']} MB, Shoda: {best['similarity']:.2f})", file=sys.stderr)
        
        # Pokud je vítěz "podezřele malý" (např. pod 50MB) a máme jiné kandidáty, 
        # možná je to jen trailer. Ale pro začátek věřme velikosti.
        
        video_url = get_direct_video_url(best['link'])
        
        if video_url:
            return {"title": best['title'], "url": video_url}
        else:
            return {"error": "Nepodařilo se vytáhnout video."}

    except Exception as e:
        print(f"CRITICAL ERROR: {e}", file=sys.stderr)
        return {"error": str(e)}

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/search')
def search():
    q = request.args.get('q')
    if not q: return jsonify({"error": "Empty query"}), 400
    res = find_movie(q)
    if "error" in res: return jsonify(res), 500
    return jsonify(res)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
