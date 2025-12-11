import os
import time
from datetime import datetime
from typing import Tuple, List, Dict

import requests, json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import sys


"""
سكربت سيلينيوم لجمع بيانات تندرات eSupply **مع تنزيل كل ملفات PDF** في مجلد
`downloads/` بجوار السكربت وإعادة تسميتها لتطابق `project_code`.
"""

# ================= مسارات ثابتة =================
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DOWNLOAD_DIR  = os.path.join(BASE_DIR, "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ================= إعدادات عامة =================
HEADLESS_BROWSER = False
URL          = "https://esupply.dubai.gov.ae/esupply/web/index.html"
WAIT         = 25
DL_WAIT      = 3
RESUME_FILE  = os.path.join(BASE_DIR, "resume.txt")
API_ENDPOINT = "https://ms.prizm-energy.com/MS/api/tenders/insert_esupply"
HEADERS      = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

# ================= تهيئة المتصفح =================

def setup_driver(headless: bool = HEADLESS_BROWSER) -> webdriver.Chrome:
    prefs = {
        "download.default_directory": DOWNLOAD_DIR,
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,
    }
    opts = Options()
    opts.add_experimental_option("prefs", prefs)
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    if headless:
        opts.add_argument("--headless=new")
    return webdriver.Chrome(options=opts)

# ================= استئناف =================

def save_resume(page: int, idx: int) -> None:
    with open(RESUME_FILE, "w", encoding="utf-8") as f:
        f.write(f"{page},{idx}")

def load_resume() -> Tuple[int, int]:
    if os.path.exists(RESUME_FILE):
        try:
            page, idx = tuple(map(int, open(RESUME_FILE).read().strip().split(",")))
            if idx >= 100:
                return page + 1, 0
            return page, idx
        except Exception:
            pass
    return 1, 0

# ================= وظائف مساعدة =================

def open_results_page(driver: webdriver.Chrome, page: int = 1) -> None:
    driver.get(URL)
    WebDriverWait(driver, WAIT).until(
        EC.element_to_be_clickable((By.XPATH, "//a[contains(.,'Search now!')]"))
    ).click()

    WebDriverWait(driver, WAIT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "a.detailLink"))
    )

    # اضغط على رأس عمود Publication Date بعد ظهور النتائج
    try:
        pub_date_th = driver.find_element(By.XPATH, "//th[a[contains(text(),'Publication Date')]]/a")
        driver.execute_script("arguments[0].click();", pub_date_th)
        WebDriverWait(driver, WAIT).until(
            lambda d: 'js-sorting' in d.find_element(By.XPATH, "//th[a[contains(text(),'Publication Date')]]").get_attribute('class')
        )
        time.sleep(1)
        # اضغط مرة ثانية للترتيب التنازلي
        driver.execute_script("arguments[0].click();", pub_date_th)
        WebDriverWait(driver, WAIT).until(
            lambda d: 'sort-desc' in d.find_element(By.XPATH, "//th[a[contains(text(),'Publication Date')]]").get_attribute('class')
        )
        time.sleep(5)
    except Exception:
        pass

    # بعد الترتيب اضغط على projectTitle
    header = driver.find_element(By.XPATH, "//a[contains(@onclick,'projectTitle')]")
    driver.execute_script("arguments[0].click();", header)
    WebDriverWait(driver, WAIT).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "a.detailLink"))
    )

    # انتقل للصفحة المطلوبة إذا page > 1
    if page > 1:
        current_page = 1
        for _ in range(1, page+1):
            try:
                # تحقق من الصفحة النشطة
                active = driver.find_element(By.XPATH, "//button[contains(@class,'PaginationButton') and contains(@class,'active')]/span").text.strip()
                if active == str(page):
                    break
                # إذا زر الصفحة المطلوبة ظاهر، اضغطه
                btns = driver.find_elements(By.XPATH, f"//button[contains(@class,'PaginationButton') and span[text()='{page}']]")
                if btns:
                    driver.execute_script("arguments[0].click();", btns[0])
                else:
                    # اضغط زر التالي
                    nav = driver.find_element(By.XPATH, "//div[contains(@class,'pagination-navigation')]")
                    nxt = nav.find_element(By.XPATH, ".//button[contains(@title,'Forward')]")
                    driver.execute_script("arguments[0].click();", nxt)
                # انتظر حتى تتغير الصفحة النشطة
                WebDriverWait(driver, WAIT).until(
                    lambda d: d.find_element(By.XPATH, "//button[contains(@class,'PaginationButton') and contains(@class,'active')]/span").text.strip() == str(page)
                )
                break
            except Exception:
                time.sleep(1)
                continue

def click_next_page(driver: webdriver.Chrome) -> bool:
    try:
        nav = driver.find_element(By.XPATH, "//div[contains(@class,'pagination-navigation')]")
        nxt = nav.find_element(By.XPATH, ".//button[contains(@title,'Forward')]")
        if nxt.get_attribute("disabled") or (nxt.get_attribute("aria-disabled") or "").lower() == "true":
            return False
        before = len(driver.find_elements(By.CSS_SELECTOR, "a.detailLink"))
        driver.execute_script("arguments[0].click();", nxt)
        WebDriverWait(driver, WAIT).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "a.detailLink")) != before)
        return True
    except Exception:
        return False

