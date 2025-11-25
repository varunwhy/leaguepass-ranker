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
# CRITICAL FIX: Nov 2025 is the 2025-26 Season, so B-Ref needs '2026'
CURRENT_SEASON_YEAR = 2026 
EXCEL_FILE = 'stars.xlsx'

# --- 0. BROWSER HEADERS (Anti-Blocking) ---
# We rotate headers to look like a real user
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.google.com/'
}

# --- 1. FALLBACK DATA (Excel) ---
def load_fallback_stars():
    if not os.path.exists(EXCEL_FILE): return {}
    try:
        df = pd.read_excel(EXCEL_FILE)
        # Convert 1-10 score to Fantasy Points (1 score ~= 5 FP)
        return {row['Player']: row['Score'] * 5 for _, row in df.iterrows()}
    except: return {}

# --- 2. PLAYER STATS (Basketball-Reference) ---
def get_rosters_and_stats():
    """
    Scrapes B-Ref. Tries 2026 (Current). If empty, tries 2025 (Last Year).
    If both fail, returns Fallback Excel data.
    """
    print("📊 Scraping Stats...")
    
    # Try Current Season First
    rosters = scrape_bref(CURRENT_SEASON_YEAR)
    if rosters: return rosters
    
    # Try Last Season (Backup)
    print("⚠️ Current season stats empty. Trying last season...")
    rosters = scrape_bref(CURRENT_SEASON_YEAR - 1)
    if rosters: return rosters
    
    # Use Excel (Last Resort)
    print("⚠️ Web scraping failed. Using Excel fallback.")
    fallback = load_fallback_stars()
    if not fallback: return {}
    
    # Convert simple Excel dict {Name: Score} to Roster format {'UNK': [{Name, Score}]}
    # Since Excel doesn't always have Team, we dump them in a generic bucket or try to map
    # For ranking, we just need the lookup to work.
    generic_roster = {'UNK': []}
    for name, fp in fallback.items():
        generic_roster['UNK'].append({'name': name, 'fp': fp})
    return generic_roster

def scrape_bref(year):
    url = f"https://www.basketball-reference.com/leagues/NBA_{year}_per_game.html"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200: return {}

        soup = BeautifulSoup(r.content, 'html.parser')
        table = soup.find('table', {'id': 'per_game_stats'})
        if not table: return {}

        df = pd.read_html(StringIO(str(table)))[0]
        df = df[df['Player'] != 'Player'] # Remove headers
        
        # Team Mapping
        BREF_MAP = {'BRK': 'BKN', 'CHO': 'CHA', 'PHO': 'PHX', 'TOT': 'SKIP'}
        
        team_rosters = {}
        for _, row in df.iterrows():
            raw_team = row['Tm']
            team = BREF_MAP.get(raw_team, raw_team)
            if team == 'SKIP': continue
            
            name = row['Player'].split("*")[0].strip()
            
            # Safe Numeric Conversion
            try:
                pts = float(row['PTS'])
                trb = float(row['TRB'])
                ast = float(row['AST'])
                stl = float(row['STL'])
                blk = float(row['BLK'])
                tov = float(row['TOV'])
                
                fp = pts + (1.2*trb) + (1.5*ast) + (3*stl) + (3*blk) - tov
            except: fp = 15.0 # Default for broken rows

            if team not in team_rosters: team_rosters[team] = []
            team_rosters[team].append({'name': name, 'fp': round(fp, 1)})
            
        return team_rosters
    except Exception as e:
        print(f"Scrape Error ({year}): {e}")
        return {}

# --- 3. AVAILABILITY (Rotowire) ---
def get_active_players():
    url = "https://www.rotowire.com/basketball/nba-lineups.php"
    active_set = set()
    try:
        r = requests.get(url, headers=HEADERS, timeout=5)
        soup = BeautifulSoup(r.text, 'html.parser')
        for box in soup.find_all(class_="lineup__box"):
            for p in box.find_all("a", {"title": True}):
                active_set.add(p['title'].strip())
        print(f"✅ Rotowire: Found {len(active_set)} active players.")
        return active_set
    except: return set()

# --- 4. SCHEDULE (CDN) ---
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
    # If we are using Excel Fallback, 'team_rosters' only has 'UNK' key
    # In that case, we scan the whole 'UNK' list for fuzzy matches
    is_fallback = 'UNK' in team_rosters and len(team_rosters) == 1
    
    roster = team_rosters.get(team_abbr, [])
    if is_fallback: roster = team_rosters['UNK']
    
    if not roster: return 0
    
    total_fp = 0
    count = 0
    has_rotowire = len(active_set) > 50
    
    for player in roster:
        name = player['name']
        val = player['fp']
        
        # If fallback mode, we assume player belongs to team if Rotowire says so
        # (This is a hack for Excel mode without teams)
        if is_fallback and has_rotowire and name not in active_set:
            continue
            
        is_playing = True
        if has_rotowire and not is_fallback:
             # Exact match check first for speed
            if name not in active_set:
                # Fuzzy check
                match, score = process.extractOne(name, active_set)
                if score < 85: is_playing = False
        
        if is_playing:
            total_fp += val
            count += 1
        
        if count >= 3: break
        
    return total_fp

# --- MAIN ---
def get_schedule_with_stats(target_date_str):
    print(f"\n🚀 RUNNING V3.2 RANKER: {target_date_str}")
    
    games_df = get_schedule_from_cdn(target_date_str)
    if games_df.empty: return pd.DataFrame()

    team_rosters = get_rosters_and_stats()
    active_set = get_active_players()
    spreads = get_betting_spreads()
    
    enriched_games = []
    
    for _, row in games_df.iterrows():
        home = row['home_team']
        away = row['away_team']
        
        h_score = calculate_team_strength(home, team_rosters, active_set)
        a_score = calculate_team_strength(away, team_rosters, active_set)
        
        match_quality = h_score + a_score
        
        spread = spreads.get(home, 10.0)
        spread_penalty = min(abs(spread) * 2, 40)
        
        # Adjusted Formula for higher FP totals (300+ is common now)
        # Base 30 + (Quality / 5)
        base = 65 if match_quality == 0 else 30
        divisor = 5.0 if match_quality > 0 else 1.0
        
        raw_score = base + (match_quality / divisor) - spread_penalty
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
