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

# --- 1. LOAD DATA (Manual CSV) ---
def load_player_stats_from_csv():
    if not os.path.exists(STATS_CSV):
        return None
    
    try:
        df = pd.read_csv(STATS_CSV)
        # Filter header rows
        df = df[df['Player'] != 'Player']
        
        # Map Teams
        BREF_MAP = {'BRK': 'BKN', 'CHO': 'CHA', 'PHO': 'PHX', 'TOT': 'SKIP'}
        
        rosters = {}
        
        for _, row in df.iterrows():
            raw_team = row['Tm']
            team = BREF_MAP.get(raw_team, raw_team)
            if team == 'SKIP': continue
            
            # Clean Name
            name = str(row['Player']).split("\\")[0]
            
            try:
                # Calc FP
                fp = float(row['PTS']) + (1.2*float(row['TRB'])) + (1.5*float(row['AST'])) + \
                     (3*float(row['STL'])) + (3*float(row['BLK'])) - float(row['TOV'])
            except: 
                continue
            
            if team not in rosters: rosters[team] = []
            rosters[team].append({'name': name, 'fp': round(fp, 1)})
            
        # Sort
        for t in rosters:
            rosters[t].sort(key=lambda x: x['fp'], reverse=True)
            
        return rosters
    except Exception as e:
        print(f"Error reading CSV: {e}")
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
        
        h_power, a_power = 50, 50
        source = "Static Fallback"
        
        if team_rosters:
            source = "Manual CSV"
            # Sum Top 3 Players
            if home in team_rosters:
                h_power = sum([p['fp'] for p in team_rosters[home][:3]])
            if away in team_rosters:
                a_power = sum([p['fp'] for p in team_rosters[away][:3]])
        
        match_quality = (h_power + a_power) / 3.5 
        
        spread = spreads.get(home, 10.0)
        spread_penalty = min(abs(spread) * 2.5, 45)
        
        raw_score = 35 + (match_quality * 0.6) - spread_penalty
        final_score = max(0, min(100, raw_score))
        
        enriched_games.append({
            'Time': convert_et_to_ist(row['time'], target_date_str),
            'Matchup': f"{away} @ {home}",
            'Spread': spread,
            'Stars': int(match_quality),
            'Score': round(final_score, 1),
            'Home_Logo': TEAM_LOGOS_URL.format(row['home_id']),
            'Away_Logo': TEAM_LOGOS_URL.format(row['away_id']),
            'Source': source
        })
        
    return pd.DataFrame(enriched_games)
