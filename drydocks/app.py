from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import keyboard
import time
from selenium.webdriver.support.ui import Select
import os
import shutil
import json
import re
from requests_toolbelt.multipart.encoder import MultipartEncoder
import requests
import traceback
from selenium.common.exceptions import TimeoutException
import pandas as pd
from datetime import datetime
import sys


# Get the root directory of the script
SCRIPT_ROOT = os.path.dirname(os.path.abspath(__file__))

SHAREPOINT_DRIVE_ID = "b!SW3p4WdqFkSGfzCxKIfYMaS0oVIopQlKiu57F-BNFmUEKDwH88KHTJiDNvOE1wap"

class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for stream in self.streams:
            stream.write(data)
            stream.flush()

    def flush(self):
        for stream in self.streams:
            stream.flush()

# Define the log directory
LOG_DIR = os.path.join(SCRIPT_ROOT, "logs")

# Ensure the directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Generate log file name with today's date
today = datetime.now().strftime("%Y-%m-%d")
log_filename = os.path.join(LOG_DIR, f"log-{today}.txt")

# Open log file in append mode
log_file = open(log_filename, "a", encoding="utf-8")

# Redirect stdout and stderr
sys.stdout = Tee(sys.stdout, log_file)
sys.stderr = Tee(sys.stderr, log_file)





#api_base_url = "http://localhost/offline_prizm_321/api/tenders/"
api_base_url = "https://ms.prizm-energy.com/MS/api/tenders/"

# when we upload files we also record them in the tender_drive tables
DRIVE_SAVE_ENDPOINT = "http://localhost/prizm331/api/tenders/save_drive_data"
# this crawler always uses the Drydocks source
SOURCE = "Drydocks"


def remove_file_if_exists(file_path):
    """Remove a file if it exists, and print a message."""
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            print(f"🗑️ Temporary file deleted: {file_path}")
        except Exception as e:
            print(f"Failed to delete file {file_path}: {e}")


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



# Base URL
base_link = "https://ehpv.fa.em2.oraclecloud.com/"



# Set the download directory inside the script's root
TARGET_DOWNLOAD_DIR = os.path.join(SCRIPT_ROOT, "downloads")

TARGET_DATA_DIR = os.path.join(SCRIPT_ROOT, "data")


HISTORY_DIR = os.path.join(SCRIPT_ROOT, "history")



HISTORY_DIR_PROCESSED = os.path.join(HISTORY_DIR, "processed")








def setup_driver():
    """Configures Chrome to automatically download files to a specific folder, moving old files to history before clearing."""

    # Ensure necessary folders exist
    os.makedirs(TARGET_DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(TARGET_DATA_DIR, exist_ok=True)
    os.makedirs(HISTORY_DIR, exist_ok=True)
    os.makedirs(HISTORY_DIR_PROCESSED, exist_ok=True)
   
    print("Download path set to:", TARGET_DOWNLOAD_DIR)
    print("Data path set to:", TARGET_DATA_DIR)
    print("History path set to:", HISTORY_DIR)
    print("History PRocessed path set to:", HISTORY_DIR_PROCESSED)
    print("Log path set to:", LOG_DIR)
    
    

    def backup_and_remove_existing_files():
        today_folder = datetime.today().strftime('%Y-%m-%d')
        backup_folder = os.path.join(HISTORY_DIR, today_folder)
        os.makedirs(backup_folder, exist_ok=True)

        for filename in os.listdir(TARGET_DOWNLOAD_DIR):
            file_path = os.path.join(TARGET_DOWNLOAD_DIR, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    # Backup before deletion
                    shutil.copy2(file_path, os.path.join(backup_folder, filename))
                    os.unlink(file_path)
                    print(f"📦 Moved and removed file: {file_path}")
                elif os.path.isdir(file_path):
                    shutil.copytree(file_path, os.path.join(backup_folder, filename))
                    shutil.rmtree(file_path)
                    print(f"📦 Moved and removed folder: {file_path}")
            except Exception as e:
                print(f"⚠️ Failed to backup/delete {file_path}. Reason: {e}")

    backup_and_remove_existing_files()

    chrome_options = webdriver.ChromeOptions()
    prefs = {
        "download.default_directory": TARGET_DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_setting_values.automatic_downloads": 1
    }
    chrome_options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)

    return driver


# Setup Selenium WebDriver with custom download path
driver = setup_driver()
driver.get(base_link)

# Wait for page load
wait = WebDriverWait(driver, 15)

# Function to check the current URL
def check_url():
    return driver.current_url






def get_latest_downloaded_file(directory=TARGET_DOWNLOAD_DIR, wait_time=30):
    """Waits for the file to be fully downloaded and returns the latest file path."""
    try:
        print(f"📂 Checking directory: {directory}")  # Debugging log

        if not os.path.exists(directory):
            print(f"❌ Directory does not exist: {directory}")
            return None

        end_time = time.time() + wait_time  # Set timeout
        
        while time.time() < end_time:
            try:
                files = os.listdir(directory)  # Get list of files
                print(f"📌 Found files: {files}")  # Debugging log
                
                files = [os.path.join(directory, f) for f in files]  # Get full paths
                files = [f for f in files if os.path.isfile(f)]  # Remove folders
                
                if not files:
                    print("⚠️ No files found. Retrying...")
                    time.sleep(1)
                    continue

                latest_file = max(files, key=os.path.getctime)  # Get most recent file
                print(f"📥 Latest detected file: {latest_file}")

                # If file is still downloading, wait and retry
                if latest_file.endswith((".crdownload", ".tmp")):  
                    print("⏳ File is still downloading... Waiting...")
                    time.sleep(10)
                    continue

                print(f"✅ Successfully detected final file: {latest_file}")
                return latest_file  # Return the final downloaded file

            except Exception as e:
                print(f"⚠️ Error while fetching files: {str(e)}")
                print(traceback.format_exc())
                time.sleep(1)  # Retry after a short delay
        
        print("❌ No new file detected in downloads after waiting.")
        return None

    except Exception as e:
        print(f"🚨 Critical error in `get_latest_downloaded_file`: {str(e)}")
        print(traceback.format_exc())
        return None




# Function to click on an element and wait for the page to load
def click_and_wait(element_id, retries=3, delay=5):
    for attempt in range(retries):
        print("\n" + "=" * 50)
        print(f"🔍 Attempt {attempt + 1}: Checking for element ➝ [ ID: {element_id} ]")

        try:
            button = wait.until(EC.presence_of_element_located((By.ID, element_id)))
            button = wait.until(EC.element_to_be_clickable((By.ID, element_id)))

            button.click()
            print(f"✅ Clicked on ➝ {element_id}")
            print("⏳ Waiting for the page to load...\n")
            time.sleep(5)
            return
        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1} failed: {str(e)}")
            if attempt < retries - 1:
                print(f"🔄 Retrying in {delay} seconds...\n")
                time.sleep(delay)

    print(f"❌ Failed to click on ➝ {element_id} after {retries} attempts.\n")

