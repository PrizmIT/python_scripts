from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
import time
import csv
import os
import requests
import re
import json

# === CONFIGURATION ===
PORTAL_URL = "https://eservice.addigital.gov.ae/OA_HTML/AppsLogin"
USERNAME = "info@prizm-energy.com"
PASSWORD = "Prizm@2025"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")

DAILY_LOG_FILE = f"ADERP_Log_{datetime.now().strftime('%Y-%m-%d')}.txt"
LOG_FILE = os.path.join(LOG_DIR, DAILY_LOG_FILE)
PROCESSED_TENDERS_FILE = os.path.join(LOG_DIR, "processed_tenders.txt")

USE_SAVED_PROFILE = False
PROFILE_DIR = "Default"
base_download_dir = os.path.join(BASE_DIR, "downloads")

# API Configuration
TENDER_API_URL = "https://ms.prizm-energy.com/MS/api/tenders/get_abudhabi_tenders"
API_TOKEN = "your_actual_api_token_here"  # Replace with real token
API_TIMEOUT = 10  # seconds

api_base_url = "https://ms.prizm-energy.com/MS/api/tenders/"

SHAREPOINT_DRIVE_ID = "b!SW3p4WdqFkSGfzCxKIfYMaS0oVIopQlKiu57F-BNFmUEKDwH88KHTJiDNvOE1wap"