def collect_tender_urls(driver: webdriver.Chrome) -> List[str]:
    return driver.execute_script(
        """
        return Array.from(document.querySelectorAll('a.detailLink')).map(a=>{
            const oc=a.getAttribute('onclick')||'';
            if(oc.includes('goToDetail')){
                const id=oc.split("goToDetail('")[1].split("'")[0];
                return `https://esupply.dubai.gov.ae/esop/toolkit/opportunity/current/${id}/detail.si`;
            }
            return a.href;
        });
        """
    )

# ================= تنزيل PDF =================

def wait_new_file(before: set, timeout: int = 20) -> str | None:
    dead = time.time() + timeout
    while time.time() < dead:
        diff = [f for f in os.listdir(DOWNLOAD_DIR) if f not in before and not f.endswith(".crdownload")]
        if diff:
            return diff[0]
        time.sleep(1)
    return None

def download_and_rename(driver: webdriver.Chrome, file_base: str) -> None:
    xpath = "//input[@type='button' and contains(@onclick,'downloadSummaryZoomed') and contains(@value,'Download')]"
    try:
        # معالجة تكرار .pdf في اسم الملف
        base_name = file_base
        if base_name.lower().endswith('.pdf.pdf'):
            base_name = base_name[:-4]
        elif base_name.lower().endswith('.pdf'):
            base_name = base_name
        else:
            base_name = base_name + '.pdf'
        # ابحث عن أي ملف مطابق (tender_xxxxx.pdf أو tender_xxxxx_1.pdf ...)
        name_no_ext = base_name[:-4] if base_name.lower().endswith('.pdf') else base_name
        found = False
        for fname in os.listdir(DOWNLOAD_DIR):
            if fname.lower().endswith('.pdf') and (fname == base_name or fname.startswith(f"{name_no_ext}_")):
                found = True
                print(f"⚠️ الملف {fname} موجود بالفعل في downloads، لن يتم تنزيله أو إعادة تسميته.")
                break
        if found:
            return
        # ...تابع التنزيل والتسمية إذا لم يوجد أي ملف مطابق...
        btn = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, xpath)))
        before = set(os.listdir(DOWNLOAD_DIR))
        driver.execute_script("arguments[0].click();", btn)
        # انتظر حتى يظهر ملف جديد مكتمل التحميل (ليس .crdownload)
        newf = None
        timeout = time.time() + 30
        while time.time() < timeout:
            files_now = set(os.listdir(DOWNLOAD_DIR)) - before
            pdfs = [f for f in files_now if f.lower().endswith('.pdf')]
            # تأكد أنه لا يوجد ملف crdownload
            crdownloads = [f for f in files_now if f.endswith('.crdownload')]
            if pdfs and not crdownloads:
                newf = pdfs[0]
                break
            time.sleep(1)
        if not newf:
            return
        src = os.path.join(DOWNLOAD_DIR, newf)
        # إعادة التسمية إذا لزم الأمر
        base = os.path.join(DOWNLOAD_DIR, base_name)
        i = 1
        target = base
        while os.path.exists(target):
            target = os.path.join(DOWNLOAD_DIR, f"{name_no_ext}_{i}.pdf")
            i += 1
        if os.path.abspath(src) != os.path.abspath(target):
            os.rename(src, target)
    except Exception:
        pass

# ================= استخراج البيانات =================

def parse_date(raw: str) -> str:
    raw = raw.strip()
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return raw