def click_element_by_partial_attribute(tag_name, attribute, partial_value, retries=3, delay=5):
    for attempt in range(retries):
        print("\n" + "=" * 50)
        print(f"🔍 Attempt {attempt + 1}: Searching for <{tag_name}> where {attribute} contains '{partial_value}'...")

        try:
            element = wait.until(EC.presence_of_element_located((By.XPATH, f"//{tag_name}[contains(@{attribute}, '{partial_value}')]")))
            element = wait.until(EC.element_to_be_clickable((By.XPATH, f"//{tag_name}[contains(@{attribute}, '{partial_value}')]")))

            element.click()
            print(f"✅ Clicked on <{tag_name}> where {attribute} contains '{partial_value}'")
            print("⏳ Waiting for the page to load...\n")
            time.sleep(5)
            return
        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1} failed: {str(e)}")
            if attempt < retries - 1:
                print(f"🔄 Retrying in {delay} seconds...\n")
                time.sleep(delay)

    print(f"❌ Failed to click on <{tag_name}> where {attribute} contains '{partial_value}' after {retries} attempts.\n")

def click_link_by_text(partial_text, retries=3, delay=5):
    for attempt in range(retries):
        print("\n" + "=" * 50)
        print(f"🔍 Attempt {attempt + 1}: Searching for <a> where text contains '{partial_text}'...")

        try:
            link = wait.until(EC.presence_of_element_located((By.XPATH, f"//a[contains(text(), '{partial_text}')]")))
            link = wait.until(EC.element_to_be_clickable((By.XPATH, f"//a[contains(text(), '{partial_text}')]")))

            link.click()
            print(f"✅ Clicked on <a> where text contains '{partial_text}'")
            print("⏳ Waiting for the page to load...\n")
            time.sleep(5)
            return
        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1} failed: {str(e)}")
            if attempt < retries - 1:
                print(f"🔄 Retrying in {delay} seconds...\n")
                time.sleep(delay)

    print(f"❌ Failed to click on <a> where text contains '{partial_text}' after {retries} attempts.\n")

from selenium.webdriver.common.action_chains import ActionChains