def get_graph_access_token():
    api_url = api_base_url + "get_token"
    """Retrieves the access token from the API."""
    headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
    try:
        response = requests.get(api_url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                access_token = data.get("access_token")
                print("✅ Access token retrieved successfully.")
                return access_token
            else:
                print("❌ Failed to retrieve token:", data)
        else:
            print(f"❌ HTTP error: {response.status_code}")
    except Exception as e:
        print(f"⚠️ Request failed: {e}")

    return None



# === LOGGING SYSTEM ===
def init_logging():
    """Initialize logging directory and files"""
    os.makedirs(LOG_DIR, exist_ok=True)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write(f"ADERP Automation Log - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*50 + "\n\n")

def log_message(message, tender_number=None, status=None):
    """Enhanced logging that preserves all historical data"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    print(log_entry)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry + "\n")
    if tender_number and status:
        update_processed_tenders(tender_number, status)

def update_processed_tenders(tender_number, status):
    """Update processed tenders while preserving all history"""
    processed = load_processed_tenders()
    if tender_number not in processed:
        processed[tender_number] = []
    processed[tender_number].append({
        "status": status,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    with open(PROCESSED_TENDERS_FILE, "w", encoding="utf-8") as f:
        for tender, entries in processed.items():
            for entry in entries:
                f.write(f"{tender},{entry['status']},{entry['timestamp']}\n")

def load_processed_tenders():
    """Load all historical processing data"""
    processed = {}
    if os.path.exists(PROCESSED_TENDERS_FILE):
        with open(PROCESSED_TENDERS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(",")
                if len(parts) >= 3:
                    tender = parts[0]
                    if tender not in processed:
                        processed[tender] = []
                    processed[tender].append({
                        "status": parts[1],
                        "timestamp": parts[2]
                    })
    return processed

# === DRIVER SETUP ===
def setup_driver(headless=False):
    """Configure and return Chrome WebDriver using system-installed Chrome"""
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-software-rasterizer")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--disable-webgl")
    chrome_options.add_argument("--disable-webgpu")

    if headless:
        chrome_options.add_argument("--headless=new")  # For modern headless support

    return webdriver.Chrome(options=chrome_options)

# === LOGIN ===
def login_with_credentials(driver, download_dir):
    """Login with retry until valid homepage is loaded or max retries exceeded"""
    MAX_LOGIN_RETRIES = 5
    for attempt in range(MAX_LOGIN_RETRIES):
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "usernameField")))
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "passwordField")))

            driver.find_element(By.ID, "usernameField").clear()
            driver.find_element(By.ID, "usernameField").send_keys(USERNAME)
            driver.find_element(By.ID, "passwordField").clear()
            driver.find_element(By.ID, "passwordField").send_keys(PASSWORD)
            driver.execute_script("submitCredentials();")
            log_message(f"🔐 Submitted credentials, waiting for homepage (attempt {attempt + 1})")
            time.sleep(5)

            # Check if the correct homepage is loaded (not the error page)
            if "OASIMPLEHOMEPAGE" in driver.current_url:
                if "Error" not in driver.title:
                    log_message("✅ Login successful and homepage loaded.")
                    return
            log_message("⚠️ Detected error page after login, retrying...")
        except Exception as e:
            log_message(f"❌ Login failed on attempt {attempt + 1}: {e}")

        time.sleep(5)

    raise Exception("❌ Login retry limit exceeded. Failed to reach valid homepage.")


# === TENDER PARSING ===
def parse_tender_number(raw_number):
    """Parse tender numbers with various formats while preserving hyphens and commas"""
    raw_str = str(raw_number).strip()
    first_space = raw_str.find(' ')
    if first_space > 0:
        number_part = raw_str[:first_space]
    else:
        number_part = raw_str
    cleaned = re.sub(r'[^\w,-]', '', number_part)
    return cleaned

# === FILE COMPARISON ===
def get_total_cloud_file_count(driver):
    """Count total files available for download with pagination"""
    total_files = 0
    while True:
        links = driver.find_elements(By.CSS_SELECTOR, "a[id^='AttachmentTable_ATTACH_']")
        total_files += len(links)
        try:
            next_page = driver.find_element(By.XPATH, "//a[@title='Next 10']")
            if next_page.is_displayed():
                driver.execute_script("arguments[0].click();", next_page)
                time.sleep(3)
            else:
                break
        except:
            break
    return total_files

def compare_file_counts_with_pagination(driver, local_dir):
    """Compare cloud files with local downloads"""
    cloud_count = get_total_cloud_file_count(driver)
    if not os.path.exists(local_dir):
        return False
    local_files = [f for f in os.listdir(local_dir) if os.path.isfile(os.path.join(local_dir, f))]
    return len(local_files) == cloud_count

# === POPUP HANDLING ===
def handle_external_popup(driver):
    """Handle external link popups"""
    try:
        popup = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.ID, "dialogYesButton")))
        driver.execute_script("arguments[0].click();", popup)
        WebDriverWait(driver, 5).until(
            lambda d: "sharepoint" in d.current_url or "onedrive" in d.current_url
        )
        time.sleep(2)
    except:
        pass

# === NAVIGATION ===
def confirm_back_to_search(driver):
    """Confirm we're back to search results screen"""
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//table[contains(@summary, 'Search Results')]"))
        )
        return True
    except:
        return False

# === PROCESS EACH TENDER ===
def download_tender_with_pagination(driver, tender_number, index, total_count):
    """Download tender documents with pagination handling"""
    log_message(f"📥 Processing Tender: {tender_number} ({index + 1}/{total_count})", tender_number, "processing")
    start_time = time.time()

    download_dir = os.path.join(base_download_dir, tender_number)
    os.makedirs(download_dir, exist_ok=True)

    try:
        driver.execute_cdp_cmd('Page.setDownloadBehavior', {
            'behavior': 'allow',
            'downloadPath': download_dir
        })
    except WebDriverException as e:
        log_message(f"⚠️ Download setup error: {e}", tender_number, "error")

    try:
        WebDriverWait(driver, 5).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        input_field = driver.find_element(By.CSS_SELECTOR, 'input[type="text"]')
        input_field.clear()
        input_field.send_keys(tender_number)

        search_button = WebDriverWait(driver, 1).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, 'button[type="submit"], input[type="submit"]'))
        )
        search_button.click()
        time.sleep(2)

        try:
            tender_link = WebDriverWait(driver, 1).until(
                EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, tender_number))
            )
            driver.execute_script("arguments[0].click();", tender_link)
        except TimeoutException:
            log_message(f"❌ Tender {tender_number} not found.", tender_number, "not_found")
            return

        if compare_file_counts_with_pagination(driver, download_dir):
            msg = "🔄 Skipping - Tender Documents Already Exist ✅"
            log_message(msg, tender_number, "already_exists")
            return

        downloaded_count = 0
        while True:
            links = driver.find_elements(By.CSS_SELECTOR, "a[id^='AttachmentTable_ATTACH_']")
            for link in links:
                driver.execute_script("arguments[0].click();", link)
                time.sleep(1.5)
                handle_external_popup(driver)
                downloaded_count += 1
            try:
                next_page = driver.find_element(By.XPATH, "//a[@title='Next 10']")
                if next_page.is_displayed():
                    driver.execute_script("arguments[0].click();", next_page)
                    time.sleep(2)
                else:
                    break
            except:
                break

        log_message(f"✅ Downloaded {downloaded_count} file(s).", tender_number, "completed")
        access_token = get_graph_access_token()
        # ensure folder exists and get its id
        folder_id = ensure_onedrive_folder(access_token, tender_number)
        files_info = []
        for file in os.listdir(download_dir):
            file_path = os.path.join(download_dir, file)
            if os.path.isfile(file_path):
                upload_result = upload_to_onedrive(tender_number, file_path, access_token)
                if upload_result.get("success"):
                    log_message(f"☁️ Uploaded to OneDrive: {file}", tender_number, "uploaded")
                    # collect for database recording
                    files_info.append({
                        "id": upload_result.get('id'),
                        "name": file
                    })
                else:
                    log_message(f"❌ OneDrive Upload Failed: {upload_result.get('error')}", tender_number, "upload_error")
        # after all uploads, send metadata to PHP
        if folder_id and files_info:
            record_drive_data_to_php(tender_number, folder_id, files_info)
        # اضغط على تابة Lines بعد رفع الملفات
        click_lines_tab(driver)
        process_lines_tab(driver, tender_number)
    except Exception as e:
        log_message(f"⚠️ Error with tender {tender_number}: {e}", tender_number, "error")

    finally:
        try:
            springboard_btn = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.XPATH, "//div[contains(@name, 'springboardItem')]//b[text()='Negotiations']"))
            )
            driver.execute_script("arguments[0].click();", springboard_btn)
            time.sleep(3)
            #if not confirm_back_to_search(driver):
                #take_screenshot(driver, "not_back_to_search", download_dir)
        except Exception as nav_err:
            log_message(f"⚠️ Navigation error: {nav_err}", tender_number, "navigation_error")

    elapsed = time.time() - start_time
    remaining = total_count - (index + 1)
    if remaining > 0:
        eta = timedelta(seconds=int(elapsed * remaining))
        log_message(f"⏳ Estimated time remaining: {eta}")

