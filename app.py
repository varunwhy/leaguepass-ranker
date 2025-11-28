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

# CSS
st.markdown("""
    <style>
    .block-container { padding-top: 3rem; }
    [data-testid="stMetricValue"] { font-size: 1.2rem; }
    </style>
    """, unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.title("🏀 NBA Ranker")
    today = datetime.now(IST_TZ).date()
    # Default to tomorrow
    sel_date = st.date_input("Broadcast Date (IST)", value=today + timedelta(days=1))
    us_date = sel_date - timedelta(days=1)
    st.info(f"US Game Date: **{us_date.strftime('%b %d')}**")
    if st.button("🔄 Refresh"): st.cache_data.clear()

# Logic
@st.cache_data(ttl=3600)
def load_data(d): return get_schedule_with_stats(d)

try:
    df = load_data(str(us_date))
except: df = pd.DataFrame()

# Display
if not df.empty and "Score" in df.columns:
    
    # Status
    src = df.iloc[0].get('Source', '')
    if "Manual" in src: st.success(f"🟢 **ONLINE** | Using Live CSV Data", icon="✅")
    else: st.warning(f"🟠 **FALLBACK** | Using Static Data", icon="⚠️")

    # --- THE DOUBLE HEADER ---
    st.subheader("📺 Your Double Header")
    
    # Split into Early (Before 8 AM) and Late (8 AM onwards)
    early_games = df[df['Sort_Hour'] < 8.0].sort_values(by='Score', ascending=False)
    late_games = df[df['Sort_Hour'] >= 8.0].sort_values(by='Score', ascending=False)
    
    col1, col2 = st.columns(2)
    
    # 1. Early Slot Card
    with col1:
        st.markdown("#### 🌅 Early Slot (5:30 - 8:00 AM)")
        if not early_games.empty:
            g = early_games.iloc[0]
            with st.container(border=True):
                c1, c2 = st.columns([3,1])
                c1.markdown(f"**{g['Matchup']}**")
                c1.caption(f"⏰ {g['Time_IST']} | 📺 {g['TV'] if g['TV'] else 'League Pass'}")
                c2.metric("Score", f"{g['Score']}", delta="Top Pick")
        else:
            st.info("No early games today.")

    # 2. Late Slot Card
    with col2:
        st.markdown("#### ☕ Late Slot (8:00 AM+)")
        if not late_games.empty:
            g = late_games.iloc[0]
            with st.container(border=True):
                c1, c2 = st.columns([3,1])
                c1.markdown(f"**{g['Matchup']}**")
                c1.caption(f"⏰ {g['Time_IST']} | 📺 {g['TV'] if g['TV'] else 'League Pass'}")
                c2.metric("Score", f"{g['Score']}", delta="Top Pick")
        else:
            st.info("No late games today.")

    st.divider()
    
    # Full Table
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
        column_order=("Time_IST", "TV", "Away_Logo", "Home_Logo", "Matchup", "Score", "Spread", "Stars")
    )

elif df.empty: st.warning("No games found.")
