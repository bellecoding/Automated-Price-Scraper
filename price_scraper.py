import os
import re
import time
import queue
import random
import logging
import argparse
import threading
import pandas as pd
from tqdm import tqdm
from urllib.parse import urlparse


from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException


import tempfile
import shutil
import psutil


INPUT_FILE = "sample_input.xlsx"
SELECTOR_FILE = "selector_sample.xlsx"
OUTPUT_FILE = "scraper_output_final.xlsx"


NUM_BROWSERS = 4
SLOW_SITE_TIMEOUT = 60
ELEMENT_WAIT_TIMEOUT = 15
MAX_RETRIES = 2
RETRY_DELAY_BASE = 5

GECKODRIVER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geckodriver.exe")


logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(threadName)s] - [%(levelname)s] - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
def log_info(message): logging.info(message)
def log_error(message): logging.error(message)
def log_warning(message): logging.warning(message)


def kill_browser_processes():
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'].lower() in ["geckodriver.exe", "firefox.exe"]:
            try: psutil.Process(proc.info['pid']).terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied): pass

def normalize_domain(url):
    try: return urlparse(url).netloc.replace("www.", "")
    except: return ""

def clean_price(price_text):
    if not price_text: return None
    price_text = price_text.strip().replace('.', '').replace(',', '.')
    cleaned_price = re.sub(r'[^\d\.]', '', price_text)
    if cleaned_price.count('.') > 1:
        parts = cleaned_price.split('.')
        cleaned_price = f"{parts[0]}.{''.join(parts[1:])}"
    return cleaned_price if cleaned_price else None


def handle_popups(driver):
 
 
    cookie_css_selectors = [
        'button[id*="cookie"][id*="accept"]', 'button[class*="cookie"][class*="accept"]',
        'button[id*="consent"][id*="accept"]', 'button[class*="consent"][class*="accept"]',
        'a[id*="cookie"][id*="accept"]', 'a[class*="cookie"][class*="accept"]',
        'div[class*="cookie-banner"] button:last-child', '#onetrust-accept-btn-handler',
        '.cc-btn.cc-allow', 'button[aria-label*="accept cookies"]',
    ]
    cookie_text_keywords = [
        "Accept All", "Accept cookies", "Accept", "Allow All", "Agree", "Got it",
        "Alle akzeptieren", "Zustimmen", "Akzeptieren", "Einverstanden", "Cookies akzeptieren",
        "Accepter tout", "Accepter les cookies", "J'accepte", "Tout accepter", "Autoriser tout",
        "Aceptar todas", "Aceptar cookies", "Aceptar", "Entendido", "Permitir todas",
        "Alle cookies accepteren", "Accepteren", "Akkoord", "Doorgaan",
        "Accept everything", "Akceptuję", "Akceptuj wszystko", "Zgadzam się", "Zaakceptuj",
        "Hyväksy kaikki", "Hyväksy evästeet", "Hyväksy", "Ok", "OK for moi",
        "Allow Cookies", "Autoriser les cookies", "Permitir cookies", "Accepteer cookies"
    ]
    general_css_selectors = [
        'button.close', 'button[aria-label*="close"]', 'span.close', 'div.close',
        '.modal-header .close', '[class*="close-button"]', 'div[id*="pop-up"] button',
        '[class*="close-icon"]', '[class*="popup-close"]', '[class*="newsletter-close"]',
        '[data-dismiss="modal"]', '[aria-label="Close"]', '#minimize'
    ]
    general_text_keywords = [
        "No, thanks", "No Thanks", "Later", "Schließen", "Fermer", "Cerrar", "Sluiten", "Zamknij", "Sulje"
    ]


    for selector in cookie_css_selectors:
        try:
            button = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
            button.click(); log_info(f"Clicked cookie button with CSS: {selector}"); time.sleep(1.5); return True
        except: continue
    for text in cookie_text_keywords:
        try:
            xpath = f"//button[normalize-space()='{text}'] | //a[normalize-space()='{text}']"
            button = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            button.click(); log_info(f"Clicked cookie button with text: '{text}'"); time.sleep(1.5); return True
        except: continue
    for selector in general_css_selectors:
        try:
            button = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
            button.click(); log_info(f"Clicked popup with CSS: {selector}"); time.sleep(1.5); return True
        except: continue
    for text in general_text_keywords:
        try:
            xpath = f"//button[normalize-space()='{text}'] | //a[normalize-space()='{text}']"
            button = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, xpath)))
            button.click(); log_info(f"Clicked popup with text: '{text}'"); time.sleep(1.5); return True
        except: continue
    return False


def init_driver():
    temp_profile_dir = tempfile.mkdtemp()
    try:
        options = Options()
        options.add_argument("--headless")
        options.add_argument("-profile"); options.add_argument(temp_profile_dir)
        service = Service(executable_path=GECKODRIVER_PATH)
        driver = webdriver.Firefox(service=service, options=options)
        return driver, temp_profile_dir
    except Exception as e:
        log_error(f"CRITICAL: Failed to initialize a driver: {e}")
        if temp_profile_dir: shutil.rmtree(temp_profile_dir, ignore_errors=True)
        return None, None

