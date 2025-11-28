import pandas as pd
import json
import os
import requests
import re
from datetime import datetime
import pytz

# --- CONSTANTS ---
IST_TZ = pytz.timezone('Asia/Kolkata')
ET_TZ = pytz.timezone('US/Eastern')
STATS_CSV = 'stats.csv'
TEAM_LOGOS_URL = "https://cdn.nba.com/logos/nba/{}/primary/L/logo.svg"

# --- STATIC DATA (2024-25 Season Stats) ---
# Used for PACE and as a FALLBACK if CSV fails
STATIC_TEAM_STATS = {
    'OKC': {'net': 11.5, 'pace': 100.0}, 'CLE': {'net': 10.2, 'pace': 101.8},
    'BOS': {'net': 9.8, 'pace': 97.5},   'GSW': {'net': 8.5, 'pace': 102.1},
    'MEM': {'net': 6.5, 'pace': 104.2},  'NYK': {'net': 5.5, 'pace': 98.5},
    'DAL': {'net': 4.8, 'pace': 100.5},  'MIN': {'net': 4.5, 'pace': 99.2},
    'DEN': {'net': 3.2, 'pace': 101.0},  'LAL': {'net': 1.5, 'pace': 103.5},
    'SAC': {'net': 1.2, 'pace': 102.0},  'PHX': {'net': 1.0, 'pace': 100.8},
    'IND': {'net': 0.5, 'pace': 104.5},  'MIA': {'net': 0.2, 'pace': 98.0},
    'ORL': {'net': 0.0, 'pace': 99.5},   'LAC': {'net': -0.5, 'pace': 100.2},
    'HOU': {'net': -1.0, 'pace': 101.5}, 'ATL': {'net': -1.5, 'pace': 104.0},
    'BKN': {'net': -2.5, 'pace': 99.0},  'SAS': {'net': -3.0, 'pace': 101.5},
    'CHA': {'net': -4.5, 'pace': 100.5}, 'DET': {'net': -5.0, 'pace': 101.2},
    'TOR': {'net': -6.5, 'pace': 101.8}, 'POR': {'net': -7.5, 'pace': 100.5},
    'NOP': {'net': -8.0, 'pace': 99.8},  'CHI': {'net': -8.5, 'pace': 103.8},
    'WAS': {'net': -9.5, 'pace': 104.5}, 'UTA': {'net': -10.5, 'pace': 102.0},
    'PHI': {'net': -2.0, 'pace': 98.5},  'MIL': {'net': 2.5, 'pace': 100.5}
}

# --- 1. LOAD DATA (Manual CSV) ---
def load_player_stats_from_csv():
    if not os.path.exists(STATS_CSV): return None
    try:
        df = pd.read_csv(STATS_CSV)
        # Filter header rows (just in case)
        df = df[df['Player'] != 'Player']
        
        BREF_MAP = {'BRK': 'BKN', 'CHO': 'CHA', 'PHO': 'PHX', 'TOT': 'SKIP'}
        
        rosters = {}
        
        for _, row in df.iterrows():
            # FIX: Look for 'Team' (your CSV header) instead of 'Tm'
            # We use .get() so it works with either 'Team' or 'Tm'
            raw_team = row.get('Team', row.get('Tm', 'SKIP'))
            
            team = BREF_MAP.get(raw_team, raw_team)
            if team == 'SKIP': continue
            
            # Clean Name
            name = str(row['Player']).split("\\")[0]
            
            try:
                # Calc FP
                # ensure these columns exist in your CSV or use .get(col, 0)
                pts = float(row['PTS'])
                trb = float(row['TRB'])
                ast = float(row['AST'])
                stl = float(row['STL'])
                blk = float(row['BLK'])
                tov = float(row.get('TOV', row.get('TO', 0))) # Handle TOV vs TO
                
                fp = pts + (1.2*trb) + (1.5*ast) + (3*stl) + (3*blk) - tov
                
                if team not in rosters: rosters[team] = []
                rosters[team].append({'fp': round(fp, 1)})
            except: 
                continue
            
        # Sort desc
        for t in rosters:
            rosters[t].sort(key=lambda x: x['fp'], reverse=True)
            
        # Debug print to confirm it worked in logs
        print(f"✅ CSV Loaded: Found {len(rosters)} teams.")
        return rosters
    except Exception as e: 
        print(f"❌ CSV Error: {e}")
        return None
        
