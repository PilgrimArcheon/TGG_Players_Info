from flask import Flask, Response, request, render_template_string, jsonify, abort
import requests, time, pandas as pd, json, io, os

app = Flask(__name__)

# --- GLOBAL MEMORY CACHE ---
DATA_CACHE = {"df": None}

# --- HTML FRONTEND ---
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>TGG Admin Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg-color: #151521;
            --card-bg: #1e1e2d;
            --accent: #FFA500;
            --text-main: #ffffff;
            --text-muted: #a1a1b5;
            --border: #2b2b40;
        }
        body { 
            background-color: var(--bg-color); color: var(--text-main); 
            font-family: 'Helvetica', sans-serif; margin: 0; 
            min-height: 100vh; box-sizing: border-box;
        }
        
        /* LOGIN SCREEN (Matches your exact layout) */
        #loginSection {
            display: flex; justify-content: center; align-items: center; height: 100vh;
        }
        .container { 
            text-align: center; background: var(--card-bg); padding: 40px; 
            border-radius: 12px; border: 1px solid var(--border); 
            max-width: 400px; width: 100%; 
        }
        input { 
            padding: 12px; width: 80%; border-radius: 6px; 
            border: none; margin-bottom: 20px; display: block; margin: 0 auto 20px;
            background: #151521; color: white; border: 1px solid var(--border);
        }
        button { 
            background-color: var(--accent); color: #000; border: none; 
            padding: 15px 30px; font-weight: bold; border-radius: 6px; 
            cursor: pointer; margin-top: 10px; transition: 0.2s; width: 100%;
        }
        button:hover { background-color: #e69500; }
        button:disabled { background-color: #555; cursor: not-allowed; color: #888; }
        #status { color: var(--accent); margin-top: 15px; display: block; font-weight: bold; }
        
        /* DASHBOARD LAYOUT */
        #dashboard { display: none; padding: 30px; max-width: 1400px; margin: auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
        .header img { width: 120px; }
        .top-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }
        .card { background: var(--card-bg); padding: 20px; border-radius: 12px; border: 1px solid var(--border); }
        .card h3 { color: var(--text-muted); font-size: 0.9em; margin-top: 0; text-transform: uppercase; letter-spacing: 1px;}
        .card .value { font-size: 2.2em; font-weight: bold; margin: 10px 0; }
        
        .charts-grid { display: grid; grid-template-columns: 1fr 2fr; gap: 20px; margin-bottom: 30px; }
        .chart-container { position: relative; height: 300px; width: 100%; }
        
        /* TABLE STYLES */
        table { width: 100%; border-collapse: collapse; text-align: left; }
        th { color: var(--text-muted); padding: 15px; border-bottom: 1px solid var(--border); font-size: 0.9em; text-transform: uppercase; }
        td { padding: 15px; border-bottom: 1px solid var(--border); }
        .status-badge { background: rgba(76, 175, 80, 0.2); color: #4CAF50; padding: 5px 10px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }
    </style>
</head>
<body>

    <!-- LOGIN SCREEN -->
    <div id="loginSection">
        <div class="container">
            <img src="https://i.imgur.com/VGHlcJB.png" alt="TRIVIA Logo" style="width: 200px; margin-bottom: 20px;">
            <input type="password" id="tokenInput" placeholder="Enter Secret Token">
            <button id="exportBtn" onclick="startExport()">ACCESS ADMIN BOARD →</button>
            <p id="status">Waiting for input...</p>
        </div>
    </div>

    <!-- MAIN DASHBOARD -->
    <div id="dashboard">
        <div class="header">
            <div>
                <img src="https://i.imgur.com/VGHlcJB.png" alt="TRIVIA Logo">
                <h2 style="margin: 5px 0 0 0;">Admin Overview</h2>
            </div>
            <button onclick="downloadCSV()" style="width: auto; padding: 12px 25px;">
                ↓ DOWNLOAD CSV DATA
            </button>
        </div>

        <!-- STAT CARDS -->
        <div class="top-cards">
            <div class="card">
                <h3>Total Players</h3>
                <div class="value" id="valTotal">0</div>
            </div>
            <div class="card">
                <h3>Valid Players (Email)</h3>
                <div class="value" id="valValid" style="color: #4CAF50;">0</div>
            </div>
            <div class="card">
                <h3>Guest Players</h3>
                <div class="value" id="valGuest" style="color: var(--accent);">0</div>
            </div>
            <div class="card">
                <h3>Top Country</h3>
                <div class="value" id="valCountry">--</div>
            </div>
        </div>

        <!-- CHARTS -->
        <div class="charts-grid">
            <div class="card">
                <h3>User Behavior (Devices)</h3>
                <div class="chart-container">
                    <canvas id="deviceChart"></canvas>
                </div>
            </div>
            <div class="card">
                <h3>Game Performance (Sign-ups)</h3>
                <div class="chart-container">
                    <canvas id="activityChart"></canvas>
                </div>
            </div>
        </div>

        <!-- RECENT PLAYERS TABLE -->
        <div class="card">
            <h3>Recent Players</h3>
            <table id="playersTable">
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Name</th>
                        <th>Email</th>
                        <th>Status</th>
                        <th>Joined Date</th>
                        <th>Device</th>
                    </tr>
                </thead>
                <tbody>
                    <!-- Populated by JS -->
                </tbody>
            </table>
        </div>
    </div>

    <script>
        let cachedToken = "";

        async function startExport() {
            const token = document.getElementById('tokenInput').value;
            const status = document.getElementById('status');
            const btn = document.getElementById('exportBtn');
            
            if (!token) { status.innerText = "Please enter a token."; return; }

            btn.disabled = true;
            status.innerText = "Authenticating & Assembling Data...\\n(This takes about 1-2 minutes)";
            
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
                    
                    // Populate Cards
                    document.getElementById('valTotal').innerText = data.metrics.total.toLocaleString();
                    document.getElementById('valValid').innerText = data.metrics.valid.toLocaleString();
                    document.getElementById('valGuest').innerText = data.metrics.guests.toLocaleString();
                    document.getElementById('valCountry').innerText = data.metrics.top_country;
                    
                    // Render Device Donut Chart
                    new Chart(document.getElementById('deviceChart'), {
                        type: 'doughnut',
                        data: { 
                            labels: Object.keys(data.devices), 
                            datasets: [{ 
                                data: Object.values(data.devices), 
                                backgroundColor: ['#FFA500', '#00d2ff', '#888', '#4CAF50'],
                                borderWidth: 0
                            }] 
                        },
                        options: { 
                            responsive: true, maintainAspectRatio: false,
                            plugins: { legend: { position: 'bottom', labels: { color: '#a1a1b5' } } },
                            cutout: '70%'
                        }
                    });

                    // Render Activity Line Chart
                    new Chart(document.getElementById('activityChart'), {
                        type: 'line',
                        data: {
                            labels: Object.keys(data.activity),
                            datasets: [{
                                label: 'New Sign-ups',
                                data: Object.values(data.activity),
                                borderColor: '#8a2be2',
                                backgroundColor: 'rgba(138, 43, 226, 0.1)',
                                borderWidth: 3,
                                tension: 0.4,
                                fill: true
                            }]
                        },
                        options: {
                            responsive: true, maintainAspectRatio: false,
                            plugins: { legend: { display: false } },
                            scales: {
                                y: { grid: { color: '#2b2b40' }, ticks: { color: '#a1a1b5' } },
                                x: { grid: { display: false }, ticks: { color: '#a1a1b5' } }
                            }
                        }
                    });

                    // Populate Table
                    const tbody = document.querySelector('#playersTable tbody');
                    tbody.innerHTML = '';
                    data.recent_players.forEach((p, index) => {
                        tbody.innerHTML += `
                            <tr>
                                <td>#${index + 1}</td>
                                <td>
                                    <div style="display:flex; align-items:center; gap:10px;">
                                        <div style="width:30px; height:30px; border-radius:50%; background:#333; display:flex; align-items:center; justify-content:center; font-weight:bold; color:var(--accent);">
                                            ${p.Name.charAt(0)}
                                        </div>
                                        ${p.Name}
                                    </div>
                                </td>
                                <td style="color:var(--text-muted);">${p.Email}</td>
                                <td><span class="status-badge">Active</span></td>
                                <td style="color:var(--text-muted);">${p.Date}</td>
                                <td style="color:var(--text-muted);">${p.Device}</td>
                            </tr>
                        `;
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

    # 5. Extraction Logic (Line-by-line processing)
    def extract_player_details(row):
        username, email, device = "Guest", None, "Unknown"
        raw = row.get('LinkedAccounts')
        if pd.notna(raw) and raw != '[]':
            try:
                clean_str = str(raw).strip('"').replace('""', '"')
                linked_accs = json.loads(clean_str)
                for entry in linked_accs:
                    if not isinstance(entry, dict): continue
                    plat = entry.get("Platform")
                    if plat == "PlayFab":
                        username = entry.get("Username", "Guest")
                        email = entry.get("Email")
                    elif plat in ["IOSDevice", "GameCenter"]:
                        device = "iOS"
                    elif plat in ["AndroidDevice", "GooglePlay"]:
                        device = "Android"
            except:
                pass
        return pd.Series([username, email, device])

    master_df[['ExtractedUsername', 'ExtractedEmail', 'Device']] = master_df.apply(extract_player_details, axis=1)

    # 6. Format Raw Data
    master_df['Sign up date'] = pd.to_datetime(master_df['Created'], errors='coerce')
    master_df['Country'] = master_df['Locations_LastLogin_CountryCode'].fillna("Unknown")
    master_df['Username'] = master_df['ExtractedUsername'].astype(str).str.title()
    master_df['Email'] = master_df['ExtractedEmail']

    # --- CALCULATE DASHBOARD STATS ---
    total_raw = len(master_df)
    
    # Identify Valid vs Guests
    valid_mask = master_df['Email'].notna() & (master_df['Email'] != 'null')
    valid_count = int(valid_mask.sum())
    guest_count = total_raw - valid_count

    # Country & Device Metrics
    country_counts = master_df[master_df['Country'] != "Unknown"]['Country'].value_counts()
    top_country = country_counts.index[0] if not country_counts.empty else "N/A"
    device_counts = master_df['Device'].value_counts().to_dict()

    # Time-Series Activity (Last 14 days of signups)
    activity_series = master_df['Sign up date'].dt.strftime('%b %d').value_counts().sort_index().tail(14).to_dict()

    # Recent Players Table (Grab top 6 valid emails)
    recent_players = []
    recent_df = master_df[valid_mask].sort_values(by='Sign up date', ascending=False).head(6)
    for _, row in recent_df.iterrows():
        recent_players.append({
            "Name": row['Username'],
            "Email": row['Email'],
            "Date": row['Sign up date'].strftime('%Y-%m-%d') if pd.notna(row['Sign up date']) else "N/A",
            "Device": row['Device']
        })

    # 7. Format Clean Final Export Data (Zoho Ready)
    clean_df = master_df[valid_mask].copy()
    final_export_df = clean_df[['Username', 'Sign up date', 'Email', 'Country', 'Device']]
    
    # Save to Global Cache
    global DATA_CACHE
    DATA_CACHE["df"] = final_export_df

    # 8. Return JSON payload to frontend
    payload = {
        "metrics": {
            "total": total_raw,
            "valid": valid_count,
            "guests": guest_count,
            "top_country": top_country
        },
        "devices": device_counts,
        "activity": activity_series,
        "recent_players": recent_players
    }

    return jsonify(payload)


@app.route('/download-csv', methods=['GET'])
def download_csv():
    token = request.args.get('token')
    if token != os.environ.get("SECRET_TOKEN"):
        abort(403)
        
    global DATA_CACHE
    if DATA_CACHE["df"] is None:
        return "Session expired or data not loaded. Please refresh the dashboard.", 404

    output = io.StringIO()
    DATA_CACHE["df"].to_csv(output, index=False)
    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=TGG_Players_Clean.csv"}
    )

if __name__ == '__main__':
    if not os.environ.get("SECRET_TOKEN") or not os.environ.get("SECRET_KEY"):
        print("WARNING: Missing SECRET_TOKEN or SECRET_KEY in environment variables!")
    app.run()