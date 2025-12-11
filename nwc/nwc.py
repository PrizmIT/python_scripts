from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import re
import requests
from datetime import datetime

# ================== CONFIG ==================
API_ENDPOINT = "https://ms.prizm-energy.com/MS/api/tenders/insert_nwc_tenders"  # يرسل فقط البيانات الأساسية
DETAILS_API = "https://ms.prizm-energy.com/MS/api/tenders/insert_nwc_details"     # يرسل التفاصيل الإضافية
HEADLESS_BROWSER = False
DELAY_BETWEEN_REQUESTS = 1.0
# ============================================

def setup_driver(headless: bool = HEADLESS_BROWSER):
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    if headless:
        options.add_argument("--headless")
    return webdriver.Chrome(options=options)

def get_value_by_title(driver, title: str) -> str:
    """Extract value that follows a <span> title inside the active tab."""
    try:
        elem = driver.find_element(By.XPATH, f"//span[contains(text(), '{title}')]/following-sibling::span")
        return elem.text.strip()
    except:
        return ""

def format_date_arabic(date_str: str) -> str:
    """Convert Arabic/dual‑format date strings to YYYY-MM-DD HH:MM:SS"""
    try:
        if re.search(r"\d{2}/\d{2}/\d{4}", date_str):
            date_part, time_part = date_str.split()
            d, m, y = date_part.split("/")
            hh, mm = time_part.split(":")
            if "م" in date_str and int(hh) < 12:
                hh = int(hh) + 12
            return f"{y}-{m}-{d} {int(hh):02}:{mm}:00"

        months = {"يناير":"01","فبراير":"02","مارس":"03","أبريل":"04","مايو":"05","يونيو":"06","يوليو":"07","أغسطس":"08","سبتمبر":"09","أكتوبر":"10","نوفمبر":"11","ديسمبر":"12"}
        m = re.search(r"(\d{1,2})\s+(\S+)\s+(\d{4}).*?(\d{1,2}):(\d{2})\s*(ص|م)", date_str)
        if m:
            d, mon_ar, y, hh, mm, ap = m.groups()
            mon = months.get(mon_ar, "01")
            hh = int(hh)
            if ap == "م" and hh < 12:
                hh += 12
            if ap == "ص" and hh == 12:
                hh = 0
            return f"{y}-{mon}-{int(d):02d} {hh:02}:{mm}:00"
        return ""
    except:
        return ""

def extract_tender_details(driver):
    """Scrape one tender page and split into basic + extra payloads"""
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "TenderBasicInfoTab")))
    tender_title = driver.find_element(By.CSS_SELECTOR, "strong.pageTitlecontet").text.strip()

    # -------- BASIC FIELDS (always visible) --------
    basic = {
        "tender_number": get_value_by_title(driver, "رقم المنافسة"),
        "tender_description": tender_title,
        "closing_date": format_date_arabic(get_value_by_title(driver, "آخر موعد لاستلام العروض")),
        "floating_date": format_date_arabic(get_value_by_title(driver, "تاريخ النشر")),
        "source": "NWC",
        "client": "NWC",
        "come_from": "NWC",
        "fees":  get_value_by_title(driver, "قيمة مستندات المنافسة"),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # extra fields that live ALSO in basic tab
    extra = {
        "duration": get_value_by_title(driver, "مدة تنفيذ المشروع"),
        "submission_place": get_value_by_title(driver, "مقر استلام العروض"),
        "contractor_name": "",
        "award_value": ""
    }

    # -------- SWITCH TO DESCRIPTION TAB --------
    try:
        desc_tab = driver.find_element(By.CSS_SELECTOR, "a[data-bs-target='#TenderDescTab']")
        driver.execute_script("arguments[0].click();", desc_tab)
        time.sleep(0.8)
    except:
        pass

    # description text
    desc_blocks = driver.find_elements(By.CSS_SELECTOR, "#TenderDescTab .desc")
    description = "\n".join([blk.text.strip() for blk in desc_blocks if blk.text.strip()])
    extra["description"] = description

    # contractor & award value reside ONLY here
    m1 = re.search(r"اسم المقاول[:\s\u061f]*([^\n]+)", description)
    if m1:
        extra["contractor_name"] = m1.group(1).strip()
    m2 = re.search(r"قيمة العقد عند الترسية[:\s\u061f]*([^\n]+)", description)
    if m2:
        extra["award_value"] = m2.group(1).strip()

    return basic, extra

def post_json(url, data):
    headers = {"Accept":"application/json","Content-Type":"application/json","User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    return requests.post(url, json=data, headers=headers, timeout=30)

def push_to_api(basic, extra):
    try:
        res = post_json(API_ENDPOINT, basic)
        if res.ok:
            tid = res.json().get("tender_id")
            print("✅", basic["tender_number"], res.json().get("status"))
            if tid:
                extra_payload = {"tender_id": tid, **extra}
                dres = post_json(DETAILS_API, extra_payload)
                print("   ↪ details", "added" if dres.ok else f"err {dres.status_code}")
        else:
            print("❌ main api", res.status_code)
    except Exception as e:
        print("❌ exception", e)
    time.sleep(DELAY_BETWEEN_REQUESTS)

""" def click_next_page(driver):
    try:
        nxt = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "ctl00_ctl40_g_2fc4981b_524c_424a_b4dd_209866ac44e2_ctl00_PagingControl_lbNext")))
        if "disabled" in nxt.get_attribute("class"):
            return False
        driver.execute_script("arguments[0].click();", nxt)
        return True
    except:
        return False """
        
def click_next_page(driver):
    try:
        next_btn = driver.find_element(By.ID, "ctl00_ctl40_g_2fc4981b_524c_424a_b4dd_209866ac44e2_ctl00_PagingControl_lbNext")
        class_attr = next_btn.get_attribute("class")
        
        if "aspNetDisabled" in class_attr:
            print("🚫 انتهينا: لا مزيد من الصفحات.")
            return False

        driver.execute_script("arguments[0].click();", next_btn)
        time.sleep(2)
        return True

    except Exception as e:
        print("⚠️ Pagination error:", e)
        return False


def main():
    driver = setup_driver()
    url = "https://www.nwc.com.sa/AR/BusinessSector/VendorsRelationships/Tenders/Pages/default.aspx"
    page = 1
    try:
        driver.get(url)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='RFQ']")))
        while True:
            print(f"📄 صفحة {page}")
            links = [a.get_attribute("href") for a in driver.find_elements(By.CSS_SELECTOR, "a[href*='RFQ']")]
            for link in links:
                driver.execute_script("window.open(arguments[0], '_blank');", link)
                driver.switch_to.window(driver.window_handles[-1])
                time.sleep(1)
                try:
                    basic, extra = extract_tender_details(driver)
                    push_to_api(basic, extra)
                except Exception as e:
                    print("❌ scrape error:", e)
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
            if not click_next_page(driver):
                break
            page += 1
            time.sleep(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