def click_actions_dropdown(partial_text, retries=3, delay=5):
    for attempt in range(retries):
        print("\n" + "=" * 50)
        print(f"🖱️ Attempt {attempt + 1}: Clicking on the dropdown for '{partial_text}'...")

        try:
            # Locate the specific "Actions" link
            actions_link = wait.until(EC.presence_of_element_located(
                (By.XPATH, f"//td[@class='x1ig']/a[contains(text(), '{partial_text}')]")
            ))

            # Scroll into view to avoid hidden issues
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", actions_link)

            # Find the corresponding dropdown icon (using a relative XPath)
            dropdown_icon = wait.until(EC.element_to_be_clickable(
                (By.XPATH, f"//td[@class='x1ig']/a[contains(text(), '{partial_text}')]/../following-sibling::td//img")
            ))

            # Ensure the dropdown is visible before clicking
            wait.until(EC.visibility_of(dropdown_icon))

            # Use ActionChains to hover over Actions first, then click
            ActionChains(driver).move_to_element(actions_link).perform()
            ActionChains(driver).move_to_element(dropdown_icon).click().perform()

            print(f"✅ Successfully clicked the dropdown for '{partial_text}'.")
            print("⏳ Waiting for the menu to appear...\n")
            time.sleep(2)  # Allow time for the dropdown to open
            return  # Exit function on success

        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1} failed: {str(e)}")
            if attempt < retries - 1:
                print(f"🔄 Retrying in {delay} seconds...\n")
                time.sleep(delay)

    print(f"❌ Failed to click the dropdown for '{partial_text}' after multiple attempts.\n")



def click_image_by_src(partial_src, retries=3, delay=5):
    for attempt in range(retries):
        print("\n" + "=" * 50)
        print(f"🖼️ Attempt {attempt + 1}: Searching for <img> where src contains '{partial_src}'...")

        try:
            img_element = wait.until(EC.presence_of_element_located((By.XPATH, f"//img[contains(@src, '{partial_src}')]")))
            img_element = wait.until(EC.element_to_be_clickable((By.XPATH, f"//img[contains(@src, '{partial_src}')]")))

            img_element.click()
            print(f"✅ Clicked on <img> where src contains '{partial_src}'")
            print("⏳ Waiting for the page to load...\n")
            time.sleep(5)
            return
        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1} failed: {str(e)}")
            if attempt < retries - 1:
                print(f"🔄 Retrying in {delay} seconds...\n")
                time.sleep(delay)

    print(f"❌ Failed to click on <img> where src contains '{partial_src}' after {retries} attempts.\n")

def click_image(title_text):

    images = driver.find_elements(By.TAG_NAME, 'img')
    for img in images:
        title = img.get_attribute('title')
        if title and title_text in title:
            img.click()
            print(f"✅ Clicked image: {title_text}")
            return

    print(f"❌ Image not found with title: {title_text}")

def click_td_by_text(partial_text, retries=3, delay=5):
    for attempt in range(retries):
        print("\n" + "=" * 50)
        print(f"🔍 Attempt {attempt + 1}: Searching for <td> where text contains '{partial_text}'...")

        try:
            link = wait.until(EC.presence_of_element_located((By.XPATH, f"//td[contains(text(), '{partial_text}')]")))
            link = wait.until(EC.element_to_be_clickable((By.XPATH, f"//td[contains(text(), '{partial_text}')]")))

            link.click()
            print(f"✅ Clicked on <td> where text contains '{partial_text}'")
            print("⏳ Waiting for the page to load...\n")
            time.sleep(5)
            return
        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1} failed: {str(e)}")
            if attempt < retries - 1:
                print(f"🔄 Retrying in {delay} seconds...\n")
                time.sleep(delay)

    print(f"❌ Failed to click on <td> where text contains '{partial_text}' after {retries} attempts.\n")

def select_option_by_text(option_text, retries=3, delay=5):
    for attempt in range(retries):
        print("\n" + "=" * 50)
        print(f"🔍 Attempt {attempt + 1}: Selecting option '{option_text}' from a dropdown...")

        try:
            select_elements = driver.find_elements(By.TAG_NAME, "select")

            for select_element in select_elements:
                try:
                    select = Select(select_element)
                    select.select_by_visible_text(option_text)
                    print(f"✅ Successfully selected '{option_text}' from dropdown.\n")
                    time.sleep(20)
                 #   read_nested_table_data(timeout=10)
                    return
                except:
                    continue

            print(f"⚠️ Option '{option_text}' not found in any dropdown.")
        except Exception as e:
            print(f"⚠️ Attempt {attempt + 1} failed: {str(e)}")

        if attempt < retries - 1:
            print(f"🔄 Retrying in {delay} seconds...\n")
            time.sleep(delay)

    print(f"❌ Failed to select option '{option_text}' after {retries} attempts.\n")





# Get the root directory of the script
SCRIPT_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# Function to sanitize folder names (replace special characters with spaces)
def sanitize_folder_name(name):
    return re.sub(r'[^\w\s]', ' ', name).strip()





