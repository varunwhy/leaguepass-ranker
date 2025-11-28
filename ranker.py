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
            
            name = str(row['Player']).split("\\")[0]
            try:
                fp = float(row['PTS']) + (1.2*float(row['TRB'])) + (1.5*float(row['AST'])) + \
                     (3*float(row['STL'])) + (3*float(row['BLK'])) - float(row.get('TOV', 0))
                
                if team not in rosters: rosters[team] = []
                rosters[team].append({'name': name, 'fp': round(fp, 1)})
            except: continue
            
        # Sort desc
        for t in rosters:
            rosters[t].sort(key=lambda x: x['fp'], reverse=True)
        return rosters
    except: return {}

# --- 2. LOAD TEAM STATS (Manual CSV) ---
def load_team_stats():
    defaults = {k: {'pace': 100.0, 'net': 0.0} for k in TEAM_MAP.values()}
    if not os.path.exists(TEAM_CSV): return defaults
    try:
        df = pd.read_csv(TEAM_CSV)
        if 'Team' in df.columns:
            df = df[df['Team'] != 'League Average']
        
        for _, row in df.iterrows():
            full_name = str(row['Team']).replace('*', '')
            abbr = TEAM_MAP.get(full_name)
            if abbr:
                try:
                    defaults[abbr] = {
                        'pace': float(row['Pace']),
                        'net': float(row['NRtg'])
                    }
                except: continue
        return defaults
    except: return defaults

# --- 3. LOAD INJURIES (CBS HTML) ---
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
                            name = row['Player']
                            status = str(row[status_col]).lower()
                            if "out" in status or "doubtful" in status:
                                injured_set.add(name)
                        except: continue
        return injured_set
    except: return set()

# --- 4. SCHEDULE (CDN) ---
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
                    games.append({
                        'home': game['homeTeam']['teamTricode'],
                        'away': game['awayTeam']['teamTricode'],
                        'home_id': game['homeTeam']['teamId'],
                        'away_id': game['awayTeam']['teamId'],
                        'time': game.get('gameStatusText', '')
                    })
                break
        return pd.DataFrame(games)
    except: return pd.DataFrame()

try: from odds import get_betting_spreads
except: def get_betting_spreads(): return {}

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

# --- MAIN ENGINE (HYBRID LOGIC) ---
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
        
        # 1. STAR POWER (Superstar Weighted)
        def get_weighted_stars(team):
            if team not in rosters: 
                # Fallback: Assume average stars (50 * 3) = 150
                return 150.0 
            
            # Filter Available
            available = [p['fp'] for p in rosters[team] if p['name'] not in injured_set]
            
            # Weighted Sum: #1 gets 1.5x, #2 gets 1.0x, #3 gets 0.5x
            # This emphasizes the "Alpha" star massively.
            weights = [1.5, 1.0, 0.5]
            score = 0
            for i, fp in enumerate(available[:3]):
                score += fp * weights[i]
            return score

        h_stars = get_weighted_stars(home)
        a_stars = get_weighted_stars(away)
        
        # Combined Star Power (Normalized)
        # Max theoretical: ~140 (Home) + ~140 (Away) = 280
        # We divide by 4.5 to get it into a ~60 point range
        star_score = (h_stars + a_stars) / 4.5
        
        # 2. TEAM QUALITY (Net Rating)
        h_net = team_stats.get(home, {'net': 0})['net']
        a_net = team_stats.get(away, {'net': 0})['net']
        
        # Add Net Rating directly. Two good teams (+5 each) = +10 Bonus.
        quality_bonus = h_net + a_net
        
        # 3. PACE (Minor Tie-Breaker)
        h_pace = team_stats.get(home, {'pace': 100})['pace']
        a_pace = team_stats.get(away, {'pace': 100})['pace']
        avg_pace = (h_pace + a_pace) / 2
        pace_bonus = max(0, (avg_pace - 98) * 1.0) # Slightly reduced weight
        
        # 4. SPREAD (Linear Penalty)
        spread = spreads.get(home, 10.0)
        spread_penalty = min(abs(spread) * 2.5, 45)
        
        # --- FINAL SCORE ---
        # Base 20 (Lower base, relying more on Stars/Quality)
        raw_score = 20 + star_score + quality_bonus + pace_bonus - spread_penalty
        final_score = max(0, min(100, raw_score))
        
        source = "Manual CSV" if rosters else "Static Fallback"
        
        enriched_games.append({
            'Time': convert_et_to_ist(row['time'], target_date_str),
            'Matchup': f"{away} @ {home}",
            'Spread': spread,
            'Stars': int(h_stars + a_stars), # Display raw weighted total
            'Score': round(final_score, 1),
            'Pace': round(avg_pace, 1),
            'Home_Logo': TEAM_LOGOS_URL.format(row['home_id']),
            'Away_Logo': TEAM_LOGOS_URL.format(row['away_id']),
            'Source': source
        })
        
    return pd.DataFrame(enriched_games)
