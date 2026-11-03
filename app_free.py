import os
import json
from datetime import datetime, timedelta
import requests
from ddgs import DDGS
from google import genai
from flask import Flask, render_template_string, jsonify

app = Flask(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FOOTBALL_DATA_API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
DATA_FILE = "daily_predictions.json"

def fetch_and_generate_predictions():
    """Fungsi utama untuk menarik jadwal dan mengolahnya via AI"""
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    url = f"https://api.football-data.org/v4/matches?dateFrom={today}&dateTo={tomorrow}"
    headers = {"X-Auth-Token": FOOTBALL_DATA_API_KEY} if FOOTBALL_DATA_API_KEY else {}
    
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        matches = data.get("matches", [])
    except Exception as e:
        matches = []
        
    predictions_result = []
    
    for match in matches[:5]:
        home_team = match['homeTeam']['name']
        away_team = match['awayTeam']['name']
        competition = match['competition']['name']
        match_time = match['utcDate']
        
        search_query = f"{home_team} vs {away_team} preview stats prediction 2026"
        context_data = ""
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(search_query, max_results=3))
                context_data = " ".join([r.get('body', '') for r in results])
        except Exception as e:
            context_data = "Data statistik tidak tersedia."
            
        ai_output = "Prediksi belum tersedia."
        if client:
            prompt = (
                f"Analisis singkat pertandingan bola antara {home_team} vs {away_team} di kompetisi {competition}. "
                f"Gunakan data berikut: {context_data}. "
                f"Berikan output dalam format ringkas: Main Pick (Pilihan Utama) dan Reasoning (Alasan singkat 1-2 kalimat saja)."
            )
            try:
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt
                )
                ai_output = response.text
            except Exception as e:
                ai_output = f"Gagal generate AI: {e}"
                
        predictions_result.append({
            "competition": competition,
            "home_team": home_team,
            "away_team": away_team,
            "time": match_time,
            "analysis": ai_output
        })
        
    output_data = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "predictions": predictions_result
    }
    
    with open(DATA_FILE, "w") as f:
        json.dump(output_data, f, indent=4)

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
            .analysis { font-size: 13px; line-height: 1.4; color: #444; background: #f9f9f9; padding: 8px; border-radius: 4px; }
            .update-info { font-size: 10px; color: #888; text-align: right; margin-bottom: 10px; }
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
            <p style="font-size: 13px; color: #666;">Belum ada data prediksi. Silakan jalankan update manual.</p>
        {% endif %}
    </body>
    </html>
    """
    return render_template_string(html_template, predictions=predictions, updated_at=updated_at)

@app.route("/force-update")
def force_update():
    try:
        fetch_and_generate_predictions()
        return jsonify({"status": "success", "message": "Prediksi berhasil diperbarui!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
