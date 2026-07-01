import streamlit as st
import pandas as pd
import os
import re
from src import FotMobScraper
from src import team_stats_scraper
from src.league_player_data import detect_url_type
from utils.app_helpers import (
    run_scraper_with_progress,
    prepare_dataframe,
    render_detailed_stats_table,
    render_simple_matches_table
)

st.set_page_config(page_title="FotMob Scraper", page_icon="⚽", layout="wide")
st.title("FotMob Data Scraper")

# Resource Intensive Dialogue Function
@st.dialog("Warning: Resource Intensive Operation")
def confirm_heavy_scrape(scrape_type):
    st.warning(
        f"**{scrape_type}** is a long-running operation that will likely exceed "
        "the resource limits of Streamlit Cloud. "
        "We recommend running this locally instead.\n\n"
        "Download and run the app locally: "
        "https://github.com/hhan31415/fotmob-scraper"
    )
    st.markdown("If you are running this locally, you can proceed.")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Continue anyway", type="primary", use_container_width=True):
            st.session_state["confirmed_heavy_scrape"] = scrape_type
            st.rerun()
    with col2:
        if st.button("Cancel", use_container_width=True):
            st.session_state["confirmed_heavy_scrape"] = None
            st.rerun()

# ── Initialize scraper ────────────────────────────────────────────────────────
if 'scraper' not in st.session_state:
    st.session_state.scraper = FotMobScraper()
if 'matches' not in st.session_state:
    st.session_state.matches = None
if 'player_data_summary' not in st.session_state:
    st.session_state.player_data_summary = None
if "confirmed_heavy_scrape" not in st.session_state:
    st.session_state["confirmed_heavy_scrape"] = None

# ── League selector (shared by both tabs) ─────────────────────────────────────
league = st.selectbox(
    "League",
    options=["Premier League", "La Liga", "Bundesliga", "Serie A", "Ligue 1", "MLS", "USL Championship"],
    help="Select a football league, or paste any FotMob URL in the relevant tab below"
)

if league == "MLS":
    league_URL = "https://www.fotmob.com/leagues/130/fixtures/mls"
    league_years = 0
    league_table_url = "https://www.fotmob.com/leagues/130/table/mls"
    league_stats_url = "https://www.fotmob.com/leagues/130/stats/mls/teams"
    league_rounds = 34
elif league == "Premier League":
    league_URL = "https://www.fotmob.com/leagues/47/fixtures/premier-league"
    league_years = 1
    league_table_url = "https://www.fotmob.com/leagues/47/table/premier-league"
    league_stats_url = "https://www.fotmob.com/leagues/47/stats/premier-league/teams"
    league_rounds = 38
elif league == "La Liga":
    league_URL = "https://www.fotmob.com/leagues/87/fixtures/laliga"
    league_years = 1
    league_table_url = "https://www.fotmob.com/leagues/87/table/laliga"
    league_stats_url = "https://www.fotmob.com/leagues/87/stats/laliga/teams"
    league_rounds = 38
elif league == "Bundesliga":
    league_URL = "https://www.fotmob.com/leagues/54/fixtures/bundesliga"
    league_years = 1
    league_table_url = "https://www.fotmob.com/leagues/54/table/bundesliga"
    league_stats_url = "https://www.fotmob.com/leagues/54/stats/bundesliga/teams"
    league_rounds = 34
elif league == "Serie A":
    league_URL = "https://www.fotmob.com/leagues/55/fixtures/serie"
    league_years = 1
    league_table_url = "https://www.fotmob.com/leagues/55/table/serie"
    league_stats_url = "https://www.fotmob.com/leagues/55/stats/serie/teams"
    league_rounds = 38
elif league == "Ligue 1":
    league_URL = "https://www.fotmob.com/leagues/53/fixtures/ligue-1"
    league_years = 1
    league_table_url = "https://www.fotmob.com/leagues/53/table/ligue-1"
    league_stats_url = "https://www.fotmob.com/leagues/53/stats/ligue-1/teams"
    league_rounds = 34
