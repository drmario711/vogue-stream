import os
import sys
import time
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
    # Tyto argumenty jsou pro Render server nezbytné
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Hledáme Chrome na serveru
    paths = [
        "/opt/render/project/.render/chrome/opt/google/chrome/google-chrome",
        "/opt/render/project/src/.render/chrome/opt/google/chrome/google-chrome"
    ]
    
    binary_found = False
    for path in paths:
        if os.path.exists(path):
            print(f"DEBUG: Chrome nalezen: {path}", file=sys.stderr)
            chrome_options.binary_location = path
            binary_found = True
            break
    
    if not binary_found:
        print("DEBUG: Chrome nenalezen na vlastní cestě, spoléhám na systém...", file=sys.stderr)

    # ZDE JE ZMĚNA: Nepoužíváme ChromeDriverManager.
    # Selenium 4.27 si samo najde/stáhne driver podle verze prohlížeče.
    service = Service() 
    
    return webdriver.Chrome(service=service, options=chrome_options)

def get_direct_video_url(page_url):
    driver = None
    try:
        print(f"DEBUG: Selenium otevírá: {page_url}", file=sys.stderr)
        driver = get_chrome_driver()
        driver.get(page_url)
        time.sleep(4) 
        
        # 1. Priorita: ID
        try:
            video = driver.find_element("id", "content_video_html5_api")
            src = video.get_attribute("src")
            if src: return src
        except:
            pass

        # 2. Priorita: Jakýkoliv MP4 source
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
        
        # ČERNÁ LISTINA - slova, která nesmí být v odkazu ani v textu
        blacklist = ['nahrat', 'profil', 'registrace', 'prihlaseni', 'podminky', 'dmca', 'kontakt', 'premium', 'upload']
        
        candidates = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True).lower()
            href_lower = href.lower()
            
            # Musí to být interní odkaz a mít nějakou délku
            if href.startswith('/') and len(text) > 3:
                
                # 1. Kontrola Blacklistu (pokud obsahuje zakázané slovo, přeskočit)
                if any(bad in href_lower for bad in blacklist) or any(bad in text for bad in blacklist):
                    continue
                
                # 2. Kontrola relevance (volitelné, ale bezpečné)
                # Odkaz by měl ideálně obsahovat část hledaného názvu
                # Rozdělíme hledaný dotaz na slova a zkontrolujeme, zda alespoň jedno je v názvu odkazu
                query_parts = query.lower().split()
                if any(part in text for part in query_parts if len(part) > 2):
                    full_link = "https://prehrajto.cz" + href
                    candidates.append((a.get_text(strip=True), full_link))

        print(f"DEBUG: Nalezeno {len(candidates)} relevantních filmů.", file=sys.stderr)

        if not candidates:
            return {"error": "Film nenalezen (žádné relevantní výsledky)."}

        # Vezmeme první
        best_title, best_link = candidates[0]
        print(f"DEBUG: Vybrán vítěz: {best_title} -> {best_link}", file=sys.stderr)
        
        video_url = get_direct_video_url(best_link)
        
        if video_url:
            return {"title": best_title, "url": video_url}
        else:
            return {"error": "Nepodařilo se vytáhnout video z přehrávače."}

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
