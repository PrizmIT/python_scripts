import requests
from datetime import datetime

# API to fetch tenders
fetch_url = "https://www.adgpg.gov.ae/SCAPI/ADGEs/AlMaqtaa/Tender/List"
fetch_headers = {"Content-Type": "application/json"}

# Your PHP backend API endpoint
insert_url = "https://ms.prizm-energy.com/MS/api/tenders/insert_abudhabi_tenders"  

payload = {
    "status": "OPEN",
    "offset": 0,
    "limit": 200,
    "Category": "",
    "Entity": "",
    "Sorting": "LAST_CREATED",
    "DueDate": "",
    "Name": ""
}

response = requests.post(fetch_url, json=payload, headers=fetch_headers)
response.raise_for_status()
data = response.json()
tenders = data.get("TenderList", [])

# Loop through each tender
for tender in tenders:
    closing_date = None

    if tender.get("DueDate"):
        closing_date = datetime.fromisoformat(tender["DueDate"].replace("Z", "")).strftime("%Y-%m-%d")

    detail_url = f"https://www.adgpg.gov.ae/SCAPI/ADGEs/AlMaqtaa/Tender/Details//{tender.get('TenderID')}"
    detail_res = requests.get(detail_url)
        
    if detail_res.ok:
        detail_data = detail_res.json()
        bidding_open_date = detail_data.get("TenderDetails", {}).get("BiddingOpenDate")
        if bidding_open_date:
            floating_date = datetime.fromisoformat(bidding_open_date.replace("Z", "")).strftime("%Y-%m-%d")

    insert_data = {
        "tender_number": tender.get("TenderNumber"),
        "tenderId": tender.get("TenderID"),
        "tenderIdString": tender.get("entityId"),
        "tender_description": tender.get("TenderName"),
        "tenderStatusName": tender.get("TenderDetails"),
        "closing_date": closing_date,
        "floating_date": floating_date,
        "source": "AbuDhabi",
        "client": tender.get("EntityName"),
        "come_from": "AbuDhabi",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    # POST to PHP backend

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    res = requests.post(insert_url, json=insert_data, headers=headers)

    if res.status_code == 200:
        print(f"✅ Pass tender {tender['TenderNumber']} to API")
    else:
        print(f"❌ Failed to insert tender {tender['TenderNumber']}: {res.status_code} - {res.text}")
