import os
import time
import requests
import json
import re

from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup


API_ENDPOINT = "https://ms.prizm-energy.com/MS/api/tenders/DEWAFetchAnnouncedTenders"

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
    all_tenders = []
    
    try:
        url = "https://www.dewa.gov.ae/en/supplier/services/tender-opening-results"
        print(f"Navigating to: {url}")
        driver.get(url)
        
        # Wait for the table to load
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".m23-table__content-table-body"))
        )
        
        time.sleep(5)
        
        # Extract tender rows from the main table
        tender_rows = driver.find_elements(By.CSS_SELECTOR, ".m23-table__content-table-row")
        print(f"Found {len(tender_rows)} tender rows")
        
        # Process each tender row
        for i, row in enumerate(tender_rows):
            try:
                # Check if this row contains a tender link (skip header rows or empty rows)
                tender_link_elements = row.find_elements(By.CSS_SELECTOR, "a.link")
                if not tender_link_elements:
                    print(f"Skipping row {i+1} - no tender link found (likely header or empty row)")
                    continue
                    
                # Extract tender link
                tender_link_element = tender_link_elements[0]
                tender_link = tender_link_element.get_attribute("href")
                tender_no = tender_link_element.text.strip()
                
                if not tender_no:
                    print(f"Skipping row {i+1} - empty tender number")
                    continue
                
                print(f"\nProcessing tender {i+1}/{len(tender_rows)}: {tender_no}")
                
                # Extract basic info from the row
                cells = row.find_elements(By.CSS_SELECTOR, ".m23-table__content-table-cell")
                if len(cells) >= 5:
                    sl_no = cells[0].text.strip()
                    
                    # Extract name of tenderer with error handling
                    try:
                        name_tenderer_p = cells[2].find_elements(By.TAG_NAME, "p")
                        name_tenderer = name_tenderer_p[0].text.strip() if name_tenderer_p else cells[2].text.strip()
                    except:
                        name_tenderer = cells[2].text.strip()
                    
                    # Extract tender type with error handling
                    try:
                        tender_type_element = cells[2].find_elements(By.TAG_NAME, "strong")
                        tender_type = tender_type_element[0].text.strip() if tender_type_element else ""
                    except:
                        tender_type = ""
                    
                    floating_date = cells[3].text.strip()
                    closing_date = cells[4].text.strip()
                    
                    # Skip if essential data is missing
                    if not name_tenderer or not floating_date or not closing_date:
                        print(f"Skipping row {i+1} - missing essential data")
                        continue
                    
                    # Validate and fix the tender link if needed
                    if not tender_link.startswith('http'):
                        if tender_link.startswith('/'):
                            tender_link = f"https://www.dewa.gov.ae{tender_link}"
                        else:
                            print(f"Invalid tender link: {tender_link}")
                            continue
                    
                    # Click the tender link to get detailed info
                    print(f"Clicking on tender link: {tender_link}")
                    driver.execute_script("window.open(arguments[0], '_blank');", tender_link)
                    driver.switch_to.window(driver.window_handles[-1])
                    
                    # Wait for the detail page to load
                    WebDriverWait(driver, 30).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, ".tender-result"))
                    )
                    
                    time.sleep(3)
                    
                    # Extract detailed tender information
                    print(f"🔍 Extracting details for: {tender_no}")
                    tender_detail = extract_tender_details(driver, tender_no, name_tenderer, 
                                                         floating_date, closing_date, tender_type)
                    
                    if tender_detail:
                        all_tenders.append(tender_detail)
                        print(f"✅ Successfully extracted tender {tender_no} with {len(tender_detail.get('offers', []))} offers")
                        
                        # Send this tender to API immediately
                        print(f"📤 Sending tender {tender_no} to API...")
                        send_single_tender_to_api(tender_detail)
                        
                    else:
                        print(f"❌ Failed to extract data for tender {tender_no}")
                    
                    # Close the detail tab and switch back to main tab
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                    
                    # Add small delay between requests
                    time.sleep(2)
                    
            except Exception as e:
                print(f"❌ Error processing tender row {i+1}: {str(e)}")
                # Make sure we're back on the main tab
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                continue
        
        print(f"\n" + "="*60)
        print(f"🎉 EXTRACTION COMPLETE")
        print(f"="*60)
        print(f"Total tenders extracted: {len(all_tenders)}")
        
        # Print summary of each tender
        total_offers = 0
        for tender in all_tenders:
            offers_count = len(tender.get('offers', []))
            total_offers += offers_count
            print(f"  📊 {tender['tender_no']}: {offers_count} offers")
        
        print(f"\n📈 SUMMARY:")
        print(f"  Total Tenders: {len(all_tenders)}")
        print(f"  Total Offers: {total_offers}")
        print(f"  Average Offers per Tender: {total_offers/len(all_tenders):.1f}" if all_tenders else "  No tenders found")
        print(f"="*60)
        
        # All tenders have been sent individually, just return the summary
        print(f"🎯 All tenders have been processed and sent to API individually!")
        
        return all_tenders
        
    except Exception as e:
        print(f"Error extracting tender data: {str(e)}")
        return []
        
    finally:
        driver.quit()

