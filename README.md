# FotMob Scraper ⚽

A powerful Python-based web scraper for extracting detailed football match data and statistics from FotMob. Built with Selenium and Streamlit, it provides a user-friendly interface to scrape data by round or for an entire season.

## 🌟 Features

-   **Scrape Matches Only**: Quickly get a list of matches for a specific round (Date, Teams, Score, Status).
-   **Scrape Matches & Stats (Round)**: Get detailed statistics for every match in a selected round.
    -   Includes: Possession, xG, Shots, Passes, Defense, Duels, and more.
-   **Scrape Matches & Stats (Season)**: Scrape data for an entire season (Rounds 1-38).
    -   *Note: This process takes time as it scrapes ~380 matches.*
-   **Pagination**: Easily navigate through large datasets with a paginated table view.
-   **CSV Export**: Download the full scraped dataset (matches + detailed stats) as a CSV file.
-   **Interactive UI**: Built with Streamlit for a smooth and responsive user experience.

## 🛠️ Prerequisites

-   **Python 3.8+**
-   **Google Chrome** (The scraper uses Selenium with a headless Chrome browser)
-   **Internet Connection**
-   *Note: The `chromedriver` is automatically managed and installed by the application, so no manual setup is required.*

## 📦 Installation

1.  **Clone the repository** (or download the source code):
    ```bash
    git clone <repository-url>
    cd football-scraper-data
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

## 🚀 How to Run

1.  **Start the Streamlit app**:
    ```bash
    streamlit run app.py
    ```

2.  **Use the Interface**:
    -   **Season**: Enter the season you want to scrape (e.g., `2024-2025`).
    -   **Round**: Select the round number (1-38) for round-specific scraping.
    -   **Buttons**:
        -   `🔍 Scrape Matches Only`: Fast scrape of basic match info for the selected round.
        -   `📊 Scrape Matches & Stats (Round)`: Detailed scrape for the selected round.
        -   `📅 Scrape Matches & Stats (Season)`: Detailed scrape for the entire season (all 38 rounds).

3.  **View & Download**:
    -   Results are displayed in a paginated table.
    -   Click `📥 Download Full Season Data (CSV)` to save the data.

## 📂 Project Structure

```
football-scraper-data/
├── app.py                  # Main Streamlit application (UI and orchestration)
├── requirements.txt        # Python dependencies
├── README.md               # Project documentation
├── src/                    # Core scraping logic
│   ├── __init__.py
│   ├── scraper.py          # Main orchestrator class (FotMobScraper)
│   ├── match_scraper.py    # Match list scraping logic
│   └── stats_scraper.py    # Match statistics scraping logic
└── utils/                  # Helper functions and utilities
    ├── driver.py           # Selenium WebDriver management
    ├── config.py           # Configuration settings
    ├── app_helpers.py      # UI rendering and data processing helpers
    └── scraper_helpers.py  # Scraping utility functions
```

## ⚠️ Important Notes

-   **Scraping Time**: Scraping detailed stats for a full season involves visiting ~380 individual match pages. This process can take a significant amount of time (potentially hours depending on your connection). The app provides a progress bar to track the status.
-   **Headless Mode**: The browser runs in headless mode (invisible) by default for efficiency.
-   **Rate Limiting**: Please be respectful of the website's resources.

## 🤝 Contributing

Feel free to open issues or submit pull requests if you have suggestions for improvements or new features!