# Function to sanitize folder names (replace special characters with spaces)
def sanitize_folder_name(name):
    # Replace special characters and newlines with spaces
    sanitized_name = re.sub(r'[^\w\s]', ' ', name)  # Replace non-alphanumeric characters with spaces
    sanitized_name = sanitized_name.replace('\n', ' ')  # Replace newlines with spaces
    sanitized_name = sanitized_name.strip()  # Remove leading and trailing whitespaces
    return sanitized_name



def  download_pdf_files_from_table(timeout=30, min_xem_elements=1):
    try:
        print("\n🔍 Waiting for 'xem' containers to fully load...")
        wait = WebDriverWait(driver, timeout)
        wait.until(lambda d: len(d.find_elements(By.CLASS_NAME, "xem")) >= min_xem_elements)
        time.sleep(2)  # Ensure all tables render

        containers = driver.find_elements(By.CLASS_NAME, "xem")

       

        for container_idx, container in enumerate(containers, start=1):
            print(f"\n📦 Processing 'xem' container #{container_idx}")

            try:
                table = WebDriverWait(container, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "table"))
                )
                tbody = table.find_element(By.TAG_NAME, "tbody")
                rows = tbody.find_elements(By.TAG_NAME, "tr")

                for row_idx, row in enumerate(rows, start=1):
                    print(f"\n🔸 Row {row_idx}:")
                    xen_cells = row.find_elements(By.CLASS_NAME, "xen")

                    if not xen_cells:
                        print("    ⚠️ No 'xen' cells found in this row.")
                        continue

               
                    # Handle PDF logic
                    pdf_found = False
                    try:
                        pdf_cell = xen_cells[7]  # 8th column (index 7)
                        pdf_img = pdf_cell.find_element(By.XPATH, ".//img[@title='View PDF']")
                        if pdf_img:
                            #row_data["pdf"] = "Clicked View PDF"
                            safe_click(pdf_img,row_idx)
                            print(f"📄 Clicked on 'View PDF' image in row {row_idx}.")
                            pdf_found = True
                    except:
                        print(f"⚠️ No 'View PDF' image found in row {row_idx}.")

                    if not pdf_found:
                        try:
                            pdf_text_cell = xen_cells[8]  # 9th column (index 8)
                            pdf_text = pdf_text_cell.text.strip()
                            if pdf_text.lower().endswith(('.pdf', '.zip')):
                               # row_data["pdf"] = pdf_text
                                driver.get(pdf_text)
                                print(f"📄 Opened PDF link from column 9 in row {row_idx}.")
                                pdf_found = True
                        except:
                            print(f"⚠️ Column 9 not found or no PDF link in row {row_idx}.")

                    

                    time.sleep(2)

            except Exception as e:
                print(f"⚠️ Error processing container #{container_idx}: {e}")

        

    except Exception as e:
        print(f"❌ Failed to find or wait for 'xem' containers: {e}")










erorrlink=[]
already_processed=[]


def handle_popup(idx):
    """Check for error popups and close them if present."""
    popup_found = False  # Default: Assume no popup

    try:
        popup_selector = (By.CLASS_NAME, "AFPopupSelector")
        popup_message_selector = (By.CLASS_NAME, "x1mu")
        popup_ok_button_selector = (By.ID, "d1::msgDlg::cancel")

        # Wait for popup to appear (handle TimeoutException)
        try:
            popup = WebDriverWait(driver, 2).until(EC.presence_of_element_located(popup_selector))
            popup_found = True  # If no exception, popup exists
        except TimeoutException:
            print("✅ No popup detected.")  # Popup was not found
            popup_found = False  # Explicitly set False

        if popup_found:
            print("⚠️ Detected error popup!")

            # Check for error message
            messages = driver.find_elements(*popup_message_selector)
            for msg in messages:
                text = msg.text.strip()
                if "The file was not downloaded or was not downloaded correctly." in text:
                    print(f"🚨 Error message detected: {text}")

                    # Click the "OK" button to close the popup
                    ok_button = driver.find_element(*popup_ok_button_selector)
                    ok_button.click()
                    print("✅ Clicked 'OK' to close the popup.")

                    if idx not in erorrlink:
                        erorrlink.append(idx)

                    time.sleep(5)  # Small delay after clicking
                    driver.refresh()
                   # click_view_pdf_and_store_data()
                    #read_nested_table_data()
                    return
                    
                    # Remove the popup manually using JavaScript
                    driver.execute_script("""
                        var popup = document.querySelector('.AFPopupSelector');
                        if (popup) {
                            popup.remove();
                            console.log("🗑️ Popup manually removed from DOM.");
                        }
                    """)

                    return  # Exit function after handling popup

    except Exception as e:
        print(f"⚠️ Exception in `handle_popup`: {str(e)}")
        print(traceback.format_exc())  # Print detailed error stack trace

    # ✅ Normal processing continues if no popup was found
    if not popup_found:
        print("✅ No popup was found, proceeding normally...")
        if idx not in already_processed:
            already_processed.append(idx)

        #downloaded_file = get_latest_downloaded_file()
        #insert_data_into_db(row_data)



