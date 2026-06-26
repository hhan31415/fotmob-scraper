import streamlit as st
import pandas as pd
import os
from src import FotMobScraper
from src.league_player_data import detect_url_type
from utils.app_helpers import (
    run_scraper_with_progress,
    prepare_dataframe,
    render_detailed_stats_table,
    render_simple_matches_table
)

st.set_page_config(page_title="FotMob Scraper", page_icon="⚽", layout="wide")

st.title("FotMob Data Scraper")
st.subheader("Scrape Match Data")
st.markdown(
    "Scrape match results and match statistics in a league. You can scrape an entire season's worth of stats or a specific round from that season."
)

# Create two columns for inputs
col3, col1, col2 = st.columns(3)

#NEW You can choose the league to scrape. Replaced BASE_URL with league_URL. league_table_url used for league player data
with col3:
    league = st.selectbox(
        "League",
        options=["Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1", "MLS", "USL Championship"],
        help="Select a football league"
    )
if league == "MLS":
    league_URL = "https://www.fotmob.com/leagues/130/fixtures/mls"
    league_years = 0
    league_table_url = "https://www.fotmob.com/leagues/130/table/mls"
elif league == "Premier League":
    league_URL = "https://www.fotmob.com/leagues/47/fixtures/premier-league"
    league_years = 1
    league_table_url = "https://www.fotmob.com/leagues/47/table/premier-league"
elif league == "La Liga":
    league_URL = "https://www.fotmob.com/leagues/87/fixtures/laliga"
    league_years = 1
    league_table_url = "https://www.fotmob.com/leagues/87/table/laliga"
elif league == "Bundesliga":
    league_URL = "https://www.fotmob.com/leagues/54/fixtures/bundesliga"
    league_years = 1
    league_table_url = "https://www.fotmob.com/leagues/54/table/bundesliga"
elif league == "Serie A":
    league_URL = "https://www.fotmob.com/leagues/55/fixtures/serie"
    league_years = 1
    league_table_url = "https://www.fotmob.com/leagues/55/table/serie"
elif league == "Ligue 1":
    league_URL = "https://www.fotmob.com/leagues/53/fixtures/ligue-1"
    league_years = 1
    league_table_url = "https://www.fotmob.com/leagues/53/table/ligue-1"
elif league == "USL Championship":
    league_URL = "https://www.fotmob.com/leagues/8972/fixtures/usl-championship"
    league_years = 0
    league_table_url = "https://www.fotmob.com/leagues/8972/table/usl-championship"
    
custom_fotmob_url = st.text_input(
    "Or paste any FotMob league or club URL (overrides dropdown above)",
    value="",
    placeholder="e.g. https://www.fotmob.com/teams/9825/overview/bayern-munich",
    help="Paste any FotMob league table or team page URL. The scraper will "
         "automatically detect whether it's a league or a club and route "
         "accordingly. Overrides the league dropdown above."
)
 
# Detect URL type and show a small status hint so the user knows what
# will happen before they click the button
if custom_fotmob_url.strip():
    url_type, normalized_url = detect_url_type(custom_fotmob_url)
    if url_type == "league":
        st.caption(f"✅ Detected: **league** — will scrape all players in this league")
    elif url_type == "club":
        st.caption(f"✅ Detected: **club** — will scrape this team's squad (~25 players, no confirmation needed)")
    else:
        st.caption("⚠️ URL not recognized — please paste a fotmob.com league or team URL")

with col1:
    if league_years == 0:
        season = st.text_input(
            "Season (Year)", 
            value="2026",
            help="Format: YYYY (e.g., 2026)"
        )
    else: 
        season = st.text_input(
            "Season (Year-Year)", 
            value="2025-2026",
            help="Format: YYYY-YYYY (e.g., 2025-2026)"
        )

with col2:
    if league == "MLS":
        round_num = st.number_input("Round", min_value=1, max_value=34, value=1)
    elif league == "Premier League":
        round_num = st.number_input("Round", min_value=1, max_value=38, value=1)
    elif league in ("La Liga", "Serie A"):
        round_num = st.number_input("Round", min_value=1, max_value=38, value=1)
    elif league in ("Bundesliga", "Ligue 1"):
        round_num = st.number_input("Round", min_value=1, max_value=34, value=1)
    elif league == "USL Championship":
        round_num = st.number_input("Round", min_value=1, max_value=36, value=1)



# Initialize session state for matches
if 'matches' not in st.session_state:
    st.session_state.matches = None
if 'scraper' not in st.session_state:
    st.session_state.scraper = None

# Scrape buttons
col_btn1, col_btn2, col_btn3 = st.columns(3)

with col_btn1:
    scrape_matches_btn = st.button("Scrape Matches Only", type="primary", width='stretch')

with col_btn2:
    scrape_stats_btn = st.button("Scrape Matches & Stats (Round)", type="primary", width='stretch')

