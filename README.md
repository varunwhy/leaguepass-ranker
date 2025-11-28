# 🏀 NBA Watchability Ranker

A personal dashboard to rank NBA games for Indian Standard Time (IST) viewing.

## 🌟 Features
- **Smart Scoring:** Ranks games based on Stars (FP), Team Quality (Net Rating), Pace, and Vegas Spreads.
- **Double Header:** Suggests the best "Early Morning" and "Breakfast" slot games.
- **Offline Data:** Uses manual CSV uploads to bypass NBA API blocking.

## 🔄 Daily Update Workflow (How to run)
1. **Download Stats:**
   - Go to [Basketball-Reference Per Game Stats](https://www.basketball-reference.com/leagues/NBA_2026_per_game.html).
   - Click "Share & Export" -> "Get as CSV".
   - Save as `stats.csv`.

2. **Download Team Stats:**
   - Go to [Basketball-Reference Advanced Stats](https://www.basketball-reference.com/leagues/NBA_2026.html#advanced-team).
   - Click "Share & Export" -> "Get as CSV".
   - Save as `team_stats.csv`.

3. **Download Injuries:**
   - Go to [CBS Sports Injuries](https://www.cbssports.com/nba/injuries/).
   - Right-click page -> "Save As..." -> `injuries.html`.

4. **Upload:**
   - Drag and drop all 3 files into this GitHub repository.
   - The App updates instantly.

## 📱 App Link
https://leaguepass-ranker.streamlit.app/ 