def extract_detail_data(driver: webdriver.Chrome) -> Dict:
    def ans(label: str):
        try:
            return driver.find_element(By.XPATH, f"//div[contains(@class,'form_question_label') and normalize-space(text())='{label}']/ancestor::li//div[contains(@class,'form_answer')]").text.strip()
        except Exception:
            return ""

    code  = ans("Project Code") or "unknown"
    title = ans("Project Title")

    # تحميل PDF الرئيسي إن وُجد
    download_and_rename(driver, code)

    # تحميل ملفات Lots
    try:
        for b in driver.find_elements(By.XPATH, "//button[contains(@onclick,'openPopUpFullScreen')]"):
            driver.execute_script("arguments[0].click();", b)
            WebDriverWait(driver, 15).until(lambda d: len(d.window_handles) > 1)
            driver.switch_to.window(driver.window_handles[-1])
            download_and_rename(driver, f"{code}")
            driver.close()
            driver.switch_to.window(driver.window_handles[0])
    except Exception:
        pass

    # رفع ملفات التندر إلى الأوندرايف في مجلد باسم التندر داخل esupply
    def upload_file_to_esupply_onedrive(file_path, tender_number, access_token):
        import requests
        file_name = os.path.basename(file_path)
        tender_folder = requests.utils.quote(tender_number)
        file_name_encoded = requests.utils.quote(file_name)
        # استخدم اسم الملف كما هو بدون إضافة extension مرة أخرى
        upload_url = (
            f"https://graph.microsoft.com/v1.0/drives/b!tTBPC_-czEqXfkJlctO4vGqZyw9Xn4JJowY-M42VuNpv_VU8ao7gRZxmtOD7507w"
            f"/root:/Documents/Etimad/esupply/{tender_folder}/{file_name_encoded}:/content"
        )
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/octet-stream",
        }
        # تحقق هل الملف موجود بالفعل على الأوندرايف بنفس الاسم
        check_url = (
            f"https://graph.microsoft.com/v1.0/drives/b!tTBPC_-czEqXfkJlctO4vGqZyw9Xn4JJowY-M42VuNpv_VU8ao7gRZxmtOD7507w"
            f"/root:/Documents/Etimad/esupply/{tender_folder}/{file_name_encoded}"
        )
        check_headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        check_resp = requests.get(check_url, headers=check_headers)
        if check_resp.status_code == 200:
            print(f"⚠️ الملف {file_name} موجود بالفعل على الأوندرايف، لن يتم رفعه مرة أخرى.")
            return False
        with open(file_path, "rb") as f:
            file_content = f.read()
        response = requests.put(upload_url, headers=headers, data=file_content)
        if response.status_code in [200, 201]:
            print(f"✅ Uploaded {file_name} to {tender_number} folder.")
            return True
        else:
            print(f"❌ Failed to upload {file_name}: {response.text}")
            return False

    def get_graph_access_token():
      
        headers = {"Accept":"application/json","Content-Type":"application/json","User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"}
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

    try:
        access_token = get_graph_access_token()
        if not access_token:
            print("❌ لم يتم جلب access token من الـ API، لن يتم رفع الملفات.")
        else:
            for fname in os.listdir(DOWNLOAD_DIR):
                if fname.startswith(code) and fname.lower().endswith('.pdf'):
                    fpath = os.path.join(DOWNLOAD_DIR, fname)
                    upload_file_to_esupply_onedrive(fpath, code, access_token)
    except Exception as e:
        print(f"❌ رفع ملفات التندر إلى الأوندرايف فشل: {e}")

    lots: List[Dict] = []
    try:
        tbl = driver.find_element(By.XPATH, "//table[caption[contains(text(),'Published Lots')]]")
        for r in tbl.find_elements(By.XPATH, ".//tr[td]"):
            tds = r.find_elements(By.TAG_NAME, "td")
            if len(tds) >= 4:
                lots.append({
                    "type": tds[0].text.strip(),
                    "code": tds[1].text.strip(),
                    "title": tds[2].text.strip(),
                    "closing_date": parse_date(tds[3].text.strip()),
                })
    except Exception:
        pass

    return {
        "project_code": code,
        "project_title": title,
        "description": ans("Description"),
        "notes": ans("Notes"),
        "supply_category": ans("Supply Category"),
        "response_currency": ans("Response Currency"),
        "publication_date": parse_date(ans("Opportunity Publication Date")),
        "closing_date":     parse_date(ans("Closing date/time")),
        "buyer_organisation": ans("Buyer Organisation"),
        "contact": ans("Contact"),
        "email": ans("Email"),
        "published_lots": lots,
    }

# ================= البرنامج الرئيسي =================

def main():

    page, start = load_resume()
    drv = setup_driver()
    tenders_batch = []
    try:
        open_results_page(drv, page)

        while True:
            urls = collect_tender_urls(drv)
            # إذا لم يوجد تندرات في الصفحة أو start أكبر من عددها، انتقل للصفحة التالية حتى تجد صفحة بها تندرات أو تنتهي الصفحات
            while start >= len(urls):
                if not click_next_page(drv):
                    print("انتهت جميع الصفحات. لا يوجد المزيد.")
                    break
                page += 1
                save_resume(page, 0)
                start = 0
                urls = collect_tender_urls(drv)

            for idx in range(start, len(urls)):
                try:
                    drv.get(urls[idx])
                    WebDriverWait(drv, WAIT).until(EC.presence_of_element_located((By.ID, "opportunityDetailFEBean")))
                    tender = extract_detail_data(drv)
                    tenders_batch.append(tender)
                    save_resume(page, idx+1)
                except Exception as ee:
                    print("⚠️", ee)
                    drv.quit(); drv = setup_driver(); open_results_page(drv, page)
                    continue
            # أرسل دفعة التندرات بعد كل صفحة
            if tenders_batch:
                try:
                    resp = requests.post(API_ENDPOINT, headers=HEADERS, json={"tenders": tenders_batch}, timeout=120)
                    print("API bulk response:", resp.text)
                except Exception as rr:
                    print("API bulk error", rr)
                tenders_batch = []
            if page == 4:
                print("✅ تم إنهاء الصفحة الرابعة. سيتم إعادة resume.txt إلى 1,0 والخروج.")
                save_resume(1, 0)
                drv.quit()
                sys.exit(0)
            start = 0
            if not click_next_page(drv):
                print("انتهت جميع الصفحات. لا يوجد المزيد.")
                break
            page += 1
            save_resume(page, 0)
    finally:
        drv.quit()

if __name__ == "__main__":
    main()
