import pandas as pd
from nba_api.stats.endpoints import scoreboardv2, leaguedashteamstats
from nba_api.stats.static import teams
from datetime import datetime, timedelta
import pytz
import re
import argparse
import os
import requests
from io import StringIO

# Import Odds and Config

from odds import get_betting_spreads

# --- CONSTANTS ---
IST_TZ = pytz.timezone('Asia/Kolkata')
ET_TZ = pytz.timezone('US/Eastern')
EXCEL_FILE = 'stars.xlsx'

# --- DATA LOADING (EXCEL) ---
def load_star_data():
    if not os.path.exists(EXCEL_FILE):
        return {}, {}
    try:
        df = pd.read_excel(EXCEL_FILE)
        star_power = dict(zip(df['Player'], df['Score']))
        team_stars = {}
        for _, row in df.iterrows():
            team = row['Team']
            if team not in team_stars: team_stars[team] = []
            team_stars[team].append(row['Player'])
        return star_power, team_stars
    except:
        return {}, {}

# Load Stars Globally
FILE_STARS, FILE_TEAMS = load_star_data()
if FILE_STARS:
    STAR_POWER = FILE_STARS
    TEAM_STARS = FILE_TEAMS

# --- INJURY SCRAPER (SMART MATCH FIX) ---
def get_injured_players():
    """
    Scrapes injuries and cross-references them against our STAR_POWER list.
    """
    url = "https://www.cbssports.com/nba/injuries/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    
    print("🚑 Checking Injury Reports...")
    try:
        r = requests.get(url, headers=headers)
        if r.status_code != 200:
            print(f"⚠️ Warning: Could not connect to injury site. Status: {r.status_code}")
            return set()

        dfs = pd.read_html(StringIO(r.text))
        if not dfs: return set()

        # Combine all tables
        injury_df = pd.concat(dfs)
        
        # 1. Filter for bad statuses (Out, Doubtful)
        bad_statuses = ['Out', 'Doubtful', 'Expected to be out', 'Out for the season']
        mask = injury_df['Injury Status'].str.contains('|'.join(bad_statuses), case=False, na=False)
        
        # 2. Get the list of messy names (e.g. "M. StrusMax Strus")
        messy_names = injury_df[mask]['Player'].tolist()
        
        # 3. Smart Match: Check if any of OUR stars are inside the messy strings
        confirmed_injured = set()
        
        # Loop through every star we track (from Excel/Config)
        for star_name in STAR_POWER.keys():
            # Check if this star appears inside ANY of the messy injury strings
            # Example: Is "Max Strus" inside "M. StrusMax Strus"? -> YES.
            for messy_name in messy_names:
                if star_name in messy_name:
                    confirmed_injured.add(star_name)
                    print(f"   ❌ {star_name} is marked INJURED (matched from '{messy_name}')")
                    break
        
        print(f"   Found {len(confirmed_injured)} injured STARS.")
        return confirmed_injured
        
    except Exception as e:
        print(f"⚠️ Warning: Injury scraper failed ({e}). Proceeding without injury data.")
        return set()

# --- CORE FUNCTIONS ---
def get_team_lookup():
    nba_teams = teams.get_teams()
    return {team['id']: team['abbreviation'] for team in nba_teams}

def convert_et_string_to_ist(time_str, game_date_str):
    if not time_str or "Final" in time_str: return time_str
    match = re.search(r"(\d+):(\d+)\s+(am|pm)", time_str, re.IGNORECASE)
    if not match: return time_str
    hour, minute, am_pm = match.groups()
    hour = int(hour); minute = int(minute)
    if am_pm.lower() == 'pm' and hour != 12: hour += 12
    if am_pm.lower() == 'am' and hour == 12: hour = 0
    dt_str = f"{game_date_str} {hour}:{minute}:00"
    dt_us = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    dt_us = ET_TZ.localize(dt_us).astimezone(IST_TZ)
    return dt_us.strftime("%a %I:%M %p")

def get_team_stats():
    print("📊 Fetching Team Stats...")
    try:
        stats = leaguedashteamstats.LeagueDashTeamStats(season='2024-25', measure_type_detailed_defense='Advanced')
        df = stats.get_data_frames()[0]
        stats_dict = {}
        for _, row in df.iterrows():
            stats_dict[row['TEAM_ID']] = {'Win_Pct': row['W_PCT'], 'Pace': row.get('PACE', row.get('E_PACE', 0))}
        return stats_dict
    except: return {}

def get_star_score(team_abbr, injured_set=None):
    if injured_set is None: injured_set = set()
    stars = TEAM_STARS.get(team_abbr, [])
    total_score = 0
    for star in stars:
        if star in injured_set: continue
        total_score += STAR_POWER.get(star, 0)
    return total_score

def calculate_excitement_score(spread, combined_win_pct, star_score):
    spread_score = max(0, 20 - abs(spread)) 
    quality_score = combined_win_pct * 30 
    star_factor = min(40, star_score * 1.5) 
    total = spread_score + quality_score + star_factor
    return round(total, 1)

def get_schedule_with_stats(target_date_str):
    print(f"📅 Fetching Schedule for US Date: {target_date_str}")
    board = scoreboardv2.ScoreboardV2(game_date=target_date_str, league_id='00')
    games_df = board.game_header.get_data_frame()
    if games_df.empty: return pd.DataFrame()

    stats_lookup = get_team_stats()
    spread_lookup = get_betting_spreads()
    injured_players = get_injured_players() # <--- Uses new smart match
    
    enriched_games = []
    team_map = get_team_lookup()
    
    for _, row in games_df.iterrows():
        home_id = row['HOME_TEAM_ID']
        away_id = row['VISITOR_TEAM_ID']
        home_abbr = team_map.get(home_id, 'UNK')
        away_abbr = team_map.get(away_id, 'UNK')
        
        h_stats = stats_lookup.get(home_id, {'Win_Pct': 0.5, 'Pace': 100})
        a_stats = stats_lookup.get(away_id, {'Win_Pct': 0.5, 'Pace': 100})
        
        spread = spread_lookup.get(home_abbr, 10.0) 
        combined_win_pct = (h_stats['Win_Pct'] + a_stats['Win_Pct']) / 2
        avg_pace = (h_stats['Pace'] + a_stats['Pace']) / 2
        
        h_stars = get_star_score(home_abbr, injured_players)
        a_stars = get_star_score(away_abbr, injured_players)
        total_stars = h_stars + a_stars
        
        final_score = calculate_excitement_score(spread, combined_win_pct, total_stars)

        enriched_games.append({
            'Time_IST': convert_et_string_to_ist(row['GAME_STATUS_TEXT'], target_date_str),
            'Matchup': f"{away_abbr} @ {home_abbr}",
            'Spread': spread,
            'Stars': total_stars,
            'Score': final_score,
            'Pace': round(avg_pace, 1),        
            'Win_Pct': round(combined_win_pct, 3)
        })
        
    return pd.DataFrame(enriched_games)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--date", type=str)
    args = parser.parse_args()

    target_date = args.date if args.date else datetime.now(IST_TZ).strftime('%Y-%m-%d')
    df = get_schedule_with_stats(target_date)
    
    if not df.empty:
        df = df.sort_values(by='Score', ascending=False)
        print("\n--- 🏆 FINAL RANKER (SORTED BY WATCHABILITY) ---")
        print(df.to_string(index=False))
    else:
        print("No games found.")