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
import requests # Musí být importováno

app = Flask(__name__, template_folder='templates')
CORS(app)

# Nastavení hlaviček, aby si web myslel, že jsme opravdový člověk (Chrome na Windows)
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
            
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def get_direct_video_url(page_url):
    driver = None
    try:
        print(f"DEBUG: Spouštím Selenium na: {page_url}", file=sys.stderr)
        driver = get_chrome_driver()
        driver.get(page_url)
        time.sleep(6) # Čekáme na načtení
        
        # Zkusíme najít video tag
        try:
            video = driver.find_element("id", "content_video_html5_api")
            return video.get_attribute("src")
        except:
            # Fallback: Najdi jakékoliv video na stránce
            sources = driver.find_elements("tag name", "source")
            for s in sources:
                if "mp4" in s.get_attribute("src"):
                    return s.get_attribute("src")
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
        # TADY Byla chyba - musíme poslat hlavičky!
        r = requests.get(search_url, headers=HEADERS)
        
        if r.status_code != 200:
            return {"error": f"Web vrátil chybu {r.status_code}"}

        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Výpis pro kontrolu (uvidíš v logu)
        print(f"DEBUG: Titulek stránky: {soup.title.string if soup.title else 'Bez titulku'}", file=sys.stderr)

        # Hledáme odkazy, které vypadají jako filmy
        candidates = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            
            # Jednoduchá logika: Odkaz začíná lomítkem, není to 'hledej' a má smysluplnou délku
            if href.startswith('/') and 'hledej' not in href and len(text) > 3:
                candidates.append((text, "https://prehrajto.cz" + href))

        print(f"DEBUG: Nalezeno {len(candidates)} kandidátů.", file=sys.stderr)

        if not candidates:
            return None

        # Vezmeme hned ten první (Prehrajto řadí podle relevance samo)
        # Už nefiltrujeme podle jména, věříme vyhledávači
        best_title, best_link = candidates[0]
        print(f"DEBUG: Vítěz: {best_title} -> {best_link}", file=sys.stderr)
        
        video_url = get_direct_video_url(best_link)
        
        if video_url:
            return {"title": best_title, "url": video_url}
        else:
            return {"error": "Nepodařilo se extrahovat video (Selenium nenašlo MP4)"}

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
    if res: 
        if "error" in res: return jsonify(res), 500
        return jsonify(res)
    return jsonify({"error": "No matching movies found"}), 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
