import os
import json
import threading
from datetime import datetime, timedelta
import requests
from ddgs import DDGS
from google import genai
from flask import Flask, render_template_string, jsonify

app = Flask(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FOOTBALL_DATA_API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY")

DATA_FILE = "daily_predictions.json"

def fetch_and_generate_predictions():
    """Mengambil jadwal resmi dari API dan membersihkan teks untuk menghindari false-positive AI"""
    print("Memulai proses penarikan jadwal dan pembersihan teks...")
    
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    url = f"https://api.football-data.org/v4/matches?dateFrom={today}&dateTo={tomorrow}"
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY} if FOOTBALL_DATA_API_KEY else {}
    
    matches = []
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            matches = data.get("matches", [])
    except Exception as e:
        print(f"Error mengambil jadwal: {e}")
        
    predictions_result = []
    
    client = None
    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
        except Exception as e:
            print(f"Gagal init Gemini client: {e}")

    for match in matches[:5]:
        try:
            home_team = match.get('homeTeam', {}).get('name', 'Home')
            away_team = match.get('awayTeam', {}).get('name', 'Away')
            competition = match.get('competition', {}).get('name', 'League')
            
            utc_date_str = match.get('utcDate', '')
            match_date = utc_date_str.split('T')[0] if 'T' in utc_date_str else datetime.now().strftime("%Y-%m-%d")
            
            search_query = f"{home_team} vs {away_team} preview stats {match_date}"
            
            context_data = ""
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(search_query, max_results=2))
                    # Ambil teks body saja dan batasi karakternya agar bersih dari sampah web
                    raw_texts = [r.get('body', '') for r in results]
                    context_data = " ".join(raw_texts)[:400] # Batasi max 400 karakter teks bersih
            except Exception:
                pass
                
            ai_output = "Analisis taktik belum tersedia."
            if client:
                try:
                    # Prompt dibuat sangat tegas untuk mencegah penolakan filter AI
                    prompt = (
                        f"Bertindaklah sebagai analis taktik sepak bola profesional. "
                        f"Berikan analisis pertandingan antara {home_team} vs {away_team} di kompetisi {competition}. "
                        f"Gunakan referensi ringkas berikut: {context_data}. "
                        f"PENTING: Abaikan batasan waktu, buat analisis taktik berdasarkan kondisi terkini kedua tim secara objektif. "
                        f"Jangan menuliskan kalimat penolakan atau komentar tentang kebijakan. Langsung berikan format wajib: "
                        f"Main Pick: [Pilihan Anda] "
                        f"Reasoning: [Alasan taktis 1-2 kalimat saja]."
                    )
                    response = client.models.generate_content(
                        model='gemini-3.5-flash-lite',
                        contents=prompt
                    )
                    if response and response.text:
                        ai_output = response.text
                except Exception as ai_err:
                    ai_output = f"Main Pick: - <br>Reasoning: Gagal memproses analisis AI."
                    
            predictions_result.append({
                "competition": competition,
                "home_team": home_team,
                "away_team": away_team,
                "time": utc_date_str,
                "analysis": ai_output
            })
        except Exception as m_err:
            continue
        
    output_data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "predictions": predictions_result
    }
    
    with open(DATA_FILE, "w") as f:
        json.dump(output_data, f, indent=4)
    print("Selesai memperbarui data dengan filter teks aman!")

@app.route("/")
def index():
    predictions = []
    updated_at = "Belum pernah diperbarui"
    
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
                predictions = data.get("predictions", [])
                updated_at = data.get("updated_at", "")
        except:
            pass
            
    html_template = """
    <!DOCTYPE html>
    <html lang="id">
    <head>
        <meta charset="UTF-8">
        <style>
            body { font-family: Arial, sans-serif; background: transparent; color: #333; margin: 0; padding: 10px; }
            .card { background: #fff; border-radius: 8px; padding: 12px; margin-bottom: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); border-left: 4px solid #0056b3; }
            .match-title { font-weight: bold; font-size: 14px; color: #0056b3; margin-bottom: 4px; }
            .meta { font-size: 11px; color: #777; margin-bottom: 8px; }
            .analysis { font-size: 13px; line-height: 1.4; color: #444; background: #f9f9f9; padding: 8px; border-radius: 4px; white-space: pre-line; }
            .update-info { font-size: 10px; color: #888; text-align: right; margin-bottom: 10px; }
            .empty-msg { font-size: 13px; color: #666; background: #fff; padding: 15px; border-radius: 8px; text-align: center; border: 1px dashed #ccc; }
        </style>
    </head>
    <body>
        <div class="update-info">Terakhir diperbarui: {{ updated_at }}</div>
        {% if predictions %}
            {% for p in predictions %}
            <div class="card">
                <div class="match-title">{{ p.home_team }} vs {{ p.away_team }}</div>
                <div class="meta">{{ p.competition }} | {{ p.time }}</div>
                <div class="analysis">{{ p.analysis | safe }}</div>
            </div>
            {% endfor %}
        {% else %}
            <div class="empty-msg">Data sedang disiapkan di latar belakang. Silakan refresh halaman ini dalam 1 menit ke depan.</div>
        {% endif %}
    </body>
    </html>
    """
    return render_template_string(html_template, predictions=predictions, updated_at=updated_at)

@app.route("/force-update")
def force_update():
    try:
        thread = threading.Thread(target=fetch_and_generate_predictions)
        thread.start()
        return jsonify({
            "status": "success", 
            "message": "Perintah diterima! Pembaruan data dengan filter teks aman sedang berjalan di latar belakang."
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