def safe_click(element,idx):
    """Click an element safely, handling popups before and after."""
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    driver.execute_script("arguments[0].click();", element)
    handle_popup(idx)
    





def read_nested_table_data(timeout=30, min_xem_elements=1):
    try:
        print("\n🔍 Waiting for 'xem' containers to fully load...")
        wait = WebDriverWait(driver, timeout)
        wait.until(lambda d: len(d.find_elements(By.CLASS_NAME, "xem")) >= min_xem_elements)
        time.sleep(2)  # Ensure all tables render

        containers = driver.find_elements(By.CLASS_NAME, "xem")

        if not containers:
            print("❌ No elements with class 'xem' found.")
            return

        os.makedirs(TARGET_DATA_DIR, exist_ok=True)
        json_path = os.path.join(TARGET_DATA_DIR, "data.json")

        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as json_file:
                try:
                    existing_data = json.load(json_file)
                    if not isinstance(existing_data, list):
                        existing_data = [existing_data]
                except json.JSONDecodeError:
                    existing_data = []
        else:
            existing_data = []

        for container_idx, container in enumerate(containers, start=1):
            print(f"\n📦 Processing 'xem' container #{container_idx}")

            try:
                table = WebDriverWait(container, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "table"))
                )
                tbody = table.find_element(By.TAG_NAME, "tbody")
                rows = tbody.find_elements(By.TAG_NAME, "tr")

                for row_idx, row in enumerate(rows, start=1):
                    print(f"\n🔸 Row {row_idx}:")
                    xen_cells = row.find_elements(By.CLASS_NAME, "xen")

                    if not xen_cells:
                        print("    ⚠️ No 'xen' cells found in this row.")
                        continue

                    row_data = {}
                    for col_idx, xen_cell in enumerate(xen_cells, start=1):
                        cell_text = xen_cell.text.strip()
                        row_data[str(col_idx)] = cell_text
                        print(f"    Column {col_idx} (class 'xen'): {cell_text}")

                    # Handle PDF logic
                    pdf_found = False
                    try:
                        pdf_cell = xen_cells[7]  # 8th column (index 7)
                        pdf_img = pdf_cell.find_element(By.XPATH, ".//img[@title='View PDF']")
                        if pdf_img:
                            #row_data["pdf"] = "Clicked View PDF"
                            print(f"📄 Clicked on 'View PDF' image in row {row_idx}.")
                            pdf_found = True
                    except:
                        print(f"⚠️ No 'View PDF' image found in row {row_idx}.")

                    if not pdf_found:
                        try:
                            pdf_text_cell = xen_cells[8]  # 9th column (index 8)
                            pdf_text = pdf_text_cell.text.strip()
                            if pdf_text.lower().endswith(('.pdf', '.zip')):
                               # row_data["pdf"] = pdf_text
                                driver.get(pdf_text)
                                print(f"📄 Opened PDF link from column 9 in row {row_idx}.")
                                pdf_found = True
                        except:
                            print(f"⚠️ Column 9 not found or no PDF link in row {row_idx}.")

                    if not pdf_found:
                        row_data["pdf"] = "No PDF found"
                        print(f"❌ No valid PDF found for row {row_idx}.")

                    # ✅ Duplicate check before appending
                    print(f"chekcing duplicate.")
                    is_duplicate = any(row_data == existing_row for existing_row in existing_data)

                    if is_duplicate:
                        print("⚠️ Duplicate row detected. Skipping save.")
                    else:
                        if any(value for value in row_data.values()):
                            existing_data.append(row_data)
                            print("✅ Row added to data.")
                            safe_click(pdf_img, row_idx,row_data)

                    time.sleep(2)

            except Exception as e:
                print(f"⚠️ Error processing container #{container_idx}: {e}")

        with open(json_path, "w", encoding="utf-8") as json_file:
            json.dump(existing_data, json_file, ensure_ascii=False, indent=4)
            print(f"\n✅ Data saved to {json_path}")

    except Exception as e:
        print(f"❌ Failed to find or wait for 'xem' containers: {e}")




api_endpoint = api_base_url + "add"




