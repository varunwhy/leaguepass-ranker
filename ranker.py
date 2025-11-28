import pandas as pd
import json
import os
import requests
import re
from datetime import datetime
import pytz
from thefuzz import process

# --- CONFIG ---
STATS_CSV = 'stats.csv'  # The file you downloaded from B-Ref
TEAM_LOGOS_URL = "https://cdn.nba.com/logos/nba/{}/primary/L/logo.svg"

# --- 1. LOAD DATA (From Manual CSV) ---
def load_player_stats_from_csv():
    """
    Reads the manually downloaded stats.csv from Basketball-Reference.
    """
    if not os.path.exists(STATS_CSV):
        return None
    
    try:
        # B-Ref CSVs often have a header row that repeats, so we filter it
        df = pd.read_csv(STATS_CSV)
        df = df[df['Player'] != 'Player'] # Clean rows
        
        # Map Teams (B-Ref uses old codes like CHO for Charlotte)
        BREF_MAP = {'BRK': 'BKN', 'CHO': 'CHA', 'PHO': 'PHX', 'TOT': 'SKIP'}
        
        rosters = {}
        
        for _, row in df.iterrows():
            raw_team = row['Tm']
            team = BREF_MAP.get(raw_team, raw_team)
            if team == 'SKIP': continue # Skip 'Total' rows, we want specific team stats
            
            # Clean Name
            name = row['Player'].split("\\")[0] # B-Ref CSV sometimes has "Name\namecode"
            
            try:
                # Calculate Fantasy Points
                pts = float(row['PTS'])
                trb = float(row['TRB'])
                ast = float(row['AST'])
                stl = float(row['STL'])
                blk = float(row['BLK'])
                tov = float(row['TOV'])
                
                fp = pts + (1.2*trb) + (1.5*ast) + (3*stl) + (3*blk) - tov
            except: continue
            
            if team not in rosters: rosters[team] = []
            rosters[team].append({'name': name, 'fp': round(fp, 1)})
            
        # Sort each team by best players
        for t in rosters:
            rosters[t].sort(key=lambda x: x['fp'], reverse=True)
            
        return rosters
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return None

# --- 2. SCHEDULE (CDN - Keep this, it works!) ---
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
                        'home_id': game['homeTeam']['teamId'], # Added for Logo
                        'away_id': game['awayTeam']['teamId'], # Added for Logo
                        'time': game.get('gameStatusText', '')
                    })
                break
        return pd.DataFrame(games_found)
    except: return pd.DataFrame()

# --- 3. ODDS (Keep this) ---
try:
    from odds import get_betting_spreads
except:
    def get_betting_spreads(): return {}

# --- HELPER: Timezone ---
def convert_et_to_ist(time_str, game_date_str):
    # (Use your existing function logic here)
    return time_str 

# --- MAIN RANKER ---
def get_schedule_with_stats(target_date_str):
    games_df = get_schedule_from_cdn(target_date_str)
    if games_df.empty: return pd.DataFrame()

    # Load from CSV
    team_rosters = load_player_stats_from_csv()
    spreads = get_betting_spreads()
    
    enriched_games = []
    
    for _, row in games_df.iterrows():
        home = row['home']
        away = row['away']
        
        # Team Power Calculation
        h_power, a_power = 50, 50
        source = "Static Fallback"
        
        if team_rosters:
            source = "Manual CSV"
            # Sum Top 3 Players
            # (Availability ignored in this version since we rely on manual CSV)
            if home in team_rosters:
                h_power = sum([p['fp'] for p in team_rosters[home][:3]])
            if away in team_rosters:
                a_power = sum([p['fp'] for p in team_rosters[away][:3]])
        
        match_quality = (h_power + a_power) / 3.5 
        
        # Scoring Logic
        spread = spreads.get(home, 10.0)
        spread_penalty = min(abs(spread) * 2.5, 45)
        raw_score = 35 + (match_quality * 0.6) - spread_penalty
        final_score = max(0, min(100, raw_score))
        
        enriched_games.append({
            'Time': row['time'], # Simplified
            'Matchup': f"{away} @ {home}",
            'Spread': spread,
            'Stars': int(match_quality),
            'Score': round(final_score, 1),
            'Home_Logo': TEAM_LOGOS_URL.format(row['home_id']),
            'Away_Logo': TEAM_LOGOS_URL.format(row['away_id']),
            'Source': source
        })
        
    return pd.DataFrame(enriched_games)