# --- 2. SCHEDULE (CDN) ---
def get_schedule_from_cdn(target_date_str):
    url = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
    try:
        r = requests.get(url, timeout=5)
        data = r.json()
        dt = datetime.strptime(target_date_str, "%Y-%m-%d")
        target_fmt = dt.strftime("%m/%d/%Y")
        
        games_found = []
        for d in data['leagueSchedule']['gameDates']:
            if target_fmt in d['gameDate']:
                for game in d['games']:
                    games_found.append({
                        'home': game['homeTeam']['teamTricode'],
                        'away': game['awayTeam']['teamTricode'],
                        'home_id': game['homeTeam']['teamId'],
                        'away_id': game['awayTeam']['teamId'],
                        'time': game.get('gameStatusText', '')
                    })
                break
        return pd.DataFrame(games_found)
    except: return pd.DataFrame()

# --- 3. ODDS ---
try:
    from odds import get_betting_spreads
except:
    def get_betting_spreads(): return {}

# --- HELPER ---
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

# --- MAIN RANKER ---
def get_schedule_with_stats(target_date_str):
    games_df = get_schedule_from_cdn(target_date_str)
    if games_df.empty: return pd.DataFrame()

    team_rosters = load_player_stats_from_csv()
    spreads = get_betting_spreads()
    
    enriched_games = []
    
    for _, row in games_df.iterrows():
        home = row['home']
        away = row['away']
        
        # 1. PACE (From Static Data)
        h_pace = STATIC_TEAM_STATS.get(home, {'pace': 100})['pace']
        a_pace = STATIC_TEAM_STATS.get(away, {'pace': 100})['pace']
        avg_pace = (h_pace + a_pace) / 2
        
        # 2. POWER (Try CSV -> Fallback to Static Net Rating)
        source = "Static Data"
        if team_rosters and home in team_rosters:
            # CSV Loaded Successfully
            source = "Manual CSV"
            h_power = sum([p['fp'] for p in team_rosters[home][:3]])
            a_power = sum([p['fp'] for p in team_rosters[away][:3]])
            # Normalize: CSV sums are ~150. We want ~80-90 range for formula.
            match_quality = (h_power + a_power) / 3.5
        else:
            # Fallback to Net Rating
            h_net = STATIC_TEAM_STATS.get(home, {'net':0})['net']
            a_net = STATIC_TEAM_STATS.get(away, {'net':0})['net']
            # Convert -10..+10 range to 0..100 scale
            h_power = 50 + (h_net * 3)
            a_power = 50 + (a_net * 3)
            match_quality = (h_power + a_power) / 2
        
        # 3. SCORING FORMULA
        spread = spreads.get(home, 10.0)
        spread_penalty = min(abs(spread) * 2.5, 45)
        
        # Add Pace Bonus (If pace > 98, add points)
        pace_bonus = max(0, (avg_pace - 98) * 1.5)
        
        raw_score = 35 + (match_quality * 0.6) + pace_bonus - spread_penalty
        final_score = max(0, min(100, raw_score))
        
        enriched_games.append({
            'Time': convert_et_to_ist(row['time'], target_date_str),
            'Matchup': f"{away} @ {home}",
            'Spread': spread,
            'Stars': int(match_quality),
            'Score': round(final_score, 1),
            'Pace': round(avg_pace, 1),
            'Home_Logo': TEAM_LOGOS_URL.format(row['home_id']),
            'Away_Logo': TEAM_LOGOS_URL.format(row['away_id']),
            'Source': source
        })
        
    return pd.DataFrame(enriched_games)