def insert_data_into_db(row_data):
    # json_path = os.path.join(TARGET_DATA_DIR, "data.json")
    # """Reads the last record from a JSON list and inserts data into MySQL database."""
    # try:
    #     with open(json_path, "r", encoding="utf-8") as json_file:
    #         data_list = json.load(json_file)

    #     if not isinstance(data_list, list) or not data_list:
    #         print("❌ data.json is empty or not a valid list.")
    #         return

    #     # Get the last record
    #     last_record = data_list[-1] 

    indata = {
        "TenderNumber": row_data.get("1"),
        "tenderDescription": row_data.get("2"),
        "floatingDate": row_data.get("4"),
        "closingDate": row_data.get("5"),
        "tenderType": row_data.get("3"),
        "client": "",
        "tenderActivityName": ""
    }

    # Validate required fields
    if not indata["TenderNumber"] or not indata["tenderDescription"]:
        print("❌ Missing required fields: TenderNumber or tenderDescription")
        return

    # Send data to API and pass the json_path for updating
    send_data_to_api(api_endpoint, indata)


    #except Exception as e:
    #    print(f"⚠️ General Error: {str(e)}")





def send_data_to_api(api_url, data):
    
    

    try:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }

        json_data = json.dumps(data, indent=4)
        response = requests.post(api_url, data=json_data, headers=headers)
        
        print("json_data")
        print( json_data )
        print(f"📡 Sending data to API: {api_url}")

        print("📡 API Response:")
        print(response)

        if response.ok:
            api_response = response.json()
            if  api_response['code'] == 1001 or  api_response['code'] == 1002:
                print("✅ Data successfully sent to API!", api_response)
                
                if api_response['code'] == 1001:
                    api_id = api_response["id"]
                    folder_url = api_response["folder_url"]
                    file_name = data.get("TenderNumber")
                    latest_file_path = find_latest_file_in_dir(TARGET_DOWNLOAD_DIR, data['TenderNumber'])
                    
                   
                    
                    result = upload_to_onedrive(latest_file_path, file_name, get_graph_access_token())
                    # حذف ملف PDF بعد نجاح الإرسال
                    remove_file_if_exists(latest_file_path)
                    if result and result.get('success'):
                        print("✅ File Result")
                        print(result)
                        print("✅ File uploaded to OneDrive successfully!")
                        # also save drive metadata locally
                        file_id = result.get('info', {}).get('id')
                        # try to extract the parent folder's Graph ID
                        folder_graph_id = result.get('info', {}).get('parentReference', {}).get('id')
                        payload = {
                            'source': SOURCE,
                            'tender_number': file_name,
                            'drive_id': folder_graph_id or api_id,
                            'files': [{'id': file_id, 'name': file_name}]
                        }
                        print('drive payload', payload)
                        try:
                            r = requests.post(DRIVE_SAVE_ENDPOINT, json=payload)
                            print('drive save', r.status_code, r.text)
                        except Exception as e:
                            print('drive save error', e)
                        return True
                    else:
                        return False
                else:
                    print("✅ Date updated successfully!")
                    return True
              
            else:
                print("❌ API did not return success:", api_response)
                return False
        else:
            print(f"❌ Error creating opportunity. Status code: {response.status_code}")
            print(f"❌ Response: {response.text}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"⚠️ Network error: {str(e)}")




def get_not_pushed_records(target_dir):
    """
    Reads data.json inside TARGET_DATA_DIR and returns records where key '15' exists and value is 'not_pushed'.

    Args:
        target_dir (str): Path to the directory containing data.json

    Returns:
        list: List of records (dict) that have '15' == 'not_pushed'
    """
    data_path = os.path.join(target_dir, "data.json")

    if not os.path.exists(data_path):
        print("❌ data.json not found in the target directory.")
        return []

    try:
        with open(data_path, "r", encoding="utf-8") as json_file:
            data = json.load(json_file)

        # If it's a list of records
        if isinstance(data, list):
            unpushed_records = [record for record in data if record.get("15") == "not_pushed"]
            print(f"✅ Found {len(unpushed_records)} records with '15' == 'not_pushed'.")
            return unpushed_records
        else:
            print("❌ data.json is not a list of records.")
            return []

    except Exception as e:
        print(f"⚠️ Error reading or parsing data.json: {e}")
        return []


def find_latest_file_in_dir(target_dir, filename):
    """
    Find the latest file in the directory that contains 'filename' in its name.
    
    Args:
        target_dir (str): Path to the directory where the file search will happen.
        filename (str): The part of the filename to search for.
    
    Returns:
        str or None: Path to the latest file, or None if no file is found.
    """
    try:
        # Get a list of all files in the directory containing the filename
        files = [f for f in os.listdir(target_dir) if filename in f]

        if not files:
            print(f"❌ No files found containing {filename}.")
            return None

        # Sort the files by creation time (latest file first)
        latest_file = max(files, key=lambda f: os.path.getmtime(os.path.join(target_dir, f)))
        latest_file_path = os.path.join(target_dir, latest_file)

        print(f"✅ Found latest file: {latest_file_path}")
        return latest_file_path
    except Exception as e:
        print(f"⚠️ Error searching for files: {e}")
        return None




def update_xls_with_status(file_path):
    try:
        # Try reading Excel file (xls or xlsx)
        df = pd.read_excel(file_path, engine='openpyxl' if file_path.endswith('.xlsx') else 'xlrd')

        print(f"✅ Read {len(df)} rows from Excel file.")

        # Add or update 'status' column
        df['status'] = 'successfull'

        # Overwrite the file
        df.to_excel(file_path, index=False)
        print(f"✅ Updated Excel file saved: {file_path}")

        return True
    except Exception as e:
        print(f"❌ Error reading or updating Excel file: {e}")
        return False




def update_html_disguised_as_xls(file_path, history_dir):
    try:
        df_list = pd.read_html(file_path)
        if not df_list:
            print("❌ No tables found in HTML.")
            return False

        df = df_list[0]
        print(f"✅ Read {len(df)} rows from disguised Excel file.")

        # Add status column placeholder
        df['status'] = ''

        for index, row in df.iterrows():
            print(f"\nRow {index + 1}:")
            for col_name, value in row.items():
                print(f"    {col_name}: {value}")
            print("-" * 40)

            try:
                # Map column indices to expected keys
                row_data = {
                    "1": str(row.get(0, '')).strip(),  # TenderNumber
                    "2": str(row.get(1, '')).strip(),  # tenderDescription
                    "3": str(row.get(2, '')).strip(),  # tenderType
                    "4": str(row.get(3, '')).strip(),  # floatingDate
                    "5": str(row.get(4, '')).strip(),  # closingDate
                }

                indata = {
                    "TenderNumber": row_data["2"],
                    "tenderDescription": row_data["1"],
                    "floatingDate": row_data["4"],
                    "closingDate": row_data["5"],
                    "tenderType": row_data["3"],
                    "client": "",
                    "tenderActivityName": ""
                }

                if not indata["TenderNumber"] or not indata["tenderDescription"]:
                    print(f"❌ Missing required fields, skipping row.{index + 1}")
                    #df.at[index, 'status'] = "failed"
                    continue

                success = send_data_to_api(api_endpoint, indata)
                df.at[index, 'status'] = "successfull" if success else "failed"

            except Exception as row_error:
                print(f"⚠️ Error processing row {index + 1}: {row_error}")
                df.at[index, 'status'] = "failed"

        # Save file in history folder
        os.makedirs(history_dir, exist_ok=True)
        today = datetime.today().strftime('%Y-%m-%d')
        base_name = os.path.basename(file_path).replace(".xls", ".xlsx")
        new_filename = f"{today}_processed_{base_name}"
        new_path = os.path.join(history_dir, new_filename)
        df.to_excel(new_path, index=False)

        print(f"\n✅ Processed file saved: {new_path}")
        return True

    except Exception as e:
        print(f"❌ Failed to read disguised Excel file: {e}")
        return False


def process_not_pushed_records(target_data_dir, target_download_dir):
    """
    Process records from the data.json file in TARGET_DATA_DIR and for each record where 
    '15' == 'not_pushed', find the latest file in TARGET_DOWNLOAD_DIR whose name matches 
    the value of key '2' in the record. After successful upload, update '15' to 'pushed'.
    """
    data_path = os.path.join(target_data_dir, "data.json")

    # Load all data (not just unpushed records)
    if not os.path.exists(data_path):
        print("❌ data.json not found in the target directory.")
        return

    try:
        with open(data_path, "r", encoding="utf-8") as json_file:
            data = json.load(json_file)

        if not isinstance(data, list):
            print("❌ data.json is not a list of records.")
            return

        data_updated = False

        for record in data:
            if record.get("15") == "not_pushed" and "2" in record:
                filename_part = record["2"]
                onedrive_foldername = record.get("1", "DefaultFolder")
                print(f"🔍 Searching for file related to: {filename_part}")

                latest_file_path = find_latest_file_in_dir(target_download_dir, filename_part)

                if latest_file_path:
                    result = upload_to_onedrive(latest_file_path, onedrive_foldername, get_graph_access_token())

                    if result.get("success"):  # Assuming the upload result is a dict with a 'success' key
                        print("✅ Upload successful. Updating record status...")
                        record["15"] = "pushed"
                        data_updated = True
                    else:
                        print("❌ Upload failed or returned unexpected result.")
                else:
                    print(f"❌ No file found for record with key '2': {filename_part}")

        if data_updated:
            with open(data_path, "w", encoding="utf-8") as json_file:
                json.dump(data, json_file, ensure_ascii=False, indent=2)
            print("💾 data.json updated with pushed records.")
        else:
            print("ℹ️ No records were updated.")

    except Exception as e:
        print(f"⚠️ Error processing records: {e}")
    


def upload_to_onedrive(file_path, file_name, access_token):
    print(f"\n🔄 Uploading file '{file_name}' to OneDrive...")
    print(f"File path: {file_path}")
    """
    Uploads a file to OneDrive using Microsoft Graph API.
    
    Args:
        file_path (str): Path to the file that needs to be uploaded.
        file_name (str): Name of the file.
        access_token (str): Microsoft Graph API access token.
    
    Returns:
        dict: A dictionary containing the status and any errors or success messages.
    """
    # Validate the access token
    if not access_token:
        return {'success': False, 'error': 'Failed to obtain Microsoft Graph access token.'}

    # Check if the file exists
    if not os.path.exists(file_path):
        return {'success': False, 'error': f"File does not exist at path: {file_path}"}

    # Validate the file name
    if not file_name or any(char in file_name for char in r'\/:*?"<>|'):
        return {'success': False, 'error': f"Invalid file name: {file_name}"}

    # URL encoding of the file name
    file_name_encoded = requests.utils.quote(file_name)
    extension = os.path.splitext(file_path)[1]
    print("extension = ",extension)
    # OneDrive upload URL (replace this with your actual path)
    upload_url = f"https://graph.microsoft.com/v1.0/drives/{SHAREPOINT_DRIVE_ID}/root:/Tenders/Drydocks/{file_name_encoded}/{file_name_encoded}{extension}:/content"
    print(upload_url)
    # Read the file content
    try:
        with open(file_path, 'rb') as file:
            file_content = file.read()
    except Exception as e:
        return {'success': False, 'error': f"Failed to read file contents: {str(e)}"}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "text/plain",
        #"Content-Length": str(len(file_content)),
    }

    try:
        response = requests.put(upload_url, headers=headers, data=file_content)
        if response.status_code in [200, 201]:
            info = {}
            try:
                info = response.json()
            except Exception:
                pass
            return {'success': True, 'message': 'File uploaded successfully to OneDrive.', 'info': info}
        else:
            return {
                'success': False,
                'error': 'Failed to upload file to OneDrive.',
                'http_code': response.status_code,
                'response': response.text
            }
    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': f"Request failed: {str(e)}"}



