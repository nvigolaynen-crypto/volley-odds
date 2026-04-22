from flask import Flask, request, jsonify, render_template_string
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

def clean_team_name(text):
    """Очищает название команды от мусора"""
    # Убираем "-й", "-я", "-е" в начале
    text = re.sub(r'^\d+[-]?[йяе]?\s*', '', text)
    # Убираем времена
    text = re.sub(r'\d{1,2}[:\.]\d{2}\s*(?:MCK|МСК|MSK)?', '', text)
    # Убираем даты
    text = re.sub(r'\d{1,2}\.\d{1,2}\.\d{4}', '', text)
    # Убираем одиночные числа
    text = re.sub(r'\b\d+\b', '', text)
    # Убираем слова-маркеры
    garbage = ['МСК', 'MCK', 'MSK', 'дата', 'time', 'date', 'время', '№', 'круг', 'тур', 'Время', 'местное']
    for g in garbage:
        text = text.replace(g, '')
    # Убираем лишние пробелы и символы
    text = re.sub(r'[^\w\s\u0400-\u04FF-]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def parse_tournament_table(url):
    """Парсит турнирную таблицу и вычисляет силу команд"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Ищем все таблицы
        tables = soup.find_all('table')
        
        if not tables:
            return None, "Таблица не найдена", []
        
        teams_data = {}
        max_points = 0
        max_win_rate = 0
        
        for table in tables:
            rows = table.find_all('tr')
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 6:
                    # Ищем название команды
                    team_name = None
                    
                    for idx, col in enumerate(cols[:4]):
                        text = col.get_text(strip=True)
                        if len(text) < 2:
                            continue
                        if re.match(r'^\d+$', text):
                            continue
                        if re.match(r'^\d{1,2}[:\.]\d{2}$', text):
                            continue
                        if re.search(r'МСК|MCK', text):
                            continue
                        
                        clean = clean_team_name(text)
                        # Пропускаем короткие и пустые
                        if len(clean) > 2 and not clean.isdigit():
                            team_name = clean
                            break
                    
                    if not team_name:
                        continue
                    
                    # Собираем всю строку для поиска чисел
                    row_text = ' '.join([c.get_text(strip=True) for c in cols])
                    
                    # Ищем очки (обычно большое число)
                    points = None
                    points_matches = re.findall(r'\b(\d{2,3})\b', row_text)
                    for p in points_matches:
                        val = int(p)
                        if 20 <= val <= 150:  # Диапазон очков в волейболе
                            points = val
                            if points > max_points:
                                max_points = points
                            break
                    
                    # Ищем партии (формат 89:31 или 89-31)
                    sets_won = None
                    sets_lost = None
                    sets_match = re.search(r'(\d+)[:-](\d+)', row_text)
                    if sets_match:
                        sets_won = int(sets_match.group(1))
                        sets_lost = int(sets_match.group(2))
                    
                    # Ищем победы/поражения
                    wins = None
                    losses = None
                    win_loss = re.search(r'(\d+)[^\d]+(\d+)\s*(?:в|п|w|l)', row_text, re.I)
                    if win_loss:
                        wins = int(win_loss.group(1))
                        losses = int(win_loss.group(2))
                    
                    teams_data[team_name] = {
                        'name': team_name,
                        'points': points,
                        'sets_won': sets_won,
                        'sets_lost': sets_lost,
                        'wins': wins,
                        'losses': losses
                    }
        
        # Вычисляем силу для каждой команды
        for team in teams_data:
            strength = 50  # по умолчанию
            data = teams_data[team]
            
            # Приоритет 1: очки
            if data['points'] and max_points > 0:
                strength = (data['points'] / max_points) * 100
            
            # Приоритет 2: соотношение партий
            elif data['sets_won'] and data['sets_lost'] and data['sets_lost'] > 0:
                sets_ratio = (data['sets_won'] / data['sets_lost']) * 100
                strength = min(100, sets_ratio)
            
            # Приоритет 3: победы/поражения
            elif data['wins'] and data['losses'] and (data['wins'] + data['losses']) > 0:
                win_rate = (data['wins'] / (data['wins'] + data['losses'])) * 100
                strength = win_rate
            
            data['strength'] = round(strength, 1)
        
        # Сортируем по силе
        sorted_teams = sorted(teams_data.items(), key=lambda x: x[1]['strength'], reverse=True)
        
        result_teams = {}
        team_names = []
        
        for name, data in sorted_teams:
            # Пропускаем явно некорректные названия
            if len(name) < 2 or name.lower() in ['дата', 'время', 'место', 'команда']:
                continue
            result_teams[name] = {
                'strength': data['strength'],
                'points': data.get('points'),
                'sets_won': data.get('sets_won'),
                'sets_lost': data.get('sets_lost'),
                'wins': data.get('wins'),
                'losses': data.get('losses')
            }
            team_names.append(name)
        
        if not result_teams:
            return None, "Не удалось распознать команды", []
        
        return result_teams, None, team_names
        
    except Exception as e:
        return None, str(e), []

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Volley Odds - Точный расчёт</title>
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
        .team-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px;
            border-bottom: 1px solid #e0e0e0;
        }
        .team-row:last-child { border-bottom: none; }
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
        select {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 1em;
            background: white;
            cursor: pointer;
        }
        .team-stats {
            margin-top: 10px;
            padding: 10px;
            background: #f0f0f0;
            border-radius: 8px;
            font-size: 0.85em;
            display: none;
        }
        .team-stats.show {
            display: block;
        }
        .stats-item {
            margin: 5px 0;
            color: #333;
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
            <div>Расчёт на основе очков и партий</div>
        </div>
        <div class="content">
            <div class="section">
                <div class="section-title">🔗 Ссылка на турнирную таблицу</div>
                <div class="url-input-group">
                    <input type="url" id="tableUrl" placeholder="https://volley.ru/calendar/...">
                    <button id="parseBtn">📊 Загрузить команды</button>
                </div>
                <div id="parsedData" class="parsed-data"></div>
                <div id="status"></div>
            </div>

            <div class="section" id="teamsSection">
                <div class="section-title">🏟️ Выберите команды</div>
                <div id="teamSelectorsContainer">
                    <div class="empty-state">
                        ⚡ Загрузите турнирную таблицу<br>
                        Команды появятся здесь
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
                    🔥 Маржа: 7.5%<br>
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
                    teamsData = data.teams;
                    teamsList = data.team_names;
                    displayParsedData(data.teams);
                    createTeamSelectors(data.teams, data.team_names);
                    showStatus('✅ Загружено: ' + data.team_names.length + ' команд', 'success');
                } else {
                    showStatus('❌ ' + data.error, 'error');
                }
            } catch (err) {
                showStatus('❌ Ошибка: ' + err.message, 'error');
            } finally {
                btn.innerHTML = '📊 Загрузить команды';
                btn.disabled = false;
            }
        }

        function displayParsedData(teams) {
            const container = document.getElementById('parsedData');
            if (!teams || Object.keys(teams).length === 0) {
                container.innerHTML = '<div style="color: #666;">⚠️ Команды не найдены</div>';
                container.classList.add('active');
                return;
            }
            
            let html = '<div style="font-weight: bold; margin-bottom: 15px;">📊 Рейтинг команд:</div>';
            let rank = 1;
            
            for (const [name, data] of Object.entries(teams)) {
                const strength = data.strength;
                let color = strength > 70 ? '#28a745' : (strength > 40 ? '#ffc107' : '#dc3545');
                html += `
                    <div class="team-row">
                        <span style="min-width: 180px;"><strong>${rank}.</strong> ${name}</span>
                        <div class="strength-bar">
                            <div class="strength-fill" style="width: ${strength}%; background: ${color}"></div>
                        </div>
                        <span style="min-width: 45px;">${strength}%</span>
                    </div>
                `;
                rank++;
            }
            container.innerHTML = html;
            container.classList.add('active');
        }

        function createTeamSelectors(teams, teamNames) {
            const container = document.getElementById('teamSelectorsContainer');
            const optionsPanel = document.getElementById('optionsPanel');
            const calculateBtn = document.getElementById('calculateBtn');
            
            if (!teamNames || teamNames.length < 2) {
                container.innerHTML = '<div class="empty-state">⚠️ Нужно минимум 2 команды</div>';
                return;
            }
            
            let options = '';
            for (let i = 0; i < teamNames.length; i++) {
                const team = teamNames[i];
                options += `<option value="${team}">${team}</option>`;
            }
            
            container.innerHTML = `
                <div class="team-selector">
                    <div class="team-card">
                        <label>🏠 Домашняя команда</label>
                        <select id="homeTeam" onchange="showTeamStats('home')">${options}</select>
                        <div id="homeStats" class="team-stats"></div>
                    </div>
                    <div class="team-card">
                        <label>✈️ Гостевая команда</label>
                        <select id="awayTeam" onchange="showTeamStats('away')">${options}</select>
                        <div id="awayStats" class="team-stats"></div>
                    </div>
                </div>
            `;
            
            optionsPanel.style.display = 'block';
            calculateBtn.style.display = 'block';
            
            // Показываем статистику для выбранных команд
            showTeamStats('home');
            showTeamStats('away');
        }

        function showTeamStats(side) {
            const select = document.getElementById(`${side}Team`);
            const statsDiv = document.getElementById(`${side}Stats`);
            const teamName = select.value;
            const data = teamsData[teamName];
            
            if (!data) return;
            
            let statsHtml = '';
            if (data.points) statsHtml += `<div class="stats-item">🏆 Очки: ${data.points}</div>`;
            if (data.sets_won && data.sets_lost) statsHtml += `<div class="stats-item">🏐 Партии: ${data.sets_won}:${data.sets_lost}</div>`;
            if (data.wins && data.losses) statsHtml += `<div class="stats-item">📊 Победы/Поражения: ${data.wins}/${data.losses}</div>`;
            statsHtml += `<div class="stats-item">💪 Сила: ${data.strength}%</div>`;
            
            statsDiv.innerHTML = statsHtml;
            statsDiv.classList.add('show');
        }

        function getStrength(team) {
            return teamsData[team]?.strength || 50;
        }

        function calculateOdds() {
            const homeTeam = document.getElementById('homeTeam').value;
            const awayTeam = document.getElementById('awayTeam').value;
            const neutral = document.getElementById('neutralVenue').checked;

            if (homeTeam === awayTeam) {
                showStatus('Выберите разные команды', 'error');
                return;
            }

            let homeStrength = getStrength(homeTeam);
            let awayStrength = getStrength(awayTeam);

            // Бонус домашнего поля +5%
            if (!neutral) {
                homeStrength = Math.min(99, homeStrength + 5);
            }

            // Расчёт вероятностей
            let homeProb = 1 / (1 + Math.exp((awayStrength - homeStrength) / 15));
            
            // Корректировка
            homeProb = Math.min(0.95, Math.max(0.05, homeProb));
            
            // Вероятность тотала (3+ сетов)
            const drawProb = Math.abs(homeStrength - awayStrength) < 20 ? 0.22 : 0.12;
            
            let awayProb = 1 - homeProb - drawProb;
            if (awayProb < 0.05) {
                awayProb = 0.05;
                homeProb = 1 - drawProb - awayProb;
            }

            // Маржа 7.5%
            const margin = 0.075;
            const homeOdds = (1 / homeProb) * (1 - margin);
            const drawOdds = (1 / drawProb) * (1 - margin);
            const awayOdds = (1 / awayProb) * (1 - margin);

            document.getElementById('homeOdds').textContent = homeOdds.toFixed(2);
            document.getElementById('drawOdds').textContent = drawOdds.toFixed(2);
            document.getElementById('awayOdds').textContent = awayOdds.toFixed(2);
            document.getElementById('homeProb').textContent = `${(homeProb*100).toFixed(1)}%`;
            document.getElementById('drawProb').textContent = `${(drawProb*100).toFixed(1)}%`;
            document.getElementById('awayProb').textContent = `${(awayProb*100).toFixed(1)}%`;
            
            let rec = homeOdds > 1.8 && homeProb > 0.5 ? '🎯 Ценность в ставке на хозяев' : 
                      awayOdds > 2.0 && awayProb > 0.35 ? '🎯 Ценность в ставке на гостей' : 
                      '📊 Фаворит очевиден';
            document.getElementById('recommendation').textContent = rec;

            document.getElementById('result').style.display = 'block';
            document.getElementById('result').scrollIntoView({ behavior: 'smooth' });
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
