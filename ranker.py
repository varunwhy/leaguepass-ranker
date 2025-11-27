import pandas as pd
import json
import os
import requests
import re
from datetime import datetime
import pytz
from thefuzz import process

# --- CONSTANTS ---
IST_TZ = pytz.timezone('Asia/Kolkata')
ET_TZ = pytz.timezone('US/Eastern')
DATA_FILE = 'nba_data.json'

# --- 1. LOAD DATA ---
def load_nba_data():
    if not os.path.exists(DATA_FILE): return None
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except: return None

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

# --- HELPER: Timezone ---
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

    db = load_nba_data()
    spreads = get_betting_spreads()
    
    enriched_games = []
    
    for _, row in games_df.iterrows():
        home = row['home']
        away = row['away']
        
        h_power, a_power = 50, 50
        h_pace, a_pace = 100, 100
        source = "Static Fallback"
        
        if db:
            source = "Live Stats (GitHub)"
            
            # --- CRITICAL FIX: SMART AVAILABILITY ---
            active_list = db.get('active_players', [])
            # If scraper failed (list empty) or too small, assume EVERYONE is active
            ignore_availability = len(active_list) < 20 
            
            active_set = set(active_list)
            
            def get_team_power(team_abbr):
                # Check if team exists in DB
                if team_abbr not in db['players']:
                    # Fallback to Net Rating
                    net = db['teams'].get(team_abbr, {'net_rating': 0})['net_rating']
                    return 50 + (net * 3)

                roster = db['players'][team_abbr]
                fp_sum = 0
                count = 0
                
                for p in roster:
                    name = p['name']
                    
                    # AVAILABILITY LOGIC
                    is_active = False
                    if ignore_availability:
                        is_active = True # Scraper failed, so count everyone
                    elif name in active_set:
                        is_active = True
                    else:
                        match, score = process.extractOne(name, active_set)
                        if score > 90: is_active = True
                    
                    if is_active:
                        fp_sum += p['fp']
                        count += 1
                    
                    if count >= 3: break
                
                return fp_sum

            h_power = get_team_power(home)
            a_power = get_team_power(away)
            
            # Get Pace (Safely)
            if home in db['teams']: h_pace = db['teams'][home]['pace']
            if away in db['teams']: a_pace = db['teams'][away]['pace']
        
        # --- CALCULATE SCORE ---
        match_quality = (h_power + a_power) / 3.5 
        avg_pace = (h_pace + a_pace) / 2
        spread = spreads.get(home, 10.0)
        spread_penalty = min(abs(spread) * 2.5, 45)
        pace_bonus = max(0, (avg_pace - 98) * 1.5)
        
        raw_score = 35 + (match_quality * 0.6) + pace_bonus - spread_penalty
        final_score = max(0, min(100, raw_score))
        
        enriched_games.append({
            'Time_IST': convert_et_to_ist(row['time'], target_date_str),
            'Matchup': f"{away} @ {home}",
            'Spread': spread,
            'Stars': int(match_quality),
            'Score': round(final_score, 1),
            'Pace': round(avg_pace, 1),
            'Win_Pct': 0.5,
            'Source': source
        })
        
    return pd.DataFrame(enriched_games)
