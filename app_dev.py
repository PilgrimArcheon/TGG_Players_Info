import requests
import time
import pandas as pd
import json
import io
import ast

# ==========================================
# 1. PLAYFAB CONFIGURATION
# ==========================================
TITLE_ID = "10B741"
SECRET_KEY = "1E3WUM5H8YYQQZFXKRF3STHN1Q4SZ5IWNACC7BCGK3IM49RFFB"
SEGMENT_ID = "A1DF5646512D0477"

HEADERS = {
    "X-SecretKey": SECRET_KEY,
    "Content-Type": "application/json"
}

# ==========================================
# 2. TRIGGER EXPORT & GET LINKS
# ==========================================
print("1. Triggering PlayFab Segment Export...")
export_res = requests.post(
    f"https://{TITLE_ID}.playfabapi.com/Admin/ExportPlayersInSegment",
    headers=HEADERS,
    json={"SegmentId": SEGMENT_ID}
)
export_id = export_res.json().get("data", {}).get("ExportId")

if not export_id:
    print("Error triggering export:", export_res.text)
    exit()

print(f"   Export initiated (ID: {export_id}). Waiting for PlayFab to build shards...")

# Poll PlayFab until the background task finishes
index_url = None
while True:
    status_res = requests.post(
        f"https://{TITLE_ID}.playfabapi.com/Admin/GetSegmentExport",
        headers=HEADERS,
        json={"ExportId": export_id}
    )
    data = status_res.json().get("data", {})
    state = data.get("State")
    
    if state == "Complete":
        index_url = data.get("IndexUrl")
        print("   Export complete!")
        break
    elif state == "Failed":
        print("   Export failed on PlayFab's end.")
        exit()
        
    time.sleep(5) # Wait 5 seconds before checking again to avoid rate limits

# Download the exportcomplete.txt file and extract the shard links
print("2. Fetching TSV Shard links...")
index_res = requests.get(index_url)
# The text file contains one URL per line
tsv_links = [link for link in index_res.text.strip().split('\n') if link]

# ==========================================
# 3. DOWNLOAD & PARSE DATA
# ==========================================
print(f"3. Downloading and merging {len(tsv_links)} PlayFab data shards...")

dataframes = []
for i, link in enumerate(tsv_links):
    try:
        df = pd.read_csv(link, sep='\t', dtype=str)
        if not df.empty:
            dataframes.append(df)
    except Exception as e:
        print(f"   Failed to process shard {i}: {e}")

if not dataframes:
    print("No data extracted from shards.")
    exit()

master_df = pd.concat(dataframes, ignore_index=True)

# ==========================================
# 4. LINE-BY-LINE EXTRACTION LOGIC
# ==========================================
def extract_player_details(row):
    username = None
    email = None
    device = "Unknown"
    
    linked_acc_raw = row['LinkedAccounts']
    
    if pd.notna(linked_acc_raw) and linked_acc_raw != '[]':
        try:
            clean_str = str(linked_acc_raw).strip('"').replace('""', '"')
            linked_accs = json.loads(clean_str)
            
            for entry in linked_accs:
                if not isinstance(entry, dict):
                    continue
                    
                plat = entry.get("Platform")
                # Extract Email and Username from PlayFab Platform specifically
                if plat == "PlayFab":
                    username = entry.get("Username")
                    email = entry.get("Email")
                # Detect mobile platform logins
                elif plat == "IOSDevice" or plat == "GameCenter":
                    device = "iOS"
                elif plat == "AndroidDevice" or plat == "GooglePlay":
                    device = "Android"
        except:
            pass
            
    return pd.Series([username, email, device])

print("4. Processing accounts and extracting specific fields...")
master_df[['ExtractedUsername', 'ExtractedEmail', 'Device']] = master_df.apply(extract_player_details, axis=1)

# ==========================================
# 5. FORMATTING & FINAL EXPORT
# ==========================================
print("5. Formatting final dataset...")

# Map the raw columns to your required clean headers
master_df['Sign up date'] = master_df['Created']
master_df['Country'] = master_df['Locations_LastLogin_CountryCode']
master_df['Username'] = master_df['ExtractedUsername']
master_df['Email'] = master_df['ExtractedEmail']

# Filter exclusively for valid emails (drop nulls)[cite: 1]
clean_df = master_df.dropna(subset=['Email'])
clean_df = clean_df[clean_df['Email'] != 'null']

# Enforce title-case capitalization on exported names[cite: 1]
clean_df = clean_df.copy()
clean_df['Username'] = clean_df['Username'].astype(str).str.title()

# Reorder and isolate only the required columns
final_export_df = clean_df[['Username', 'Sign up date', 'Email', 'Country', 'Device']]

# Save to CSV
final_export_df.to_csv("TGG_Players_Info.csv", index=False)
print(f"\nSUCCESS! {len(final_export_df)} fully formatted players saved to TGG_Players_Info_Final.csv")