import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time

app = Flask(__name__, template_folder='templates')
CORS(app)

def get_chrome_driver():
    """Nastavení Chrome pro Render.com prostředí"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Cesta k Chrome na Renderu (pokud existuje)
    chrome_path = "/opt/render/project/.render/chrome/opt/google/chrome/google-chrome"
    if os.path.exists(chrome_path):
        chrome_options.binary_location = chrome_path

    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def get_direct_video_url(page_url):
    driver = None
    try:
        print(f"Otevírám: {page_url}")
        driver = get_chrome_driver()
        driver.get(page_url)
        # Čekáme na načtení
        time.sleep(5) 
        
        # Hledáme video tag
        video = driver.find_element("id", "content_video_html5_api")
        url = video.get_attribute("src")
        
        if not url:
            source = video.find_element("tag name", "source")
            url = source.get_attribute("src")
            
        return url
    except Exception as e:
        print(f"Chyba: {e}")
        return None
    finally:
        if driver:
            driver.quit()

def find_movie(query):
    base = "https://prehrajto.cz/hledej/"
    search_url = base + query.replace(" ", "+")
    
    try:
        import requests
        r = requests.get(search_url)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Jednoduché hledání prvního odkazu
        links = soup.find_all('a', href=True)
        for link in links:
            if link['href'].startswith('/') and 'hledej' not in link['href'] and len(link.get_text()) > 3:
                if query.lower() in link.get_text().lower():
                    full_link = "https://prehrajto.cz" + link['href']
                    # Získat MP4
                    mp4 = get_direct_video_url(full_link)
                    if mp4:
                        return {"title": link.get_text(strip=True), "url": mp4}
        return None
    except Exception as e:
        print(e)
        return None

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/search')
def search():
    q = request.args.get('q')
    if not q: return jsonify({"error": "Empty query"}), 400
    res = find_movie(q)
    if res: return jsonify(res)
    return jsonify({"error": "Not found"}), 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)