with col_btn3:
    scrape_season_btn = st.button("Scrape Matches & Stats (Season)", type="primary", width='stretch', help="Warning: This will take a long time!")

# Initialize scraper if needed
if st.session_state.scraper is None:
    st.session_state.scraper = FotMobScraper()

# Handle button clicks
if scrape_matches_btn:
    try:
        with st.spinner("Starting scraper..."):
            matches = run_scraper_with_progress(
                st.session_state.scraper.get_matches,
                season, round_num, league_URL,
                progress_divisor=100
            )
            
            if matches:
                st.session_state.matches = matches
                st.success(f"Successfully scraped {len(matches)} matches!")
            else:
                st.warning("No matches found. Please check the season and round number.")
    except Exception as e:
        st.error(f"An error occurred: {e}")

if scrape_stats_btn:
    try:
        with st.spinner("Starting scraper (this may take a while)..."):
            matches_with_stats = run_scraper_with_progress(
                st.session_state.scraper.get_matches_with_stats,
                season, round_num, league_URL,
                progress_divisor=100
            )
            
            if matches_with_stats:
                st.session_state.matches = matches_with_stats
                st.success(f"Successfully scraped {len(matches_with_stats)} matches with stats!")
            else:
                st.warning("No matches found. Please check the season and round number.")
    except Exception as e:
        st.error(f"An error occurred: {e}")

if scrape_season_btn:
    try:
        with st.spinner("Starting season scraper (this will take a LONG time)..."):
            season_stats = run_scraper_with_progress(
                st.session_state.scraper.get_season_stats,
                season, league_URL, 
                progress_divisor=100
            )
            
            if season_stats:
                st.session_state.matches = season_stats
                st.success(f"Successfully scraped {len(season_stats)//2} matches for the entire season!")
            else:
                st.warning("No matches found. Please check the season.")
    except Exception as e:
        st.error(f"An error occurred: {e}")

# Display matches if available
if st.session_state.matches:
    matches = st.session_state.matches
    
    # Process data using helper function
    df, final_cols, is_detailed_stats = prepare_dataframe(matches)
    
    if is_detailed_stats:
        # Display detailed stats with optional pagination
        st.success(f"Loaded data for {len(df)//2} matches ({len(df)} rows)")
        render_detailed_stats_table(df, final_cols, season)
    else:
        # Display simple matches table
        render_simple_matches_table(df, final_cols)
        
        # Match stats section (Only show if we don't have detailed stats yet)
        st.markdown("---")
        st.subheader("Match Statistics")
        
        # Create a selectbox for match selection
        match_options = [f"{i+1}. {m['home']} vs {m['away']} ({m['status']})" for i, m in enumerate(matches)]
        selected_match_idx = st.selectbox(
            "Select a match to view detailed stats:",
            range(len(match_options)),
            format_func=lambda x: match_options[x]
        )
        
        if st.button("Get Match Stats", type="secondary"):
            selected_match = matches[selected_match_idx]
            
            # Check if match has finished (only FT matches have stats)
            if selected_match['status'] not in ['FT', 'HT']:
                st.warning("⚠️ Detailed stats are only available for finished matches (FT status).")
            else:
                try:
                    # Create a fresh scraper instance for stats
                    stats_scraper = FotMobScraper()
                    
                    stats = run_scraper_with_progress(
                        stats_scraper.get_match_stats,
                        selected_match['url'],
                        progress_divisor=100
                    )
                    
                    # Close the stats scraper
                    stats_scraper.close()
                    
                    if stats:
                        st.success("Stats loaded successfully!")
                        
                        # Display stats by section
                        for section_name, section_stats in stats.items():
                            with st.expander(f"{section_name}", expanded=True):
                                if section_stats:
                                    # Create a DataFrame for the section
                                    stats_df = pd.DataFrame([
                                        {
                                            "Stat": stat_name,
                                            selected_match['home']: values[0],
                                            selected_match['away']: values[1]
                                        }
                                        for stat_name, values in section_stats.items()
                                    ])
                                    
                                    st.dataframe(
                                        stats_df,
                                        width='stretch',
                                        hide_index=True
                                    )
                                else:
                                    st.info("No stats available for this section.")
                    else:
                        st.error("Could not retrieve stats. The match may not have detailed stats available.")
                        
                except Exception as e:
                    st.error(f"An error occurred while fetching stats: {e}")
st.subheader("Scrape Player Data")
st.markdown(
    "Scrapes every player's profile info, market value, and full season stats "
    "(xG, xGOT, passing, defending, etc.). Use the dropdown above for a preset "
    "league, or paste any FotMob league or club URL in the field above to "
    "override."
)
 
if 'player_data_summary' not in st.session_state:
    st.session_state.player_data_summary = None
 
