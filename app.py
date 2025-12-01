import streamlit as st
import pandas as pd
from src import FotMobScraper
from utils.app_helpers import (
    run_scraper_with_progress,
    prepare_dataframe,
    render_detailed_stats_table,
    render_simple_matches_table
)

st.set_page_config(page_title="FotMob Scraper", page_icon="⚽", layout="wide")

st.title("⚽ FotMob Football Scraper")
st.markdown("Scrape Premier League match data by season and round")

# Create two columns for inputs
col1, col2 = st.columns(2)

with col1:
    season = st.text_input(
        "Season (Year-Year)", 
        value="2025-2026",
        help="Format: YYYY-YYYY (e.g., 2025-2026)"
    )

with col2:
    round_num = st.number_input(
        "Round", 
        min_value=1, 
        max_value=38, 
        value=1,
        help="Select round number (1-38)"
    )

# Initialize session state for matches
if 'matches' not in st.session_state:
    st.session_state.matches = None
if 'scraper' not in st.session_state:
    st.session_state.scraper = None

# Scrape buttons
col_btn1, col_btn2, col_btn3 = st.columns(3)

with col_btn1:
    scrape_matches_btn = st.button("🔍 Scrape Matches Only", type="primary", width='stretch')

with col_btn2:
    scrape_stats_btn = st.button("📊 Scrape Matches & Stats (Round)", type="primary", width='stretch')

with col_btn3:
    scrape_season_btn = st.button("📅 Scrape Matches & Stats (Season)", type="primary", width='stretch', help="Warning: This will take a long time!")

# Initialize scraper if needed
if st.session_state.scraper is None:
    st.session_state.scraper = FotMobScraper()

# Handle button clicks
if scrape_matches_btn:
    try:
        with st.spinner("Starting scraper..."):
            matches = run_scraper_with_progress(
                st.session_state.scraper.get_matches,
                season, round_num,
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
                season, round_num,
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
                season,
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
        st.subheader("📊 Match Statistics")
        
        # Create a selectbox for match selection
        match_options = [f"{i+1}. {m['home']} vs {m['away']} ({m['status']})" for i, m in enumerate(matches)]
        selected_match_idx = st.selectbox(
            "Select a match to view detailed stats:",
            range(len(match_options)),
            format_func=lambda x: match_options[x]
        )
        
        if st.button("📈 Get Match Stats", type="secondary"):
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
                        st.success("✅ Stats loaded successfully!")
                        
                        # Display stats by section
                        for section_name, section_stats in stats.items():
                            with st.expander(f"📋 {section_name}", expanded=True):
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
                        st.error("❌ Could not retrieve stats. The match may not have detailed stats available.")
                        
                except Exception as e:
                    st.error(f"An error occurred while fetching stats: {e}")

# Instructions
with st.expander("ℹ️ How to use"):
    st.markdown("""
    **Scraping Matches:**
    1. Enter the season in the format `YYYY-YYYY` (e.g., `2025-2026`)
    2. Select the round number (1-38)
    3. Click the **Scrape Matches** button
    4. Wait for the results to appear below
    
    **Viewing Match Stats:**
    1. After scraping matches, select a match from the dropdown
    2. Click the **Get Match Stats** button
    3. View detailed statistics including xG, Shots, Passes, etc.
    
    **Note:** 
    - The scraper uses Selenium with headless Chrome, so it may take a few seconds to load.
    - Detailed stats are only available for finished matches (FT status).
    """)
