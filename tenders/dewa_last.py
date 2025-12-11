import os
import time
import requests
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

API_ENDPOINT = "https://ms.prizm-energy.com/MS/api/tenders/DEWAFetchTenders"

def convert_date_format(date_str):
    """Convert date from '12-Sep-2025' format to '2025-09-12' format"""
    if not date_str or date_str.strip() == '':
        return None
    
    try:
        date_obj = datetime.strptime(date_str.strip(), '%d-%b-%Y')
        return date_obj.strftime('%Y-%m-%d')
    except ValueError as e:
        print(f"Error converting date '{date_str}': {str(e)}")
        return None

def extract_tender_data():
    # Setup Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    )
    
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        url = "https://www.dewa.gov.ae/en/supplier/services/list-of-tender-documents"
        print(f"Navigating to: {url}")
        driver.get(url)
        
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CLASS_NAME, "tender-result"))
        )
        
        time.sleep(5)
        
        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        
        tender_results = soup.find_all('div', class_='tender-result')
        
        tenders_data = []
        
        for tender in tender_results:
            tender_data = {}
            
            title = tender.find('h2', class_='tender-result__title')
            if title:
                tender_data['si_no'] = title.text.strip()
            
            details = tender.find('dl', class_='tender-result__details')
            if details:
                keys = details.find_all('dt', class_='tender-result__key')
                values = details.find_all('dd', class_='tender-result__value')
                
                for key, value in zip(keys, values):
                    key_text = key.text.strip().replace(':', '')
                    
                    if key_text == 'Tender No':
                        tender_no = value.get_text().strip().split('\n')[0].strip()
                        tender_data['tender_no'] = tender_no
                        
                    elif key_text == 'Name of Tenderer ':
                        tender_data['tender_name'] = value.text.strip()
                        
                    elif key_text == 'Tender Status':
                        tender_data['tender_status'] = value.text.strip()
            
            expander_content = tender.find('div', class_='m37-expander__content')
            if expander_content:
                doc_details = expander_content.find('dl', class_='tender-result__details')
                if doc_details:
                    doc_keys = doc_details.find_all('dt', class_='tender-result__key')
                    doc_values = doc_details.find_all('dd', class_='tender-result__value')
                    
                    for key, value in zip(doc_keys, doc_values):
                        key_text = key.get_text().strip().replace(':', '')
                        
                        if 'Tender Fee' in key_text:
                            tender_data['tender_fee'] = value.text.strip()
                            
                        elif key_text == 'Floating Date':
                            raw_date = value.text.strip()
                            tender_data['floating_date'] = convert_date_format(raw_date)
                            
                        elif key_text == 'Closing Date':
                            raw_date = value.text.strip()
                            tender_data['closing_date'] = convert_date_format(raw_date)
                            
                        elif key_text == 'Buying Details':
                            link = value.find('a')
                            if link:
                                tender_data['purchase_link'] = link.get('href')
            
            if tender_data:
                tenders_data.append(tender_data)
        
        print(f"Found {len(tenders_data)} tenders")
        
        for i, tender in enumerate(tenders_data, 1):
            print(f"\n--- Tender {i} ---")
            for key, value in tender.items():
                print(f"{key}: {value}")
        
        if tenders_data:
            send_to_api(tenders_data)
        
        return tenders_data
        
    except Exception as e:
        print(f"Error extracting tender data: {str(e)}")
        return []
        
    finally:
        driver.quit()

def send_to_api(tenders_data):
    """Send each tender individually to the API endpoint"""
    headers = {
        "Accept":"application/json",
        "Content-Type":"application/json",
        "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    success_count = 0
    error_count = 0
    
    print(f"\nSending {len(tenders_data)} tenders to API (one by one)...")
    
    for i, tender in enumerate(tenders_data, 1):
        try:
            print(f"\nSending tender {i}/{len(tenders_data)}: {tender.get('tender_no', 'N/A')}")
            
            response = requests.post(API_ENDPOINT, json=tender, headers=headers, timeout=30)
            
            if response.status_code == 200:
                print(f"✅ Tender {i} sent successfully")
                print(f"Response: {response.text}")
                success_count += 1
            else:
                print(f"❌ Tender {i} failed with status {response.status_code}")
                print(f"Response: {response.text}")
                error_count += 1
                
        except Exception as e:
            print(f"❌ Error sending tender {i}: {str(e)}")
            error_count += 1
    
    print(f"\n=== Summary ===")
    print(f"✅ Successful: {success_count}")
    print(f"❌ Errors: {error_count}")
    print(f"📊 Total: {len(tenders_data)}")

if __name__ == "__main__":
    print("Starting DEWA tender extraction...")
    extract_tender_data()
    print("Finished.")
