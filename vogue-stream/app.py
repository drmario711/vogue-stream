import os
import sys
import time
import re
import difflib
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

app = Flask(__name__, template_folder='templates')
CORS(app)

def get_chrome_driver():
    chrome_options = Options()
    # Nutné nastavení pro Render
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Hledání cesty k Chrome
    paths = [
        "/opt/render/project/.render/chrome/opt/google/chrome/google-chrome",
        "/opt/render/project/src/.render/chrome/opt/google/chrome/google-chrome"
    ]
    for path in paths:
        if os.path.exists(path):
            print(f"DEBUG: Chrome nalezen: {path}", file=sys.stderr)
            chrome_options.binary_location = path
            break
    
    service = Service()
    return webdriver.Chrome(service=service, options=chrome_options)

def parse_size_mb(text):
    """Vytáhne velikost v MB z textu"""
    try:
        match = re.search(r'(\d+[.,]?\d*)\s*(GB|MB)', text, re.IGNORECASE)
        if not match: return 0
        val = float(match.group(1).replace(',', '.'))
        unit = match.group(2).upper()
        return val * 1024 if unit == 'GB' else val
    except:
        return 0

def extract_video_from_page(driver, url):
    """Jde na stránku a zkusí najít MP4"""
    try:
        print(f"DEBUG: Otevírám detail videa: {url}", file=sys.stderr)
        driver.get(url)
        time.sleep(4) # Čas na načtení přehrávače
        
        # 1. Zkusíme HTML5 video tag
        try:
            video = driver.find_element(By.ID, "content_video_html5_api")
            src = video.get_attribute("src")
            if src and len(src) > 10: return src
        except:
            pass

        # 2. Zkusíme source tagy
        sources = driver.find_elements(By.TAG_NAME, "source")
        for s in sources:
            src = s.get_attribute("src")
            if src and "mp4" in src:
                return src
        
        return None
    except Exception as e:
        print(f"DEBUG: Chyba při extrakci: {e}", file=sys.stderr)
        return None

def find_movie(query):
    driver = None
    try:
        driver = get_chrome_driver()
        
        # 1. VYHLEDÁVÁNÍ (Nyní přes Selenium, aby se načetlo vše!)
        base = "https://prehrajto.cz/hledej/"
        search_url = base + query.replace(" ", "+")
        print(f"DEBUG: Načítám seznam výsledků: {search_url}", file=sys.stderr)
        
        driver.get(search_url)
        time.sleep(5) # Počkáme, až JavaScript vykreslí výsledky
        
        # Získáme HTML z prohlížeče
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        candidates = []
        query_words = [w.lower() for w in query.split() if len(w) > 2]
        
        # Projdeme VŠECHNY odkazy
        all_links = soup.find_all('a', href=True)
        print(f"DEBUG: Na stránce nalezeno celkem {len(all_links)} odkazů.", file=sys.stderr)

        for a in all_links:
            href = a['href']
            text = a.get_text(strip=True)
            text_lower = text.lower()
            
            # Musí to být odkaz na video (ne /front/, ne /hledej/)
            if href.startswith('/') and len(text) > 3:
                if any(x in href for x in ['/front/', '/hledej/', '/profil/', 'registrace', 'podminky']):
                    continue
                
                # KLÍČOVÝ FILTR: Odkaz MUSÍ obsahovat alespoň jedno slovo z dotazu
                # Např. pokud hledáš "Harry Potter", text musí obsahovat "harry" nebo "potter"
                match_word = False
                for qw in query_words:
                    if qw in text_lower:
                        match_word = True
                        break
                
                if not match_word:
                    continue

                # Zkusíme najít velikost
                full_context = text
                if a.parent: full_context += " " + a.parent.get_text()
                size_mb = parse_size_mb(full_context)
                
                # Spočítáme shodu celého názvu
                ratio = difflib.SequenceMatcher(None, query.lower(), text_lower).ratio()
                
                candidates.append({
                    'title': text,
                    'link': "https://prehrajto.cz" + href,
                    'size_mb': size_mb,
                    'ratio': ratio
                })

        print(f"DEBUG: Po filtrování zbylo {len(candidates)} relevantních filmů.", file=sys.stderr)

        if not candidates:
            return {"error": "Nenalezen žádný film odpovídající dotazu."}

        # Seřadíme: 1. Velikost, 2. Podobnost názvu
        candidates.sort(key=lambda x: (x['size_mb'], x['ratio']), reverse=True)

        # Zkusíme projít TOP 3 kandidáty (kdyby první nefungoval)
        for i, best in enumerate(candidates[:3]):
            print(f"DEBUG: Zkouším kandidáta č.{i+1}: {best['title']} ({best['size_mb']} MB)", file=sys.stderr)
            
            video_url = extract_video_from_page(driver, best['link'])
            
            if video_url:
                print(f"DEBUG: ÚSPĚCH! Video nalezeno.", file=sys.stderr)
                return {"title": best['title'], "url": video_url}
            else:
                print(f"DEBUG: U tohoto kandidáta video nešlo extrahovat.", file=sys.stderr)
        
        return {"error": "Video se nepodařilo přehrát u žádného z nalezených souborů."}

    except Exception as e:
        print(f"CRITICAL ERROR: {e}", file=sys.stderr)
        return {"error": str(e)}
    finally:
        if driver:
            try: driver.quit()
            except: pass

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
