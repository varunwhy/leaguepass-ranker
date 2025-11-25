# config.py

# 1. Add your API Key here
import streamlit as st

# --- API KEYS ---
# Instead of pasting the key here (which is public), we ask Streamlit for it.
# This requires you to have set up the key in Streamlit Community Cloud -> Settings -> Secrets
try:
    ODDS_API_KEY = st.secrets["ODDS_API_KEY"]
except FileNotFoundError:
    # This block handles the case if you run it locally on your laptop
    # without a secrets.toml file. You can paste your key here for local testing,
    # but DO NOT commit it to GitHub if the repo is public.
    ODDS_API_KEY = ""

# 2. Mapping dictionary: Odds API Team Name -> NBA API Abbreviation
TEAM_NAME_MAP = {
    'Atlanta Hawks': 'ATL', 'Boston Celtics': 'BOS', 'Brooklyn Nets': 'BKN',
    'Charlotte Hornets': 'CHA', 'Chicago Bulls': 'CHI', 'Cleveland Cavaliers': 'CLE',
    'Dallas Mavericks': 'DAL', 'Denver Nuggets': 'DEN', 'Detroit Pistons': 'DET',
    'Golden State Warriors': 'GSW', 'Houston Rockets': 'HOU', 'Indiana Pacers': 'IND',
    'Los Angeles Clippers': 'LAC', 'Los Angeles Lakers': 'LAL', 'Memphis Grizzlies': 'MEM',
    'Miami Heat': 'MIA', 'Milwaukee Bucks': 'MIL', 'Minnesota Timberwolves': 'MIN',
    'New Orleans Pelicans': 'NOP', 'New York Knicks': 'NYK', 'Oklahoma City Thunder': 'OKC',
    'Orlando Magic': 'ORL', 'Philadelphia 76ers': 'PHI', 'Phoenix Suns': 'PHX',
    'Portland Trail Blazers': 'POR', 'Sacramento Kings': 'SAC', 'San Antonio Spurs': 'SAS',
    'Toronto Raptors': 'TOR', 'Utah Jazz': 'UTA', 'Washington Wizards': 'WAS'
}

