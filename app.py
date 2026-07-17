from flask import Flask, Response, request, render_template_string, jsonify
import requests, time, pandas as pd, json, io, os

app = Flask(__name__)

DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<body>
    <h1>TGG Player Export</h1>
    <input type="password" id="tokenInput" placeholder="Enter Secret Token">
    <button id="exportBtn" onclick="startExport()">Start Export</button>
    <p>Status: <span id="status">Waiting for input...</span></p>

    <script>
        async function startExport() {
            const token = document.getElementById('tokenInput').value;
            const status = document.getElementById('status');
            const btn = document.getElementById('exportBtn');
            
            btn.disabled = true;
            status.innerText = "Processing... this can take a minute.";
            
            try {
                const response = await fetch('/generate-export', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({token: token})
                });

                if (response.ok) {
                    const blob = await response.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = "TGG_Players_Info.csv";
                    a.click();
                    status.innerText = "Success! Download started.";
                } else {
                    status.innerText = "Error: " + await response.text();
                }
            } catch (e) {
                status.innerText = "Connection Error.";
            }
            btn.disabled = false;
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(DASHBOARD_HTML)

# Pull secrets securely from Environment Variables
SECRET_TOKEN = os.environ.get("SECRET_TOKEN")
SECRET_KEY = os.environ.get("SECRET_KEY")

# Safety check: Ensure the variables actually exist in the environment
if not SECRET_TOKEN or not SECRET_KEY:
    print("WARNING: Missing SECRET_TOKEN or SECRET_KEY in environment variables!")

# PLAYFAB CONFIG
TITLE_ID = "10B741"
SEGMENT_ID = "A1DF5646512D0477"
HEADERS = {"X-SecretKey": SECRET_KEY, "Content-Type": "application/json"}

@app.route('/generate-export', methods=['POST']) 
def generate_export():
    # 1. Security Check
    data = request.get_json() 
    if not data or data.get('token') != os.environ.get("SECRET_TOKEN"):
        return "Invalid Token", 403
        
    # 2. Trigger Export
    export_res = requests.post(
        f"https://{TITLE_ID}.playfabapi.com/Admin/ExportPlayersInSegment",
        headers=HEADERS, json={"SegmentId": SEGMENT_ID}
    )
    export_id = export_res.json().get("data", {}).get("ExportId")
    if not export_id:
        return "Failed to start PlayFab export", 500

    # 3. Poll for Completion
    index_url = None
    while True:
        status_res = requests.post(
            f"https://{TITLE_ID}.playfabapi.com/Admin/GetSegmentExport",
            headers=HEADERS, json={"ExportId": export_id}
        )
        data = status_res.json().get("data", {})
        state = data.get("State")
        if state == "Complete":
            index_url = data.get("IndexUrl")
            break
        elif state == "Failed":
            return "Export failed on PlayFab", 500
        time.sleep(3)

    # 4. Fetch Links
    index_res = requests.get(index_url)
    tsv_links = [link for link in index_res.text.strip().split('\n') if link]

    # 5. Download & Merge
    dataframes = []
    for link in tsv_links:
        try:
            df = pd.read_csv(link, sep='\t', dtype=str)
            if not df.empty:
                dataframes.append(df)
        except:
            pass
    
    if not dataframes:
        return "No data found", 404

    master_df = pd.concat(dataframes, ignore_index=True)

    # 6. Extraction Logic
    def extract_player_details(row):
        username, email, device = None, None, "Unknown"
        raw = row.get('LinkedAccounts')
        if pd.notna(raw) and raw != '[]':
            try:
                clean_str = str(raw).strip('"').replace('""', '"')
                linked_accs = json.loads(clean_str)
                for entry in linked_accs:
                    if not isinstance(entry, dict): continue
                    plat = entry.get("Platform")
                    if plat == "PlayFab":
                        username = entry.get("Username")
                        email = entry.get("Email")
                    elif plat in ["IOSDevice", "GameCenter"]:
                        device = "iOS"
                    elif plat in ["AndroidDevice", "GooglePlay"]:
                        device = "Android"
            except:
                pass
        return pd.Series([username, email, device])

    master_df[['ExtractedUsername', 'ExtractedEmail', 'Device']] = master_df.apply(extract_player_details, axis=1)

    # 7. Format
    master_df['Sign up date'] = master_df['Created']
    master_df['Country'] = master_df['Locations_LastLogin_CountryCode']
    master_df['Username'] = master_df['ExtractedUsername']
    master_df['Email'] = master_df['ExtractedEmail']

    clean_df = master_df.dropna(subset=['Email'])
    clean_df = clean_df[clean_df['Email'] != 'null'].copy()
    clean_df['Username'] = clean_df['Username'].astype(str).str.title()

    final_export_df = clean_df[['Username', 'Sign up date', 'Email', 'Country', 'Device']]

    # 8. Return directly as a downloadable CSV via memory
    output = io.StringIO()
    final_export_df.to_csv(output, index=False)
    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=TGG_Players_Info.csv"}
    )

if __name__ == '__main__':
    app.run()