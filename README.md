# FotMob Data Scraper

A powerful Python-based web scraper for extracting detailed football league, player, and match data and statistics from FotMob. Built with Selenium and Streamlit, it provides a user-friendly interface to scrape data by round or for an entire season.

## Features

-   **Scrape Matches Only**: Quickly get a list of matches for a specific round (Date, Teams, Score, Status).
-   **Scrape Matches & Stats (Round)**: Get detailed statistics for every match in a selected round.
    -   Includes: Possession, xG, Shots, Passes, Defense, Duels, and more.
-   **Scrape Matches & Stats (Season)**: Scrape data for an entire season.
    -   *Note: This process takes time as it scrapes ~380 matches.*
-   **Pagination**: Easily navigate through large datasets with a paginated table view.
-   **CSV Export**: Download the full scraped dataset (matches + detailed stats) as a CSV file.
-   **Interactive UI**: Built with Streamlit for a smooth and responsive user experience.
-   **UPDATES: Scrape all players in league and season**: Scrape all player data for a specific league and team for a season.
-   **Streamlit App**: FotMob Data Scraper is now an app on streamlit! Check it out on https://fotmob-data-scraper.streamlit.app/

## Prerequisites

-   **Python 3.8+**
-   **Google Chrome** (The scraper uses Selenium with a headless Chrome browser)
-   **Internet Connection**
-   *Note: The `chromedriver` is automatically managed and installed by the application, so no manual setup is required.*

## Installation

1.  **Clone the repository** (or download the source code):
    ```bash
    git clone <repository-url>
    cd football-scraper-data
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## How to Run

1.  **Start the Streamlit app**:
    ```bash
    streamlit run app.py
    ```

2.  **Use the Interface**:
    -   **Season**: Enter the league you want to scrape.
    -   **Season**: Enter the season you want to scrape (e.g., `2024-2025`).
    -   **Round**: Select the round number for round-specific scraping.
    -   **URL Override**: The app doesn't have a league you want? Want to scrape a specific club? Paste the url for a specific league or club to override the above information.
    -   **Buttons**:
        -   `Scrape Matches Only`: Fast scrape of basic match info for the selected round.
        -   `Scrape Matches & Stats (Round)`: Detailed scrape for the selected round.
        -   `Scrape Matches & Stats (Season)`: Detailed scrape for the entire season (all 38 rounds).
        -   `Scrape all players in league and season`: Detailed scrape for player data of a league and season.

3.  **View & Download**:
    -   Results are displayed in a paginated table.
    -   Click `Download Full Season Data (CSV)` to save the data.

##  Project Structure

```
fotmob-scraper/
├── app.py                     # Main Streamlit application (UI and orchestration)
├── packages.txt               # System dependencies for Streamlit Cloud (Chromium)
├── requirements.txt           # Python dependencies
├── README.md                  # Project documentation
├── .gitignore
├── src/                       # Core scraping logic
│   ├── __init__.py
│   ├── scraper.py             # Main orchestrator class (FotMobScraper)
│   ├── match_scraper.py       # Match list scraping logic
│   ├── stats_scraper.py       # Match statistics scraping logic
│   ├── player_scraper.py      # Individual player profile + season stats scraping
│   ├── team_scraper.py        # Team squad scraping
│   ├── league_scraper.py      # League table / team list scraping (handles conference splits)
│   └── league_player_data.py  # Orchestrator: scrapes every player in a league, team by team
└── utils/                     # Helper functions and utilities
    ├── __init__.py
    ├── driver.py              # Selenium WebDriver management (setup, health checks, recovery)
    ├── config.py              # Configuration settings
    ├── app_helpers.py         # UI rendering and data processing helpers
    ├── scraper_helpers.py     # Scraping utility functions
    ├── csv_export.py          # Writes per-team and combined player CSVs (with resume support)
    └── cleanup_player_csv.py  # Post-processing: currency conversion, column renaming, rounding
```

## Important Notes

-   **Scraping Time**: Scraping detailed stats for a full season involves visiting ~380 individual match pages. This process can take a significant amount of time (potentially hours depending on your connection). The app provides a progress bar to track the status.
-   **Headless Mode**: The browser runs in headless mode (invisible) by default for efficiency.
-   **Rate Limiting**: Please be respectful of the website's resources.

## Contributing

Feel free to open issues or submit pull requests if you have suggestions for improvements or new features!
