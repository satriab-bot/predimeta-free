import os
import json
import time
from datetime import datetime, timedelta
import requests
from ddgs import DDGS
from google import genai
from flask import Flask, render_template_string

app = Flask(__name__)

# Mengambil API Key secara aman dari Environment Variables server (Render)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FOOTBALL_DATA_API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)
DATA_FILE = "daily_predictions.json"

# Template HTML untuk menampilkan hasil yang sudah otomatis digenerate ke pembaca blog
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <title>PrediMeta - Free Daily Predictions</title>
    <style>
        :root {
            --bg-body: #0b0f19;
            --bg-card: #131b2e;
            --border-color: #1e293b;
            --text-color: #f8fafc;
            --text-muted: #94a3b8;
            --box-pick: #1e293b;
            --btn-secondary: #1e293b;
        }

        [data-theme="light"] {
            --bg-body: #f1f5f9;
            --bg-card: #ffffff;
            --border-color: #e2e8f0;
            --text-color: #0f172a;
            --text-muted: #64748b;
            --box-pick: #eff6ff;
            --btn-secondary: #e2e8f0;
        }

        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg-body); color: var(--text-color); margin: 0; padding: 20px; display: flex; justify-content: center; min-height: 100vh; box-sizing: border-box; transition: background 0.3s, color 0.3s; }
        .container { width: 100%; max-width: 850px; }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; background: var(--bg-card); border: 1px solid var(--border-color); padding: 20px; border-radius: 12px; }
        .match-card { background: var(--bg-card); border: 1px solid var(--border-color); padding: 25px; border-radius: 12px; margin-bottom: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); }
        .match-header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 15px; margin-bottom: 15px; }
        .team-name { font-size: 18px; font-weight: bold; color: #38bdf8; }
        .pick-box { background: var(--box-pick); border: 1px solid #3b82f6; padding: 15px; border-radius: 8px; margin-bottom: 15px; font-size: 14px; line-height: 1.6; color: var(--text-color); }
        .reason-box { background: var(--bg-body); padding: 15px; border-radius: 8px; border-left: 4px solid #3b82f6; font-size: 13px; line-height: 1.6; color: var(--text-muted); }
        button { background: #3b82f6; color: white; border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="card-header">
            <div>
                <h2 style="margin: 0; color: var(--text-color);">PrediMeta Free Version</h2>
                <p style="font-size: 12px; color: var(--text-muted); margin: 5px 0 0 0;">Pembaruan otomatis setiap hari pukul 10:30 WIB</p>
            </div>
            <button type="button" id="theme-toggle" onclick="toggleTheme()">🌙 Mode Terang</button>
        </div>

        {% if predictions %}
            {% for item in predictions %}
            <div class="match-card">
                <div class="match-header">
                    <div>
                        <div style="font-size: 10px; color: var(--text-muted); text-transform: uppercase;">Home</div>
                        <span class="team-name">{{ item.home }}</span>
                    </div>
                    <div style="font-weight: bold; color: #64748b;">VS</div>
                    <div style="text-align: right;">
                        <div style="font-size: 10px; color: var(--text-muted); text-transform: uppercase;">Away</div>
                        <span class="team-name">{{ item.away }}</span>
                    </div>
                </div>

                <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 10px;">⏰ Jadwal Laga (UTC): {{ item.date }}</div>

                <h4 style="margin: 0 0 8px 0; color: var(--text-color);">Main Pick</h4>
                <div class="pick-box">
                    {{ item.pick | safe }}
                </div>

                <h4 style="margin: 15px 0 8px 0; color: var(--text-color);">Alasan Analisis</h4>
                <div class="reason-box">
                    {{ item.reason | safe }}
                </div>
            </div>
            {% endfor %}
        {% else %}
            <div class="match-card" style="text-align: center; color: var(--text-muted);">
                Belum ada data prediksi otomatis untuk 24 jam ke depan. Sistem akan memperbarui secara otomatis pada pukul 10:30 WIB.
            </div>
        {% endif %}
    </div>

    <script>
        function toggleTheme() {
            const html = document.documentElement;
            const btn = document.getElementById('theme-toggle');
            if (html.getAttribute('data-theme') === 'light') {
                html.removeAttribute('data-theme');
                btn.textContent = '🌙 Mode Terang';
                localStorage.setItem('theme', 'dark');
            } else {
                html.setAttribute('data-theme', 'light');
                btn.textContent = '☀️ Mode Gelap';
                localStorage.setItem('theme', 'light');
            }
        }
        window.addEventListener('DOMContentLoaded', () => {
            if (localStorage.getItem('theme') === 'light') {
                document.documentElement.setAttribute('data-theme', 'light');
                document.getElementById('theme-toggle').textContent = '☀️ Mode Gelap';
            }
        });
    </script>
</body>
</html>
"""

def fetch_and_generate_predictions():
    """Fungsi utama yang dijadwalkan berjalan otomatis setiap jam 10.30 WIB"""
    print(f"\n[CRON JOB] Memulai pembaruan prediksi otomatis: {datetime.now()}")
    
    # 1. Ambil jadwal dari football-data.org (24 jam ke depan)
    url = "https://api.football-data.org/v4/matches"
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY}
    
    now = datetime.now()
    future = now + timedelta(days=1)
    
    params = {
        "dateFrom": now.strftime("%Y-%m-%d"),
        "dateTo": future.strftime("%Y-%m-%d")
    }
    
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            print(f"[ERROR] Gagal mengambil API jadwal: {response.status_code}")
            return
        
        matches_data = response.json().get("matches", [])
    except Exception as e:
        print(f"[ERROR] Koneksi API jadwal gagal: {str(e)}")
        return

    compiled_results = []

    # 2. Iterasi setiap pertandingan yang ditarik dari API
    for match in matches_data:
        home = match["homeTeam"]["name"]
        away = match["awayTeam"]["name"]
        match_date = match["utcDate"][:10]

        # Grounding data via DDGS
        search_query = f"{home} vs {away} match preview stats {match_date}"
        search_results_text = ""
        
        try:
            with DDGS() as ddgs:
                results = [r for r in ddgs.text(search_query, max_results=4)]
                for r in results:
                    search_results_text += f"- [{r.get('title')}]: {r.get('body')}\n"
        except Exception as e:
            search_results_text = "Pencarian data mandiri."

        # 3. Eksekusi Mesin Gemini (Hanya Main Pick & Alasan)
        prompt = f"""
        PENTING: Waktu/Tanggal target pertandingan adalah pada tanggal {match_date}. 
        Bertindaklah sebagai mesin analisis statistik sepak bola profesional. 
        Analisis pertandingan antara {home} (Kandang) melawan {away} (Tandang).
        
        Berikut adalah data mentah hasil pencarian web:
        {search_results_text}
        
        Berikan jawaban dalam format HTML murni tanpa blok markdown (tanpa ```), menggunakan persis 2 bagian dipisahkan oleh satu tag <hr>:
        
        [BAGIAN 1: MAIN PICK]
        Sebutkan rekomendasi prediksi utama (Main Pick) secara tegas dan tingkat keyakinannya.
        
        <hr>
        
        [BAGIAN 2: ALASAN ANALISIS]
        Berikan alasan analitis singkat dan tajam mengapa pilihan tersebut diambil berdasarkan tren performa terkini.
        """

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            raw_text = response.text
            parts = raw_text.split("<hr>")
            
            pick_content = parts[0].replace("[BAGIAN 1: MAIN PICK]", "").strip()
            reason_content = parts[1].replace("[BAGIAN 2: ALASAN ANALISIS]", "").strip() if len(parts) > 1 else "Analisis performa terkini."

            compiled_results.append({
                "home": home,
                "away": away,
                "date": match["utcDate"],
                "pick": pick_content,
                "reason": reason_content
            })
            
            # Jeda singkat untuk menjaga rate limit
            time.sleep(2)
            
        except Exception as e:
            print(f"[ERROR] Gagal memproses {home} vs {away}: {str(e)}")

    # 4. Simpan hasil ke file JSON lokal yang dibaca oleh web view
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(compiled_results, f, ensure_ascii=False, indent=4)
    print(f"[SUCCESS] Berhasil memperbarui {len(compiled_results)} prediksi otomatis.")

@app.route("/")
def index():
    """Halaman utama yang menampilkan hasil prediksi instan dari file JSON"""
    predictions = []
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                predictions = json.load(f)
        except Exception:
            predictions = []
            
    return render_template_string(HTML_TEMPLATE, predictions=predictions)

import os

if __name__ == "__main__":
    # Mengambil port dari environment Render secara otomatis, default ke 5000 jika dijalankan lokal
    port = int(os.environ.get("PORT", 5000))
    # Wajib binding ke "0.0.0.0" agar bisa diakses oleh publik Render
    app.run(host="0.0.0.0", port=port)
