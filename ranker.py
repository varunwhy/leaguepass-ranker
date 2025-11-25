import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz
import re
import os

# NBA API
from nba_api.stats.endpoints import scoreboardv2, leaguedashplayerstats
from nba_api.stats.static import teams

# Import Odds
try:
    from odds import get_betting_spreads
except ImportError:
    def get_betting_spreads(): return {}

# --- CONSTANTS ---
IST_TZ = pytz.timezone('Asia/Kolkata')
ET_TZ = pytz.timezone('US/Eastern')
EXCEL_FILE = 'stars.xlsx'

# --- 0. BROWSER HEADERS (Prevent Blocking) ---
# The NBA blocks generic python requests. We must pretend to be a browser.
NBA_HEADERS = {
    'Host': 'stats.nba.com',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:91.0) Gecko/20100101 Firefox/91.0',
    'Accept': 'application/json, text/plain, */*',
    'Referer': 'https://stats.nba.com/',
    'Origin': 'https://stats.nba.com',
    'Connection': 'keep-alive',
    'x-nba-stats-origin': 'stats',
    'x-nba-stats-token': 'true'
}

# --- 1. FALLBACK DATA (Excel) ---
def load_fallback_stars():
    """Loads stars.xlsx if the API fails."""
    if not os.path.exists(EXCEL_FILE): return {}
    try:
        df = pd.read_excel(EXCEL_FILE)
        # Create a simple dict: {'LeBron James': 45.0, ...}
        # We map the 1-10 scale to Fantasy Points (approx 1 pt = 5 FP)
        return {row['Player']: row['Score'] * 5 for _, row in df.iterrows()}
    except: return {}

# --- 2. AUTOMATED SCORING (API) ---
def get_all_player_values():
    print("📊 Fetching active player stats (Fantasy Points)...")
    try:
        # We use headers to avoid 403 Forbidden errors
        stats = leaguedashplayerstats.LeagueDashPlayerStats(
            season='2025-26', # CURRENT SEASON
            headers=NBA_HEADERS,
            timeout=10 # Short timeout so app doesn't hang
        )
        df = stats.get_data_frames()[0]
        
        if df.empty: raise Exception("Empty Dataframe returned")

        team_rosters = {}
        for _, row in df.iterrows():
            team_abbr = row['TEAM_ABBREVIATION']
            name = row['PLAYER_NAME']
            # FP Formula
            fp = (row['PTS'] * 1.0) + (row['REB'] * 1.2) + (row['AST'] * 1.5) + \
                 (row['STL'] * 3.0) + (row['BLK'] * 3.0) - (row['TOV'] * 1.0)
            gp = row['GP'] if row['GP'] > 0 else 1
            avg_fp = round(fp / gp, 1)
            
            if team_abbr not in team_rosters: team_rosters[team_abbr] = []
            team_rosters[team_abbr].append({'name': name, 'fp': avg_fp})
            
        # Sort rosters by strength
        for team in team_rosters:
            team_rosters[team].sort(key=lambda x: x['fp'], reverse=True)
            
        print(f"✅ API Success: Indexed {len(df)} players.")
        return team_rosters, True # True = API worked

    except Exception as e:
        print(f"⚠️ API Failed ({e}). Switching to Fallback Mode.")
        return {}, False # False = Use Fallback

# --- 3. AVAILABILITY (Rotowire) ---
def get_projected_active_players():
    url = "https://www.rotowire.com/basketball/nba-lineups.php"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    active_players = set()
    try:
        r = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(r.text, 'html.parser')
        for box in soup.find_all(class_="lineup__box"):
            for p in box.find_all("a", {"title": True}):
                active_players.add(p['title'])
        print(f"✅ Rotowire Success: Found {len(active_players)} active players.")
        return active_players
    except: return set()

# --- UTILS ---
def get_team_lookup():
    nba_teams = teams.
