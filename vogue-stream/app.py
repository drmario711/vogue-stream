import os
import sys
import time
import re
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from bs4 import BeautifulSoup
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

app = Flask(__name__, template_folder='templates')
CORS(app)

# Tváříme se jako běžný prohlížeč, aby nás web neblokoval
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
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

def parse_size_gb(text):
    """Vrátí velikost v GB. Pokud je v MB, převede na GB."""
    if not text: return 0
    text = text.upper().replace(',', '.')
    
    # Hledáme např. "9.29 GB"
    match_gb = re.search(r'(\d+\.?\d*)\s*GB', text)
    if match_gb:
        return float(match_gb.group(1))
        
    # Hledáme např. "800 MB" -> 0.8 GB
    match_mb = re.search(r'(\d+\.?\d*)\s*MB', text)
    if match_mb:
        return float(match_mb.group(1)) / 1024.0
        
    return 0

def extract_video_direct_link(url):
    """Tady (a jen tady) použijeme Chrome, abychom získali MP4"""
    driver = None
    try:
        print(f"DEBUG: Spouštím Chrome pro odkaz: {url}", file=sys.stderr)
        driver = get_chrome_driver()
        driver.get(url)
        time.sleep(4) # Čekáme na načtení přehrávače
        
        # 1. Hledáme ID videa
        try:
            video = driver.find_element(By.ID, "content_video_html5_api")
            src = video.get_attribute("src")
            if src and "http" in src: return src
        except:
            pass
            
        # 2. Hledáme source tagy
        sources = driver.find_elements(By.TAG_NAME, "source")
        for s in sources:
            src = s.get_attribute("src")
            if src and "mp4" in src: return src
            
        return None
    except Exception as e:
        print(f"DEBUG: Chyba extrakce: {e}", file=sys.stderr)
        return None
    finally:
        if driver: driver.quit()

def find_movie(query):
    # 1. RYCHLÉ HLEDÁNÍ (Bez Chromu, jen stáhnutí HTML)
    base_url = "https://prehrajto.cz/hledej/"
    search_url = base_url + query.replace(" ", "+")
    print(f"DEBUG: Rychlé hledání na: {search_url}", file=sys.stderr)
    
    try:
        response = requests.get(search_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        candidates = []
        
        # Hledáme všechny odkazy, které vypadají jako film
        # Odkazy na prehrajto mají strukturu /nazev-filmu/id
        links = soup.find_all('a', href=True)
        
        for link in links:
            href = link['href']
            
            # Musí to být odkaz na video (obsahuje alespoň 2 lomítka v cestě a není to systémový odkaz)
            # Typický odkaz: /harry-potter-a-kamen-mudrcu/6904d45ac19b6
            if not href.startswith('/') or href.count('/') < 2:
                continue
            if any(x in href for x in ['/hledej/', '/profil/', '/front/', 'registrace', 'login']):
                continue
                
            # Získáme text odkazu i text v okolí (často je velikost vedle odkazu)
            text_inside = link.get_text(strip=True)
            text_parent = link.parent.get_text(strip=True) if link.parent else ""
            full_text = text_inside + " " + text_parent
            
            # Filtr názvu: Odkaz musí obsahovat část hledaného textu
            # Pokud hledám "Spiderman 3", v odkazu musí být "spiderman"
            simple_query = query.split()[0].lower() # Vezmeme první slovo dotazu pro jistotu
            if simple_query not in href.replace('-', ' ').lower():
                continue

            # Získáme velikost
            size_gb = parse_size_gb(full_text)
            
            candidates.append({
                'title': text_inside,
                'link': "https://prehrajto.cz" + href,
                'size': size_gb
            })
            
        print(f"DEBUG: Nalezeno {len(candidates)} kandidátů.", file=sys.stderr)
        
        if not candidates:
            return {"error": "Nenalezeny žádné soubory."}

        # 2. SEŘAZENÍ PODLE VELIKOSTI (Největší nahoře)
        candidates.sort(key=lambda x: x['size'], reverse=True)
        
        # 3. EXTRAKCE VIDEA (Zkusíme top 3)
        for best in candidates[:3]:
            print(f"DEBUG: Zkouším kandidáta: {best['link']} ({best['size']} GB)", file=sys.stderr)
            
            video_url = extract_video_direct_link(best['link'])
            
            if video_url:
                return {"title": best['title'], "url": video_url}
        
        return {"error": "Video se nepodařilo přehrát."}

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