def click_lines_tab(driver):
    """Click the 'Lines' tab after tender file download."""
    try:
        lines_tab_label = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//a[@title='Lines']/label"))
        )
        driver.execute_script("arguments[0].click();", lines_tab_label)
        log_message("✅ 'Lines' tab clicked successfully.")
    except Exception as e:
        log_message(f"⚠️ Failed to click 'Lines' tab: {e}")

def process_lines_tab(driver, tender_number):
    """Iterate rows in Lines tab, extract details for each line and send to API, including tender_number."""
    insert_url = "https://ms.prizm-energy.com/MS/api/tenders/insert_abudhabi_tenders"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "SubTabRegion.ItemsTable:Content"))
        )
        table = driver.find_element(By.ID, "SubTabRegion.ItemsTable:Content")
        trs = table.find_elements(By.XPATH, ".//tr")
        total_rows = len(trs)
        idx = 0
        while idx < total_rows:
            try:
                table = driver.find_element(By.ID, "SubTabRegion.ItemsTable:Content")
                trs = table.find_elements(By.XPATH, ".//tr")
                if idx >= len(trs):
                    break
                tr = trs[idx]
                link = None
                all_links = tr.find_elements(By.XPATH, ".//a")
                for l in all_links:
                    try:
                        if l.is_displayed() and l.is_enabled():
                            link = l
                            break
                    except Exception:
                        continue
                if not link:
                    tds = tr.find_elements(By.TAG_NAME, "td")
                    for td in tds:
                        td_links = td.find_elements(By.TAG_NAME, "a")
                        for l in td_links:
                            try:
                                if l.is_displayed() and l.is_enabled():
                                    link = l
                                    break
                            except Exception:
                                continue
                        if link:
                            break
                if not link:
                    log_message(f"⚠️ No clickable link found in row {idx+1} (checked all <a> tags)")
                    try:
                        row_text = tr.text
                        log_message(f"ℹ️ Row {idx+1} content: {row_text}")
                    except Exception:
                        pass
                    idx += 1
                    continue
                driver.execute_script("arguments[0].scrollIntoView(true);", link)
                driver.execute_script("arguments[0].click();", link)
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "ItemDetailsHeaderTL"))
                )
                details = {}
                for span_id in [
                    "LineType", "ItemNumber", "ItemRevision", "ItemDescription",
                    "CategoryName", "ShoppingCategory", "UnitOfMeasure", "ItemQuantity",
                    "ShipToAddress", "CurrencyCode", "NumberPriceDecimals", "BidStartPrice",
                    "TargetPrice", "CurrentPrice", "NeedByStartDate", "NeedByDate",
                    "PoAgreedAmount", "PoMinRelAmount"
                ]:
                    try:
                        details[span_id] = driver.find_element(By.ID, span_id).text
                    except Exception:
                        details[span_id] = ""
                details["tender_number"] = tender_number
                # log_message(f"✅ Line {idx+1} details: {details}")
                insert_data = details.copy()
                try:
                    res = requests.post(insert_url, json=insert_data, headers=headers)
                    log_message(f"➡️ Sent to API, status: {res.status_code}, response: {res.text[:200]}")
                except Exception as api_err:
                    log_message(f"❌ Failed to send to API: {api_err}")
                driver.back()
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "SubTabRegion.ItemsTable:Content"))
                )
                idx += 1
            except Exception as e:
                log_message(f"⚠️ Failed to process line {idx+1}: {e}")
                idx += 1
    except Exception as e:
        log_message(f"⚠️ Failed to process Lines tab: {e}")

