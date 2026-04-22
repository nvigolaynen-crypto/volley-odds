from flask import Flask, request, jsonify, render_template_string
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

TEAMS_DATABASE = {
    'Zenit': {'attack': 92, 'defense': 88, 'homeBonus': 1.15, 'name': 'Зенит-Казань'},
    'Dinamo': {'attack': 85, 'defense': 82, 'homeBonus': 1.10, 'name': 'Динамо Москва'},
    'Lokomotiv': {'attack': 88, 'defense': 85, 'homeBonus': 1.12, 'name': 'Локомотив Новосибирск'},
    'Fakel': {'attack': 78, 'defense': 80, 'homeBonus': 1.08, 'name': 'Факел Ямал'},
    'Kuzbass': {'attack': 82, 'defense': 79, 'homeBonus': 1.09, 'name': 'Кузбасс Кемерово'},
    'Belogorie': {'attack': 86, 'defense': 83, 'homeBonus': 1.11, 'name': 'Белогорье Белгород'}
}

def parse_tournament_table(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        tables = soup.find_all('table')
        
        if not tables:
            return None, "Таблица не найдена"
        
        teams_data = {}
        for row in tables[0].find_all('tr'):
            cols = row.find_all('td')
            if len(cols) >= 2:
                for key, team in TEAMS_DATABASE.items():
                    for col in cols:
                        if team['name'].lower() in col.get_text(strip=True).lower():
                            for c in cols:
                                numbers = re.findall(r'(\d+(?:\.\d+)?)', c.get_text(strip=True))
                                if numbers and key not in teams_data:
                                    try:
                                        val = float(numbers[0])
                                        if val > 100:
                                            val = min(100, val / 10)
                                        teams_data[key] = val
                                    except:
                                        pass
        return teams_data, None
    except Exception as e:
        return None, str(e)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Volley Odds Calculator</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            overflow: hidden;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        }
        .header {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }
        .header h1 { font-size: 2.5em; margin-bottom: 10px; }
        .content { padding: 30px; }
        .section {
            background: #f8f9fa;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 25px;
        }
        .section-title {
            font-size: 1.3em;
            font-weight: bold;
            margin-bottom: 15px;
            color: #333;
            border-left: 4px solid #f5576c;
            padding-left: 12px;
        }
        .url-input-group {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }
        .url-input-group input {
            flex: 1;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 1em;
        }
        .url-input-group button {
            width: auto;
            padding: 12px 25px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-weight: bold;
        }
        .parsed-data {
            background: white;
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
            display: none;
        }
        .parsed-data.active { display: block; }
        .team-strength {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px;
            border-bottom: 1px solid #e0e0e0;
        }
        .strength-bar {
            flex: 1;
            margin: 0 15px;
            height: 8px;
            background: #e0e0e0;
            border-radius: 4px;
            overflow: hidden;
        }
        .strength-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            border-radius: 4px;
        }
        .team-selector {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 30px;
            margin-bottom: 25px;
        }
        .team-card {
            background: white;
            padding: 20px;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .team-card label {
            display: block;
            font-weight: bold;
            margin-bottom: 10px;
            color: #555;
        }
        select, input {
            width: 100%;
            padding: 10px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 1em;
        }
        .options {
            display: flex;
            gap: 20px;
            margin-bottom: 25px;
        }
        .checkbox-label {
            display: flex;
            align-items: center;
            gap: 8px;
            cursor: pointer;
        }
        button {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 15px;
            font-size: 1.1em;
            border-radius: 50px;
            cursor: pointer;
            width: 100%;
            font-weight: bold;
        }
        button:hover { transform: translateY(-2px); }
        .result {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 15px;
            margin-top: 20px;
            text-align: center;
            display: none;
        }
        .odds-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 20px;
            margin-top: 20px;
        }
        .odds-card {
            background: rgba(255,255,255,0.2);
            padding: 20px;
            border-radius: 12px;
        }
        .odds-card .value { font-size: 2em; font-weight: bold; }
        .loading {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 3px solid rgba(255,255,255,.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .status {
            margin-top: 10px;
            padding: 10px;
            border-radius: 8px;
        }
        .status.success { background: #d4edda; color: #155724; }
        .status.error { background: #f8d7da; color: #721c24; }
        @media (max-width: 768px) {
            .team-selector, .odds-grid { grid-template-columns: 1fr; }
            .url-input-group { flex-direction: column; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏐 Volley Odds by Shtopor</h1>
            <div>Профессиональный расчёт + парсинг таблиц</div>
        </div>
        <div class="content">
            <div class="section">
                <div class="section-title">🔗 Ссылка на турнирную таблицу</div>
                <div class="url-input-group">
                    <input type="url" id="tableUrl" placeholder="https://volley.ru/calendar/...">
                    <button id="parseBtn">📊 Загрузить таблицу</button>
                </div>
                <div id="parsedData" class="parsed-data"></div>
                <div id="status"></div>
            </div>

            <div class="section">
                <div class="section-title">🏟️ Выберите команды</div>
                <div class="team-selector">
                    <div class="team-card">
                        <label>🏠 Домашняя команда</label>
                        <select id="homeTeam">
                            <option value="Zenit">Зенит-Казань</option>
                            <option value="Dinamo">Динамо Москва</option>
                            <option value="Lokomotiv">Локомотив Новосибирск</option>
                            <option value="Fakel">Факел Ямал</option>
                            <option value="Kuzbass">Кузбасс Кемерово</option>
                            <option value="Belogorie">Белогорье Белгород</option>
                        </select>
                    </div>
                    <div class="team-card">
                        <label>✈️ Гостевая команда</label>
                        <select id="awayTeam">
                            <option value="Belogorie">Белогорье Белгород</option>
                            <option value="Dinamo">Динамо Москва</option>
                            <option value="Zenit">Зенит-Казань</option>
                            <option value="Lokomotiv">Локомотив Новосибирск</option>
                            <option value="Fakel">Факел Ямал</option>
                            <option value="Kuzbass">Кузбасс Кемерово</option>
                        </select>
                    </div>
                </div>
                <div class="options">
                    <label class="checkbox-label">
                        <input type="checkbox" id="neutralVenue"> 🏟️ Нейтральная площадка
                    </label>
                </div>
            </div>

            <button onclick="calculateOdds()">🎯 Рассчитать котировки</button>

            <div id="result" class="result">
                <h3>📈 Результат расчёта</h3>
                <div class="odds-grid">
                    <div class="odds-card">
                        <div>🏠 Победа хозяев</div>
                        <div class="value" id="homeOdds">-</div>
                        <div id="homeProb">-</div>
                    </div>
                    <div class="odds-card">
                        <div>🤝 Тотал</div>
                        <div class="value" id="drawOdds">-</div>
                        <div id="drawProb">-</div>
                    </div>
                    <div class="odds-card">
                        <div>✈️ Победа гостей</div>
                        <div class="value" id="awayOdds">-</div>
                        <div id="awayProb">-</div>
                    </div>
                </div>
                <div style="margin-top: 20px;">
                    🔥 Маржа: <span id="margin">-</span>%<br>
                    ⭐ Рекомендация: <span id="recommendation">-</span>
                </div>
            </div>
        </div>
    </div>

    <script>
        let parsedStrengths = {};

        async function parseTable() {
            const url = document.getElementById('tableUrl').value;
            if (!url) {
                showStatus('Введите URL', 'error');
                return;
            }

            const btn = document.getElementById('parseBtn');
            btn.innerHTML = '<span class="loading"></span> Загрузка...';
            btn.disabled = true;

            try {
                const response = await fetch('/parse-table', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: url })
                });
                const data = await response.json();

                if (data.success) {
                    parsedStrengths = data.teams;
                    displayParsedData(data.teams);
                    showStatus('✅ Таблица распарсена!', 'success');
                } else {
                    showStatus('❌ Ошибка: ' + data.error, 'error');
                }
            } catch (err) {
                showStatus('❌ Ошибка соединения', 'error');
            } finally {
                btn.innerHTML = '📊 Загрузить таблицу';
                btn.disabled = false;
            }
        }

        function displayParsedData(teams) {
            const container = document.getElementById('parsedData');
            let html = '<div style="font-weight: bold; margin-bottom: 10px;">📈 Распознанные команды:</div>';
            const names = {'Zenit':'Зенит','Dinamo':'Динамо','Lokomotiv':'Локомотив','Fakel':'Факел','Kuzbass':'Кузбасс','Belogorie':'Белогорье'};
            for (const [key, val] of Object.entries(teams)) {
                html += `<div class="team-strength"><span>${names[key] || key}</span><div class="strength-bar"><div class="strength-fill" style="width: ${val}%"></div></div><span>${val.toFixed(1)}%</span></div>`;
            }
            container.innerHTML = html;
            container.classList.add('active');
        }

        function getStrength(team) {
            return parsedStrengths[team] || { 'Zenit':90, 'Dinamo':83, 'Lokomotiv':86, 'Fakel':79, 'Kuzbass':80, 'Belogorie':84 }[team] || 80;
        }

        function calculateOdds() {
            const homeTeam = document.getElementById('homeTeam').value;
            const awayTeam = document.getElementById('awayTeam').value;
            const isNeutral = document.getElementById('neutralVenue').checked;

            let homeStrength = getStrength(homeTeam);
            let awayStrength = getStrength(awayTeam);

            const bonuses = { 'Zenit':1.15, 'Dinamo':1.10, 'Lokomotiv':1.12, 'Fakel':1.08, 'Kuzbass':1.09, 'Belogorie':1.11 };
            if (!isNeutral) homeStrength *= bonuses[homeTeam];

            let homeProb = 1 / (1 + Math.exp((awayStrength - homeStrength) / 25));
            if (isNeutral) homeProb = (homeProb + 0.5) / 2;

            const drawProb = Math.abs(homeStrength - awayStrength) < 10 ? 0.15 : 0.08;
            let awayProb = 1 - homeProb - drawProb;
            if (awayProb < 0) { awayProb = 0.1; homeProb = 0.82; }

            const margin = 0.05;
            const homeOdds = (1 / homeProb) * (1 - margin);
            const drawOdds = (1 / drawProb) * (1 - margin);
            const awayOdds = (1 / awayProb) * (1 - margin);

            document.getElementById('homeOdds').textContent = homeOdds.toFixed(2);
            document.getElementById('drawOdds').textContent = drawOdds.toFixed(2);
            document.getElementById('awayOdds').textContent = awayOdds.toFixed(2);
            document.getElementById('homeProb').textContent = `${(homeProb*100).toFixed(1)}%`;
            document.getElementById('drawProb').textContent = `${(drawProb*100).toFixed(1)}%`;
            document.getElementById('awayProb').textContent = `${(awayProb*100).toFixed(1)}%`;
            document.getElementById('margin').textContent = ((1/homeOdds+1/drawOdds+1/awayOdds)-1).toFixed(2);
            document.getElementById('recommendation').textContent = homeOdds > 1.5 && homeProb > 0.45 ? '🎯 Ценность на хозяев' : awayOdds > 2.0 && awayProb > 0.35 ? '🎯 Ценность на гостей' : '📊 Фаворит очевиден';

            document.getElementById('result').style.display = 'block';
        }

        function showStatus(msg, type) {
            const div = document.getElementById('status');
            div.innerHTML = `<div class="status ${type}">${msg}</div>`;
            setTimeout(() => div.innerHTML = '', 5000);
        }

        document.getElementById('parseBtn').onclick = parseTable;
    </script>
</body>
</html>
'''

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/parse-table', methods=['POST'])
def parse_table():
    data = request.json
    url = data.get('url')
    if not url:
        return jsonify({'success': False, 'error': 'No URL'})
    teams, error = parse_tournament_table(url)
    if error:
        return jsonify({'success': False, 'error': error})
    return jsonify({'success': True, 'teams': teams})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)