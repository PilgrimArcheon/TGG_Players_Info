from flask import Flask, Response, request, render_template_string, jsonify, abort
import requests, time, pandas as pd, json, io, os

app = Flask(__name__)

# --- GLOBAL MEMORY CACHE ---
# Holds the dataframe so we don't have to fetch from PlayFab twice
DATA_CACHE = {"df": None}

# --- HTML FRONTEND ---
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>TGG Admin Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { 
            background-color: #000000; color: #ffffff; 
            font-family: 'Helvetica', sans-serif; 
            display: flex; justify-content: center; align-items: center; 
            min-height: 100vh; margin: 0; padding: 20px; box-sizing: border-box;
        }
        .container { 
            text-align: center; background: #111; padding: 40px; 
            border-radius: 12px; border: 1px solid #333; 
            max-width: 800px; width: 100%; 
        }
        h1 { color: #FFA500; letter-spacing: 2px; }
        input { 
            padding: 12px; width: 250px; border-radius: 6px; 
            border: none; margin-bottom: 20px; display: block; margin: 0 auto 20px;
        }
        button { 
            background-color: #FFA500; color: #000; border: none; 
            padding: 15px 30px; font-weight: bold; border-radius: 6px; 
            cursor: pointer; margin-top: 10px; transition: 0.2s;
        }
        button:hover { background-color: #e69500; }
        button:disabled { background-color: #555; cursor: not-allowed; color: #888; }
        #status { color: #FFA500; margin-top: 15px; display: block; font-weight: bold; }
        
        /* Dashboard Layout */
        #dashboard { display: none; margin-top: 20px; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; text-align: left; }
        .card { background: #222; padding: 20px; border-radius: 8px; text-align: center; border: 1px solid #333; }
        .stat-number { font-size: 3em; color: #FFA500; font-weight: bold; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="container">
        <img src="https://i.imgur.com/VGHlcJB.png" alt="TRIVIA Logo" style="width: 200px; margin-bottom: 20px;">
        
        <!-- LOGIN SECTION -->
        <div id="loginSection">
            <h1>ADMIN LOGIN</h1>
            <input type="password" id="tokenInput" placeholder="Enter Secret Token">
            <button id="loadBtn" onclick="loadDashboard()">ACCESS DASHBOARD →</button>
            <p id="status"></p>
        </div>

        <!-- DASHBOARD SECTION -->
        <div id="dashboard">
            <h1 style="margin-bottom: 30px;">PLAYER ANALYTICS</h1>
            
            <div class="grid">
                <div class="card">
                    <h3 style="margin-top:0; color: #ccc;">Total Valid Players</h3>
                    <div class="stat-number" id="totalPlayers">0</div>
                    <p style="color: #777; font-size: 0.9em;">(Accounts with valid emails)</p>
                </div>
                
                <div class="card">
                    <h3 style="margin-top:0; color: #ccc;">Device Breakdown</h3>
                    <div style="height: 200px; display: flex; justify-content: center;">
                        <canvas id="deviceChart"></canvas>
                    </div>
                </div>
            </div>

            <button id="exportBtn" onclick="downloadCSV()" style="width: 100%; margin-top: 30px; font-size: 1.1em;">
                DOWNLOAD CLEAN CSV DATA ↓
            </button>
        </div>
    </div>

    <script>
        let cachedToken = "";

        async function loadDashboard() {
            const token = document.getElementById('tokenInput').value;
            const status = document.getElementById('status');
            const btn = document.getElementById('loadBtn');
            
            if (!token) { status.innerText = "Please enter a token."; return; }

            btn.disabled = true;
            status.innerText = "Authenticating & Fetching PlayFab Data...\\n(This usually takes 1-2 minutes)";
            
            try {
                const response = await fetch('/load-data', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({token: token})
                });

                if (response.ok) {
                    const data = await response.json();
                    cachedToken = token;
                    
                    // Swap UI
                    document.getElementById('loginSection').style.display = 'none';
                    document.getElementById('dashboard').style.display = 'block';
                    
                    // Populate Text Data
                    document.getElementById('totalPlayers').innerText = data.total;
                    
                    // Render Chart.js
                    new Chart(document.getElementById('deviceChart'), {
                        type: 'doughnut',
                        data: { 
                            labels: ['iOS', 'Android', 'Unknown'], 
                            datasets: [{ 
                                data: [data.iOS, data.Android, data.Unknown], 
                                backgroundColor: ['#FFA500', '#4CAF50', '#555'],
                                borderWidth: 0
                            }] 
                        },
                        options: { 
                            responsive: true, 
                            maintainAspectRatio: false,
                            plugins: { legend: { position: 'right', labels: { color: '#ccc' } } } 
                        }
                    });
                } else {
                    status.innerText = "Error: " + await response.text();
                    btn.disabled = false;
                }
            } catch (e) {
                status.innerText = "Connection Error. Please try again.";
                btn.disabled = false;
            }
        }

        function downloadCSV() {
            window.location.href = `/download-csv?token=${cachedToken}`;
        }
    </script>
</body>
</html>
"""

# --- FLASK ROUTES ---

@app.route('/')
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route('/load-data', methods=['POST'])
def load_data():
    data = request.get_json()
    if not data or data.get('token') != os.environ.get("SECRET_TOKEN"):
        return "Invalid Token", 403

    TITLE_ID = "10B741"
    SEGMENT_ID = "A1DF5646512D0477"
    SECRET_KEY = os.environ.get("SECRET_KEY")
    HEADERS = {"X-SecretKey": SECRET_KEY, "Content-Type": "application/json"}

    # 1. Trigger Export
    export_res = requests.post(
        f"https://{TITLE_ID}.playfabapi.com/Admin/ExportPlayersInSegment",
        headers=HEADERS, json={"SegmentId": SEGMENT_ID}
    )
    export_id = export_res.json().get("data", {}).get("ExportId")
    if not export_id:
        return "Failed to start PlayFab export", 500

    # 2. Poll for Completion
    index_url = None
    while True:
        status_res = requests.post(
            f"https://{TITLE_ID}.playfabapi.com/Admin/GetSegmentExport",
            headers=HEADERS, json={"ExportId": export_id}
        )
        status_data = status_res.json().get("data", {})
        state = status_data.get("State")
        if state == "Complete":
            index_url = status_data.get("IndexUrl")
            break
        elif state == "Failed":
            return "Export failed on PlayFab", 500
        time.sleep(3)

    # 3. Fetch Links
    index_res = requests.get(index_url)
    tsv_links = [link for link in index_res.text.strip().split('\n') if link]

    # 4. Download & Merge
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

    # 5. Extraction Logic
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

    # 6. Format
    master_df['Sign up date'] = master_df['Created']
    master_df['Country'] = master_df['Locations_LastLogin_CountryCode']
    master_df['Username'] = master_df['ExtractedUsername']
    master_df['Email'] = master_df['ExtractedEmail']

    clean_df = master_df.dropna(subset=['Email'])
    clean_df = clean_df[clean_df['Email'] != 'null'].copy()
    clean_df['Username'] = clean_df['Username'].astype(str).str.title()

    final_export_df = clean_df[['Username', 'Sign up date', 'Email', 'Country', 'Device']]

    # 7. Save to Global Cache for immediate download later
    global DATA_CACHE
    DATA_CACHE["df"] = final_export_df

    # 8. Calculate Stats for the Dashboard
    device_counts = final_export_df['Device'].value_counts().to_dict()
    
    stats = {
        "total": len(final_export_df),
        "iOS": device_counts.get("iOS", 0),
        "Android": device_counts.get("Android", 0),
        "Unknown": device_counts.get("Unknown", 0)
    }

    return jsonify(stats)

@app.route('/download-csv', methods=['GET'])
def download_csv():
    # 1. Security Check
    token = request.args.get('token')
    if token != os.environ.get("SECRET_TOKEN"):
        abort(403)
        
    # 2. Check if data is cached
    global DATA_CACHE
    if DATA_CACHE["df"] is None:
        return "Session expired or data not loaded. Please refresh the dashboard.", 404

    # 3. Serve the cached CSV
    output = io.StringIO()
    DATA_CACHE["df"].to_csv(output, index=False)
    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=TGG_Players_Clean.csv"}
    )

if __name__ == '__main__':
    # Startup check
    if not os.environ.get("SECRET_TOKEN") or not os.environ.get("SECRET_KEY"):
        print("WARNING: Missing SECRET_TOKEN or SECRET_KEY in environment variables!")
    app.run()