import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz
import re
import time

# NBA API
from nba_api.stats.endpoints import scoreboardv2, leaguedashplayerstats
from nba_api.stats.static import teams

# Import Odds
try:
    from odds import get_betting_spreads
except ImportError:
    # Fallback if odds.py is missing/broken
    def get_betting_spreads(): return {}

# --- CONSTANTS ---
IST_TZ = pytz.timezone('Asia/Kolkata')
ET_TZ = pytz.timezone('US/Eastern')

# --- 1. AUTOMATED PLAYER SCORING ---
def get_all_player_values():
    """
    Fetches stats for ALL active players and organizes them by TEAM.
    Returns: {'LAL': [{'name': 'LeBron James', 'fp': 55.2}, ...], 'GSW': ...}
    """
    print("📊 Fetching active player stats (Fantasy Points)...")
    try:
        # Get stats for the current season
        stats = leaguedashplayerstats.LeagueDashPlayerStats(season='2024-25')
        df = stats.get_data_frames()[0]
        
        team_rosters = {}
        
        for _, row in df.iterrows():
            team_abbr = row['TEAM_ABBREVIATION']
            name = row['PLAYER_NAME']
            
            # Fantasy Score Formula (NBA Standard)
            fp = (row['PTS'] * 1.0) + (row['REB'] * 1.2) + (row['AST'] * 1.5) + \
                 (row['STL'] * 3.0) + (row['BLK'] * 3.0) - (row['TOV'] * 1.0)
            
            # Per Game Impact
            gp = row['GP'] if row['GP'] > 0 else 1
            avg_fp = round(fp / gp, 1)
            
            if team_abbr not in team_rosters:
                team_rosters[team_abbr] = []
            
            team_rosters[team_abbr].append({'name': name, 'fp': avg_fp})
            
        # Sort each roster by FP (Best players first)
        for team in team_rosters:
            team_rosters[team].sort(key=lambda x: x['fp'], reverse=True)
            
        print(f"✅ Indexed {len(df)} players across {len(team_rosters)} teams.")
        return team_rosters
        
    except Exception as e:
        print(f"⚠️ Error fetching player stats: {e}")
        return {}

# --- 2. INTELLIGENT AVAILABILITY (Rotowire) ---
def get_projected_active_players():
    """
    Scrapes Rotowire for projected lineups.
    Returns: Set of names {'LeBron James', 'Stephen Curry', ...}
    """
    url = "https://www.rotowire.com/basketball/nba-lineups.php"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    
    print("🕵️‍♂️ Scouting Rotowire lineups...")
    active_players = set()
    
    try:
        r = requests.get(url, headers=headers)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Rotowire 'lineup__box' contains the teams
        lineup_boxes = soup.find_all(class_="lineup__box")
        
        for box in lineup_boxes:
            # Get all players listed in the lineup lists
            # Note: We grab 'title' from the <a> tag which usually has the full name
            players = box.find_all("a", {"title": True})
            for p in players:
                name = p['title']
                active_players.add(name)
                
        print(f"✅ Found {len(active_players)} projected active players.")
        return active_players

    except Exception as e:
        print(f"⚠️ Error scraping lineups: {e}")
        return set()

# --- CORE UTILS ---
def get_team_lookup():
    nba_teams = teams.get_teams()
    return {team['id']: team['abbreviation'] for team in nba_teams}

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
    except:
        return time_str

# --- 3. SCORING LOGIC ---
def calculate_team_power(team_abbr, team_rosters, active_players):
    """
    Sums the FP of the top 3 active players on the team.
    """
    roster = team_rosters.get(team_abbr, [])
    if not roster: return 0
    
    total_fp = 0
    count = 0
    
    # Check if we have valid rotowire data
    has_rotowire_data = len(active_players) > 50 
    
    for player in roster:
        name = player['name']
        val = player['fp']
        
        # AVAILABILITY CHECK:
        # If we have Rotowire data, ONLY count player if he is in the active set.
        # We use a simple substring check to handle "L. James" vs "LeBron James"
        is_active = True
        if has_rotowire_data:
            # Check if name roughly matches anything in the active set
            # (Checking if 'LeBron James' is in the set is usually safe)
            if name not in active_players:
                # Try fuzzy check (e.g. if Rotowire has "Luka Doncic" and API has "Luka Dončić")
                # For speed, we stick to exact match first.
                is_active = False
                
        if is_active:
            total_fp += val
            count += 1
            
        # Only sum the top 3 players (The "Big Three" logic)
        # This prevents deep teams from beating star-heavy teams in watchability
        if count >= 3:
            break
            
    return total_fp

# --- MAIN LOOP ---
def get_schedule_with_stats(target_date_str):
    print(f"\n📅 RUNNING RANKER FOR: {target_date_str}")
    
    # 1. Fetch Data
    board = scoreboardv2.ScoreboardV2(game_date=target_date_str, league_id='00')
    games_df = board.game_header.get_data_frame()
    if games_df.empty: return pd.DataFrame()

    # 2. Get Intelligence
    team_rosters = get_all_player_values()    # Player Values
    active_set = get_projected_active_players() # Who is playing
    spreads = get_betting_spreads()           # Vegas Odds
    
    enriched_games = []
    team_map = get_team_lookup()

    for _, row in games_df.iterrows():
        home_id = row['HOME_TEAM_ID']
        away_id = row['VISITOR_TEAM_ID']
        home_abbr = team_map.get(home_id, 'UNK')
        away_abbr = team_map.get(away_id, 'UNK')
        
        # 3. Calculate Scores (THE FIX IS HERE)
        h_power = calculate_team_power(home_abbr, team_rosters, active_set)
        a_power = calculate_team_power(away_abbr, team_rosters, active_set)
        
        # Combined Star Power (Max usually around 300
