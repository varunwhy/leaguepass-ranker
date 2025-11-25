import pandas as pd
import requests
import re
from datetime import datetime
import pytz
from bs4 import BeautifulSoup
from io import StringIO
from thefuzz import process
import os

# --- CONSTANTS ---
IST_TZ = pytz.timezone('Asia/Kolkata')
ET_TZ = pytz.timezone('US/Eastern')
CURRENT_SEASON_YEAR = 2026

# --- STATIC DATA (2024-25 Season Stats) ---
# This ensures the app works even if ALL scrapers are blocked.
# [Net Rating (Strength), Pace]
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

# --- 1. PLAYER STATS (Live Scraper) ---
def get_rosters_and_stats():
    print("📊 Scraping B-Ref for Stats...")
    url = f"https://www.basketball-reference.com/leagues/NBA_{CURRENT_SEASON_YEAR}_per_game.html"
    HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36'}
    
    try:
        r = requests.get(url, headers=HEADERS, timeout=6)
        if r.status_code != 200: return {}

        soup = BeautifulSoup(r.content, 'html.parser')
        table = soup.find('table', {'id': 'per_game_stats'})
        if not table: return {}

        df = pd.read_html(StringIO(str(table)))[0]
        df = df[df['Player'] != 'Player']
        
        cols = ['PTS', 'TRB', 'AST', 'STL', 'BLK', 'TOV']
        for c in cols: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        
        team_rosters = {}
        # Map B-Ref teams to Standard
        BREF_MAP = {'BRK': 'BKN', 'CHO': 'CHA', 'PHO': 'PHX', 'TOT': 'SKIP'}
        
        for _, row in df.iterrows():
            raw_team = row['Tm']
            team = BREF_MAP.get(raw_team, raw_team)
            if team == 'SKIP': continue
            
            name = row['Player'].split("*")[0].strip()
            fp = (row['PTS']*1) + (row['TRB']*1.2) + (row['AST']*1.5) + (row['STL']*3) + (row['BLK']*3) - (row['TOV']*1)
            
            if team not in team_rosters: team_rosters[team] = []
            team_rosters[team].append({'name': name, 'fp': round(fp, 1)})
            
        # Sort rosters
        for t in team_rosters:
            team_rosters[t].sort(key=lambda x: x['fp'], reverse=True)
            
        return team_rosters
    except: return {}

# --- 2. AVAILABILITY (Rotowire) ---
def get_active_players():
    url = "https://www.rotowire.com/basketball/nba-lineups.php"
    try:
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=4)
        soup = BeautifulSoup(r.text, 'html.parser')
        active_set = set()
        for box in soup.find_all(class_="lineup__box"):
            for p in box.find_all("a", {"title": True}):
                active_set.add(p['title'].strip())
        return active_set
    except: return set()

# --- 3. SCHEDULE (CDN) ---
def get_schedule_from_cdn(target_date_str):
    url = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
    try:
        r = requests.get(url, timeout=5)
        data = r.json()
        # Date match logic ...
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

# --- 4. ODDS ---
try:
    from odds import get_betting_spreads
except:
    def get_betting_spreads(): return {}

# --- HELPER: Timezone ---
def convert_time(t_str, d_str):
    # Simple pass-through or regex logic from previous steps
    return t_str # (Keeping short for brevity, use your existing regex function here)

# --- MAIN RANKER ENGINE ---
def get_schedule_with_stats(target_date_str):
    print(f"🚀 Running Ranker V4.0 for {target_date_str}")
    
    games_df = get_schedule_from_cdn(target_date_str)
    if games_df.empty: return pd.DataFrame()

    # Fetch Live Data
    team_rosters = get_rosters_and_stats()
    active_set = get_active_players()
    spreads = get_betting_spreads()
    
    enriched_games = []
    
    for _, row in games_df.iterrows():
        home = row['home']
        away = row['away']
        
        # --- METRIC 1: TEAM STRENGTH (Level 1 vs Level 2) ---
        # Try Live Player Stats first
        if team_rosters and home in team_rosters:
            # Calculate active stars
            h_power = sum([p['fp'] for p in team_rosters[home] if p['name'] in active_set][:3])
            a_power = sum([p['fp'] for p in team_rosters[away] if p['name'] in active_set][:3])
            match_quality = (h_power + a_power) / 4 # Normalize to ~100 scale
            source = "Live Stats"
        else:
            # FALLBACK: Use Static Net Rating
            # Net Rating ranges from -10 to +10. We shift it to be positive.
            h_net = STATIC_TEAM_STATS.get(home, {'net':0})['net']
            a_net = STATIC_TEAM_STATS.get(away, {'net':0})['net']
            
            # Convert Net Rating to a "Power Score" (0-100 scale)
            # Avg team = 50 pts. +10 team = 80 pts.
            h_power = 50 + (h_net * 3)
            a_power = 50 + (a_net * 3)
            match_quality = (h_power + a_power) / 2
            source = "Static Data"

        # --- METRIC 2: PACE ---
        # Use Static Pace (Reliable)
        h_pace = STATIC_TEAM_STATS.get(home, {'pace': 100})['pace']
        a_pace = STATIC_TEAM_STATS.get(away, {'pace': 100})['pace']
        avg_pace = (h_pace + a_pace) / 2
        
        # --- METRIC 3: SPREAD ---
        spread = spreads.get(home, 10.0) # Default 10 if odds fail
        spread_penalty = min(abs(spread) * 2.5, 45)
        
        # --- FINAL FORMULA ---
        # Base (40) + Quality + PaceBonus - SpreadPenalty
        pace_bonus = max(0, (avg_pace - 98) * 1.5) # Reward fast games
        
        raw_score = 40 + (match_quality * 0.6) + pace_bonus - spread_penalty
        final_score = max(0, min(100, raw_score))
        
        enriched_games.append({
            'Time_IST': row['time'], # Apply your regex converter here
            'Matchup': f"{away} @ {home}",
            'Spread': spread,
            'Stars': int(match_quality), # This is now distinct per game!
            'Score': round(final_score, 1),
            'Pace': round(avg_pace, 1),
            'Win_Pct': 0.5, # Placeholder or fetch from static
            'Source': source
        })
        
    return pd.DataFrame(enriched_games)


