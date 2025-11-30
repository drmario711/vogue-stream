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

app = Flask(__name__, template_folder='templates')
CORS(app)

def get_chrome_driver():
    """Nastavení Chrome pro Render.com prostředí"""
    chrome_options = Options()
    # Tyto flagy jsou KRITICKÉ pro server (headless)
    chrome_options.add_argument("--headless=new") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Cesta k Chrome na Renderu (pokud existuje)
    # Zkontrolujeme dvě možné cesty, kam se to mohlo nainstalovat
    paths = [
        "/opt/render/project/.render/chrome/opt/google/chrome/google-chrome",
        "/opt/render/project/src/.render/chrome/opt/google/chrome/google-chrome"
    ]
    
    binary_found = False
    for path in paths:
        if os.path.exists(path):
            print(f"DEBUG: Chrome nalezen zde: {path}", file=sys.stderr)
            chrome_options.binary_location = path
            binary_found = True
            break
            
    if not binary_found:
        print("DEBUG: Chrome nenalezen na standardních cestách. Zkouším default...", file=sys.stderr)

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def get_direct_video_url(page_url):
    driver = None
    try:
        print(f"DEBUG: Otevírám stránku {page_url}", file=sys.stderr)
        driver = get_chrome_driver()
        driver.get(page_url)
        
        # Čekáme déle (8 sekund), server může být pomalý
        time.sleep(8) 
        
        # Zkusíme najít video
        try:
            video = driver.find_element("id", "content_video_html5_api")
            url = video.get_attribute("src")
            return url
        except:
            # Pokud nenajde ID, zkusí najít jakýkoliv MP4 odkaz
            print("DEBUG: ID videa nenalezeno, hledám source tag...", file=sys.stderr)
            sources = driver.find_elements("tag name", "source")
            for source in sources:
                src = source.get_attribute("src")
                if "mp4" in src:
                    return src
            return None
            
    except Exception as e:
        # TOTO JE DŮLEŽITÉ: Vypíše chybu do logu
        print(f"CHYBA SELENIUM: {str(e)}", file=sys.stderr)
        return f"ERROR: {str(e)}" # Vrátíme chybu jako text, abychom ji viděli
    finally:
        if driver:
            driver.quit()

def find_movie(query):
    base = "https://prehrajto.cz/hledej/"
    search_url = base + query.replace(" ", "+")
    
    try:
        import requests
        print(f"DEBUG: Hledám v seznamu: {search_url}", file=sys.stderr)
        r = requests.get(search_url)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        links = soup.find_all('a', href=True)
        for link in links:
            if link['href'].startswith('/') and 'hledej' not in link['href'] and len(link.get_text()) > 3:
                if query.lower() in link.get_text().lower():
                    full_link = "https://prehrajto.cz" + link['href']
                    
                    # Získat MP4
                    result = get_direct_video_url(full_link)
                    
                    # Pokud se vrátila chyba (text začínající ERROR), pošleme ji na frontend
                    if result and result.startswith("ERROR"):
                        return {"error": result}
                        
                    if result:
                        return {"title": link.get_text(strip=True), "url": result}
        return None
    except Exception as e:
        print(f"CHYBA: {e}", file=sys.stderr)
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
        if "error" in res:
            return jsonify(res), 500 # Vrátí chybu serveru
        return jsonify(res)
        
    return jsonify({"error": "Not found"}), 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
