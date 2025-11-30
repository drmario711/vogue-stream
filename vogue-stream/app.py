import os
import sys
import time
import re
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

app = Flask(__name__, template_folder='templates')
CORS(app)

def get_chrome_driver():
    chrome_options = Options()
    # Nastavení pro server (Render)
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Najdi Chrome na Renderu
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

def get_size_in_gb(text):
    """
    Hledá v textu 'GB'. Pokud najde '9.29 GB', vrátí číslo 9.29.
    Pokud je to v MB, vrátí malinké číslo (např. 0.5).
    Pokud nic nenajde, vrátí 0.
    """
    if not text: return 0
    text = text.upper().replace(',', '.')
    
    # Hledáme číslo následované GB
    match_gb = re.search(r'(\d+\.?\d*)\s*GB', text)
    if match_gb:
        return float(match_gb.group(1))
        
    # Hledáme číslo následované MB (vydělíme 1024, aby to bylo v GB)
    match_mb = re.search(r'(\d+\.?\d*)\s*MB', text)
    if match_mb:
        return float(match_mb.group(1)) / 1024.0
        
    return 0

def extract_video_direct_link(driver, url):
    """Otevře detail filmu a najde MP4 odkaz"""
    try:
        print(f"DEBUG: Otevírám detail: {url}", file=sys.stderr)
        driver.get(url)
        time.sleep(3) # Počkáme na načtení přehrávače
        
        # 1. Nejlepší metoda: Najít <video> tag s ID
        try:
            video = driver.find_element(By.ID, "content_video_html5_api")
            src = video.get_attribute("src")
            if src and "http" in src: 
                return src
        except:
            pass
            
        # 2. Záložní metoda: Najít jakýkoliv zdroj s .mp4
        sources = driver.find_elements(By.TAG_NAME, "source")
        for source in sources:
            src = source.get_attribute("src")
            if src and "mp4" in src:
                return src
                
        return None
    except Exception as e:
        print(f"DEBUG: Chyba extrakce: {e}", file=sys.stderr)
        return None

def find_movie(query):
    driver = None
    try:
        driver = get_chrome_driver()
        
        # 1. Jdeme na vyhledávání
        search_url = f"https://prehrajto.cz/hledej/{query.replace(' ', '+')}"
        print(f"DEBUG: Hledám na: {search_url}", file=sys.stderr)
        
        driver.get(search_url)
        time.sleep(5) # Počkáme, až se načtou obrázky a texty
        
        # 2. Najdeme všechny odkazy na stránce
        # Hledáme elementy, které vypadají jako položky videa
        all_links = driver.find_elements(By.TAG_NAME, "a")
        
        candidates = []
        
        for link in all_links:
            try:
                href = link.get_attribute("href")
                # Získáme všechen text uvnitř odkazu (včetně velikosti, času atd.)
                # .get_attribute("innerText") je často spolehlivější než .text u skrytých prvků
                full_text = link.get_attribute("innerText") 
                
                if not href or not full_text: continue
                
                # Zjednodušený filtr:
                # 1. Musí to být odkaz na detail (ne reklama, ne login)
                if "/hledej/" in href or "partner" in href or "registrace" in href: continue
                if not href.startswith("https://prehrajto.cz"): continue
                
                # 2. Musí obsahovat hledaný název (stačí část)
                # Rozdělíme hledaný dotaz na slova (např. "harry potter" -> "harry", "potter")
                query_parts = query.lower().split()
                # Pokud alespoň jedno slovo z dotazu není v textu odkazu, ignorujeme to
                if not any(part in full_text.lower() for part in query_parts if len(part) > 2):
                    continue

                # 3. Získáme velikost
                size_gb = get_size_in_gb(full_text)
                
                # Pokud to má méně než 0.1 GB (100MB), je to asi blbost nebo trailer
                if size_gb < 0.1: continue
                
                candidates.append({
                    "title": full_text.split('\n')[0].strip(), # První řádek je obvykle název
                    "link": href,
                    "size": size_gb
                })
                
            except:
                continue

        print(f"DEBUG: Nalezeno {len(candidates)} možných souborů.", file=sys.stderr)

        if not candidates:
            return {"error": "Nenalezeny žádné videosoubory."}

        # 3. SEŘADIT PODLE VELIKOSTI (Největší = Nejlepší kvalita)
        candidates.sort(key=lambda x: x['size'], reverse=True)
        
        # Zkusíme postupně nejlepší 3 (kdyby první nešel)
        for cand in candidates[:3]:
            print(f"DEBUG: Zkouším: {cand['title']} ({cand['size']:.2f} GB)", file=sys.stderr)
            video_url = extract_video_direct_link(driver, cand['link'])
            
            if video_url:
                return {"title": cand['title'], "url": video_url}
        
        return {"error": "Nepodařilo se získat přímý odkaz na video."}

    except Exception as e:
        print(f"CRITICAL ERROR: {e}", file=sys.stderr)
        return {"error": str(e)}
    finally:
        if driver: driver.quit()

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