def worker(url_queue, results_list, selector_map):
    log_info("Worker starting...")
    driver, temp_profile_dir = init_driver()
    if not driver:
        log_error("Worker failed to start a browser and is shutting down.")
        
        while not url_queue.empty():
            try:
                url_info = url_queue.get_nowait()
                
                log_error(f"URL lost due to worker start failure: {url_info[1]}")
                url_queue.task_done()
            except queue.Empty:
                break
        return

    while not url_queue.empty():
        try:
            url_info = url_queue.get_nowait()
        except queue.Empty:
            break

        index, url, product_name = url_info
        domain = normalize_domain(url)
        site_selectors = selector_map.get(domain)
        result_base = {"index": index, "product_name": product_name, "url": url, "domain": domain}

        if not site_selectors:
            log_error(f"No selector for domain: {domain} ({url})")
            results_list.append({**result_base, "error": "No selector found for domain"})
            url_queue.task_done()
            continue
        
        for attempt in range(1, MAX_RETRIES + 1):
            start_time = time.time()
            error_msg = "Unknown error"
            try:
                driver.get(url)
                handle_popups(driver)
                price_selector = site_selectors.get("selector")
                price_element = WebDriverWait(driver, ELEMENT_WAIT_TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, price_selector)))
                price = clean_price(price_element.text)
                duration = time.time() - start_time
                log_info(f"SUCCESS: Price {price} for {url} ({duration:.2f}s)")
                results_list.append({**result_base, "price": price, "error": None, "duration": round(duration, 2), "attempt": attempt})
                break 
            except Exception as e:
                error_msg = f"{type(e).__name__}: {str(e).splitlines()[0]}"
                log_warning(f"Attempt {attempt}/{MAX_RETRIES} failed for {url}: {error_msg}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_BASE)
            
            if attempt >= MAX_RETRIES:
                duration = time.time() - start_time
                results_list.append({**result_base, "price": None, "error": error_msg, "duration": round(duration, 2), "attempt": attempt})
        
        url_queue.task_done()

    log_info("Worker finished. Closing browser.")
    if driver: driver.quit()
    if temp_profile_dir: shutil.rmtree(temp_profile_dir, ignore_errors=True)

def main(test_mode=False):
    kill_browser_processes()
    log_info(f"Starting scraper with {NUM_BROWSERS} parallel browsers.")

    try:
        df = pd.read_excel(INPUT_FILE)
        if test_mode: df = df.head(20)
        log_info(f"Loaded {len(df)} URLs to process.")
    except Exception as e:
        log_error(f"Fatal: Could not read {INPUT_FILE}. Error: {e}"); return
        
    try:
        selector_df = pd.read_excel(SELECTOR_FILE)
        selector_map = {row['domain'].replace("www.", "").lower().strip(): {"selector": row['selector']} for _, row in selector_df.iterrows()}
        log_info(f"Loaded {len(selector_map)} selectors.")
    except Exception as e:
        log_error(f"Fatal: Could not read {SELECTOR_FILE}. Error: {e}"); return

    url_queue = queue.Queue()
    for index, row in df.iterrows():
        url_queue.put((index, row['urls'], row.get('products', 'N/A')))

    results_list = []
    threads = []
    total_urls = url_queue.qsize()
    
    for i in range(NUM_BROWSERS):
        thread = threading.Thread(target=worker, args=(url_queue, results_list, selector_map), name=f"Browser-{i+1}")
        threads.append(thread)
        thread.start()

    with tqdm(total=total_urls, desc="Scraping URLs") as pbar:
        while any(t.is_alive() for t in threads):
            pbar.update(total_urls - url_queue.qsize() - pbar.n)
            time.sleep(1)
        pbar.update(total_urls - pbar.n)

    for thread in threads:
        thread.join()
    
    log_info("All workers have finished.")

    if not results_list:
        log_error("No results were generated."); return
        
    final_df = pd.DataFrame(sorted(results_list, key=lambda x: x.get('index', -1)))
    url_to_country = df.set_index('urls')['country'].to_dict() if "country" in df.columns else {}
    final_df['country'] = final_df['url'].map(url_to_country).fillna('general')

    try:
        with pd.ExcelWriter(OUTPUT_FILE) as writer:
            final_df.to_excel(writer, sheet_name='All_Results', index=False)
            for country, group in final_df.groupby("country"):
                group.to_excel(writer, sheet_name=str(country)[:31], index=False)
        log_info(f"✅ Final output saved to {OUTPUT_FILE} with sheets per country.")
    except Exception as e:
        log_error(f"Failed to save final output: {e}")
    finally:
        kill_browser_processes()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Web scraper for product prices.")
    parser.add_argument("--test", action="store_true", help="Run in test mode with the first 20 URLs.")
    args = parser.parse_args()
    main(test_mode=args.test)