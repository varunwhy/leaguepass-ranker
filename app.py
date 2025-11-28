import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz

# Import your backend logic
# Ensure ranker.py is in the same folder!
try:
    from ranker import get_schedule_with_stats, IST_TZ
except ImportError:
    st.error("Could not import 'ranker.py'. Make sure both files are in the same folder.")
    st.stop()

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="NBA League Pass Ranker",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS HACKS FOR MOBILE ---
# This removes some default padding to make it look better on phones
st.markdown("""
    <style>
    .block-container {
        padding-top: 3rem;
        padding-bottom: 0rem;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.5rem;
    }
    </style>
    """, unsafe_allow_html=True)

# --- SIDEBAR: CONTROLS ---
with st.sidebar:
    st.title("🏀 NBA Ranker")
    st.caption("Plan your viewing schedule.")
    
    # 1. Date Picker (India Time)
    # Default to "Tomorrow" (since we usually plan ahead)
    today_ist = datetime.now(IST_TZ).date()
    default_date = today_ist + timedelta(days=1)
    
    selected_date_ist = st.date_input(
        "Select Broadcast Date (India)",
        value=default_date
    )
    
    # Logic: If I want to watch on Tuesday Morning (India),
    # I need the schedule from Monday (US).
    us_game_date = selected_date_ist - timedelta(days=1)
    
    st.divider()
    
    st.info(f"📅 Fetching US Schedule for:\n**{us_game_date.strftime('%A, %b %d')}**")
    
    # Refresh Button (clears cache to get fresh odds/injuries)
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()

# --- MAIN APP LOGIC ---

# Cache the heavy lifting so it doesn't re-run every time you click something
@st.cache_data(ttl=3600) # Cache clears every 1 hour automatically
def load_data(date_str):
    return get_schedule_with_stats(date_str)

# Show a loading spinner while fetching
with st.spinner(f'Scouting games for {selected_date_ist.strftime("%A")}...'):
    try:
        df = load_data(str(us_game_date))
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        df = pd.DataFrame()

# --- DISPLAY ---
if not df.empty and "Score" in df.columns:
    # Sort by Score
    df = df.sort_values(by='Score', ascending=False)
    
    # 1. DATA SOURCE INDICATOR (NEW)
    # Check the first row to see if we are using Live Stats or Static Data
    data_source = df.iloc[0].get('Source', 'Unknown')
    
    # FIX: Use 'in' to match partial string, or match the exact string
    if "Live Stats" in data_source:
        st.success(f"🟢 **System Status: ONLINE** | {data_source}", icon="✅")
    else:
        st.warning(f"🟠 **System Status: OFFLINE** | API Blocked. Using Static Data", icon="⚠️")
    
    # 2. THE HERO SECTION (Top Game)
    top_game = df.iloc[0]
    
    st.subheader("🔥 Game of the Day")
    
    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"### {top_game['Matchup']}")
            st.caption(f"⏰ {top_game['Time_IST']}")
        with col2:
            st.metric("Score", f"{top_game['Score']}", delta="Must Watch" if top_game['Score'] > 80 else None)
            
        c1, c2, c3, c4 = st.columns(4) # Added 4th column for extra detail
        c1.metric("Spread", f"{top_game['Spread']}")
        c2.metric("Stars", f"{int(top_game['Stars'])}")
        c3.metric("Pace", f"{top_game['Pace']}")
        c4.caption(f"Data: {top_game.get('Source', 'N/A')}") # Shows source for specific game

    st.divider()
    
    
    st.subheader("📋 Full Schedule")
    
    st.dataframe(
        df,
        column_config={
            "Home_Logo": st.column_config.ImageColumn("Home", width="small"),
            "Away_Logo": st.column_config.ImageColumn("Away", width="small"),
            "Matchup": "Game",
            "Score": st.column_config.ProgressColumn(
                "Watchability",
                format="%.1f",
                min_value=0,
                max_value=100,
            ),
            "Spread": st.column_config.NumberColumn("Spread", format="%.1f"),
            "Stars": st.column_config.NumberColumn("Star Power", format="%d"),
        },
        use_container_width=True,
        hide_index=True,
        # Reorder columns to put Logos next to Matchup
        column_order=("Time", "Away_Logo", "Home_Logo", "Matchup", "Score", "Spread", "Stars")
    )

elif df.empty:
    st.warning("No games found for this date.")
else:

    st.error("Data loaded but columns are missing. Check ranker.py output.")


