from flask import Flask, request, jsonify, render_template_string
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

def parse_tournament_table(url):
    """Парсит турнирную таблицу и извлекает только команды с правильным рейтингом"""
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
        team_positions = []  # Для хранения позиций команд
        
        # Парсим каждую таблицу
        for table in tables:
            rows = table.find_all('tr')
            position = 1
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 2:
                    # Ищем название команды
                    team_name = None
                    team_strength = None
                    
                    for col_idx, col in enumerate(cols[:4]):  # Проверяем первые 4 колонки
                        text = col.get_text(strip=True)
                        
                        # Фильтруем мусор: убираем даты, времена, города, числа
                        is_date = re.match(r'^\d{2}[:\.]\d{2}$|^\d{1,2}\.\d{1,2}\.\d{4}$|^\d{4}$', text)
                        is_time = re.match(r'^\d{1,2}[:\.]\d{2}$', text)
                        is_city = re.search(r'МСК|MCK|MSK', text)
                        is_pure_number = text.isdigit() and len(text) <= 4
                        is_garbage = len(text) < 3 and text.isdigit()
                        
                        if not is_date and not is_time and not is_city and not is_pure_number and not is_garbage:
                            # Очищаем название от лишних символов
                            clean_name = re.sub(r'[^\w\s\u0400-\u04FF-]', '', text).strip()
                            clean_name = re.sub(r'\s+', ' ', clean_name)
                            
                            # Убираем слова-маркеры
                            garbage_words = ['дата', 'time', 'date', 'место', 'position', 'rank', '№']
                            if len(clean_name) > 2 and not any(gw in clean_name.lower() for gw in garbage_words):
                                team_name = clean_name
                                break
                    
                    if team_name and team_name not in all_teams:
                        # Ищем числовые показатели в строке (очки, проценты)
                        numbers = re.findall(r'(\d+(?:\.\d+)?)', row.get_text())
                        strength = None
                        
                        for num in numbers:
                            val = float(num)
                            # Нормализуем значение
                            if 0 < val <= 100:
                                strength = val
                                break
                            elif 100 < val <= 200:
                                strength = val / 2
                                break
                            elif val > 200:
                                strength = min(100, val / 10)
                                break
                        
                        # Если нет числовых показателей, используем позицию в таблице
                        # Чем выше позиция (меньше число) - тем сильнее команда
                        if strength is None:
                            # Преобразуем позицию в силу (1 место = 95%, последнее = 50%)
                            max_teams = 20  # Предполагаем максимум 20 команд
                            strength = max(30, 95 - (position - 1) * (45 / max_teams))
                        
                        teams_data[team_name] = {
                            'strength': round(strength, 1),
                            'attack': round(strength, 1),
                            'defense': round(max(30, strength - 10), 1),
                            'homeBonus': 1.10,
                            'name': team_name,
                            'position': position
                        }
                        all_teams.append(team_name)
                        team_positions.append(position)
                        position += 1
        
        # Сортируем команды по силе (от сильных к слабым)
        if teams_data:
            all_teams.sort(key=lambda x: teams_data[x]['strength'], reverse=True)
        
        if not teams_data:
            return None, "Не удалось распознать команды в таблице", []
        
        return teams_data, None, all_teams
        
    except Exception as e:
        return None, str(e), []

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Volley Odds - Чистый парсер</title>
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
            max-height: 300px;
            overflow-y: auto;
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
        .empty-state {
            text-align: center;
            padding: 40px;
            color: #999;
        }
        .rank-badge {
            background: #e0e0e0;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.75em;
            margin-left: 10px;
            color: #666;
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
            <div>Чистый парсинг турнирных таблиц</div>
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
                    showStatus('✅ Найдено команд: ' + data.team_names.length, 'success');
                } else {
                    showStatus('❌ Ошибка: ' + data.error, 'error');
                }
            } catch (err) {
                showStatus('❌ Ошибка: ' + err.message, 'error');
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
            
            let html = '<div style="font-weight: bold; margin-bottom: 15px;">📊 Рейтинг команд (от сильных к слабым):</div>';
            
            // Сортируем по силе (от сильных к слабым)
            const sortedTeams = Object.entries(teams).sort((a, b) => b[1].strength - a[1].strength);
            
            for (let i = 0; i < sortedTeams.length; i++) {
                const [name, data] = sortedTeams[i];
                const strength = data.strength;
                const rank = i + 1;
                html += `
                    <div class="team-strength">
                        <span style="font-weight: bold; min-width: 200px;">
                            ${rank}. 🏐 ${name}
                        </span>
                        <div class="strength-bar">
                            <div class="strength-fill" style="width: ${strength}%"></div>
                        </div>
                        <span style="font-weight: bold; color: #28a745; min-width: 60px;">${strength.toFixed(1)}%</span>
                    </div>
                `;
            }
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
            
            // Сортируем команды для выпадающего списка
            const sortedTeams = [...teamNames].sort((a, b) => {
                return teams[b].strength - teams[a].strength;
            });
            
            let optionsHtml = '';
            for (let i = 0; i < sortedTeams.length; i++) {
                const team = sortedTeams[i];
                const strength = teams[team].strength;
                optionsHtml += `<option value="${team}">${team} (сила ${strength.toFixed(1)}%)</option>`;
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

        function getTeamStrength(teamName) {
            if (teamsData[teamName]) {
                return teamsData[teamName].strength;
            }
            return 50;
        }

        function calculateOdds() {
            const homeTeam = document.getElementById('homeTeam').value;
            const awayTeam = document.getElementById('awayTeam').value;
            const isNeutral = document.getElementById('neutralVenue').checked;

            if (homeTeam === awayTeam) {
                showStatus('❌ Выберите разные команды', 'error');
                return;
            }

            let homeStrength = getTeamStrength(homeTeam);
            let awayStrength = getTeamStrength(awayTeam);

            // Бонус домашнего поля
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

            // Коэффициенты
            const margin = 0.05;
            const homeOdds = (1 / homeProb) * (1 - margin);
            const drawOdds = (1 / drawProb) * (1 - margin);
            const awayOdds = (1 / awayProb) * (1 - margin);
            
            const actualMargin = ((1/homeOdds + 1/drawOdds + 1/awayOdds) - 1) * 100;

            let recommendation = '';
            if (homeOdds > 1.5 && homeProb > 0.45) {
                recommendation = '🎯 Ценность в ставке на хозяев';
            } else if (awayOdds > 2.0 && awayProb > 0.35) {
                recommendation = '🎯 Ценность в ставке на гостей';
            } else {
                recommendation = '📊 Фаворит очевиден';
            }

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
