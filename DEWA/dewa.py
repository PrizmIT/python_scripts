import os
import time
import requests
import base64
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

API_ENDPOINT = "https://ms.prizm-energy.com/MS/api/tenders/DEWAFetch"

buffers_dir = os.path.join(os.path.dirname(__file__), "buffers")
os.makedirs(buffers_dir, exist_ok=True)

chrome_options = Options()
prefs = {
    "download.default_directory": buffers_dir,
    "download.prompt_for_download": False,
    "download.directory_upgrade": True,
    "safebrowsing.enabled": True
}
chrome_options.add_experimental_option("prefs", prefs)
""" chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage") """

driver = webdriver.Chrome(options=chrome_options)


url = "https://www.dewa.gov.ae/en/supplier/services/procurement-rfx"
driver.get(url)

WebDriverWait(driver, 30).until(
    EC.presence_of_element_located((By.CLASS_NAME, "m23-table__content-table"))
)

table = driver.find_element(By.CLASS_NAME, "m23-table__content-table")
tbody = table.find_element(By.TAG_NAME, "tbody")

rows = tbody.find_elements(By.TAG_NAME, "tr")

def convert_date(date_str):
    import re
    months = {
        'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04', 'May': '05', 'Jun': '06',
        'Jul': '07', 'Aug': '08', 'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
    }
    match = re.match(r"(\d{2})-(\w{3})-(\d{4})", date_str.strip())
    if match:
        day, mon, year = match.groups()
        return f"{year}-{months.get(mon, '01')}-{day}"
    return date_str

def encode_file(filepath):
    if os.path.exists(filepath):
        with open(filepath, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return None

tenders_batch = []

for row in rows:
    cells = row.find_elements(By.TAG_NAME, "td")
    rfx_no = cells[0].text.split("\n")[0]
    rfx_desc = cells[1].text
    floating_date = convert_date(cells[2].text)
    closing_date = convert_date(cells[3].text)
    filename = f"{rfx_no}.pdf"
    file_path = os.path.join(buffers_dir, filename)

    try:
        link_tag = cells[0].find_element(By.TAG_NAME, "a")
        ActionChains(driver).move_to_element(link_tag).click(link_tag).perform()
        print(f"Clicked download link for file: {rfx_no}")
        time.sleep(3)
    except Exception as e:
        print(f"Failed to click download link for file {rfx_no}: {e}")

    file_b64 = encode_file(file_path)
    tender = {
        "rfx_no": rfx_no,
        "rfx_desc": rfx_desc,
        "floating_date": floating_date,
        "closing_date": closing_date,
        "filename": filename,
        "file": file_b64
    }
    tenders_batch.append(tender)

headers = {"Accept":"application/json","Content-Type":"application/json","User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
if tenders_batch:
    payload = {"tenders": tenders_batch}
    response = requests.post(API_ENDPOINT, json=payload, headers=headers)
    print(f"API Bulk Response: {response.text}")

driver.quit()
print("Finished scraping and downloading all files.")
