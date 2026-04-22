from flask import Flask, request, jsonify, render_template_string
import requests
from bs4 import BeautifulSoup
import re

app = Flask(__name__)

def parse_tournament_table(url):
    """Парсит турнирную таблицу и вычисляет силу команд на основе очков и партий"""
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
        max_sets_ratio = 0
        
        for table in tables:
            rows = table.find_all('tr')
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 8:  # Достаточно колонок для турнирной таблицы
                    # Извлекаем название команды (обычно в 1-2 колонке)
                    team_name = None
                    for col_idx in range(min(3, len(cols))):
                        text = cols[col_idx].get_text(strip=True)
                        # Очищаем от лишних символов
                        clean_name = re.sub(r'[^\w\s\u0400-\u04FF-]', '', text).strip()
                        clean_name = re.sub(r'\s+', ' ', clean_name)
                        # Убираем цифры и короткие слова
                        if len(clean_name) > 3 and not clean_name.isdigit():
                            team_name = clean_name
                            break
                    
                    if not team_name:
                        continue
                    
                    # Ищем числовые показатели
                    points = None
                    sets_won = None
                    sets_lost = None
                    wins = None
                    losses = None
                    
                    for idx, col in enumerate(cols):
                        text = col.get_text(strip=True)
                        # Ищем очки
                        if 'оч' in text.lower() or idx == len(cols) - 2:  # Очки часто в предпоследней колонке
                            points_match = re.search(r'(\d+)', text)
                            if points_match:
                                points = int(points_match.group(1))
                        
                        # Ищем партии (формат типа 89:31)
                        if ':' in text:
                            parts = text.split(':')
                            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                                sets_won = int(parts[0])
                                sets_lost = int(parts[1])
                        
                        # Ищем победы/поражения
                        if 'в' in text.lower() or 'п' in text.lower():
                            nums = re.findall(r'(\d+)', text)
                            if len(nums) >= 2:
                                wins = int(nums[0])
                                losses = int(nums[1])
                    
                    # Вычисляем силу команды
                    strength = 50  # по умолчанию
                    
                    # Приоритет 1: очки
                    if points is not None:
                        if points > max_points:
                            max_points = points
                        strength = points
                    
                    # Приоритет 2: соотношение партий
                    if sets_won is not None and sets_lost is not None and sets_lost > 0:
                        sets_ratio = (sets_won / sets_lost) * 100
                        if sets_ratio > max_sets_ratio:
                            max_sets_ratio = sets_ratio
                        if strength == 50 or strength < sets_ratio:
                            strength = sets_ratio
                    
                    # Приоритет 3: победы/поражения
                    if wins is not None and losses is not None and (wins + losses) > 0:
                        win_rate = (wins / (wins + losses)) * 100
                        if strength == 50 or strength < win_rate:
                            strength = win_rate
                    
                    teams_data[team_name] = {
                        'raw_name': team_name,
                        'points': points,
                        'sets_won': sets_won,
                        'sets_lost': sets_lost,
                        'wins': wins,
                        'losses': losses,
                        'raw_strength': strength
                    }
        
        # Нормализуем силу от 0 до 100 на основе максимальных значений
        if max_points > 0:
            for team in teams_data:
                if teams_data[team]['points'] is not None:
                    teams_data[team]['strength'] = (teams_data[team]['points'] / max_points) * 100
                elif teams_data[team]['raw_strength'] > 0:
                    if max_sets_ratio > 0:
                        teams_data[team]['strength'] = (teams_data[team]['raw_strength'] / max_sets_ratio) * 100
                    else:
                        teams_data[team]['strength'] = min(100, teams_data[team]['raw_strength'])
                else:
                    teams_data[team]['strength'] = 50
        else:
            for team in teams_data:
                teams_data[team]['strength'] = min(100, teams_data[team]['raw_strength'])
        
        # Сортируем по силе (от сильных к слабым)
        sorted_teams = sorted(teams_data.items(), key=lambda x: x[1]['strength'], reverse=True)
        
        # Формируем итоговый список
        result_teams = {}
        team_names = []
        
        for name, data in sorted_teams:
            final_strength = round(data['strength'], 1)
            result_teams[name] = {
                'strength': final_strength,
                'attack': final_strength,
                'defense': max(30, final_strength - 10),
                'homeBonus': 1.10,
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
    <title>Volley Odds - Правильный расчёт</title>
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
            max-height: 400px;
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
            background: linear-gradient(90deg, #dc3545, #ffc107, #28a745);
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
        .team-stats {
            font-size: 0.8em;
            color: #666;
            margin-top: 5px;
        }
        .rank-badge {
            display: inline-block;
            background: #e0e0e0;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.7em;
            margin-left: 8px;
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
            <div>Точный расчёт на основе очков и партий</div>
        </div>
        <div class="content">
            <div class="section">
                <div class="section-title">🔗 Ссылка на турнирную таблицу</div>
                <div class="url-input-group">
                    <input type="url" id="tableUrl" placeholder="https://volley.ru/calendar/...">
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
            
            let rank = 1;
            for (const [name, data] of Object.entries(teams)) {
                const strength = data.strength;
                let statsHtml = '';
                if (data.points) statsHtml += `⚡ Очки: ${data.points} | `;
                if (data.sets_won) statsHtml += `🏐 Партии: ${data.sets_won}:${data.sets_lost || '?'}`;
                
                html += `
                    <div class="team-strength">
                        <div style="min-width: 250px;">
                            <span style="font-weight: bold;">${rank}. 🏐 ${name}</span>
                            ${statsHtml ? `<div class="team-stats">${statsHtml}</div>` : ''}
                        </div>
                        <div class="strength-bar">
                            <div class="strength-fill" style="width: ${strength}%; background: ${strength > 70 ? '#28a745' : strength > 40 ? '#ffc107' : '#dc3545'}"></div>
                        </div>
                        <span style="font-weight: bold; min-width: 60px; color: ${strength > 70 ? '#28a745' : strength > 40 ? '#ffc107' : '#dc3545'}">${strength.toFixed(1)}%</span>
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
                container.innerHTML = '<div class="empty-state">⚠️ Найдено недостаточно команд (нужно минимум 2)</div>';
                return;
            }
            
            let homeOptions = '';
            let awayOptions = '';
            
            for (let i = 0; i < teamNames.length; i++) {
                const team = teamNames[i];
                const data = teams[team];
                const strength = data.strength;
                
                let statsText = '';
                if (data.points) statsText = ` | очки: ${data.points}`;
                if (data.sets_won) statsText += ` | партии: ${data.sets_won}:${data.sets_lost || '?'}`;
                
                const optionText = `${team} (сила ${strength.toFixed(1)}%${statsText})`;
                homeOptions += `<option value="${team}">${optionText}</option>`;
                awayOptions += `<option value="${team}">${optionText}</option>`;
            }
            
            container.innerHTML = `
                <div class="team-selector">
                    <div class="team-card">
                        <label>🏠 Домашняя команда</label>
                        <select id="homeTeam">
                            ${homeOptions}
                        </select>
                    </div>
                    <div class="team-card">
                        <label>✈️ Гостевая команда</label>
                        <select id="awayTeam">
                            ${awayOptions}
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

            // Бонус домашнего поля (+10% к силе)
            if (!isNeutral) {
                homeStrength = Math.min(100, homeStrength * 1.10);
            }

            // Расчёт вероятностей (чем выше сила, тем больше шансов)
            const strengthDiff = homeStrength - awayStrength;
            let homeProb = 1 / (1 + Math.exp(-strengthDiff / 15));
            
            // Корректировка для нейтрального поля
            if (isNeutral) {
                homeProb = (homeProb + 0.5) / 2;
            }

            // Вероятность тотала (3+ сетов) выше в равных матчах
            const drawProb = Math.abs(homeStrength - awayStrength) < 20 ? 0.20 : 0.10;
            
            let awayProb = 1 - homeProb - drawProb;
            if (awayProb < 0.05) {
                awayProb = 0.05;
                homeProb = 1 - drawProb - awayProb;
            }

            // Коэффициенты с маржой 5%
            const margin = 0.05;
            const homeOdds = (1 / homeProb) * (1 - margin);
            const drawOdds = (1 / drawProb) * (1 - margin);
            const awayOdds = (1 / awayProb) * (1 - margin);
            
            const actualMargin = ((1/homeOdds + 1/drawOdds + 1/awayOdds) - 1) * 100;

            let recommendation = '';
            if (homeOdds > 1.8 && homeProb > 0.5) {
                recommendation = '🎯 Хорошая ценность в ставке на хозяев';
            } else if (awayOdds > 2.0 && awayProb > 0.35) {
                recommendation = '🎯 Хорошая ценность в ставке на гостей';
            } else if (homeOdds < 1.3 && homeProb > 0.75) {
                recommendation = '📊 Фаворит очевиден, ставьте на него';
            } else {
                recommendation = '📊 Равный матч, смотрите live-ставки';
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