elif league == "USL Championship":
    league_URL = "https://www.fotmob.com/leagues/8972/fixtures/usl-championship"
    league_years = 0
    league_table_url = "https://www.fotmob.com/leagues/8972/table/usl-championship"
    league_stats_url = "https://www.fotmob.com/leagues/8972/stats/usl-championship/teams"
    league_rounds = 36

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_matches, tab_players, tab_team_stats = st.tabs(["Match Stats", "Player Stats", "Team Stats"])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: MATCH SCRAPING
# ═══════════════════════════════════════════════════════════════════════════════
with tab_matches:
    st.markdown(
        "Scrape match results and statistics. Use the league dropdown above "
        "or paste any FotMob league URL below."
    )

    # Custom URL input (match tab -- league URLs only)
    custom_match_url = st.text_input(
        "Paste any FotMob league URL (overrides dropdown)",
        value="",
        placeholder="e.g. https://www.fotmob.com/leagues/87/overview/laliga",
        help="Paste any FotMob league URL. Must be a league (not a club) for match scraping.",
        key="custom_match_url"
    )

   # Resolve which league URL and rounds to actually use
    if custom_match_url.strip():
        url_type, normalized_match_url = detect_url_type(custom_match_url)
        if url_type == "league":
            active_league_URL = re.sub(
                r'(?:https://www\.fotmob\.com)?/leagues/(\d+)/[^/]+/(.+)',
                r'https://www.fotmob.com/leagues/\1/fixtures/\2',
                normalized_match_url
            )
            st.caption(f"Using custom league URL: `{active_league_URL}`")
            active_rounds = st.number_input(
                "Number of rounds in this league",
                min_value=1, max_value=99,
                value=league_rounds,
                help="Enter the total number of rounds for the custom league you pasted."
            )
        else:
            active_league_URL = league_URL
            active_rounds = league_rounds
            st.caption("URL not recognized as a league - using dropdown selection instead")
    else:
        active_league_URL = league_URL
        active_rounds = league_rounds

    # Season / round inputs
    col1, col2 = st.columns(2)
    with col1:
        if league_years == 0:
            season = st.text_input("Season (Year)", value="2026",
                                   help="Format: YYYY (e.g., 2026)")
        else:
            season = st.text_input("Season (Year-Year)", value="2025-2026",
                                   help="Format: YYYY-YYYY (e.g., 2025-2026)")
    with col2:
        round_num = st.number_input("Round", min_value=1,
                                    max_value=active_rounds, value=1)

    # Scrape buttons
    col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)
    with col_btn1:
        scrape_matches_btn = st.button("Matches Only (Round)",
                                       type="primary", use_container_width=True)
    with col_btn2:
        scrape_matches_season_btn = st.button("Matches Only (Season)",
                                               type="primary", use_container_width=True)
    with col_btn3:
        scrape_stats_btn = st.button("Matches & Stats (Round)",
                                     type="primary", use_container_width=True)
    with col_btn4:
        scrape_season_btn = st.button("Matches & Stats (Season)",
                                      type="primary", use_container_width=True,
                                      help="Warning: This will take a long time!")

    # Button handlers
    if scrape_matches_btn:
        try:
            with st.spinner("Scraping matches..."):
                matches = run_scraper_with_progress(
                    st.session_state.scraper.get_matches,
                    season, round_num, active_league_URL,
                    progress_divisor=100
                )
                if matches:
                    st.session_state.matches = matches
                    st.success(f"Successfully scraped {len(matches)} matches!")
                else:
                    st.warning("No matches found. Please check the season and round number.")
        except Exception as e:
            st.error(f"An error occurred: {e}")

    if scrape_matches_season_btn:
        try:
            with st.spinner("Scraping full season matches (this will take a while)..."):
                matches = run_scraper_with_progress(
                    st.session_state.scraper.get_matches_season,
                    season, active_league_URL, active_rounds,
                    progress_divisor=100
                )
                if matches:
                    st.session_state.matches = matches
                    st.success(f"Successfully scraped {len(matches)} matches for the entire season!")
                else:
                    st.warning("No matches found. Please check the season.")
        except Exception as e:
            st.error(f"An error occurred: {e}")

    if scrape_stats_btn:
        try:
            with st.spinner("Scraping matches and stats (this may take a while)..."):
                matches = run_scraper_with_progress(
                    st.session_state.scraper.get_matches_with_stats,
                    season, round_num, active_league_URL,
                    progress_divisor=100
                )
                if matches:
                    st.session_state.matches = matches
                    st.success(f"Successfully scraped {len(matches)} matches with stats!")
                else:
                    st.warning("No matches found. Please check the season and round number.")
        except Exception as e:
            st.error(f"An error occurred: {e}")

    if scrape_season_btn:
        confirm_heavy_scrape("Scrape Matches & Stats (Season)")

    if st.session_state.get("confirmed_heavy_scrape") == "Scrape Matches & Stats (Season)":
        st.session_state["confirmed_heavy_scrape"] = None
        try:
            with st.spinner("Scraping full season with stats (this will take a LONG time)..."):
                matches = run_scraper_with_progress(
                    st.session_state.scraper.get_season_stats,
                    season, active_league_URL, active_rounds,
                    progress_divisor=100
                )
                if matches:
                    st.session_state.matches = matches
                    st.success(f"Successfully scraped {len(matches)//2} matches for the entire season!")
                else:
                    st.warning("No matches found. Please check the season.")
        except Exception as e:
            st.error(f"An error occurred: {e}")

    # Display match results
    if st.session_state.matches:
        matches = st.session_state.matches
        df, final_cols, is_detailed_stats = prepare_dataframe(matches)

        if is_detailed_stats:
            st.success(f"Loaded data for {len(df)//2} matches ({len(df)} rows)")
            render_detailed_stats_table(df, final_cols, season)
        else:
            render_simple_matches_table(df, final_cols)

            st.markdown("---")
            st.subheader("Match Statistics")
            match_options = [f"{i+1}. {m['home']} vs {m['away']} ({m['status']})"
                             for i, m in enumerate(matches)]
            selected_match_idx = st.selectbox(
                "Select a match to view detailed stats:",
                range(len(match_options)),
                format_func=lambda x: match_options[x]
            )

            if st.button("Get Match Stats", type="secondary"):
                selected_match = matches[selected_match_idx]
                if selected_match['status'] not in ['FT', 'HT']:
                    st.warning("Detailed stats are only available for finished matches (FT status).")
                else:
                    try:
                        stats_scraper_inst = FotMobScraper()
                        stats = run_scraper_with_progress(
                            stats_scraper_inst.get_match_stats,
                            selected_match['url'],
                            progress_divisor=100
                        )
                        stats_scraper_inst.close()

                        if stats:
                            st.success("Stats loaded successfully!")
                            for section_name, section_stats in stats.items():
                                with st.expander(f"{section_name}", expanded=True):
                                    if section_stats:
                                        stats_df = pd.DataFrame([
                                            {
                                                "Stat": stat_name,
                                                selected_match['home']: values[0],
                                                selected_match['away']: values[1]
                                            }
                                            for stat_name, values in section_stats.items()
                                        ])
                                        st.dataframe(stats_df, use_container_width=True,
                                                     hide_index=True)
                                    else:
                                        st.info("No stats available for this section.")
                        else:
                            st.error("Could not retrieve stats.")
                    except Exception as e:
                        st.error(f"An error occurred while fetching stats: {e}")

    # Instructions
    with st.expander("How to use"):
        st.markdown("""
        1. Select a league from the dropdown above, or paste a custom FotMob league URL.
        2. Enter the season and round number.
        3. Click one of the four scrape buttons:
           - **Matches Only (Round)**: match list for one round, no stats
           - **Matches Only (Season)**: match list for all rounds, no stats
           - **Matches & Stats (Round)**: match list + detailed stats for one round
           - **Matches & Stats (Season)**: match list + detailed stats for entire season *(very slow)*
        4. For individual match stats, select a finished match (FT) from the dropdown and click **Get Match Stats**.
        """
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: PLAYER SCRAPING
# ═══════════════════════════════════════════════════════════════════════════════
with tab_players:
    st.markdown(
        "Scrapes every player's profile info, market value, and full season stats "
        "(xG, xGOT, passing, defending, etc.). Use the league dropdown above "
        "or paste any FotMob league or club URL below."
    )

    custom_player_url = st.text_input(
        "Paste any FotMob league or club URL (overrides dropdown)",
        value="",
        placeholder="e.g. https://www.fotmob.com/teams/8586/overview/tottenham-hotspur",
        help="Paste any FotMob league table or team page URL. Overrides the league dropdown above.",
        key="custom_player_url"
    )

    if custom_player_url.strip():
        url_type, normalized_url = detect_url_type(custom_player_url)
        if url_type == "league":
            st.caption("Detected: **league** — will scrape all players in this league")
        elif url_type == "club":
            st.caption("Detected: **club** — will scrape this team's squad (~25 players)")
        else:
            st.caption("URL not recognized — please paste a fotmob.com league or team URL")
    else:
        url_type = "league"
        normalized_url = league_table_url

    if url_type == "league":
        button_label = "Scrape All Players in League"
        button_disabled = False
    else:
        button_label = "Scrape Club Squad"
        button_disabled = url_type == "unknown"

    scrape_players_btn = st.button(
        button_label,
        type="primary",
        use_container_width=True,
        disabled=button_disabled,
        key="scrape_players_btn",
        help="Warning: This will take a long time!" if url_type == "league" else None
    )

    if scrape_players_btn:
        if url_type == "league":
            confirm_heavy_scrape("Scrape All Players in League")
        elif url_type == "club":
            st.session_state["confirmed_heavy_scrape"] = "Scrape Club Squad"
            st.rerun()

    if st.session_state.get("confirmed_heavy_scrape") in ("Scrape All Players in League", "Scrape Club Squad"):
        scrape_type = st.session_state["confirmed_heavy_scrape"]
        st.session_state["confirmed_heavy_scrape"] = None
        try:
            if scrape_type == "Scrape All Players in League":
                if custom_player_url.strip():
                    slug = re.search(r'/leagues/\d+/[^/]+/(.+)', normalized_url)
                    output_dir = f"player_data_{slug.group(1).replace('-', '_')}" if slug else f"player_data_{league.replace(' ', '_').lower()}"
                else:
                    output_dir = f"player_data_{league.replace(' ', '_').lower()}"

                with st.spinner("Scraping all players... this will take a while."):
                    summary = run_scraper_with_progress(
                        st.session_state.scraper.get_league_player_data,
                        normalized_url, output_dir,
                        progress_divisor=100
                    )
            else:
                slug = re.search(r'/teams/\d+/[^/]+/(.+)', normalized_url)
                output_dir = f"player_data_{slug.group(1).replace('-', '_')}" if slug else "player_data_club"

                with st.spinner("Scraping club squad..."):
                    summary = run_scraper_with_progress(
                        st.session_state.scraper.get_club_player_data,
                        normalized_url, output_dir,
                        progress_divisor=100
                    )

            if summary and summary.get("total_players", 0) > 0:
                st.session_state.player_data_summary = summary
                st.success(f"Successfully scraped {summary['total_players']} players!")
                if summary.get("teams_failed", 0) > 0:
                    st.warning(f"{summary['teams_failed']} team(s) failed to scrape and were skipped.")
            elif summary is not None:
                st.warning("No player data found. Please check the URL.")

        except Exception as e:
            st.error(f"An error occurred: {e}")

    # Results display
    if st.session_state.player_data_summary:
        summary = st.session_state.player_data_summary
        combined_csv_path = summary.get("combined_csv_path")

        if combined_csv_path and os.path.isfile(combined_csv_path):
            player_df = pd.read_csv(combined_csv_path)

            label = summary.get('team_name') or f"{summary.get('league_name')} {summary.get('season')}"
            st.markdown(f"**{len(player_df)} players** — {label}")

            st.dataframe(player_df, use_container_width=True, hide_index=True, height=750)

            with open(combined_csv_path, "rb") as f:
                csv_bytes = f.read()

            st.download_button(
                label="Download Player Data (CSV)",
                data=csv_bytes,
                file_name=os.path.basename(combined_csv_path),
                mime="text/csv",
                type="primary",
                use_container_width=True
            )

            with st.expander("Per-team CSV files"):
                st.markdown(f"Individual team CSVs saved to `{os.path.dirname(combined_csv_path)}/`:")
                for team_name, path in summary.get("team_csv_paths", {}).items():
                    st.markdown(f"- **{team_name}**: `{path}`")
        else:
            st.warning("Combined CSV file not found on disk.")

    with st.expander("How to use"):
        st.markdown("""
        1. Select a league from the dropdown above, or paste a custom FotMob URL below.
        2. For a **full league scrape**: click **Scrape All Players in League** and confirm the popup.
        3. For a **single club**: paste the club's FotMob URL and click **Scrape Club Squad**.
        4. Results appear as a table with a download button once the scrape is complete.

        **Note:** For local hosting, if a league scrape is interrupted, re-run with the same league selected — already-completed teams are skipped automatically.

        **Note:** CSVs are saved locally. To force a full re-scrape, delete the corresponding `player_data_*/` folder.
        """)

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: TEAM STATS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_team_stats:
    st.markdown(
        "Scrape team statistics for a full league or a single club. "
        "Use the league dropdown above or paste any FotMob URL below."
    )

    custom_stats_url = st.text_input(
        "Paste any FotMob league stats or team URL (overrides dropdown)",
        value="",
        placeholder="e.g. https://www.fotmob.com/teams/8586/overview/tottenham-hotspur",
        help="Paste a FotMob league stats URL or any team URL. "
             "Scrapes all teams in the league, or just the one team.",
        key="custom_stats_url"
    )

    if custom_stats_url.strip():
        if "/teams/" in custom_stats_url:
            stats_url_type = "team"
            active_stats_url = custom_stats_url.strip()
            st.caption("Detected: single team — will scrape this team's stats only")
        elif "/leagues/" in custom_stats_url:
            stats_url_type = "league"
            # Normalize to stats/teams page
            active_stats_url = re.sub(
                r'(?:https://www\.fotmob\.com)?/leagues/(\d+)/[^/]+/([^/?]+).*',
                r'https://www.fotmob.com/leagues/\1/stats/\2/teams',
                custom_stats_url.strip()
            )
            st.caption(f"Detected: league — will scrape all teams. Using: `{active_stats_url}`")
        else:
            stats_url_type = "unknown"
            active_stats_url = league_stats_url
            st.caption("URL not recognized - using dropdown selection instead")
    else:
        stats_url_type = "league"
        active_stats_url = league_stats_url
    if 'available_seasons' not in st.session_state:
        st.session_state.available_seasons = []
    if 'selected_season' not in st.session_state:
        st.session_state.selected_season = None

    col_season1, col_season2 = st.columns([1, 2])
    with col_season1:
        if st.button("Load available seasons", type="secondary",
                    key="load_seasons_btn"):
            with st.spinner("Fetching seasons..."):
                st.session_state.scraper.setup_driver()
                seasons = team_stats_scraper.get_available_seasons(
                    st.session_state.scraper.driver, active_stats_url
                )
                if seasons:
                    st.session_state.available_seasons = seasons
                    st.success(f"Found {len(seasons)} seasons.")
                else:
                    st.warning("Could not load seasons.")

    with col_season2:
        if st.session_state.available_seasons:
            selected_season = st.selectbox(
                "Season",
                options=["Current season"] + st.session_state.available_seasons,
                key="team_stats_season_select"
            )
            st.session_state.selected_season = (
                None if selected_season == "Current season" else selected_season
            )
        else:
            st.caption("Click 'Load available seasons' to select a historical season.")
            st.session_state.selected_season = None

    scrape_team_stats_btn = st.button(
        "Scrape League Team Stats" if stats_url_type != "team" else "Scrape Team Stats",
        type="primary",
        use_container_width=True,
    )

    if 'team_stats_result' not in st.session_state:
        st.session_state.team_stats_result = None

    if scrape_team_stats_btn:
        try:
            if stats_url_type == "team":
                with st.spinner("Scraping team stats..."):
                    result = run_scraper_with_progress(
                        st.session_state.scraper.get_team_stats,
                        active_stats_url,
                        progress_divisor=100
                    )
                    if result:
                        st.session_state.team_stats_result = [result]
                        st.success(f"Scraped stats for {result.get('team_name')}!")
                    else:
                        st.warning("No stats found. Please check the URL.")
            else:
                with st.spinner("Scraping league team stats..."):
                    result = run_scraper_with_progress(
                            st.session_state.scraper.get_league_team_stats,
                            active_stats_url,
                            st.session_state.get("selected_season"),
                            progress_divisor=100
                        )
                    if result:
                        st.session_state.team_stats_result = result
                        st.success(f"Scraped stats for {len(result)} teams!")
                    else:
                        st.warning("No stats found. Please check the URL.")
        except Exception as e:
            st.error(f"An error occurred: {e}")

    if st.session_state.team_stats_result:
        result = st.session_state.team_stats_result
        df = pd.DataFrame(result)

        st.markdown(f"**{len(df)} team(s)**, {len(df.columns)} columns")
        st.dataframe(df, use_container_width=True, hide_index=True, height=600)

        csv_bytes = df.to_csv(index=False).encode("utf-8")
        season_label = (st.session_state.get("selected_season") or "current").replace("/", "-")
        st.download_button(
            label="Download Team Stats (CSV)",
            data=csv_bytes,
            file_name=f"team_stats_{league.replace(' ', '_').lower()}_{season_label}.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True
        )

    with st.expander("How to use"):
        st.markdown("""
        1. Select a league from the dropdown above, or paste any FotMob URL below.
        2. For a **full league**: use the dropdown or paste any FotMob league URL and click **Scrape League Team Stats**.
        3. For a **single team**: paste any FotMob team URL and click **Scrape Team Stats**.
        4. Results appear as a table with one row per team and one column per stat category.
        5. Download the full dataset as a CSV using the button below the table.
        """)