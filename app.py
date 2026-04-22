from flask import Flask, request, jsonify, render_template_string
import requests
from bs4 import BeautifulSoup
import re
from collections import defaultdict

app = Flask(__name__)

def clean_team_name(text):
    """Очищает название команды от мусора"""
    text = re.sub(r'^\d+[-]?[йяе]?\s*', '', text)
    text = re.sub(r'\s*\d+[-]?[йяе]?\s*$', '', text)
    text = re.sub(r'\d{1,2}[:\.]\d{2}\s*(?:MCK|МСК|MSK)?', '', text)
    text = re.sub(r'\d{1,2}\.\d{1,2}\.\d{4}', '', text)
    text = re.sub(r'\b\d+\b', '', text)
    garbage = ['МСК', 'MCK', 'MSK', 'дата', 'time', 'date', 'время', '№', 'круг', 'тур', 'Время', 'местное', 'место', 'команда', 'игрок']
    for g in garbage:
        text = text.replace(g, '')
    text = re.sub(r'[^\w\s\u0400-\u04FF]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def calculate_ball_handicap(home_balls_won, home_balls_lost, away_balls_won, away_balls_lost, is_neutral=False):
    """Рассчитывает фору по мячам (очкам)"""
    if not all([home_balls_won, home_balls_lost, away_balls_won, away_balls_lost]):
        return None
    
    # Среднее количество очков за матч
    home_avg = home_balls_won / home_balls_lost if home_balls_lost > 0 else 1
    away_avg = away_balls_won / away_balls_lost if away_balls_lost > 0 else 1
    
    # Соотношение сил
    strength_ratio = home_avg / away_avg
    
    # Базовая фора (в очках)
    base_handicap = (strength_ratio - 1) * 25
    
    # Корректировка на домашнюю площадку
    if not is_neutral:
        base_handicap += 2.5
    
    # Округляем до 0.5
    handicap = round(base_handicap * 2) / 2
    
    # Ограничиваем диапазон
    handicap = max(-15.5, min(15.5, handicap))
    
    return handicap

def parse_tournament_table(url):
    """Парсит турнирную таблицу и все матчи"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        tables = soup.find_all('table')
        
        if not tables:
            return None, "Таблица не найдена", []
        
        teams_stats = {}
        team_names_set = set()
        
        # Находим все названия команд
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 2:
                    for idx, col in enumerate(cols[:3]):
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
                        if len(clean) > 2 and not clean.isdigit():
                            if clean.lower() not in ['дата', 'время', 'место', 'команда']:
                                team_names_set.add(clean)
        
        # Инициализируем статистику
        for name in team_names_set:
            teams_stats[name] = {
                'name': name,
                'balls_won': 0,
                'balls_lost': 0,
                'sets_won': 0,
                'sets_lost': 0,
                'matches': 0
            }
        
        # Парсим матчи для сбора статистики
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 4:
                    row_text = ' '.join([c.get_text(strip=True) for c in cols])
                    
                    # Ищем команды в строке
                    teams_in_row = []
                    for team in team_names_set:
                        if team.lower() in row_text.lower():
                            teams_in_row.append(team)
                    
                    if len(teams_in_row) == 2:
                        team1, team2 = teams_in_row[0], teams_in_row[1]
                        
                        # Ищем счета партий
                        set_matches = re.findall(r'(\d)[:-](\d)', row_text)
                        # Ищем очки
                        ball_matches = re.findall(r'(\d{1,3})[:-](\d{1,3})', row_text)
                        
                        # Партии
                        sets1 = 0
                        sets2 = 0
                        for s1, s2 in set_matches:
                            if int(s1) > int(s2):
                                sets1 += 1
                            else:
                                sets2 += 1
                        
                        if sets1 > 0 or sets2 > 0:
                            teams_stats[team1]['sets_won'] += sets1
                            teams_stats[team1]['sets_lost'] += sets2
                            teams_stats[team2]['sets_won'] += sets2
                            teams_stats[team2]['sets_lost'] += sets1
                            teams_stats[team1]['matches'] += 1
                            teams_stats[team2]['matches'] += 1
                        
                        # Очки
                        balls1 = 0
                        balls2 = 0
                        for b1, b2 in ball_matches:
                            if int(b1) > 0 and int(b2) > 0:
                                balls1 += int(b1)
                                balls2 += int(b2)
                        
                        if balls1 > 0 or balls2 > 0:
                            teams_stats[team1]['balls_won'] += balls1
                            teams_stats[team1]['balls_lost'] += balls2
                            teams_stats[team2]['balls_won'] += balls2
                            teams_stats[team2]['balls_lost'] += balls1
        
        # Формируем результат
        result_teams = {}
        team_names = []
        
        for name, stats in teams_stats.items():
            if stats['balls_won'] == 0 and stats['sets_won'] == 0:
                continue
            
            result_teams[name] = {
                'name': name,
                'balls_won': stats['balls_won'] if stats['balls_won'] > 0 else None,
                'balls_lost': stats['balls_lost'] if stats['balls_lost'] > 0 else None,
                'sets_won': stats['sets_won'] if stats['sets_won'] > 0 else None,
                'sets_lost': stats['sets_lost'] if stats['sets_lost'] > 0 else None,
                'matches': stats['matches']
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
        .final-result {
            background: rgba(255,215,0,0.2);
            border: 2px solid gold;
        }
        .handicap-card {
            background: rgba(0,255,0,0.15);
            border: 1px solid #4CAF50;
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
            <div class="section">
                <div class="section-title">🔗 Ссылка на турнирную таблицу</div>
                <div class="url-input-group">
                    <input type="url" id="tableUrl" placeholder="https://volley.ru/calendar/...">
                    <button id="parseBtn">📊 Загрузить данные</button>
                </div>
                <div id="parsedData" class="parsed-data"></div>
                <div id="status"></div>
            </div>

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

            <div class="section" id="teamsSection">
                <div class="section-title">🏟️ Выберите команды из таблицы</div>
                <div id="teamSelectorsContainer">
                    <div class="empty-state">
                        ⚡ Загрузите турнирную таблицу<br>
                        Команды появятся здесь
                    </div>
                </div>
            </div>

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
                
                <!-- Фора по мячам -->
                <div class="result-card handicap-card" style="margin-top: 15px;">
                    <div class="label">🏐 ФОРА ПО МЯЧАМ (ОЧКАМ)</div>
                    <div class="value" id="handicap">-</div>
                    <div class="small" id="handicapDesc">-</div>
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
            
            let html = '<div style="font-weight: bold; margin-bottom: 15px;">📊 Команды из таблицы:</div>';
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
            
            return { homeOdds: Math.round(odds * 100) / 100, homeProb: Math.round(homeProb * 1000) / 10, awayOdds: Math.round(awayOdds * 100) / 100, awayProb: Math.round(awayProb * 1000) / 10 };
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
            
            return { homeOdds: Math.round(odds * 100) / 100, homeProb: Math.round(homeProb * 1000) / 10, awayOdds: Math.round(awayOdds * 100) / 100, awayProb: Math.round(awayProb * 1000) / 10 };
        }

        function calculateHandicap(homeBallsWon, homeBallsLost, awayBallsWon, awayBallsLost, isNeutral) {
            if (!homeBallsWon || !homeBallsLost || !awayBallsWon || !awayBallsLost) return null;
            
            let homeAvg = homeBallsWon / homeBallsLost;
            let awayAvg = awayBallsWon / awayBallsLost;
            
            let strengthRatio = homeAvg / awayAvg;
            let handicap = (strengthRatio - 1) * 25;
            
            if (!isNeutral) handicap += 2.5;
            
            handicap = Math.round(handicap * 2) / 2;
            handicap = Math.max(-15.5, Math.min(15.5, handicap));
            
            return handicap;
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
            
            // Расчёт PR
            let prResult = null;
            let prAvailable = homeBallsWon && homeBallsLost && awayBallsWon && awayBallsLost;
            if (prAvailable) {
                prResult = calculatePR(homeBallsWon, homeBallsLost, awayBallsWon, awayBallsLost, isNeutral);
            }
            
            // Расчёт BT
            let btResult = null;
            let btAvailable = homeSetsWon && homeSetsLost && awaySetsWon && awaySetsLost;
            if (btAvailable) {
                btResult = calculateBT(homeSetsWon, homeSetsLost, awaySetsWon, awaySetsLost, isNeutral);
            }
            
            // Финальный результат
            let finalOdds = null;
            let finalProb = null;
            let totalUnder = false;
            
            if (prResult && btResult) {
                finalOdds = Math.round(((prResult.homeOdds + btResult.homeOdds) / 2) * 100) / 100;
                finalProb = Math.round(((prResult.homeProb + btResult.homeProb) / 2) * 10) / 10;
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
            
            // Расчёт форы по мячам
            let handicap = null;
            if (prAvailable) {
                handicap = calculateHandicap(homeBallsWon, homeBallsLost, awayBallsWon, awayBallsLost, isNeutral);
            }
            
            // Отображение
            document.getElementById('prOdds').textContent = prResult ? `${prResult.homeOdds} / ${prResult.awayOdds}` : '—';
            document.getElementById('prProb').textContent = prResult ? `${homeName}: ${prResult.homeProb}% | ${awayName}: ${prResult.awayProb}%` : 'Нет данных по очкам';
            document.getElementById('btOdds').textContent = btResult ? `${btResult.homeOdds} / ${btResult.awayOdds}` : '—';
            document.getElementById('btProb').textContent = btResult ? `${homeName}: ${btResult.homeProb}% | ${awayName}: ${btResult.awayProb}%` : 'Нет данных по сетам';
            document.getElementById('finalOdds').textContent = finalOdds ? `${finalOdds} / ${finalOdds ? Math.round((1/finalOdds*100/0.925) * 100) / 100 : '-'}` : '—';
            document.getElementById('finalProb').textContent = finalProb ? `${homeName}: ${finalProb}% | ${awayName}: ${Math.round((100-finalProb) * 10) / 10}%` : '—';
            
            // Отображение форы
            if (handicap !== null) {
                let handicapText = '';
                if (handicap > 0) {
                    handicapText = `${homeName} (${handicap}) : ${awayName} (${-handicap})`;
                    document.getElementById('handicapDesc').innerHTML = `🏠 ${homeName} фаворит на ${handicap} очков<br>✈️ ${awayName} андердог (+${-handicap})`;
                } else if (handicap < 0) {
                    handicapText = `${homeName} (${handicap}) : ${awayName} (${-handicap})`;
                    document.getElementById('handicapDesc').innerHTML = `🏠 ${homeName} андердог (${handicap})<br>✈️ ${awayName} фаворит на ${-handicap} очков`;
                } else {
                    handicapText = `${homeName} (0) : ${awayName} (0)`;
                    document.getElementById('handicapDesc').innerHTML = `⚖️ Равные команды, фора 0`;
                }
                document.getElementById('handicap').textContent = handicapText;
            } else {
                document.getElementById('handicap').textContent = '—';
                document.getElementById('handicapDesc').textContent = 'Нет данных для расчёта форы';
            }
            
            let totalHtml = '';
            if (totalUnder) {
                totalHtml = '<div style="background: rgba(255,215,0,0.3); padding: 10px; border-radius: 8px;">📉 Выносной матч! Рекомендуется рассмотреть тотал меньше (Under). Например, Total Points Under 39.5</div>';
            } else if (prResult && btResult && Math.abs(prResult.homeProb - btResult.homeProb) < 15) {
                totalHtml = '<div style="background: rgba(255,215,0,0.2); padding: 10px; border-radius: 8px;">⚖️ PR и BT совпадают. Матч ожидается конкурентным.</div>';
            }
            document.getElementById('totalInfo').innerHTML = totalHtml;
            
            let recommendation = '';
            if (handicap !== null && Math.abs(handicap) > 5) {
                recommendation = `🎯 Фора ${handicap > 0 ? homeName : awayName} ${Math.abs(handicap)} с хорошими шансами`;
            } else if (finalOdds && finalOdds > 1.8 && finalProb > 55) {
                recommendation = `🎯 Ценность в ставке на ${homeName} (коэффициент ${finalOdds})`;
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