# Determine what we're actually going to scrape
if custom_fotmob_url.strip():
    url_type, normalized_url = detect_url_type(custom_fotmob_url)
else:
    url_type = "league"
    normalized_url = league_table_url  # from the existing dropdown logic
 
# Only show the confirmation checkbox for league scrapes (slow)
# Club scrapes are fast enough (~25 players) to skip it
if url_type == "league":
    confirm_long_scrape = st.checkbox(
        f"I understand this will scrape all teams in this league and may take 45-90+ minutes"
    )
    button_disabled = not confirm_long_scrape
    button_label = "Scrape All Players in League"
else:
    confirm_long_scrape = True  # no confirmation needed for single club
    button_disabled = url_type == "unknown"  # only disable if URL wasn't recognized
    button_label = "Scrape Club Squad"
 
scrape_players_btn = st.button(
    button_label,
    type="primary",
    width='stretch',
    disabled=button_disabled,
    help="Check the box above to enable" if url_type == "league" and not confirm_long_scrape
         else "Paste a valid FotMob URL above to enable" if url_type == "unknown"
         else None
)
 
if scrape_players_btn:
    try:
        if url_type == "league":
            output_dir = f"player_data_{league.replace(' ', '_').lower()}"
            if custom_fotmob_url.strip():
                # Use a slug from the URL itself as the output folder name
                import re
                slug = re.search(r'/leagues/\d+/[^/]+/(.+)', normalized_url)
                output_dir = f"player_data_{slug.group(1).replace('-', '_')}" if slug else output_dir
 
            with st.spinner(f"Scraping all players... this will take a while."):
                summary = run_scraper_with_progress(
                    st.session_state.scraper.get_league_player_data,
                    normalized_url, output_dir,
                    progress_divisor=100
                )
 
        elif url_type == "club":
            import re
            slug = re.search(r'/teams/\d+/[^/]+/(.+)', normalized_url)
            output_dir = f"player_data_{slug.group(1).replace('-', '_')}" if slug else "player_data_club"
 
            with st.spinner(f"Scraping club squad..."):
                summary = run_scraper_with_progress(
                    st.session_state.scraper.get_club_player_data,
                    normalized_url, output_dir,
                    progress_divisor=100
                )
        else:
            st.error("Please paste a valid FotMob league or team URL above.")
            summary = None
 
        if summary and summary.get("total_players", 0) > 0:
            st.session_state.player_data_summary = summary
            st.success(
                f"Successfully scraped {summary['total_players']} players!"
            )
            if summary.get("teams_failed", 0) > 0:
                st.warning(f"{summary['teams_failed']} team(s) failed to scrape and were skipped.")
        elif summary is not None:
            st.warning("No player data found. Please check the URL is a valid FotMob league or team page.")
 
    except Exception as e:
        st.error(f"An error occurred: {e}")

if st.session_state.player_data_summary:
    summary = st.session_state.player_data_summary
    combined_csv_path = summary.get("combined_csv_path")

    if combined_csv_path and os.path.isfile(combined_csv_path):
        player_df = pd.read_csv(combined_csv_path)

        st.markdown(f"**{len(player_df)} players** across **{summary['league_name']} {summary['season']}**")

        st.dataframe(
            player_df,
            width='stretch',
            hide_index=True,
            height=750
        )

        with open(combined_csv_path, "rb") as f:
            csv_bytes = f.read()

        st.download_button(
            label="Download All Player Data (CSV)",
            data=csv_bytes,
            file_name=os.path.basename(combined_csv_path),
            mime="text/csv",
            type="primary",
            width='stretch'
        )

        with st.expander("Per-team CSV files"):
            st.markdown(f"If running locally: individual team CSVs were also saved to `{os.path.dirname(combined_csv_path)}/`:")
            for team_name, path in summary.get("team_csv_paths", {}).items():
                st.markdown(f"- **{team_name}**: `{path}`")
    else:
        st.warning("Combined CSV file not found on disk.")

# Instructions
with st.expander("How to use"):
    st.markdown("""
    **Scraping Matches:**
    1. Choose the league you want
    2. Enter the season in the format `YYYY` or `YYYY-YYYY`
    3. Select the round number
    4. Click one of the three **Scrape Matches** button
    5. Wait for the results to appear below
    
    **Note:** 
    - The scraper uses Selenium with headless Chrome, so it may take a few seconds to load.
    - Detailed stats are only available for finished matches (FT status).
                
    **Scraping Players:**
    1. Choose the league you want
    2. Enter the season in the format `YYYY` or `YYYY-YYYY`
    4. Click the **Scrape All Players in League** button
    5. Wait for the results to appear below
    
    **Note:**
    - CSVs will be stored in files for individual clubs and the entire dataset. To redo a scrape with the same league, you must delete the corresponding files for a league.
    """)
