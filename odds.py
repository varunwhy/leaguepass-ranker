import requests
from config import ODDS_API_KEY, TEAM_NAME_MAP

def get_betting_spreads():
    """
    Fetches NBA spreads from The Odds API.
    Returns a dictionary: {'LAL': -5.5, 'GSW': 5.5, ...}
    """
    if "PASTE_YOUR" in ODDS_API_KEY:
        print("⚠️ PLEASE UPDATE YOUR ODDS_API_KEY IN CONFIG.PY")
        return {}

    # API Endpoint for NBA Spreads
    url = f'https://api.the-odds-api.com/v4/sports/basketball_nba/odds'
    params = {
        'apiKey': ODDS_API_KEY,
        'regions': 'us', # US Bookmakers
        'markets': 'spreads', 
        'oddsFormat': 'decimal'
    }

    print("💰 Fetching Betting Odds...")
    response = requests.get(url, params=params)
    
    if response.status_code != 200:
        print(f"❌ Failed to get odds: {response.status_code}")
        return {}

    data = response.json()
    spread_dict = {}

    for game in data:
        # The API gives us a list of bookmakers. We'll just take the first one (usually DraftKings/FanDuel)
        bookmakers = game.get('bookmakers', [])
        if not bookmakers:
            continue
            
        # Get the spread from the first bookmaker
        markets = bookmakers[0].get('markets', [])
        if not markets:
            continue
            
        outcomes = markets[0].get('outcomes', [])
        
        for outcome in outcomes:
            team_name = outcome['name']
            spread = outcome.get('point', 0)
            
            # Map Full Name (Lakers) to Abbr (LAL)
            abbr = TEAM_NAME_MAP.get(team_name)
            
            if abbr:
                spread_dict[abbr] = spread

    return spread_dict

# Test it directly
if __name__ == "__main__":
    print(get_betting_spreads())