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
import base64

API_ENDPOINT = "https://ms.prizm-energy.com/MS/api/tenders/DEWAFetchTenders"
buffers_dir = os.path.join(os.path.dirname(__file__), "documents")
os.makedirs(buffers_dir, exist_ok=True)

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

def download_pdf_and_get_path(driver, pdf_link_element, tender_no):
    """Download PDF and return the file path"""
    try:
        # احصل على قائمة الملفات قبل التحميل
        files_before = set(os.listdir(buffers_dir))
        
        # اضغط على اللينك لتحميل الملف
        pdf_link_element.click()
        
        # انتظر حتى يظهر ملف جديد
        max_wait_time = 10
        start_time = time.time()
        downloaded_file = None
        
        while time.time() - start_time < max_wait_time:
            time.sleep(1)
            files_after = set(os.listdir(buffers_dir))
            new_files = files_after - files_before
            
            # ابحث عن ملف PDF جديد
            pdf_files = [f for f in new_files if f.lower().endswith('.pdf')]
            if pdf_files:
                downloaded_file = pdf_files[0]
                break
        
        if downloaded_file:
            file_path = os.path.join(buffers_dir, downloaded_file)
            print(f"✅ PDF downloaded: {downloaded_file}")
            return file_path
        else:
            print("⚠️ PDF download failed or timeout")
            return None
            
    except Exception as e:
        print(f"❌ Error downloading PDF: {str(e)}")
        return None

def send_tender_with_pdf_to_api(tender_data, pdf_path=None):
    """Send tender data + PDF as base64 inside JSON to API (matches PHP endpoint)"""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    payload = tender_data.copy()

    # لو في ملف PDF، ضيفه Base64
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        payload["file"] = encoded
        payload["filename"] = os.path.basename(pdf_path)
    else:
        payload["file"] = None
        payload["filename"] = None

    try:
        response = requests.post(API_ENDPOINT, json=payload, headers=headers, timeout=30)
        return response
    except Exception as e:
        print(f"❌ Error sending to API: {str(e)}")
        return None
        
        
def extract_tender_data():
    # Setup Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")

    prefs = {
        "download.default_directory": buffers_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True
    }
    chrome_options.add_experimental_option("prefs", prefs)
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
            
            # جزء تحميل الـ PDF المعدل
            try:
                pdf_link_element = driver.find_element(
                    By.XPATH,
                    f"//a[@class='link DisplayPDF' and @data-tender='{tender_data.get('tender_no', '')}']"
                )
                if pdf_link_element:
                    # حمل الـ PDF واحصل على مساره
                    pdf_path = download_pdf_and_get_path(driver, pdf_link_element, tender_data.get('tender_no'))
                    
                    if pdf_path:
                        tender_data['advertisement_pdf'] = pdf_path
                        tender_data['pdf_file_path'] = pdf_path  # حفظ المسار للإرسال
                        print(f"📄 PDF ready for upload: {pdf_path}")
                    else:
                        tender_data['advertisement_pdf'] = None
                        tender_data['pdf_file_path'] = None
                        print("⚠️ No PDF downloaded")

            except Exception as e:
                print(f"⚠️ No PDF or error occurred for tender {tender_data.get('tender_no')}: {str(e)}")
                tender_data['advertisement_pdf'] = None
                tender_data['pdf_file_path'] = None
            
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
                if key != 'pdf_file_path':  # لا تطبع مسار الملف في اللوج
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
    """Send each tender with PDF to the API endpoint"""
    success_count = 0
    error_count = 0
    
    print(f"\nSending {len(tenders_data)} tenders to API with PDFs...")
    
    for i, tender in enumerate(tenders_data, 1):
        try:
            print(f"\nSending tender {i}/{len(tenders_data)}: {tender.get('tender_no', 'N/A')}")
            
            pdf_path = tender.get('pdf_file_path')
            response = send_tender_with_pdf_to_api(tender, pdf_path)
            
            if response and response.status_code == 200:
                print(f"✅ Tender {i} sent successfully")
                success_count += 1
                
                # احذف الملف المؤقت بعد الإرسال الناجح
                if pdf_path and os.path.exists(pdf_path):
                    os.remove(pdf_path)
                    print(f"🗑️ Temporary file deleted: {pdf_path}")
                    
            else:
                status_code = response.status_code if response else "No response"
                print(f"❌ Tender {i} failed with status {status_code}")
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