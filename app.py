import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import pytz

try:
    from ranker import get_schedule_with_stats, IST_TZ
except ImportError:
    st.error("Missing ranker.py")
    st.stop()

st.set_page_config(page_title="NBA Ranker", page_icon="🏀", layout="wide")

st.markdown("""
    <style>
    .block-container { padding-top: 3rem; }
    [data-testid="stMetricValue"] { font-size: 1.2rem; }
    </style>
    """, unsafe_allow_html=True)

with st.sidebar:
    st.title("🏀 NBA Ranker")
    today = datetime.now(IST_TZ).date()
    sel_date = st.date_input("Broadcast Date (IST)", value=today + timedelta(days=1))
    us_date = sel_date - timedelta(days=1)
    st.info(f"US Game Date: **{us_date.strftime('%b %d')}**")
    if st.button("🔄 Refresh"): st.cache_data.clear()

@st.cache_data(ttl=3600)
def load_data(d): return get_schedule_with_stats(d)

try:
    df = load_data(str(us_date))
except: df = pd.DataFrame()

if not df.empty and "Score" in df.columns:
    
    src = df.iloc[0].get('Source', '')
    if "Manual" in src: st.success(f"🟢 **ONLINE** | Using Live CSV Data", icon="✅")
    else: st.warning(f"🟠 **FALLBACK** | Using Static Data", icon="⚠️")

    # --- DOUBLE HEADER LOGIC ---
    st.subheader("📺 Your Double Header")
    
    # Early: 5:00 AM to 8:00 AM (Sort Hour < 8)
    early_games = df[df['Sort_Hour'] < 8.0].sort_values(by='Score', ascending=False)
    # Late: 8:00 AM onwards (Sort Hour >= 8)
    late_games = df[df['Sort_Hour'] >= 8.0].sort_values(by='Score', ascending=False)
    
    col1, col2 = st.columns(2)
    
    # Function to render a game card
    def render_card(container, game, title):
        with container:
            st.markdown(f"#### {title}")
            if game is not None:
                with st.container(border=True):
                    c1, c2 = st.columns([3,1])
                    with c1:
                        st.markdown(f"**{game['Matchup']}**")
                        st.caption(f"⏰ {game['Time_IST']} | 📺 {game['TV'] if game['TV'] else 'League Pass'}")
                    with c2:
                        st.metric("Score", f"{game['Score']}", delta="Top Pick")
            else:
                st.info("No games in this slot today.")

    # 1. Early Slot
    top_early = early_games.iloc[0] if not early_games.empty else None
    render_card(col1, top_early, "🌅 Early Slot (5:30 - 8:00 AM)")

    # 2. Late Slot
    top_late = late_games.iloc[0] if not late_games.empty else None
    render_card(col2, top_late, "☕ Late Slot (8:00 AM+)")

    st.divider()
    
    # --- FULL SCHEDULE TABLE ---
    st.subheader("📋 Full Schedule")
    df_display = df.sort_values(by='Score', ascending=False)
    
    st.dataframe(
        df_display,
        column_config={
            "Home_Logo": st.column_config.ImageColumn("Home", width="small"),
            "Away_Logo": st.column_config.ImageColumn("Away", width="small"),
            "TV": st.column_config.TextColumn("Broadcast"),
            "Score": st.column_config.ProgressColumn("Rank", format="%.1f", min_value=0, max_value=100),
            "Stars": st.column_config.NumberColumn("Stars", format="%d"),
        },
        use_container_width=True,
        hide_index=True,
        # Updated to use 'Time_IST' which now has the correct formatted string
        column_order=("Time_IST", "TV", "Away_Logo", "Home_Logo", "Matchup", "Score", "Spread", "Stars")
    )

elif df.empty: st.warning("No games found.")
