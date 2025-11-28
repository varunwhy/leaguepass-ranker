import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz

# Import backend logic
try:
    from ranker import get_schedule_with_stats, IST_TZ
except ImportError:
    st.error("Could not import 'ranker.py'. Make sure files are in the same folder.")
    st.stop()

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="NBA League Pass Ranker",
    page_icon="🏀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS HACKS ---
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

# --- SIDEBAR ---
with st.sidebar:
    st.title("🏀 NBA Ranker")
    st.caption("Plan your viewing schedule.")
    
    today_ist = datetime.now(IST_TZ).date()
    default_date = today_ist + timedelta(days=1)
    
    selected_date_ist = st.date_input(
        "Select Broadcast Date (India)",
        value=default_date
    )
    
    us_game_date = selected_date_ist - timedelta(days=1)
    
    st.divider()
    st.info(f"📅 US Game Night:\n**{us_game_date.strftime('%A, %b %d')}**")
    
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()

# --- MAIN APP LOGIC ---
@st.cache_data(ttl=3600)
def load_data(date_str):
    return get_schedule_with_stats(date_str)

with st.spinner(f'Scouting games for {selected_date_ist.strftime("%A")}...'):
    try:
        df = load_data(str(us_game_date))
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        df = pd.DataFrame()

# --- DISPLAY ---
if not df.empty and "Score" in df.columns:
    df = df.sort_values(by='Score', ascending=False)
    
    # 1. DATA SOURCE INDICATOR
    data_source = df.iloc[0].get('Source', 'Unknown')
    if "Manual" in data_source or "Live" in data_source:
        st.success(f"🟢 **System Status: ONLINE** | {data_source}", icon="✅")
    else:
        st.warning(f"🟠 **System Status: FALLBACK** | {data_source}", icon="⚠️")
    
    # 2. HERO SECTION
    top_game = df.iloc[0]
    
    st.subheader("🔥 Game of the Day")
    
    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            # Display Title
            st.markdown(f"### {top_game['Matchup']}")
            # FIX: Changed 'Time_IST' to 'Time'
            st.caption(f"⏰ {top_game['Time']}") 
        with col2:
            st.metric("Score", f"{top_game['Score']}", delta="Must Watch" if top_game['Score'] > 80 else None)
            
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Spread", f"{top_game['Spread']}")
        c2.metric("Stars", f"{int(top_game['Stars'])}")
        # Handle Pace missing if using old data
        pace_val = top_game.get('Pace', 100)
        c3.metric("Pace", f"{pace_val}")
        c4.caption(f"Data: {top_game.get('Source', 'N/A')}")

    st.divider()
    
    # 3. FULL TABLE
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
        # FIX: Updated column order to match new keys
        column_order=("Time", "Away_Logo", "Home_Logo", "Matchup", "Score", "Spread", "Stars")
    )

elif df.empty:
    st.warning("No games found for this date.")
else:
    st.error("Data loaded but columns are missing.")
