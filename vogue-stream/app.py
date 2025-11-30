import os
import sys
import time
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import requests

app = Flask(__name__, template_folder='templates')
CORS(app)

# Hlavičky pro requests (aby si web myslel, že jsme člověk)
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
    
    # Cesta k Chrome na Renderu
    paths = [
        "/opt/render/project/.render/chrome/opt/google/chrome/google-chrome",
        "/opt/render/project/src/.render/chrome/opt/google/chrome/google-chrome"
    ]
    
    binary_path = None
    for path in paths:
        if os.path.exists(path):
            print(f"DEBUG: Chrome binárka nalezena: {path}", file=sys.stderr)
            chrome_options.binary_location = path
            binary_path = path
            break
            
    # MAGIE: Pokud jsme našli binárku, řekneme managerovi, ať stáhne driver PŘESNĚ pro ni
    try:
        if binary_path:
            # Získáme verzi nainstalovaného Chrome a stáhneme odpovídající driver
            driver_path = ChromeDriverManager().install()
        else:
            driver_path = ChromeDriverManager().install()
            
        print(f"DEBUG: Driver nainstalován: {driver_path}", file=sys.stderr)
        service = Service(driver_path)
        return webdriver.Chrome(service=service, options=chrome_options)
        
    except Exception as e:
        print(f"CHYBA DRIVERU: {e}", file=sys.stderr)
        raise e

def get_direct_video_url(page_url):
    driver = None
    try:
        print(f"DEBUG: Spouštím Selenium na: {page_url}", file=sys.stderr)
        driver = get_chrome_driver()
        driver.get(page_url)
        time.sleep(5) # Čekání na načtení skriptů
        
        # 1. Zkusíme najít ID
        try:
            video = driver.find_element("id", "content_video_html5_api")
            src = video.get_attribute("src")
            if src: return src
        except:
            pass

        # 2. Zkusíme najít jakýkoliv MP4 source
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
        print(f"DEBUG: Stahuji stránku {search_url}", file=sys.stderr)
        r = requests.get(search_url, headers=HEADERS)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # TADY BYLA CHYBA - Přidáme seznam zakázaných slov
        forbidden_words = ['nahrat', 'profil', 'registrace', 'prihlaseni', 'podminky', 'dmca', 'kontakt', 'premium']
        
        candidates = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            
            # Přísnější filtr
            if href.startswith('/') and 'hledej' not in href and len(text) > 3:
                # Kontrola zakázaných slov
                if any(bad_word in href.lower() for bad_word in forbidden_words):
                    continue
                    
                full_link = "https://prehrajto.cz" + href
                candidates.append((text, full_link))

        print(f"DEBUG: Nalezeno {len(candidates)} validních kandidátů.", file=sys.stderr)

        if not candidates:
            return {"error": "Žádný film nenalezen (seznam prázdný)"}

        # Vezmeme první validní výsledek
        best_title, best_link = candidates[0]
        print(f"DEBUG: Vítěz: {best_title} -> {best_link}", file=sys.stderr)
        
        video_url = get_direct_video_url(best_link)
        
        if video_url:
            return {"title": best_title, "url": video_url}
        else:
            return {"error": "Nepodařilo se extrahovat video (odkaz nenalezen)"}

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
