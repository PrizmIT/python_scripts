import os
import time
import requests
from urllib.parse import urlparse, parse_qs
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

API_ENDPOINT = "https://ms.prizm-energy.com/MS/api/tenders/insert_etimad_tenders" 
HEADLESS_BROWSER = False
STATE_FILE = "page_state.txt"

def post_json(url, data):
    headers = {
        "Accept":"application/json",
        "Content-Type":"application/json",
        "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        r = requests.post(url, json=data, headers=headers, timeout=30)
        print("📥 رد السيرفر:", r.text)
        if r.status_code == 200:
            print(f"✅ تم إدخال المناقصة {data.get('reference')} بنجاح")
        else:
            print(f"⚠️ خطأ من السيرفر {r.status_code} - {r.text}")
    except Exception as e:
        print(f"🚨 فشل إرسال {data.get('reference')} للـ API - {e}")

def setup_driver(headless: bool = HEADLESS_BROWSER):
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    if headless:
        options.add_argument("--headless")
    return webdriver.Chrome(options=options)

# دالة تجيب آخر رقم صفحة متسجل
def load_last_page():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            try:
                return int(f.read().strip())
            except:
                return 1
    return 1

# دالة تحدث رقم الصفحة في الملف
def save_last_page(page_number):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(str(page_number))

# ابدأ من آخر صفحة متسجلة أو 1
page_number = load_last_page()
while True:
    driver = setup_driver()
    wait = WebDriverWait(driver, 20)

    url = f"https://tenders.etimad.sa/Tender/AllTendersForVisitor?PageNumber={page_number}"
    print(f"📄 بيسحب الصفحة {page_number} ...")
    driver.get(url)
    try:
        cards = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, ".tender-card")))
    except:
        print("✅ مفيش كروت تانية، وقف.")
        break

    print(f"  - اتسحب {len(cards)} كارد")

    if len(cards) == 0:
        break

    for card in cards:
        try:
            ref_number = card.get_attribute("data-ref").strip()
            title = card.find_element(By.CSS_SELECTOR, "h3 a").text.strip()
            p_tag = card.find_element(By.CSS_SELECTOR, "p.pb-2")
            agency = p_tag.text.replace("التفاصيل", "").strip()
            activity = ""
            try:
                activity_label = card.find_element(By.XPATH, ".//label[contains(text(),'النشاط الأساسي')]")
                activity = activity_label.find_element(By.XPATH, "./following-sibling::span").text.strip()
            except:
                pass

            dates = card.find_elements(By.CSS_SELECTOR, ".tender-date span")
            last_enquiry = dates[1].text if len(dates) > 1 else ""
            last_offer_date = dates[2].text if len(dates) > 2 else ""

            # تاريخ النشر
            publish_date = ""
            try:
                publish_date = card.find_element(By.XPATH, ".//div[contains(text(),'تاريخ النشر')]//span").text.strip()
            except:
                pass

            # نوع المناقصة
            tender_type = ""
            try:
                tender_type = card.find_element(By.CSS_SELECTOR, ".badge.badge-primary").text.strip()
            except:
                pass

            price = card.find_element(By.CSS_SELECTOR, ".tender-coast span").text.strip()

            # رابط التفاصيل
            details_a = card.find_element(By.CSS_SELECTOR, "a.pull-right")
            details_link = details_a.get_attribute("href")

            # استخراج STenderId من الرابط
            tenderIdString = ""
            try:
                parsed = urlparse(details_link)
                qs = parse_qs(parsed.query)
                if "STenderId" in qs:
                    tenderIdString = qs["STenderId"][0]
            except Exception as e:
                print("⚠️ ماقدرتش أجيب STenderId:", e)

            # افتح التفاصيل في تبويب جديد
            driver.execute_script("window.open(arguments[0]);", details_link)
            driver.switch_to.window(driver.window_handles[-1])

            try:
                # انتظر ظهور التفاصيل
                details_wait = WebDriverWait(driver, 40)
                details_wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#basicDetials .list-group-item")))

                details = {}
                items = driver.find_elements(By.CSS_SELECTOR, "#basicDetials .list-group-item")
                for item in items:
                    try:
                        label = item.find_element(By.CSS_SELECTOR, ".etd-item-title").text.strip()
                        value = item.find_element(By.CSS_SELECTOR, ".etd-item-info span").text.strip()
                        details[label] = value
                    except:
                        continue

            except Exception as e:
                print(f"⚠️ ماقدرتش أسحب تفاصيل الكارد {ref_number} - {e}")
                details = {}

            # رجع للصفحة الأساسية
            driver.close()
            driver.switch_to.window(driver.window_handles[0])

            # خزّن البيانات
            tender_data = {
                "page": page_number,
                "reference": ref_number,
                "tenderIdString": tenderIdString,
                "title": title,
                "agency": agency,
                "activity": activity,
                "publish_date": publish_date,
                "last_enquiry": last_enquiry,
                "last_offer_date": last_offer_date,
                "tender_type": tender_type,
                "booklet_price": price,
                "details": details
            }
            post_json(API_ENDPOINT, tender_data)
            time.sleep(1)

        except Exception as e:
            print("خطأ في الكارد:", e)

    page_number += 1
    save_last_page(page_number)  # خزّن الصفحة الجاية
    driver.quit()
