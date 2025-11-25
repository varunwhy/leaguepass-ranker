import pandas as pd
import requests
import re
from datetime import datetime
import pytz
from bs4 import BeautifulSoup
from io import StringIO
from thefuzz import process # Smart string matching

# --- CONSTANTS ---
IST_TZ = pytz.timezone('Asia/Kolkata')
ET_TZ = pytz.timezone('US/Eastern')
CURRENT_SEASON_YEAR = 2025 

# --- TEAM MAPPING (B-Ref -> NBA API Standard) ---
# Basketball-Reference uses slightly different codes for some teams
BREF_MAP = {
    'BRK': 'BKN', 'CHO': 'CHA', 'PHO': 'PHX', 
    'TOT': 'SKIP' # 'TOT' means Total stats for traded players; we skip and take the specific team row
}

# --- 1. PLAYER STATS & ROSTERS (Source: Basketball-Reference) ---
def get_rosters_and_stats():
    """
    Scrapes B-Ref to get stats AND map players to teams.
    Returns: Dictionary {'LAL': [{'name': 'LeBron James', 'fp': 52.0}, ...], ...}
    """
    print("📊 Scraping Basketball-Reference for Rosters & Stats...")
    url = f"https://www.basketball-reference.com/leagues/NBA_{CURRENT_SEASON_YEAR}_per_game.html"
    
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200: return {}

        soup = BeautifulSoup(r.content, 'html.parser')
        table = soup.find('table', {'id': 'per_game_stats'})
        if not table: return {}

        df = pd.read_html(StringIO(str(table)))[0]
        df = df[df['Player'] != 'Player'] # Remove header repeats
        
        # Numeric conversions
        cols = ['PTS', 'TRB', 'AST', 'STL', 'BLK', 'TOV', 'G']
        for c in cols: df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        
        team_rosters = {}
        
        for _, row in df.iterrows():
            # 1. Get Team
            raw_team = row['Tm']
            team = BREF_MAP.get(raw_team, raw_team)
            if team == 'SKIP': continue
            
            # 2. Get Name & Stats
            name = row['Player'].split("*")[0].strip() # Remove '*' from All-Stars
            
            # FP Formula
            fp = (row['PTS'] * 1.0) + (row['TRB'] * 1.2) + (row['AST'] * 1.5) + \
                 (row['STL'] * 3.0) + (row['BLK'] * 3.0) - (row['TOV'] * 1.0)
            
            if team not in team_rosters: team_rosters[team] = []
            
            # Add to roster
            team_rosters[team].append({'name': name, 'fp': round(fp, 1)})
            
        # Sort every roster by FP (Best players first)
        for t in team_rosters:
            team_rosters[t].sort(key=lambda x: x['fp'], reverse=True)
            
        print(f"✅ Indexed rosters for {len(team_rosters)} teams.")
        return team_rosters

    except Exception as e:
        print(f"⚠️ Stats Scraper Error: {e}")
        return {}

# --- 2. AVAILABILITY (Source: Rotowire) ---
def get_active_players():
    """
    Scrapes Rotowire for projected starters/rotation.
    Returns a set of names.
    """
    url = "https://www.rotowire.com/basketball/nba-lineups.php"
    headers = {"User-Agent": "Mozilla/5.0"}
    active_set = set()
    try:
        r = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Rotowire keeps changing class names, but 'lineup__box' is usually stable
        # We look for all links inside these boxes
        for box in soup.find_all(class_="lineup__box"):
            for p in box.find_all("a", {"title": True}):
                active_set.add(p['title'].strip())
                
        print(f"✅ Rotowire: Found {len(active_set)} active players.")
        return active_set
    except: return set()

# --- 3. SCHEDULE (Source: NBA CDN) ---
def get_schedule_from_cdn(target_date_str):
    url = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"
    try:
        r = requests.get(url, timeout=5)
        data = r.json()
        game_dates = data.get('leagueSchedule', {}).get('gameDates', [])
        
        dt = datetime.strptime(target_date_str, "%Y-%m-%d")
        target_fmt = dt.strftime("%m/%d/%Y")
        
        games_found = []
        for d in game_dates:
            if target_fmt in d['gameDate']:
                for game in d['games']:
                    games_found.append({
                        'home_team': game['homeTeam']['teamTricode'],
                        'away_team': game['awayTeam']['teamTricode'],
                        'status': game.get('gameStatusText', 'Scheduled')
                    })
                break
        return pd.DataFrame(games_found)
    except: return pd.DataFrame()

# --- UTILS ---
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

try:
    from odds import get_betting_spreads
except:
    def get_betting_spreads(): return {}

# --- SCORING ENGINE ---
def calculate_team_strength(team_abbr, team_rosters, active_set):
    """
    Sums FP of top 3 ACTIVE players.
    Uses fuzzy matching to check if roster player is in Rotowire list.
    """
    roster = team_rosters.get(team_abbr, [])
    if not roster: return 0
    
    total_fp = 0
    count = 0
    has_rotowire_data = len(active_set) > 50
    
    for player in roster:
        name = player['name']
        val = player['fp']
        
        is_playing = True
        
        # INTELLIGENT AVAILABILITY CHECK
        if has_rotowire_data:
            # 1. Exact Match
            if name in active_set:
                pass
            # 2. Fuzzy Match (Slow but accurate)
            # If "Luka Doncic" (BRef) vs "Luka Dončić" (Rotowire)
            else:
                # We extract the best match from active_set
                # If score > 90, we assume it's the same person
                match, score = process.extractOne(name, active_set)
                if score < 90:
                    is_playing = False # Likely Out
        
        if is_playing:
            total_fp += val
            count += 1
        
        if count >= 3: break # Cap at top 3 players
        
    return total_fp

# --- MAIN ---
def get_schedule_with_stats(target_date_str):
    print(f"\n🚀 RUNNING V3.1 CONNECTED RANKER: {target_date_str}")
    
    games_df = get_schedule_from_cdn(target_date_str)
    if games_df.empty: return pd.DataFrame()

    team_rosters = get_rosters_and_stats()
    active_set = get_active_players()
    spreads = get_betting_spreads()
    
    enriched_games = []
    
    for _, row in games_df.iterrows():
        home = row['home_team']
        away = row['away_team']
        
        # Calculate Strength using the new logic
        h_score = calculate_team_strength(home, team_rosters, active_set)
        a_score = calculate_team_strength(away, team_rosters, active_set)
        
        # Match Quality = Sum of Star Power
        # Typical superstar has ~50 FP. Two loaded teams = ~300 FP total.
        match_quality = h_score + a_score
        
        # Odds
        spread = spreads.get(home, 10.0)
        spread_penalty = min(abs(spread) * 2, 40)
        
        # Final Score Formula
        # Base 40 + (Quality / 4) - Penalty
        # If Quality is 0 (scraper failed), Base 65 kicks in (Odds only)
        
        if match_quality == 0:
            raw_score = 65 - spread_penalty
        else:
            raw_score = 40 + (match_quality / 4) - spread_penalty
            
        final_score = max(0, min(100, raw_score))
        
        enriched_games.append({
            'Time_IST': convert_et_to_ist(row['status'], target_date_str),
            'Matchup': f"{away} @ {home}",
            'Spread': spread,
            'Stars': int(match_quality),
            'Score': round(final_score, 1),
            'Pace': 100,
            'Win_Pct': 0.5
        })
        
    return pd.DataFrame(enriched_games)
