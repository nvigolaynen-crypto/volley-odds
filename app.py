from flask import Flask, request, jsonify, render_template_string
import requests
from bs4 import BeautifulSoup
import re
import math

app = Flask(__name__)

def clean_team_name(text):
    """Очищает название команды от мусора"""
    text = re.sub(r'^\d+[-]?[йяе]?\s*', '', text)
    text = re.sub(r'\s*\d+[-]?[йяе]?\s*$', '', text)
    text = re.sub(r'\d{1,2}[:\.]\d{2}\s*(?:MCK|МСК|MSK)?', '', text)
    text = re.sub(r'\d{1,2}\.\d{1,2}\.\d{4}', '', text)
    text = re.sub(r'\b\d+\b', '', text)
    garbage = ['МСК', 'MCK', 'MSK', 'дата', 'time', 'date', 'время', '№', 'круг', 'тур', 'Время', 'местное', 'место']
    for g in garbage:
        text = text.replace(g, '')
    text = re.sub(r'[^\w\s\u0400-\u04FF]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def calculate_pr_odds(balls_won, balls_lost, home_bonus=1.05):
    """Расчёт коэффициента на основе очков (PR)"""
    if balls_won is None or balls_lost is None or balls_lost == 0:
        return None
    
    # Соотношение выигранных/проигранных очков
    ratio = balls_won / balls_lost
    
    # Вероятность победы на основе очков
    prob = ratio / (1 + ratio)
    
    # Применяем бонус домашней площадки
    prob = prob * home_bonus
    prob = min(0.95, max(0.05, prob))
    
    # Коэффициент с маржой 7.5%
    margin = 0.075
    odds = (1 / prob) * (1 - margin)
    
    return round(odds, 2), round(prob * 100, 1)

def calculate_bt_odds(sets_won, sets_lost, home_bonus=1.03):
    """Расчёт коэффициента на основе сетов (BT)"""
    if sets_won is None or sets_lost is None or sets_lost == 0:
        return None
    
    # Соотношение выигранных/проигранных сетов
    ratio = sets_won / sets_lost
    
    # Вероятность победы на основе сетов (более консервативно)
    prob = ratio / (1 + ratio)
    
    # Применяем бонус домашней площадки (меньше, чем для очков)
    prob = prob * home_bonus
    prob = min(0.95, max(0.05, prob))
    
    # Коэффициент с маржой 7.5%
    margin = 0.075
    odds = (1 / prob) * (1 - margin)
    
    return round(odds, 2), round(prob * 100, 1)

def check_total_under(home_strength_pr, away_strength_pr, home_strength_bt, away_strength_bt):
    """Проверка на тотал (выносной матч)"""
    # Если разница в силе большая - тотал меньше
    diff_pr = abs(home_strength_pr - away_strength_pr) if home_strength_pr and away_strength_pr else 0
    diff_bt = abs(home_strength_bt - away_strength_bt) if home_strength_bt and away_strength_bt else 0
    
    if diff_pr > 40 or diff_bt > 35:
        return True
    return False

def parse_tournament_table(url):
    """Парсит турнирную таблицу для PR и BT"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        tables = soup.find_all('table')
        
        if not tables:
            return None, "Таблица не найдена", []
        
        teams_data = {}
        
        for table in tables:
            rows = table.find_all('tr')
            
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 4:
                    # Поиск названия команды
                    team_name = None
                    for idx, col in enumerate(cols[:3]):
                        text = col.get_text(strip=True)
                        if len(text) < 2:
                            continue
                        if re.match(r'^\d+$', text):
                            continue
                        if re.match(r'^\d{1,2}[:\.]\d{2}$', text):
                            continue
                        clean = clean_team_name(text)
                        if len(clean) > 2 and not clean.isdigit():
                            if clean.lower() not in ['дата', 'время', 'место', 'команда']:
                                team_name = clean
                                break
                    
                    if not team_name:
                        continue
                    
                    if team_name in teams_data:
                        continue
                    
                    # Собираем всю строку
                    row_text = ' '.join([c.get_text(strip=True) for c in cols])
                    
                    # Поиск мячей (очков) - формат 89:31 или 89-31
                    balls_won = None
                    balls_lost = None
                    sets_won = None
                    sets_lost = None
                    
                    # Ищем все пары чисел
                    matches = re.findall(r'(\d+)[:-](\d+)', row_text)
                    
                    for w, l in matches:
                        w_int = int(w)
                        l_int = int(l)
                        # Мячи обычно в диапазоне 20-150
                        if 20 <= w_int <= 200 and 20 <= l_int <= 200:
                            balls_won = w_int
                            balls_lost = l_int
                        # Сеты обычно 0-5
                        elif w_int <= 5 and l_int <= 5:
                            sets_won = w_int
                            sets_lost = l_int
                    
                    teams_data[team_name] = {
                        'name': team_name,
                        'balls_won': balls_won,
                        'balls_lost': balls_lost,
                        'sets_won': sets_won,
                        'sets_lost': sets_lost
                    }
        
        if not teams_data:
            return None, "Не удалось распознать команды", []
        
        return teams_data, None, list(teams_data.keys())
        
    except Exception as e:
        return None, str(e), []

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Volley Odds - PR+BT | Shtopor</title>
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
        .badge {
            display: inline-block;
            background: rgba(255,255,255,0.2);
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
        }
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
        .stats-input {
            margin-top: 15px;
        }
        .stats-input input {
            margin-bottom: 10px;
        }
        .options {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
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
        .result h3 { font-size: 1.5em; margin-bottom: 20px; }
        .result-card {
            background: rgba(255,255,255,0.15);
            padding: 20px;
            border-radius: 12px;
            margin-bottom: 15px;
        }
        .result-card .label {
            font-size: 0.85em;
            opacity: 0.8;
            margin-bottom: 5px;
        }
        .result-card .value {
            font-size: 2em;
            font-weight: bold;
        }
        .result-card .small {
            font-size: 0.9em;
            margin-top: 5px;
        }
        .final-result {
            background: rgba(255,215,0,0.2);
            border: 2px solid gold;
        }
        .manual-stats {
            display: none;
        }
        .manual-stats.active {
            display: block;
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
        .team-stats {
            margin-top: 10px;
            padding: 10px;
            background: #f0f0f0;
            border-radius: 8px;
            font-size: 0.85em;
            display: none;
        }
        .team-stats.show { display: block; }
        .stats-item { margin: 5px 0; color: #333; }
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
            .team-selector { grid-template-columns: 1fr; }
            .url-input-group { flex-direction: column; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏐 Volley Odds by Shtopor</h1>
            <div class="badge">PR+BT | Professional Betting Tool</div>
        </div>
        <div class="content">
            <!-- Ссылка на турнирную таблицу -->
            <div class="section">
                <div class="section-title">🔗 Ссылка на турнирную таблицу</div>
                <div class="url-input-group">
                    <input type="url" id="tableUrl" placeholder="https://volley.ru/calendar/...">
                    <button id="parseBtn">📊 Загрузить данные</button>
                </div>
                <div id="parsedData" class="parsed-data"></div>
                <div id="status"></div>
            </div>

            <!-- Ручной ввод -->
            <div class="section">
                <div class="section-title">✏️ Ручной ввод статистики</div>
                <button id="manualStatsBtn" style="background: #28a745; width: auto; padding: 10px 20px;">📝 Ввести статистику вручную</button>
                <div id="manualStats" class="manual-stats">
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 15px;">
                        <div>
                            <label style="font-weight: bold;">🏠 Хозяева:</label>
                            <input type="text" id="homeName" placeholder="Название команды" value="Хозяева">
                            <input type="number" id="homeSetsWon" placeholder="Выигранные сеты" value="">
                            <input type="number" id="homeSetsLost" placeholder="Проигранные сеты" value="">
                            <input type="number" id="homeBallsWon" placeholder="Выигранные очки" value="">
                            <input type="number" id="homeBallsLost" placeholder="Проигранные очки" value="">
                        </div>
                        <div>
                            <label style="font-weight: bold;">✈️ Гости:</label>
                            <input type="text" id="awayName" placeholder="Название команды" value="Гости">
                            <input type="number" id="awaySetsWon" placeholder="Выигранные сеты" value="">
                            <input type="number" id="awaySetsLost" placeholder="Проигранные сеты" value="">
                            <input type="number" id="awayBallsWon" placeholder="Выигранные очки" value="">
                            <input type="number" id="awayBallsLost" placeholder="Проигранные очки" value="">
                        </div>
                    </div>
                </div>
            </div>

            <!-- Выбор команд из таблицы -->
            <div class="section" id="teamsSection">
                <div class="section-title">🏟️ Выберите команды из таблицы</div>
                <div id="teamSelectorsContainer">
                    <div class="empty-state">
                        ⚡ Загрузите турнирную таблицу<br>
                        Команды появятся здесь
                    </div>
                </div>
            </div>

            <!-- Настройки -->
            <div class="section">
                <div class="section-title">⚙️ Настройки</div>
                <div class="options">
                    <label class="checkbox-label">
                        <input type="checkbox" id="neutralVenue"> 🏟️ Нейтральная площадка
                    </label>
                    <label class="checkbox-label">
                        <input type="checkbox" id="useManual"> 📊 Использовать ручной ввод
                    </label>
                </div>
            </div>

            <button id="calculateBtn" onclick="calculateOdds()">🎯 Рассчитать котировки</button>

            <div id="result" class="result">
                <h3>📈 Результат расчёта</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px;">
                    <div class="result-card">
                        <div class="label">PR (Личные очки)</div>
                        <div class="value" id="prOdds">-</div>
                        <div class="small" id="prProb">-</div>
                    </div>
                    <div class="result-card">
                        <div class="label">BT (Сеты)</div>
                        <div class="value" id="btOdds">-</div>
                        <div class="small" id="btProb">-</div>
                    </div>
                    <div class="result-card final-result">
                        <div class="label">⭐ FINAL RESULT</div>
                        <div class="value" id="finalOdds">-</div>
                        <div class="small" id="finalProb">-</div>
                    </div>
                </div>
                <div id="totalInfo" style="margin-top: 15px; padding: 10px; background: rgba(255,255,255,0.1); border-radius: 8px;"></div>
                <div style="margin-top: 15px;">
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
                btn.innerHTML = '📊 Загрузить данные';
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
            
            let html = '<div style="font-weight: bold; margin-bottom: 15px;">📊 Данные из таблицы:</div>';
            for (const [name, data] of Object.entries(teams)) {
                html += `<div class="team-row">
                    <span style="min-width: 200px;">🏐 ${name}</span>
                    <span style="font-size: 0.8em; color: #666;">`;
                if (data.balls_won) html += `🎯 Очки: ${data.balls_won}:${data.balls_lost} `;
                if (data.sets_won) html += `🏆 Сеты: ${data.sets_won}:${data.sets_lost}`;
                html += `</span></div>`;
            }
            container.innerHTML = html;
            container.classList.add('active');
        }

        function createTeamSelectors(teams, teamNames) {
            const container = document.getElementById('teamSelectorsContainer');
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
            
            showTeamStats('home');
            showTeamStats('away');
        }

        function showTeamStats(side) {
            const select = document.getElementById(`${side}Team`);
            if (!select) return;
            const statsDiv = document.getElementById(`${side}Stats`);
            const teamName = select.value;
            const data = teamsData[teamName];
            
            if (!data) return;
            
            let statsHtml = '';
            if (data.balls_won && data.balls_lost) {
                statsHtml += `<div class="stats-item">🎯 Очки: ${data.balls_won}:${data.balls_lost}</div>`;
            }
            if (data.sets_won && data.sets_lost) {
                statsHtml += `<div class="stats-item">🏆 Сеты: ${data.sets_won}:${data.sets_lost}</div>`;
            }
            statsDiv.innerHTML = statsHtml;
            statsDiv.classList.add('show');
        }

        function getTeamData(teamName) {
            return teamsData[teamName] || null;
        }

        function calculatePR(homeBallsWon, homeBallsLost, awayBallsWon, awayBallsLost, isNeutral) {
            if (!homeBallsWon || !homeBallsLost || !awayBallsWon || !awayBallsLost) return null;
            if (homeBallsLost === 0 || awayBallsLost === 0) return null;
            
            let homeRatio = homeBallsWon / homeBallsLost;
            let awayRatio = awayBallsWon / awayBallsLost;
            
            let homeProb = homeRatio / (homeRatio + awayRatio);
            
            if (!isNeutral) homeProb *= 1.05;
            homeProb = Math.min(0.95, Math.max(0.05, homeProb));
            
            const margin = 0.075;
            const odds = (1 / homeProb) * (1 - margin);
            const awayProb = 1 - homeProb;
            const awayOdds = (1 / awayProb) * (1 - margin);
            
            return { homeOdds: round(odds, 2), homeProb: round(homeProb * 100, 1), awayOdds: round(awayOdds, 2), awayProb: round(awayProb * 100, 1) };
        }

        function calculateBT(homeSetsWon, homeSetsLost, awaySetsWon, awaySetsLost, isNeutral) {
            if (!homeSetsWon || !homeSetsLost || !awaySetsWon || !awaySetsLost) return null;
            if (homeSetsLost === 0 || awaySetsLost === 0) return null;
            
            let homeRatio = homeSetsWon / homeSetsLost;
            let awayRatio = awaySetsWon / awaySetsLost;
            
            let homeProb = homeRatio / (homeRatio + awayRatio);
            
            if (!isNeutral) homeProb *= 1.03;
            homeProb = Math.min(0.95, Math.max(0.05, homeProb));
            
            const margin = 0.075;
            const odds = (1 / homeProb) * (1 - margin);
            const awayProb = 1 - homeProb;
            const awayOdds = (1 / awayProb) * (1 - margin);
            
            return { homeOdds: round(odds, 2), homeProb: round(homeProb * 100, 1), awayOdds: round(awayOdds, 2), awayProb: round(awayProb * 100, 1) };
        }

        function round(num, decimals) {
            return Math.round(num * Math.pow(10, decimals)) / Math.pow(10, decimals);
        }

        function calculateOdds() {
            const isNeutral = document.getElementById('neutralVenue').checked;
            const useManual = document.getElementById('useManual').checked;
            
            let homeName, awayName;
            let homeBallsWon, homeBallsLost, homeSetsWon, homeSetsLost;
            let awayBallsWon, awayBallsLost, awaySetsWon, awaySetsLost;
            
            if (useManual) {
                homeName = document.getElementById('homeName').value || 'Хозяева';
                awayName = document.getElementById('awayName').value || 'Гости';
                homeSetsWon = parseInt(document.getElementById('homeSetsWon').value) || null;
                homeSetsLost = parseInt(document.getElementById('homeSetsLost').value) || null;
                homeBallsWon = parseInt(document.getElementById('homeBallsWon').value) || null;
                homeBallsLost = parseInt(document.getElementById('homeBallsLost').value) || null;
                awaySetsWon = parseInt(document.getElementById('awaySetsWon').value) || null;
                awaySetsLost = parseInt(document.getElementById('awaySetsLost').value) || null;
                awayBallsWon = parseInt(document.getElementById('awayBallsWon').value) || null;
                awayBallsLost = parseInt(document.getElementById('awayBallsLost').value) || null;
            } else {
                const homeTeam = document.getElementById('homeTeam')?.value;
                const awayTeam = document.getElementById('awayTeam')?.value;
                if (!homeTeam || !awayTeam) {
                    showStatus('Выберите команды или включите ручной ввод', 'error');
                    return;
                }
                homeName = homeTeam;
                awayName = awayTeam;
                const homeData = getTeamData(homeTeam);
                const awayData = getTeamData(awayTeam);
                if (homeData) {
                    homeSetsWon = homeData.sets_won;
                    homeSetsLost = homeData.sets_lost;
                    homeBallsWon = homeData.balls_won;
                    homeBallsLost = homeData.balls_lost;
                }
                if (awayData) {
                    awaySetsWon = awayData.sets_won;
                    awaySetsLost = awayData.sets_lost;
                    awayBallsWon = awayData.balls_won;
                    awayBallsLost = awayData.balls_lost;
                }
            }
            
            if (homeName === awayName) {
                showStatus('Выберите разные команды', 'error');
                return;
            }
            
            // Расчёт PR (по очкам)
            let prResult = null;
            let prAvailable = homeBallsWon && homeBallsLost && awayBallsWon && awayBallsLost;
            if (prAvailable) {
                prResult = calculatePR(homeBallsWon, homeBallsLost, awayBallsWon, awayBallsLost, isNeutral);
            }
            
            // Расчёт BT (по сетам)
            let btResult = null;
            let btAvailable = homeSetsWon && homeSetsLost && awaySetsWon && awaySetsLost;
            if (btAvailable) {
                btResult = calculateBT(homeSetsWon, homeSetsLost, awaySetsWon, awaySetsLost, isNeutral);
            }
            
            // Финальный результат (среднее)
            let finalOdds = null;
            let finalProb = null;
            let totalUnder = false;
            
            if (prResult && btResult) {
                finalOdds = round((prResult.homeOdds + btResult.homeOdds) / 2, 2);
                finalProb = round((prResult.homeProb + btResult.homeProb) / 2, 1);
                // Проверка на тотал
                if (Math.abs(prResult.homeProb - prResult.awayProb) > 40 || Math.abs(btResult.homeProb - btResult.awayProb) > 35) {
                    totalUnder = true;
                }
            } else if (prResult) {
                finalOdds = prResult.homeOdds;
                finalProb = prResult.homeProb;
            } else if (btResult) {
                finalOdds = btResult.homeOdds;
                finalProb = btResult.homeProb;
            }
            
            // Отображение
            document.getElementById('prOdds').textContent = prResult ? `${prResult.homeOdds} / ${prResult.awayOdds}` : '—';
            document.getElementById('prProb').textContent = prResult ? `${homeName}: ${prResult.homeProb}% | ${awayName}: ${prResult.awayProb}%` : 'Нет данных по очкам';
            document.getElementById('btOdds').textContent = btResult ? `${btResult.homeOdds} / ${btResult.awayOdds}` : '—';
            document.getElementById('btProb').textContent = btResult ? `${homeName}: ${btResult.homeProb}% | ${awayName}: ${btResult.awayProb}%` : 'Нет данных по сетам';
            document.getElementById('finalOdds').textContent = finalOdds ? `${finalOdds} / ${finalOdds ? round(1/finalOdds*100/0.925, 2) : '-'}` : '—';
            document.getElementById('finalProb').textContent = finalProb ? `${homeName}: ${finalProb}% | ${awayName}: ${round(100-finalProb, 1)}%` : '—';
            
            let totalHtml = '';
            if (totalUnder) {
                totalHtml = '<div style="background: rgba(255,215,0,0.3); padding: 10px; border-radius: 8px;">📉 Выносной матч! Рекомендуется рассмотреть тотал меньше (Under). Например, Total Points Under 39.5</div>';
            } else if (prResult && btResult && Math.abs(prResult.homeProb - btResult.homeProb) < 15) {
                totalHtml = '<div style="background: rgba(255,215,0,0.2); padding: 10px; border-radius: 8px;">⚖️ PR и BT совпадают. Матч ожидается конкурентным.</div>';
            } else if (prResult && btResult) {
                totalHtml = '<div style="background: rgba(255,165,0,0.2); padding: 10px; border-radius: 8px;">⚠️ Расхождение между PR и BT. Рекомендуется осторожность.</div>';
            }
            document.getElementById('totalInfo').innerHTML = totalHtml;
            
            let recommendation = '';
            if (finalOdds && finalOdds > 1.8 && finalProb > 55) {
                recommendation = `🎯 Ценность в ставке на ${homeName} (коэффициент ${finalOdds})`;
            } else if (finalOdds && finalOdds < 1.3 && finalProb > 75) {
                recommendation = `📊 Фаворит очевиден - ${homeName}`;
            } else if (totalUnder) {
                recommendation = '📉 Рекомендуется рассмотреть тотал меньше (Under)';
            } else {
                recommendation = '📊 Равный матч, смотрите live';
            }
            document.getElementById('recommendation').textContent = recommendation;
            
            document.getElementById('result').style.display = 'block';
            document.getElementById('result').scrollIntoView({ behavior: 'smooth' });
        }

        function showStatus(msg, type) {
            const div = document.getElementById('status');
            div.innerHTML = `<div class="status ${type}">${msg}</div>`;
            setTimeout(() => div.innerHTML = '', 5000);
        }

        document.getElementById('parseBtn').onclick = parseTable;
        document.getElementById('manualStatsBtn').onclick = () => {
            document.getElementById('manualStats').classList.toggle('active');
        };
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
