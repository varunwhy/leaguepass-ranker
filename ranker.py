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

# --- 1. LOAD DATA (From JSON) ---
def load_nba_data():
    if not os.path.exists(DATA_FILE):
        return None
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except: return None

# --- 2. SCHEDULE (CDN - Still Live) ---
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

    # Load the Pre-Fetched Data
    db = load_nba_data()
    spreads = get_betting_spreads()
    
    enriched_games = []
    
    for _, row in games_df.iterrows():
        home = row['home']
        away = row['away']
        
        h_power, a_power = 50, 50
        h_pace, a_pace = 100, 100
        source = "Live API (Cached)"
        
        if db:
            # 1. TEAM STRENGTH (Top 3 Active Players)
            active_set = set(db.get('active_players', []))
            
            def get_team_fp(team_abbr):
                roster = db['players'].get(team_abbr, [])
                if not roster: return 0
                fp_sum = 0
                count = 0
                for p in roster:
                    # Check Availability
                    if p['name'] in active_set:
                        fp_sum += p['fp']
                        count += 1
                    else:
                        # Fuzzy Match Check (Handle name differences)
                        match, score = process.extractOne(p['name'], active_set)
                        if score > 85:
                            fp_sum += p['fp']
                            count += 1
                    if count >= 3: break
                return fp_sum

            h_fp = get_team_fp(home)
            a_fp = get_team_fp(away)
            
            # If roster fetch failed for some reason, fallback to Team Net Rating
            if h_fp == 0:
                h_net = db['teams'].get(home, {'net_rating': 0})['net_rating']
                h_power = 50 + (h_net * 3)
            else:
                h_power = h_fp
                
            if a_fp == 0:
                a_net = db['teams'].get(away, {'net_rating': 0})['net_rating']
                a_power = 50 + (a_net * 3)
            else:
                a_power = a_fp
            
            # 2. PACE
            h_pace = db['teams'].get(home, {'pace': 100})['pace']
            a_pace = db['teams'].get(away, {'pace': 100})['pace']
        
        else:
            source = "No Data File Found"

        # Calculate Score
        match_quality = (h_power + a_power) / 4 # Normalize FP sum to ~100
        avg_pace = (h_pace + a_pace) / 2
        spread = spreads.get(home, 10.0)
        spread_penalty = min(abs(spread) * 2.5, 45)
        pace_bonus = max(0, (avg_pace - 98) * 1.5)
        
        raw_score = 40 + (match_quality * 0.6) + pace_bonus - spread_penalty
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