def extract_tender_details(driver, tender_no, name_tenderer, floating_date, closing_date, tender_type):
    """Extract detailed tender information and all offers from the detail page"""
    try:
        tender_data = {
            "tender_no": tender_no,
            "name_tenderer": name_tenderer,
            "floating_date": convert_date_format(floating_date),
            "closing_date": convert_date_format(closing_date),
            "tender_type": tender_type,
            "offers": []
        }
        
        # Extract main tender details from the first tender-result div
        main_details = driver.find_elements(By.CSS_SELECTOR, ".tender-result")[0]
        detail_items = main_details.find_elements(By.CSS_SELECTOR, "dl.tender-result__details dt, dl.tender-result__details dd")
        
        # Process the detail items in pairs (dt, dd)
        for i in range(0, len(detail_items), 2):
            if i + 1 < len(detail_items):
                key = detail_items[i].text.strip()
                value = detail_items[i + 1].text.strip()
                
                if key == "Tender No":
                    tender_data["tender_no"] = value
                elif key == "Name of Tenderer":
                    tender_data["name_tenderer"] = value
                elif key == "Floating Date":
                    tender_data["floating_date"] = convert_date_format(value)
                elif key == "Closing Date":
                    tender_data["closing_date"] = convert_date_format(value)
                elif key == "Tender Type":
                    tender_data["tender_type"] = value
        
                # Extract all offers
        offer_sections = driver.find_elements(By.CSS_SELECTOR, ".tender-result")[1:]  # Skip the first one (main details)
        
        print(f"\n📋 Tender Details:")
        print(f"   Tender No: {tender_data['tender_no']}")
        print(f"   Name: {tender_data['name_tenderer']}")
        print(f"   Type: {tender_data['tender_type']}")
        print(f"   Floating Date: {tender_data['floating_date']}")
        print(f"   Closing Date: {tender_data['closing_date']}")
        print(f"   Found {len(offer_sections)} offers to extract...")
        
        for idx, offer_section in enumerate(offer_sections, 1):
            try:
                offer_data = {}
                
                # Extract offer number from the title
                title_element = offer_section.find_element(By.CSS_SELECTOR, "h2.tender-result__title")
                offer_data["offer_no"] = title_element.text.strip()
                
                print(f"\n   💼 {offer_data['offer_no']}:")
                
                # Extract offer details
                detail_lists = offer_section.find_elements(By.CSS_SELECTOR, "dl.tender-result__details")
                
                for detail_list in detail_lists:
                    items = detail_list.find_elements(By.CSS_SELECTOR, "dt, dd")
                    
                    i = 0
                    while i < len(items):
                        if items[i].tag_name.lower() == 'dt':
                            key = items[i].text.strip()
                            
                            # Collect all consecutive dd elements after this dt
                            dd_elements = []
                            j = i + 1
                            while j < len(items) and items[j].tag_name.lower() == 'dd':
                                dd_elements.append(items[j])
                                j += 1
                            
                            # Process based on the key
                            if key == "Name of the Tenderer" and dd_elements:
                                value = dd_elements[0].text.strip()
                                offer_data["tenderer_name"] = value
                                print(f"      👤 Tenderer: {value}")
                            elif "Total Price" in key and "Currency" in key and dd_elements:
                                # Handle multiple dd elements for price (including different currencies)
                                
                                # Extract prices from all dd elements
                                aed_amount = 0
                                foreign_currency_data = None
                                
                                for price_elem in dd_elements:
                                    price_text = price_elem.text.strip()
                                    if price_text and price_text not in [',', '']:
                                        # Check if this is AED (has dirham symbol)
                                        dirham_span = price_elem.find_elements(By.CSS_SELECTOR, "span.dirham-symbol")
                                        if dirham_span:
                                            # This is AED amount - get text without the span
                                            aed_text = price_elem.get_attribute('textContent').replace('D', '').strip()
                                            aed_numeric = re.sub(r'[^\d.,]', '', aed_text)
                                            if aed_numeric:
                                                try:
                                                    if ',' in aed_numeric and '.' in aed_numeric:
                                                        aed_numeric = aed_numeric.replace(',', '')
                                                    elif ',' in aed_numeric:
                                                        parts = aed_numeric.split(',')
                                                        if len(parts[-1]) == 3:
                                                            aed_numeric = aed_numeric.replace(',', '')
                                                    aed_amount = float(aed_numeric)
                                                except ValueError:
                                                    aed_amount = 0
                                        else:
                                            # This might be foreign currency with exchange rate
                                            if price_text.startswith(','):
                                                price_text = price_text[1:].strip()  # Remove leading comma
                                            
                                            # Look for pattern like "1,314,100.00 EUR ( 4.29400 )"
                                            currency_pattern = r'([\d,]+\.?\d*)\s*([A-Z]{3})\s*\(\s*([\d.]+)\s*\)'
                                            match = re.search(currency_pattern, price_text)
                                            
                                            if match:
                                                amount_str = match.group(1)
                                                currency = match.group(2)
                                                exchange_rate = float(match.group(3))
                                                
                                                # Clean the amount
                                                amount_str = amount_str.replace(',', '')
                                                try:
                                                    foreign_amount = float(amount_str)
                                                    foreign_currency_data = {
                                                        'amount': foreign_amount,
                                                        'currency': currency,
                                                        'exchange_rate': exchange_rate,
                                                        'aed_equivalent': foreign_amount * exchange_rate
                                                    }
                                                except ValueError:
                                                    continue
                                
                                # Determine final price
                                final_price = None
                                final_currency = 'AED'
                                price_details = []
                                
                                if aed_amount > 0:
                                    # Use AED amount if it's greater than 0
                                    final_price = aed_amount
                                    price_details.append(f"{aed_amount} AED")
                                elif foreign_currency_data:
                                    # Convert foreign currency to AED using exchange rate
                                    final_price = foreign_currency_data['aed_equivalent']
                                    price_details.append(f"{foreign_currency_data['amount']} {foreign_currency_data['currency']} × {foreign_currency_data['exchange_rate']} = {final_price} AED")
                                
                                # Add foreign currency info if both exist
                                if aed_amount > 0 and foreign_currency_data:
                                    price_details.append(f"{foreign_currency_data['amount']} {foreign_currency_data['currency']} (rate: {foreign_currency_data['exchange_rate']})")
                                
                                offer_data["total_price"] = final_price
                                offer_data["price_currency"] = final_currency
                                
                                if foreign_currency_data:
                                    offer_data["original_currency"] = foreign_currency_data['currency']
                                    offer_data["original_amount"] = foreign_currency_data['amount']
                                    offer_data["exchange_rate"] = foreign_currency_data['exchange_rate']
                                
                                print(f"      💰 Price: {' | '.join(price_details)}")
                            elif key == "Delivery or Completion" and dd_elements:
                                value = dd_elements[0].text.strip()
                                offer_data["delivery_completion"] = value
                                print(f"      📅 Delivery: {value if value else 'N/A'}")
                            elif "Bank Guarante" in key and dd_elements:
                                value = dd_elements[0].text.strip()
                                offer_data["bank_guarantee"] = value
                                print(f"      🏦 Bank Guarantee: {value}")
                            elif key == "Remarks" and dd_elements:
                                value = dd_elements[0].text.strip()
                                offer_data["remarks"] = value
                                print(f"      📝 Remarks: {value}")
                            elif dd_elements:
                                # Print any unmatched key-value pairs for debugging
                                value = dd_elements[0].text.strip()
                                print(f"      🔍 Unknown field '{key}': {value}")
                            
                            # Move to next dt element
                            i = j
                        else:
                            i += 1
                
                tender_data["offers"].append(offer_data)
                
            except Exception as e:
                print(f"      ❌ Error extracting offer {idx}: {str(e)}")
                continue
        
        print(f"\n✅ Successfully extracted {len(tender_data['offers'])} offers for tender {tender_no}")
        print("=" * 80)
        return tender_data    
    except Exception as e:
        print(f"Error extracting tender details: {str(e)}")
        return None