def get_active_negotiations_file(download_dir):
    """Searches for ActiveNegotiations.xls or .xlsx in the download directory."""
    for ext in ['.xls', '.xlsx']:
        file_path = os.path.join(download_dir, f"ActiveNegotiations{ext}")
        if os.path.exists(file_path):
            print(f"✅ Found file: {file_path}")
            return file_path
    print("❌ ActiveNegotiations.xls(x) not found in downloads.")
    return None



# **Login Check**
current_url = check_url()
if "AtkHomePageWelcome" in current_url or "FuseWelcome" in current_url:
    print("\n🎉 Already logged in! Current URL:", current_url, "\n")
else:
    try:
        print("\n🔑 Logging in...")
        username_input = wait.until(EC.visibility_of_element_located((By.NAME, "userid")))
        password_input = wait.until(EC.visibility_of_element_located((By.NAME, "password")))

        username_input.send_keys("info@prizm-energy.com")
        password_input.send_keys('gsTQQ3QJKY4!Mx2')

        login_button = wait.until(EC.element_to_be_clickable((By.ID, "btnActive")))
        login_button.click()

        wait.until(EC.url_changes(base_link))
        current_url = check_url()

        if "AtkHomePageWelcome" in current_url or "FuseWelcome" in current_url:
            print("\n✅ Login successful! Redirected to:", current_url, "\n")
        else:
            print("\n⚠️ Login might have failed. Current URL:", current_url, "\n")
    except Exception as e:
        print("\n❌ Error during login:", str(e), "\n")

# **Main Logic**
while True:

    current_url = check_url()

    if "AtkHomePageWelcome" in current_url:
        print("\n📌 On AtkHomePageWelcome, clicking on 'pt1:_UIShome'...\n")
        click_and_wait("pt1:_UIShome")

    elif "FuseWelcome" in current_url:
        print("\n📌 On FuseWelcome, navigating through Supplier Portal...\n")
        click_and_wait("groupNode_supplier_portal")
        click_and_wait("itemNode_supplier_portal_supplier_portal_0")
        click_link_by_text("View Active Negotiations")
        select_option_by_text("Closing in Next 7 Days")
        click_image("Export to Excel")
        download_pdf_files_from_table()
        active_file = get_active_negotiations_file(TARGET_DOWNLOAD_DIR)

        if active_file:
         update_html_disguised_as_xls(active_file,HISTORY_DIR_PROCESSED)
        else:
         print("❌ Could not process the Excel file.")


       
       # select_option_by_text("Open Invitations")
       # process_not_pushed_records(TARGET_DATA_DIR, TARGET_DOWNLOAD_DIR)
        print("\n🎯 Reached final target. No further navigation required.\n")
        driver.quit()
        break
      

    else:
        print("\n⚠️ On an unrecognized page:", current_url, "\n")
