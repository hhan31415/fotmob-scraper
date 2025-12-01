"""Helper functions for the Streamlit app."""

import streamlit as st
import pandas as pd
import time


def run_scraper_with_progress(scraper_func, *args, progress_divisor=1):
    """
    Run a scraper function with a progress bar.
    
    Args:
        scraper_func: The scraper function to call
        *args: Arguments to pass to the scraper function
        progress_divisor: Divide progress by this (1 for 0-1 scale, 100 for 0-100 scale)
        
    Returns:
        The result from the scraper function
    """
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    def update_progress(percent, text):
        progress_bar.progress(percent / progress_divisor)
        status_text.text(text)
    
    try:
        result = scraper_func(*args, progress_callback=update_progress)
        
        # Clear progress bar after completion
        time.sleep(1)
        progress_bar.empty()
        status_text.empty()
        
        return result
    except Exception as e:
        progress_bar.empty()
        status_text.empty()
        raise e


def prepare_dataframe(matches):
    """
    Process matches list into a formatted DataFrame.
    
    Args:
        matches (list): List of match dictionaries
        
    Returns:
        tuple: (df, final_cols, is_detailed_stats)
    """
    df = pd.DataFrame(matches)
    
    # Check data format (Old: list of matches, New: list of team rows)
    is_detailed_stats = "Team" in df.columns
    
    if is_detailed_stats:
        # Add "No" column (1, 2, 3...)
        df.insert(0, 'No', range(1, 1 + len(df)))
        
        # Fix Score column for Excel (prevent date conversion)
        if 'Score' in df.columns:
            df['Score'] = df['Score'].apply(
                lambda x: x.replace(' - ', ' v ') if isinstance(x, str) and ' - ' in x else x
            )
        
        # Reorder columns: Put key info first
        priority_cols = ["No", "Date", "Match", "Team", "Side", "Score", "Goal scored", "Goal conceded", "points", "Status"]
        other_cols = [c for c in df.columns if c not in priority_cols and c != "Url"]
        
        final_cols = priority_cols + other_cols
        
        # Ensure columns exist (just in case)
        final_cols = [c for c in final_cols if c in df.columns]
        
        return df, final_cols, True
        
    else:
        # Add match numbers (1, 2, 3...)
        df.insert(0, 'No', range(1, 1 + len(df)))
        
        # Reorder columns (excluding URL for display)
        base_cols = ["No", "date", "home", "score", "away", "status"]
        
        # Ensure base columns exist
        for col in base_cols:
            if col not in df.columns:
                df[col] = "N/A"
                
        df_display = df[base_cols].copy()
        
        # Rename base columns for display
        rename_map = {
            "date": "Date", 
            "home": "Home Team", 
            "score": "Score", 
            "away": "Away Team", 
            "status": "Status"
        }
        df_display.rename(columns=rename_map, inplace=True)
        
        return df_display, list(df_display.columns), False


def render_detailed_stats_table(df, final_cols, season):
    """
    Render detailed stats table with optional pagination and download.
    
    Args:
        df (pd.DataFrame): The DataFrame to display
        final_cols (list): List of columns to display
        season (str): Current season string (for filename)
    """
    # Check if this is season data (more than 40 rows = more than 1 round worth of data)
    is_season_data = len(df) > 40
    
    if is_season_data:
        # Pagination Logic (only for season data)
        rows_per_page = 20
        total_rows = len(df)
        total_pages = (total_rows - 1) // rows_per_page + 1
        
        if 'current_page' not in st.session_state:
            st.session_state.current_page = 1
            
        # Reset page if data changes significantly (heuristic)
        if 'last_total_rows' not in st.session_state or st.session_state.last_total_rows != total_rows:
            st.session_state.current_page = 1
            st.session_state.last_total_rows = total_rows

        # Pagination controls
        col_p1, col_p2, col_p3 = st.columns([1, 10, 1])
        with col_p1:
            if st.button("⬅️ Previous", disabled=st.session_state.current_page == 1, width='stretch'):
                st.session_state.current_page -= 1
                st.rerun()
        
        with col_p2:
            st.markdown(f"<div style='text-align: center; padding-top: 5px;'>Page <b>{st.session_state.current_page}</b> of <b>{total_pages}</b></div>", unsafe_allow_html=True)
            
        with col_p3:
            if st.button("Next ➡️", disabled=st.session_state.current_page == total_pages, width='stretch'):
                st.session_state.current_page += 1
                st.rerun()
        
        # Slice data for current page
        start_idx = (st.session_state.current_page - 1) * rows_per_page
        end_idx = start_idx + rows_per_page
        
        st.dataframe(
            df[final_cols].iloc[start_idx:end_idx],
            width='stretch',
            hide_index=True,
            height=750
        )
        
        # Download button for ALL data (not just current page)
        st.markdown("---")
        csv = df[final_cols].to_csv(index=False).encode('utf-8')
        
        st.download_button(
            label="📥 Download Full Season Data (CSV)",
            data=csv,
            file_name=f"fotmob_season_{season.replace(' ', '_')}_stats.csv",
            mime="text/csv",
            type="primary",
            width='stretch'
        )
    else:
        # For single round data, just display the table without pagination
        st.dataframe(
            df[final_cols],
            width='stretch',
            hide_index=True,
            height=750
        )


def render_simple_matches_table(df, final_cols):
    """
    Render simple matches table (for "Scrape Matches Only").
    
    Args:
        df (pd.DataFrame): The DataFrame to display
        final_cols (list): List of columns to display
    """
    st.dataframe(
        df[final_cols],
        width='stretch',
        hide_index=True
    )
