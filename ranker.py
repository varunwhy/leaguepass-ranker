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

# --- 1. LOAD PLAYERS ---
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

# --- 2. LOAD TEAM STATS ---
def load_team_stats():
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
                    w = float(row['W'])
                    l = float(row['L'])
                    defaults[abbr] = {
                        'pace': float(row['Pace']),
                        'net': float(row['NRtg']),
                        'ortg': float(row['ORtg']),
                        'wins': w / (w + l) if (w + l) > 0 else 0.5
                    }
                except: continue
        return defaults
    except: return defaults

# --- 3. LOAD INJURIES ---
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

# --- 4. SCHEDULE & TV (ROBUST TV FIX) ---
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
                    
                    # --- TV LOGIC FIX ---
                    tv_display = "League Pass" # Default
                    broadcasters = game.get('broadcasters', {})
                    
                    # 1. Check National TV first (ESPN, TNT, NBATV)
                    nat_list = broadcasters.get('national', [])
                    if nat_list:
                        tv_display = nat_list[0]['broadcasterDisplay']
                    
                    # 2. If no national, just mark as 'Local' or leave as League Pass
                    else:
                        tv_display = "Local Broadcast"

                    games.append({
                        'home': game['homeTeam']['teamTricode'],
                        'away': game['awayTeam']['teamTricode'],
                        'home_id': game['homeTeam']['teamId'],
                        'away_id': game['awayTeam']['teamId'],
                        'utc_time': game['gameDateTimeUTC'], 
                        'tv': tv_display
                    })
                break
        return pd.DataFrame(games)
    except: return pd.DataFrame()

# --- ODDS ---
try: from odds import get_betting_spreads
except: 
    def get_betting_spreads(): return {}

# --- HELPER: UTC to IST ---
def convert_utc_to_ist(utc_str):
    try:
        dt_utc = datetime.strptime(utc_str, "%Y-%m-%dT%H:%M:%SZ")
        dt_utc = dt_utc.replace(tzinfo=pytz.utc)
        dt_ist = dt_utc.astimezone(IST_TZ)
        
        time_str = dt_ist.strftime("%a %I:%M %p")
        sort_hour = dt_ist.hour + (dt_ist.minute / 60.0)
        return time_str, sort_hour
    except:
        return "TBD", 0.0

# --- MAIN ENGINE ---
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
        
        # 1. STARS
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
        
        # 2. QUALITY
        h_info = team_stats.get(home, {'net':0, 'wins':0.5, 'ortg':115})
        a_info = team_stats.get(away, {'net':0, 'wins':0.5, 'ortg':115})
        quality_score = (h_info['net'] + a_info['net']) * 1.5
        
        narrative_bonus = 0
        if h_info['wins'] > 0.60 and a_info['wins'] > 0.60: narrative_bonus = 10
        elif h_info['wins'] > 0.50 and a_info['wins'] > 0.50: narrative_bonus = 5
            
        avg_off = (h_info['ortg'] + a_info['ortg']) / 2
        style_bonus = max(0, (avg_off - 112) * 0.8)
        
        # 3. TV BONUS
        # Give bonus if it's a "Big" national broadcaster
        tv_name = row['tv']
        tv_bonus = 5 if any(x in tv_name for x in ['ESPN', 'TNT', 'ABC', 'NBATV']) else 0
        
        # 4. SPREAD
        spread = spreads.get(home, 10.0)
        spread_penalty = min(abs(spread) * 2.5, 45)
        
        # FINAL
        raw_score = 30 + star_score + quality_score + narrative_bonus + style_bonus + tv_bonus - spread_penalty
        final_score = max(0, min(100, raw_score))
        
        # TIME
        ist_time, sort_hour = convert_utc_to_ist(row['utc_time'])
        source = "Manual CSV" if rosters else "Static Fallback"
        
        enriched_games.append({
            'Time_IST': ist_time,
            'Sort_Hour': sort_hour,
            'Matchup': f"{away} @ {home}",
            'Spread': spread,
            'Stars': int(h_stars + a_stars),
            'Score': round(final_score, 1),
            'TV': tv_name,
            'Home_Logo': TEAM_LOGOS_URL.format(row['home_id']),
            'Away_Logo': TEAM_LOGOS_URL.format(row['away_id']),
            'Source': source
        })
        
    return pd.DataFrame(enriched_games)
