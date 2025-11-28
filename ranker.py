import pandas as pd
import json
import os
import requests
import re
from datetime import datetime
import pytz

# --- CONSTANTS ---
IST_TZ = pytz.timezone('Asia/Kolkata')
STATS_CSV = 'stats.csv'
TEAM_CSV = 'team_stats.csv'
INJURY_HTML = 'injuries.html'
TEAM_LOGOS_URL = "https://cdn.nba.com/logos/nba/{}/primary/L/logo.svg"

# --- TEAM MAPPER ---
TEAM_MAP = {
    'Atlanta Hawks': 'ATL', 'Boston Celtics': 'BOS', 'Brooklyn Nets': 'BKN',
    'Charlotte Hornets': 'CHA', 'Chicago Bulls': 'CHI', 'Cleveland Cavaliers': 'CLE',
    'Dallas Mavericks': 'DAL', 'Denver Nuggets': 'DEN', 'Detroit Pistons': 'DET',
    'Golden State Warriors': 'GSW', 'Houston Rockets': 'HOU', 'Indiana Pacers': 'IND',
    'Los Angeles Clippers': 'LAC', 'Los Angeles Lakers': 'LAL', 'Memphis Grizzlies': 'MEM',
    'Miami Heat': 'MIA', 'Milwaukee Bucks': 'MIL', 'Minnesota Timberwolves': 'MIN',
    'New Orleans Pelicans': 'NOP', 'New York Knicks': 'NYK', 'Oklahoma City Thunder': 'OKC',
    'Orlando Magic': 'ORL', 'Philadelphia 76ers': 'PHI', 'Phoenix Suns': 'PHX',
    'Portland Trail Blazers': 'POR', 'Sacramento Kings': 'SAC', 'San Antonio Spurs': 'SAS',
    'Toronto Raptors': 'TOR', 'Utah Jazz': 'UTA', 'Washington Wizards': 'WAS'
}

# --- 1. LOAD PLAYERS (Manual CSV) ---
def load_players():
    if not os.path.exists(STATS_CSV): return {}
    try:
        df = pd.read_csv(STATS_CSV)
        df = df[df['Player'] != 'Player']
        BREF_ABBR = {'BRK': 'BKN', 'CHO': 'CHA', 'PHO': 'PHX', 'TOT': 'SKIP'}
        rosters = {}
        for _, row in df.iterrows():
            raw_team = row.get('Team', row.get('Tm', 'SKIP'))
            team = BREF_ABBR.get(raw_team, raw_team)
            if team == 'SKIP': continue
            try:
                fp = float(row['PTS']) + (1.2*float(row['TRB'])) + (1.5*float(row['AST'])) + \
                     (3*float(row['STL'])) + (3*float(row['BLK'])) - float(row.get('TOV', 0))
                if team not in rosters: rosters[team] = []
                rosters[team].append({'name': str(row['Player']).split("\\")[0], 'fp': round(fp, 1)})
            except: continue
        for t in rosters: rosters[t].sort(key=lambda x: x['fp'], reverse=True)
        return rosters
    except: return {}

# --- 2. LOAD TEAM STATS (Manual CSV) ---
def load_team_stats():
    # Defaults: 50% Win Rate, 0 Net Rating
    defaults = {k: {'pace': 100.0, 'net': 0.0, 'ortg': 115.0, 'wins': 0.5} for k in TEAM_MAP.values()}
    if not os.path.exists(TEAM_CSV): return defaults
    
    try:
        df = pd.read_csv(TEAM_CSV)
        if 'Team' in df.columns: df = df[df['Team'] != 'League Average']
        
        for _, row in df.iterrows():
            full_name = str(row['Team']).replace('*', '')
            abbr = TEAM_MAP.get(full_name)
            if abbr:
                try:
                    # Calculate Win % (W / (W+L))
                    w = float(row['W'])
                    l = float(row['L'])
                    win_pct = w / (w + l) if (w + l) > 0 else 0.5
                    
                    defaults[abbr] = {
                        'pace': float(row['Pace']),
                        'net': float(row['NRtg']),
                        'ortg': float(row['ORtg']),
                        'wins': win_pct
                    }
                except: continue
        return defaults
    except: return defaults

# --- 3. LOAD INJURIES (CBS) ---
def load_injuries():
    if not os.path.exists(INJURY_HTML): return set()
    try:
        dfs = pd.read_html(INJURY_HTML)
        injured_set = set()
        for df in dfs:
            if 'Player' in df.columns:
                status_col = 'Injury Status' if 'Injury Status' in df.columns else 'Status'
                if status_col in df.columns:
                    for _, row in df.iterrows():
                        try:
                            if "out" in str(row[status_col]).lower() or "doubtful" in str(row[status_col]).lower():
                                injured_set.add(row['Player'])
                        except: continue
        return injured_set
    except: return set()

# --- 4. SCHEDULE & TV (CDN) ---
def get_schedule_from_cdn(target_date_str):
    url = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
    try:
        r = requests.get(url, timeout=5)
        data = r.json()
        dt = datetime.strptime(target_date_str, "%Y-%m-%d")
        target_fmt = dt.strftime("%m/%d/%Y")
        
        games = []
        for d in data['leagueSchedule']['gameDates']:
            if target_fmt in d['gameDate']:
                for game in d['games']:
                    # Extract National TV
                    nat_tv = ""
                    broadcasters = game.get('broadcasters', {}).get('national', [])
                    if broadcasters:
                        nat_tv = broadcasters[0]['broadcasterDisplay']
                    
                    games.append({
                        'home': game['homeTeam']['teamTricode'],
                        'away': game['awayTeam']['teamTricode'],
                        'home_id': game['homeTeam']['teamId'],
                        'away_id': game['awayTeam']['teamId'],
                        'time': game.get('gameStatusText', ''),
                        'tv': nat_tv
                    })
                break
        return pd.DataFrame(games)
    except: return pd.DataFrame()

