import pandas as pd
import json
import requests
from bs4 import BeautifulSoup
from nba_api.stats.endpoints import leaguedashplayerstats, leaguedashteamstats
from datetime import datetime

# --- CONFIG ---
# We use official NBA headers because this runs LOCALLY (Unblocked)
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Referer': 'https://www.nba.com/'
}
CURRENT_SEASON = '2025-26' # Make sure this matches the API's current season ID

def fetch_live_nba_stats():
    print("🚀 Starting Data Update...")
    
    data = {}
    
    # 1. TEAM STATS (Net Rating, Pace)
    print("📊 Fetching Team Stats (Official NBA API)...")
    try:
        teams = leaguedashteamstats.LeagueDashTeamStats(
            season=CURRENT_SEASON,
            headers=HEADERS,
            timeout=30
        ).get_data_frames()[0]
        
        team_data = {}
        for _, row in teams.iterrows():
            abbr = row['TEAM_ABBREVIATION']
            team_data[abbr] = {
                'net_rating': row['E_NET_RATING'],
                'pace': row['E_PACE'],
                'w_pct': row['W_PCT']
            }
        data['teams'] = team_data
        print(f"   ✅ Indexed {len(team_data)} teams.")
    except Exception as e:
        print(f"   ❌ Team Stats Failed: {e}")
        data['teams'] = {}

    # 2. PLAYER STATS (Fantasy Points)
    print("⛹️ Fetching Player Stats...")
    try:
        players = leaguedashplayerstats.LeagueDashPlayerStats(
            season=CURRENT_SEASON,
            headers=HEADERS,
            timeout=30
        ).get_data_frames()[0]
        
        player_data = {}
        for _, row in players.iterrows():
            name = row['PLAYER_NAME']
            # FP Formula: PTS + 1.2*REB + 1.5*AST + 3*STL + 3*BLK - 1*TOV
            fp = (row['PTS']) + (row['REB']*1.2) + (row['AST']*1.5) + \
                 (row['STL']*3) + (row['BLK']*3) - (row['TOV'])
            gp = row['GP'] if row['GP'] > 0 else 1
            
            # Organize by Team so we don't need complex mapping later
            team = row['TEAM_ABBREVIATION']
            if team not in player_data: player_data[team] = []
            
            player_data[team].append({
                'name': name,
                'fp': round(fp / gp, 1)
            })
            
        # Sort rosters
        for t in player_data:
            player_data[t].sort(key=lambda x: x['fp'], reverse=True)
            
        data['players'] = player_data
        print(f"   ✅ Indexed {len(players)} players.")
    except Exception as e:
        print(f"   ❌ Player Stats Failed: {e}")
        data['players'] = {}

    # 3. AVAILABILITY (Rotowire)
    print("🚑 Fetching Active Players (Rotowire)...")
    try:
        r = requests.get("https://www.rotowire.com/basketball/nba-lineups.php", headers=HEADERS)
        soup = BeautifulSoup(r.text, 'html.parser')
        active_players = []
        for box in soup.find_all(class_="lineup__box"):
            for p in box.find_all("a", {"title": True}):
                active_players.append(p['title'].strip())
        
        data['active_players'] = active_players
        print(f"   ✅ Found {len(active_players)} active players.")
    except Exception as e:
        print(f"   ❌ Rotowire Failed: {e}")
        data['active_players'] = []
        
    # 4. TIMESTAMP
    data['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # SAVE TO FILE
    with open('nba_data.json', 'w') as f:
        json.dump(data, f)
    
    print("\n✅ SUCCESS! Data saved to 'nba_data.json'")

if __name__ == "__main__":
    fetch_live_nba_stats()