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
            --bg-color: #12121a;
            --card-bg: #1a1a24;
            --accent: #FFA500;
            --accent-alt: #00d2ff;
            --text-main: #ffffff;
            --text-muted: #a1a1b5;
            --border: #2b2b40;
        }
        body { 
            background-color: var(--bg-color); color: var(--text-main); 
            font-family: 'Helvetica', sans-serif; margin: 0; 
            min-height: 100vh; box-sizing: border-box;
        }
        
        /* LOGIN SCREEN */
        #loginSection {
            display: flex; justify-content: center; align-items: center; height: 100vh;
        }
        .container { 
            text-align: center; background: var(--card-bg); padding: 50px 40px; 
            border-radius: 12px; border: 1px solid var(--border); 
            max-width: 450px; width: 100%; box-sizing: border-box;
        }
        input { 
            padding: 15px; width: 100%; border-radius: 6px; 
            border: 1px solid var(--border); margin-bottom: 20px; 
            background: var(--bg-color); color: white; box-sizing: border-box;
            font-size: 16px; font-family: monospace; letter-spacing: 2px;
        }
        input:focus { outline: 1px solid var(--accent); }
        button { 
            background-color: var(--accent); color: #000; border: none; 
            padding: 15px 30px; font-weight: bold; border-radius: 6px; 
            cursor: pointer; transition: 0.2s; width: 100%; font-size: 14px;
        }
        button:hover { background-color: #e69500; }
        button:disabled { background-color: #555; cursor: not-allowed; color: #888; }
        #status { color: var(--accent); margin-top: 20px; display: block; font-weight: bold; font-size: 14px; }
        
        /* DASHBOARD LAYOUT */
        #dashboard { display: none; padding: 30px; max-width: 1500px; margin: auto; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; }
        .header img { width: 120px; }
        .top-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; }
        .card { background: var(--card-bg); padding: 20px; border-radius: 12px; border: 1px solid var(--border); }
        .card h3 { color: var(--text-muted); font-size: 0.9em; margin-top: 0; text-transform: uppercase; letter-spacing: 1px;}
        .card .value { font-size: 2.2em; font-weight: bold; margin: 10px 0; }
        
        /* CHARTS GRID (Updated to 3 columns) */
        .charts-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; margin-bottom: 30px; }
        .chart-container { position: relative; height: 280px; width: 100%; }
        
        /* TABLES GRID */
        .tables-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        table { width: 100%; border-collapse: collapse; text-align: left; }
        th { color: var(--text-muted); padding: 15px; border-bottom: 1px solid var(--border); font-size: 0.9em; text-transform: uppercase; }
        td { padding: 15px; border-bottom: 1px solid var(--border); font-size: 0.95em; }
        .status-badge { background: rgba(76, 175, 80, 0.15); color: #4CAF50; padding: 5px 10px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }
        .status-badge.alt { background: rgba(0, 210, 255, 0.15); color: var(--accent-alt); }
    </style>
</head>
<body>

    <!-- LOGIN SCREEN -->
    <div id="loginSection">
        <div class="container">
            <img src="https://i.imgur.com/VGHlcJB.png" alt="TRIVIA Logo" style="width: 200px; margin-bottom: 40px;">
            <input type="password" id="tokenInput" placeholder="Enter Secret Token">
            <button id="exportBtn" onclick="startExport()">ACCESS ADMIN BOARD →</button>
            <p id="status"></p>
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
                ↓ EXPORT CSV
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
                <h3>Device Distribution</h3>
                <div class="chart-container">
                    <canvas id="deviceChart"></canvas>
                </div>
            </div>
            <div class="card">
                <h3>New Sign-ups (14 Days)</h3>
                <div class="chart-container">
                    <canvas id="activityChart"></canvas>
                </div>
            </div>
            <div class="card">
                <h3>Login Activity (14 Days)</h3>
                <div class="chart-container">
                    <canvas id="loginChart"></canvas>
                </div>
            </div>
        </div>

        <!-- TABLES GRID -->
        <div class="tables-grid">
            <!-- RECENT SIGN-UPS -->
            <div class="card">
                <h3>Recent Sign-ups</h3>
                <table id="recentTable">
                    <thead>
                        <tr>
                            <th>Rank</th>
                            <th>Player Name</th>
                            <th>Status</th>
                            <th>Joined Date</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- Populated by JS -->
                    </tbody>
                </table>
            </div>

            <!-- TOP ACTIVE PLAYERS -->
            <div class="card">
                <h3>Top Active Players</h3>
                <table id="topPlayersTable">
                    <thead>
                        <tr>
                            <th>Player Name</th>
                            <th>Email</th>
                            <th>Status</th>
                            <th>Last Login</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- Populated by JS -->
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        let cachedToken = "";

        async function startExport() {
            const token = document.getElementById('tokenInput').value;
            const status = document.getElementById('status');
            const btn = document.getElementById('exportBtn');
            
            if (!token) { status.innerText = "Error: Please enter a token."; return; }

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
                    
                    document.getElementById('loginSection').style.display = 'none';
                    document.getElementById('dashboard').style.display = 'block';
                    
                    // Cards
                    document.getElementById('valTotal').innerText = data.metrics.total.toLocaleString();
                    document.getElementById('valValid').innerText = data.metrics.valid.toLocaleString();
                    document.getElementById('valGuest').innerText = data.metrics.guests.toLocaleString();
                    document.getElementById('valCountry').innerText = data.metrics.top_country;
                    
                    // Device Donut Chart
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

                    // Sign-ups Line Chart
                    new Chart(document.getElementById('activityChart'), {
                        type: 'line',
                        data: {
                            labels: Object.keys(data.activity),
                            datasets: [{
                                label: 'New Sign-ups',
                                data: Object.values(data.activity),
                                borderColor: '#8a2be2',
                                backgroundColor: 'rgba(138, 43, 226, 0.1)',
                                borderWidth: 3, tension: 0.4, fill: true
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

                    // Logins Bar Chart
                    new Chart(document.getElementById('loginChart'), {
                        type: 'bar',
                        data: {
                            labels: Object.keys(data.logins),
                            datasets: [{
                                label: 'Daily Logins',
                                data: Object.values(data.logins),
                                backgroundColor: '#00d2ff',
                                borderRadius: 4
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

                    // Populate Recent Signups Table
                    const recentTbody = document.querySelector('#recentTable tbody');
                    recentTbody.innerHTML = '';
                    data.recent_players.forEach((p, index) => {
                        recentTbody.innerHTML += `
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
                                <td><span class="status-badge">New</span></td>
                                <td style="color:var(--text-muted);">${p.Date}</td>
                            </tr>
                        `;
                    });

                    // Populate Top Active Table
                    const topTbody = document.querySelector('#topPlayersTable tbody');
                    topTbody.innerHTML = '';
                    data.top_players.forEach((p) => {
                        topTbody.innerHTML += `
                            <tr>
                                <td>
                                    <div style="display:flex; align-items:center; gap:10px;">
                                        <div style="width:30px; height:30px; border-radius:50%; background:#333; display:flex; align-items:center; justify-content:center; font-weight:bold; color:var(--accent-alt);">
                                            ${p.Name.charAt(0)}
                                        </div>
                                        ${p.Name}
                                    </div>
                                </td>
                                <td style="color:var(--text-muted);">${p.Email}</td>
                                <td><span class="status-badge alt">Active</span></td>
                                <td style="color:var(--text-muted);">${p.LastActive}</td>
                            </tr>
                        `;
                    });

                } else {
                    const errText = await response.text();
                    status.innerText = "Error: " + (errText || "Invalid Token");
                    btn.disabled = false;
                }
            } catch (e) {
                status.innerText = "Error: Connection Failed. Please try again.";
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

    export_res = requests.post(
        f"https://{TITLE_ID}.playfabapi.com/Admin/ExportPlayersInSegment",
        headers=HEADERS, json={"SegmentId": SEGMENT_ID}
    )
    export_id = export_res.json().get("data", {}).get("ExportId")
    if not export_id:
        return "Failed to start PlayFab export", 500

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

    index_res = requests.get(index_url)
    tsv_links = [link for link in index_res.text.strip().split('\n') if link]

    total_raw = 0
    valid_rows = []
    device_counts = {"iOS": 0, "Android": 0, "Unknown": 0}
    country_counts = {}
    all_signup_dates = []
    all_login_dates = []

    # Memory-Optimized Processing Loop
    for link in tsv_links:
        try:
            df = pd.read_csv(link, sep='\t', dtype=str)
            total_raw += len(df)
            
            for _, row in df.iterrows():
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
                
                device_counts[device] = device_counts.get(device, 0) + 1
                
                country = str(row.get('Locations_LastLogin_CountryCode', 'Unknown'))
                if country == 'nan' or not country: country = 'Unknown'
                if country != 'Unknown':
                    country_counts[country] = country_counts.get(country, 0) + 1
                    
                created = pd.to_datetime(row.get('Created'), errors='coerce')
                if pd.notna(created):
                    all_signup_dates.append(created)

                last_login = pd.to_datetime(row.get('LastLogin'), errors='coerce')
                if pd.notna(last_login):
                    all_login_dates.append(last_login)
                
                # Store Valid Users
                if pd.notna(email) and str(email).lower() != 'null':
                    valid_rows.append({
                        'Username': str(username).title(),
                        'Sign up date': created.strftime('%Y-%m-%d %H:%M:%S') if pd.notna(created) else "",
                        'Last Login': last_login.strftime('%Y-%m-%d %H:%M:%S') if pd.notna(last_login) else "",
                        'Email': email,
                        'Country': country,
                        'Device': device
                    })
            
            del df 
        except:
            pass

    final_export_df = pd.DataFrame(valid_rows)
    
    global DATA_CACHE
    DATA_CACHE["df"] = final_export_df

    # --- CALCULATE DASHBOARD STATS ---
    valid_count = len(final_export_df)
    guest_count = total_raw - valid_count
    
    top_country = max(country_counts, key=country_counts.get) if country_counts else "N/A"

    activity_series = {}
    if all_signup_dates:
        s_dates = pd.Series(all_signup_dates)
        activity_series = s_dates.dt.strftime('%b %d').value_counts().sort_index().tail(14).to_dict()

    login_series = {}
    if all_login_dates:
        l_dates = pd.Series(all_login_dates)
        login_series = l_dates.dt.strftime('%b %d').value_counts().sort_index().tail(14).to_dict()

    recent_players = []
    top_players = []
    
    if not final_export_df.empty:
        # Table 1: Recent Signups
        sorted_recent = final_export_df.sort_values(by='Sign up date', ascending=False).head(5)
        for _, row in sorted_recent.iterrows():
            recent_players.append({
                "Name": row['Username'],
                "Date": row['Sign up date'].split()[0] if row['Sign up date'] else "N/A"
            })
            
        # Table 2: Top Active (Most recent logins with emails)
        sorted_top = final_export_df[final_export_df['Last Login'] != ""].sort_values(by='Last Login', ascending=False).head(5)
        for _, row in sorted_top.iterrows():
            top_players.append({
                "Name": row['Username'],
                "Email": row['Email'],
                "LastActive": row['Last Login'].split()[0] if row['Last Login'] else "N/A"
            })

    payload = {
        "metrics": {
            "total": total_raw,
            "valid": valid_count,
            "guests": guest_count,
            "top_country": top_country
        },
        "devices": device_counts,
        "activity": activity_series,
        "logins": login_series,
        "recent_players": recent_players,
        "top_players": top_players
    }

    return jsonify(payload)

@app.route('/download-csv', methods=['GET'])
def download_csv():
    token = request.args.get('token')
    if token != os.environ.get("SECRET_TOKEN"):
        abort(403)
        
    global DATA_CACHE
    if DATA_CACHE["df"] is None or DATA_CACHE["df"].empty:
        return "Session expired or data not loaded. Please refresh the dashboard.", 404

    output = io.StringIO()
    DATA_CACHE["df"].to_csv(output, index=False)
    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=TGG_Players_Info.csv"}
    )

if __name__ == '__main__':
    if not os.environ.get("SECRET_TOKEN") or not os.environ.get("SECRET_KEY"):
        print("WARNING: Missing SECRET_TOKEN or SECRET_KEY in environment variables!")
    app.run()