# --- ODDS ---
try: from odds import get_betting_spreads
except: 
    def get_betting_spreads(): return {}

# --- HELPER: Time Parsing for Sorting ---
def parse_time(time_str, date_str):
    # Returns 24h float for sorting (e.g. 6.5 for 6:30 AM)
    try:
        match = re.search(r"(\d+):(\d+)\s+(am|pm)", time_str, re.IGNORECASE)
        if not match: return 0
        h, m, p = match.groups()
        h = int(h) + (12 if p.lower() == 'pm' and int(h) != 12 else 0)
        h = 0 if p.lower() == 'am' and int(h) == 12 else h
        return h + (int(m)/60)
    except: return 0

def convert_et_to_ist(time_str, game_date_str):
    if not time_str or "Final" in time_str: return time_str
    try:
        match = re.search(r"(\d+):(\d+)\s+(am|pm)", time_str, re.IGNORECASE)
        if not match: return time_str
        h, m, p = match.groups()
        h = int(h) + (12 if p.lower() == 'pm' and int(h) != 12 else 0)
        h = 0 if p.lower() == 'am' and int(h) == 12 else h
        dt_us = datetime.strptime(f"{game_date_str} {h}:{m}", "%Y-%m-%d %H:%M")
        dt_us = ET_TZ.localize(dt_us)
        return dt_us.astimezone(IST_TZ).strftime("%a %I:%M %p")
    except: return time_str

# --- MAIN ENGINE (V10) ---
def get_schedule_with_stats(target_date_str):
    games_df = get_schedule_from_cdn(target_date_str)
    if games_df.empty: return pd.DataFrame()

    rosters = load_players()
    team_stats = load_team_stats()
    injured_set = load_injuries()
    spreads = get_betting_spreads()
    
    enriched_games = []
    
    for _, row in games_df.iterrows():
        home = row['home']
        away = row['away']
        
        # 1. STAR POWER (Weighted)
        def get_stars(team):
            if team not in rosters: return 150.0
            avail = [p['fp'] for p in rosters[team] if p['name'] not in injured_set]
            weights = [1.5, 1.0, 0.5]
            score = 0
            for i, fp in enumerate(avail[:3]): score += fp * weights[i]
            return score

        h_stars = get_stars(home)
        a_stars = get_stars(away)
        star_score = (h_stars + a_stars) / 6.0 
        
        # 2. QUALITY & NARRATIVE (Win %)
        h_info = team_stats.get(home, {'net':0, 'wins':0.5, 'ortg':115})
        a_info = team_stats.get(away, {'net':0, 'wins':0.5, 'ortg':115})
        
        # Net Rating Bonus
        quality_score = (h_info['net'] + a_info['net']) * 1.5
        
        # "Contender Bonus" (Narrative)
        # If both teams are winning (>60%), it's a narrative game.
        narrative_bonus = 0
        if h_info['wins'] > 0.60 and a_info['wins'] > 0.60:
            narrative_bonus = 10 # Big game!
        elif h_info['wins'] > 0.50 and a_info['wins'] > 0.50:
            narrative_bonus = 5  # Solid game
            
        # 3. STYLE (Offense)
        avg_off = (h_info['ortg'] + a_info['ortg']) / 2
        style_bonus = max(0, (avg_off - 112) * 0.8)
        
        # 4. BROADCAST BONUS
        tv_bonus = 0
        if row['tv'] in ['ESPN', 'TNT', 'ABC', 'NBATV']:
            tv_bonus = 5
        
        # 5. SPREAD
        spread = spreads.get(home, 10.0)
        spread_penalty = min(abs(spread) * 2.5, 45)
        
        # FINAL FORMULA
        raw_score = 30 + star_score + quality_score + narrative_bonus + style_bonus + tv_bonus - spread_penalty
        final_score = max(0, min(100, raw_score))
        
        # Sorting Helper (IST Hour)
        # 1. Convert "7:30 pm ET" to "06.5" (float hour in IST) for sorting
        # This allows us to split Early vs Late games easily
        ist_str = convert_et_to_ist(row['time'], target_date_str)
        # Extract hour float from IST string (e.g. "Sat 06:30 AM" -> 6.5)
        match = re.search(r"(\d+):(\d+)\s+(AM|PM)", ist_str)
        if match:
            h, m, p = match.groups()
            h = int(h)
            if p == "PM" and h != 12: h += 12
            if p == "AM" and h == 12: h = 0
            sort_hour = h + (int(m)/60)
        else:
            sort_hour = 0

        source = "Manual CSV" if rosters else "Static Fallback"
        
        enriched_games.append({
            'Time_IST': ist_str,
            'Sort_Hour': sort_hour, # Hidden column for logic
            'Matchup': f"{away} @ {home}",
            'Spread': spread,
            'Stars': int(h_stars + a_stars),
            'Score': round(final_score, 1),
            'TV': row['tv'],
            'Home_Logo': TEAM_LOGOS_URL.format(row['home_id']),
            'Away_Logo': TEAM_LOGOS_URL.format(row['away_id']),
            'Source': source
        })
        
    return pd.DataFrame(enriched_games)