# === API FUNCTIONS ===
def get_api_headers():
    """Return required headers for API requests"""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"
    return headers

def fetch_tenders_from_api():
    """Fetch tenders from API with proper error handling"""
    try:
        headers = get_api_headers()
        log_message(f"🌐 Making API request to: {TENDER_API_URL}")
        
        response = requests.get(
            TENDER_API_URL,
            headers=headers,
            timeout=API_TIMEOUT
        )
        
        log_message(f"API Response Status: {response.status_code}")
        if len(response.text) > 200:
            log_message(f"API Response Sample: {response.text[:200]}...")
        else:
            log_message(f"API Full Response: {response.text}")
        
        response.raise_for_status()
        
        try:
            api_data = response.json()
            if not api_data.get("status", False):
                raise ValueError("API returned unsuccessful status")
            return api_data.get("data", [])
            
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON response: {response.text[:200]}")

    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if hasattr(e, 'response') and e.response:
            error_msg += f" | Status: {e.response.status_code} | Response: {e.response.text[:200]}"
        log_message(f"❌ API request failed: {error_msg}")
        return None
    except Exception as e:
        log_message(f"❌ Unexpected API error: {str(e)}")
        return None

def process_tenders():
    """Process tenders from API"""
    log_message("\n" + "="*50)
    log_message(f"🚀 Starting ADERP Automation - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    api_data = fetch_tenders_from_api()
    if api_data is None:
        log_message("⚠️ Aborting due to API failure")
        return None
        
    tender_list = []
    for item in api_data:
        tender_number = parse_tender_number(item.get("tender_number", ""))
        if not tender_number:
            continue
            
        processed = load_processed_tenders()
        if tender_number in processed:
            skip_count = sum(1 for entry in processed[tender_number] 
                          if entry["status"] in ("already_exists", "not_found"))
            if skip_count >= 2:
                status = "skipped_not_found" if any(
                    "not_found" in entry["status"] for entry in processed[tender_number]
                ) else "skipped_exists"
                log_message(f"🔄 Tender {tender_number} skipped ({status.replace('_', ' ')})", 
                           tender_number, status)
                continue
                
        tender_list.append(tender_number)
    
    if not tender_list:
        log_message("ℹ️ No new tenders to process after filtering")
        return None
        
    log_message(f"📄 Found {len(tender_list)} tenders to process")
    return tender_list


# === OneDrive helpers ===

def ensure_onedrive_folder(access_token, tender_number, source="ADERP"):
    """Make sure a folder exists for the tender and return its OneDrive id."""
    if not access_token:
        return None
    drive_id = SHAREPOINT_DRIVE_ID
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    folder_path = f"Tenders/{source}/{tender_number}"
    # try to fetch existing folder metadata
    meta_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{folder_path}"
    r = requests.get(meta_url, headers=headers)
    if r.status_code == 200:
        try:
            return r.json().get('id')
        except Exception:
            return None
    # not found -> create under parent
    parent_path = f"Tenders/{source}"
    create_url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{parent_path}:/children"
    body = {
        "name": tender_number,
        "folder": {},
        "@microsoft.graph.conflictBehavior": "replace"
    }
    r2 = requests.post(create_url, headers=headers, json=body)
    if r2.status_code in (200, 201):
        try:
            return r2.json().get('id')
        except Exception:
            return None
    log_message(f"❌ Could not ensure folder, status {r2.status_code}: {r2.text}")
    return None


def record_drive_data_to_php(tender_number, folder_id, files_info, source="ADERP"):
    """Send folder/file metadata to the PHP endpoint so it can be stored."""
    url = "https://ms.prizm-energy.com/MS/api/tenders/save_drive_data"
    payload = {
        "source": source,
        "tender_number": tender_number,
        "drive_id": folder_id,
        "files": files_info
    }
    headers = {"Content-Type": "application/json"}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        log_message(f"➡️ Drive data recorded, php status {r.status_code}, resp: {r.text[:200]}")
    except Exception as e:
        log_message(f"⚠️ Failed to call PHP save_drive_data: {e}")


def upload_to_onedrive(tender_number, file_path, access_token):
    if not access_token:
        return {'success': False, 'error': 'Failed to obtain Microsoft Graph access token.'}

    if not os.path.exists(file_path):
        return {'success': False, 'error': f"File does not exist at path: {file_path}"}

    file_name = os.path.basename(file_path)
    if not file_name or any(char in file_name for char in r'\/:*?"<>|'):
        return {'success': False, 'error': f"Invalid file name: {file_name}"}

    file_name_encoded = requests.utils.quote(file_name)
    folder_path = f"Tenders/ADERP/{tender_number}"

    check_url = f"https://graph.microsoft.com/v1.0/drives/{SHAREPOINT_DRIVE_ID}/root:/{folder_path}/{file_name_encoded}"

    # Check if the file exists
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    response = requests.get(check_url, headers=headers)
    if response.status_code == 200:
        return {'success': False, 'error': f"File already exists: {file_name}"}

    # If not found, proceed with upload
    upload_url = f"https://graph.microsoft.com/v1.0/drives/{SHAREPOINT_DRIVE_ID}/root:/{folder_path}/{file_name_encoded}:/content"

    try:
        with open(file_path, 'rb') as file:
            file_content = file.read()
    except Exception as e:
        return {'success': False, 'error': f"Failed to read file contents: {str(e)}"}

    headers["Content-Type"] = "application/octet-stream"

    try:
        upload_response = requests.put(upload_url, headers=headers, data=file_content)
        if upload_response.status_code in [200, 201]:
            # capture id from response JSON if available
            try:
                info = upload_response.json()
                file_id = info.get('id')
            except Exception:
                file_id = None
            return {
                'success': True,
                'message': 'File uploaded successfully to OneDrive.',
                'id': file_id,
                'name': file_name
            }
        else:
            return {
                'success': False,
                'error': 'Failed to upload file to OneDrive.',
                'http_code': upload_response.status_code,
                'response': upload_response.text
            }
    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': f"Request failed: {str(e)}"}


def ensure_correct_homepage(driver, download_dir, max_attempts=5):
    for attempt in range(max_attempts):
        log_message(f"🔍 Checking if homepage is valid (attempt {attempt + 1})")
        try:
            # Must contain correct URL and NOT be error page
            if "OASIMPLEHOMEPAGE" in driver.current_url and "Error" not in driver.title:
                # Check for presence of 'Tenders & Auctions' icon
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//b[contains(text(), 'Tenders &')]"))
                )
                log_message("✅ Correct homepage loaded with Tenders icon.")
                return True
            else:
                log_message("⚠️ Incorrect homepage or error page.")
        except Exception as e:
            log_message(f"⚠️ Homepage validation failed: {e}")

        log_message("🔁 Retrying login...")
        driver.get(PORTAL_URL)
        login_with_credentials(driver, download_dir)
        time.sleep(3)

    log_message("❌ Failed to reach correct homepage after multiple attempts.")
    return False


