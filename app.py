from flask import Flask, request, jsonify, render_template_string
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

# Пустая база команд - будет заполняться из таблицы
TEAMS_DATABASE = {}

def parse_tournament_table(url):
    """Парсит турнирную таблицу и извлекает все команды с их показателями"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ищем все таблицы на странице
        tables = soup.find_all('table')
        
        if not tables:
            return None, "Таблица не найдена на странице", []
        
        teams_data = {}
        all_teams = []
        
        # Парсим каждую таблицу
        for table in tables:
            rows = table.find_all('tr')
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 2:
                    # Собираем текст всей строки
                    row_text = ' '.join([c.get_text(strip=True) for c in cols])
                    
                    # Ищем название команды (обычно в первых колонках)
                    team_name = None
                    for col in cols[:3]:  # Проверяем первые 3 колонки
                        text = col.get_text(strip=True)
                        # Фильтруем мусор (числа, короткие слова)
                        if len(text) > 2 and not text.isdigit() and not text.replace('.', '').isdigit():
                            if not any(x in text.lower() for x in ['команда', 'team', 'клуб', 'club', 'место', 'place', 'position']):
                                team_name = text
                                break
                    
                    if team_name:
                        # Ищем числовые показатели (очки, проценты)
                        numbers = re.findall(r'(\d+(?:\.\d+)?)', row_text)
                        strength = 50  # Значение по умолчанию
                        
                        for num in numbers:
                            val = float(num)
                            # Определяем наиболее вероятный показатель силы
                            if 0 < val <= 100:
                                strength = val
                                break
                            elif 100 < val <= 200:
                                strength = val / 2
                                break
                            elif val > 200:
                                strength = min(100, val / 10)
                                break
                        
                        # Нормализуем название команды (убираем лишние символы)
                        team_name = re.sub(r'[^\w\s\u0400-\u04FF-]', '', team_name).strip()
                        
                        if team_name and len(team_name) > 2:
                            teams_data[team_name] = {
                                'strength': round(strength, 1),
                                'attack': round(strength, 1),
                                'defense': round(max(30, strength - 10), 1),
                                'homeBonus': 1.10,
                                'name': team_name
                            }
                            all_teams.append(team_name)
        
        if not teams_data:
            return None, "Не удалось распознать команды в таблице", []
        
        return teams_data, None, all_teams
        
    except Exception as e:
        return None, str(e), []

# HTML с динамическими командами
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Volley Odds - Динамический парсер</title>
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
            padding: 10px;
            border-bottom: 1px solid #e0e0e0;
        }
        .team-strength:last-child { border-bottom: none; }
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
            background: linear-gradient(90deg, #28a745, #007bff);
            border-radius: 4px;
            transition: width 0.5s;
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
        .status.info { background: #d1ecf1; color: #0c5460; }
        .empty-state {
            text-align: center;
            padding: 40px;
            color: #999;
        }
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
            <div>Динамический парсер турнирных таблиц</div>
        </div>
        <div class="content">
            <div class="section">
                <div class="section-title">🔗 Ссылка на турнирную таблицу</div>
                <div class="url-input-group">
                    <input type="url" id="tableUrl" placeholder="https://example.com/volleyball-standings">
                    <button id="parseBtn">📊 Загрузить команды из таблицы</button>
                </div>
                <div id="parsedData" class="parsed-data"></div>
                <div id="status"></div>
            </div>

            <div class="section" id="teamsSection">
                <div class="section-title">🏟️ Выберите команды</div>
                <div id="teamSelectorsContainer">
                    <div class="empty-state">
                        ⚡ Сначала загрузите турнирную таблицу по ссылке<br>
                        Команды появятся здесь автоматически
                    </div>
                </div>
                <div class="options" id="optionsPanel" style="display: none;">
                    <label class="checkbox-label">
                        <input type="checkbox" id="neutralVenue"> 🏟️ Нейтральная площадка
                    </label>
                </div>
            </div>

            <button id="calculateBtn" style="display: none;" onclick="calculateOdds()">🎯 Рассчитать котировки</button>

            <div id="result" class="result">
                <h3>📈 Результат расчёта</h3>
                <div class="odds-grid">
                    <div class="odds-card">
                        <div>🏠 Победа хозяев</div>
                        <div class="value" id="homeOdds">-</div>
                        <div id="homeProb">-</div>
                    </div>
                    <div class="odds-card">
                        <div>🤝 Тотал (3+ сета)</div>
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
        let teamsList = [];
        let teamsData = {};

        async function parseTable() {
            const url = document.getElementById('tableUrl').value;
            if (!url) {
                showStatus('Введите URL турнирной таблицы', 'error');
                return;
            }

            const btn = document.getElementById('parseBtn');
            const originalText = btn.innerHTML;
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
                    teamsData = data.teams;
                    teamsList = data.team_names;
                    displayParsedData(data.teams);
                    createTeamSelectors(data.teams, data.team_names);
                    showStatus('✅ Таблица распарсена! Найдено команд: ' + data.team_names.length, 'success');
                } else {
                    showStatus('❌ Ошибка: ' + data.error, 'error');
                }
            } catch (err) {
                showStatus('❌ Ошибка соединения: ' + err.message, 'error');
            } finally {
                btn.innerHTML = originalText;
                btn.disabled = false;
            }
        }

        function displayParsedData(teams) {
            const container = document.getElementById('parsedData');
            
            if (!teams || Object.keys(teams).length === 0) {
                container.innerHTML = '<div style="color: #666;">⚠️ Не удалось распознать команды</div>';
                container.classList.add('active');
                return;
            }
            
            let html = '<div style="font-weight: bold; margin-bottom: 15px;">📊 Распознанные команды из таблицы:</div>';
            for (const [name, data] of Object.entries(teams)) {
                const strength = data.strength || data.attack || 50;
                html += `
                    <div class="team-strength">
                        <span style="font-weight: bold; min-width: 200px;">🏐 ${name}</span>
                        <div class="strength-bar">
                            <div class="strength-fill" style="width: ${strength}%"></div>
                        </div>
                        <span style="font-weight: bold; color: #28a745; min-width: 60px;">${strength.toFixed(1)}%</span>
                    </div>
                `;
            }
            html += '<div style="margin-top: 10px; font-size: 0.85em; color: #666;">✅ Данные загружены. Выберите команды для расчёта.</div>';
            container.innerHTML = html;
            container.classList.add('active');
        }

        function createTeamSelectors(teams, teamNames) {
            const container = document.getElementById('teamSelectorsContainer');
            const optionsPanel = document.getElementById('optionsPanel');
            const calculateBtn = document.getElementById('calculateBtn');
            
            if (!teamNames || teamNames.length < 2) {
                container.innerHTML = '<div class="empty-state">⚠️ Найдено недостаточно команд (нужно минимум 2)</div>';
                return;
            }
            
            // Создаём выпадающие списки
            let optionsHtml = '';
            for (let i = 0; i < teamNames.length; i++) {
                const team = teamNames[i];
                const strength = teams[team]?.strength || 50;
                optionsHtml += `<option value="${i}">${team} (${strength.toFixed(1)}%)</option>`;
            }
            
            container.innerHTML = `
                <div class="team-selector">
                    <div class="team-card">
                        <label>🏠 Домашняя команда</label>
                        <select id="homeTeam">
                            ${optionsHtml}
                        </select>
                    </div>
                    <div class="team-card">
                        <label>✈️ Гостевая команда</label>
                        <select id="awayTeam">
                            ${optionsHtml}
                        </select>
                    </div>
                </div>
            `;
            
            optionsPanel.style.display = 'block';
            calculateBtn.style.display = 'block';
        }

        function getTeamStrength(teamIndex) {
            const teamName = teamsList[teamIndex];
            if (teamName && teamsData[teamName]) {
                return teamsData[teamName].strength || teamsData[teamName].attack || 50;
            }
            return 50;
        }

        function calculateOdds() {
            const homeIndex = parseInt(document.getElementById('homeTeam').value);
            const awayIndex = parseInt(document.getElementById('awayTeam').value);
            const isNeutral = document.getElementById('neutralVenue').checked;

            if (homeIndex === awayIndex) {
                showStatus('❌ Выберите разные команды', 'error');
                return;
            }

            let homeStrength = getTeamStrength(homeIndex);
            let awayStrength = getTeamStrength(awayIndex);

            // Бонус домашнего поля (стандартный 1.1)
            if (!isNeutral) {
                homeStrength *= 1.10;
            }

            // Расчёт вероятностей
            let homeProb = 1 / (1 + Math.exp((awayStrength - homeStrength) / 25));
            if (isNeutral) {
                homeProb = (homeProb + 0.5) / 2;
            }

            const drawProb = Math.abs(homeStrength - awayStrength) < 10 ? 0.15 : 0.08;
            let awayProb = 1 - homeProb - drawProb;
            if (awayProb < 0) {
                awayProb = 0.1;
                homeProb = 1 - drawProb - awayProb;
            }

            // Коэффициенты с маржой 5%
            const margin = 0.05;
            const homeOdds = (1 / homeProb) * (1 - margin);
            const drawOdds = (1 / drawProb) * (1 - margin);
            const awayOdds = (1 / awayProb) * (1 - margin);
            
            const actualMargin = ((1/homeOdds + 1/drawOdds + 1/awayOdds) - 1) * 100;

            // Рекомендация
            let recommendation = '';
            if (homeOdds > 1.5 && homeProb > 0.45) {
                recommendation = '🎯 Ценность в ставке на хозяев';
            } else if (awayOdds > 2.0 && awayProb > 0.35) {
                recommendation = '🎯 Ценность в ставке на гостей';
            } else if (homeOdds < 1.4 && homeProb > 0.7) {
                recommendation = '📊 Фаворит очевиден';
            } else {
                recommendation = '📊 Равный матч, смотрите live';
            }

            // Отображение
            document.getElementById('homeOdds').textContent = homeOdds.toFixed(2);
            document.getElementById('drawOdds').textContent = drawOdds.toFixed(2);
            document.getElementById('awayOdds').textContent = awayOdds.toFixed(2);
            document.getElementById('homeProb').textContent = `${(homeProb*100).toFixed(1)}%`;
            document.getElementById('drawProb').textContent = `${(drawProb*100).toFixed(1)}%`;
            document.getElementById('awayProb').textContent = `${(awayProb*100).toFixed(1)}%`;
            document.getElementById('margin').textContent = actualMargin.toFixed(2);
            document.getElementById('recommendation').textContent = recommendation;

            document.getElementById('result').style.display = 'block';
            document.getElementById('result').scrollIntoView({ behavior: 'smooth' });
        }

        function showStatus(message, type) {
            const statusDiv = document.getElementById('status');
            statusDiv.innerHTML = `<div class="status ${type}">${message}</div>`;
            setTimeout(() => {
                statusDiv.innerHTML = '';
            }, 5000);
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
        return jsonify({'success': False, 'error': 'URL не указан'})
    
    teams_data, error, team_names = parse_tournament_table(url)
    
    if error:
        return jsonify({'success': False, 'error': error})
    
    return jsonify({
        'success': True, 
        'teams': teams_data,
        'team_names': team_names
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