def send_single_tender_to_api(tender_data):
    """Send a single tender to the API endpoint"""
    headers = {
        "Accept":"application/json",
        "Content-Type":"application/json",
        "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        tender_no = tender_data.get('tender_no', 'N/A')
        offers_count = len(tender_data.get('offers', []))
        
        print(f"   📡 Sending to API: {tender_no} ({offers_count} offers)")
        
        response = requests.post(API_ENDPOINT, json=tender_data, headers=headers, timeout=30)
        
        if response.status_code == 200:
            print(f"   ✅ Successfully sent to API")
            print(f"   📄 Response: {response.text}")
            return True
        else:
            print(f"   ❌ API request failed with status {response.status_code}")
            print(f"   📄 Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error sending to API: {str(e)}")
        return False

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
            tender_no = tender.get('tender_no', 'N/A')
            offers_count = len(tender.get('offers', []))
            print(f"\n📤 Sending tender {i}/{len(tenders_data)}: {tender_no} ({offers_count} offers)")
            
            response = requests.post(API_ENDPOINT, json=tender, headers=headers, timeout=30)
            
            if response.status_code == 200:
                print(f"✅ Tender {tender_no} sent successfully")
                print(f"Response: {response.text}")
                success_count += 1
            else:
                print(f"❌ Tender {tender_no} failed with status {response.status_code}")
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
    tenders_data = extract_tender_data()
    print(f"Finished. Extracted {len(tenders_data)} tenders total.")