def click_tenders_icon_with_retry(driver, retries=5, delay=3):
    for attempt in range(retries):
        try:
            tenders_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//b[contains(text(), 'Tenders &')]"))
            )
            driver.execute_script("arguments[0].click();", tenders_button)
            log_message(f"✅ 'Tenders & Auctions' clicked on attempt {attempt + 1}")
            return
        except Exception as e:
            log_message(f"⚠️ Attempt {attempt + 1} to click 'Tenders & Auctions' failed: {e}")
            time.sleep(delay)
    raise Exception("❌ Failed to click 'Tenders & Auctions' after multiple attempts.")

# === MAIN EXECUTION ===
def main(tender_list):
    """Main execution with persistent logging"""
    try:
        driver = setup_driver(headless=False)
        log_message("🌐 Opening portal...")
        MAX_RETRIES = 10
        for attempt in range(MAX_RETRIES):
            try:
                log_message(f"🔄 Attempting to open login page (try {attempt+1})")
                driver.get(PORTAL_URL)
                WebDriverWait(driver, 15).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "usernameField"))
                )
                log_message("✅ Login page loaded successfully")
                break
            except Exception as e:
                log_message(f"⚠️ Login page failed to load: {e}")
                time.sleep(5)
        else:
            log_message("❌ Failed to load login page after multiple attempts")
            driver.quit()
            return


        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        login_dir = os.path.join(base_download_dir, "login")
        os.makedirs(login_dir, exist_ok=True)

        if "login" in driver.current_url.lower():
            log_message("🔐 Logging in...")
            login_with_credentials(driver, login_dir)

        click_tenders_icon_with_retry(driver)
        log_message("📂 Tenders section opened.")

        for index, tender_number in enumerate(tender_list):
            try:
                download_tender_with_pagination(driver, tender_number, index, len(tender_list))
            except Exception as e:
                log_message(f"❌ Skipped tender {tender_number}: {e}", tender_number, "skipped")
                continue

    except Exception as e:
        log_message(f"❌ General failure: {e}")
    finally:
        try:
            driver.quit()
        except:
            pass
        log_message("🎯 Processing complete!")

if __name__ == "__main__":
    init_logging()
    tenders = process_tenders()
    if tenders:
        main(tenders)
