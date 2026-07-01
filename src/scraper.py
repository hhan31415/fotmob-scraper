"""Main FotMob scraper class - orchestrates match and stats scraping."""

from utils import driver
from . import match_scraper
from . import stats_scraper
from . import league_player_data
from . import team_stats_scraper

#Summary of change from main: added parameter league_URL to allow choosing different leagues

class FotMobScraper:
    """
    Main scraper class for FotMob football data.
    
    This class acts as a facade, delegating to specialized modules
    for driver management, match scraping, and stats scraping.
    """
    
    def __init__(self):
        """Initialize the scraper with a WebDriver instance."""
        self.driver = driver.setup_driver()
    
    def setup_driver(self):
        """Ensure the driver is alive, recreating if necessary."""
        self.driver = driver.ensure_driver_alive(self.driver)
    
    #NEW Added league_URL to use for match_scraper.scape_matches()
    def get_matches(self, season, round_num, league_URL, progress_callback=None):
        """
        Scrape match data for a specific season and round.
        
        Args:
            season (str): Season in format "YYYY-YYYY" (e.g., "2024-2025")
            round_num (int): Round number (1-38)
            progress_callback (callable, optional): Callback for progress updates
            
        Returns:
            list: List of match dictionaries with keys:
                - home: Home team name
                - away: Away team name
                - score: Match score or time
                - status: Match status (FT, Live, Upcoming, etc.)
                - url: Match URL
                - date: Match date
        """
        self.setup_driver()
        return match_scraper.scrape_matches(
            self.driver, 
            season, 
            round_num, league_URL, 
            progress_callback
        )
    
    def get_match_stats(self, match_url, progress_callback=None):
        """
        Scrape detailed statistics for a specific match.
        
        Args:
            match_url (str): URL of the match page
            progress_callback (callable, optional): Callback for progress updates
            
        Returns:
            dict: Dictionary of stats organized by section:
                - Top stats: Ball possession, xG, shots, etc.
                - Expected goals (xG): Detailed xG breakdown
                - Shots: Shot statistics
                - Passes: Passing statistics
                - Discipline: Cards
                - Defense: Defensive statistics
                - Duels: Duel statistics
        """
        self.setup_driver()
        return stats_scraper.scrape_match_stats(
            self.driver,
            match_url,
            progress_callback
        )

    def get_matches_with_stats(self, season, round_num, league_URL, progress_callback=None):
        """
        Scrape matches and their stats for a specific season and round.
        
        Args:
            season (str): Season in format "YYYY-YYYY"
            round_num (int): Round number
            progress_callback (callable, optional): Callback for progress updates
            
        Returns:
            list: List of dictionaries, two per match (one for Home, one for Away)
        """
        from utils.scraper_helpers import create_team_rows
        
        # 1. Get all matches first
        if progress_callback:
            progress_callback(0, "Fetching match list...")
            
        matches = self.get_matches(season, round_num, league_URL)
        
        if not matches:
            return []
            
        total_matches = len(matches)
        results = []
        
        # 2. Iterate through each match and get stats
        for i, match in enumerate(matches):
            # Update progress
            if progress_callback:
                percent = int((i / total_matches) * 100)
                progress_callback(percent, f"Scraping match {i+1}/{total_matches}: {match['home']} vs {match['away']}")
            
            # Create base rows for home and away using helper
            home_row, away_row = create_team_rows(match, round_num)
            
            # Only scrape stats if match is finished
            if match['status'] in ['FT', 'HT']:
                try:
                    stats = self.get_match_stats(match['url'])
                    
                    # Flatten stats into rows
                    for section, section_stats in stats.items():
                        for stat_name, values in section_stats.items():
                            # values[0] is Home, values[1] is Away
                            home_row[stat_name] = values[0]
                            away_row[stat_name] = values[1]
                            
                except Exception as e:
                    print(f"Failed to get stats for {match['home']} vs {match['away']}: {e}")
            
            results.append(home_row)
            results.append(away_row)
            
        if progress_callback:
            progress_callback(100, "Finished scraping all matches!")
            
        return results


    def get_matches_season(self, season, league_URL, total_rounds=38, progress_callback=None):
        """
        Scrape match list (no stats) for an entire season.

        Args:
            season (str): Season in format "YYYY-YYYY" or "YYYY"
            league_URL (str): FotMob fixtures URL for the league
            total_rounds (int): Number of rounds in this league's season
            progress_callback (callable, optional): Callback for progress updates

        Returns:
            list: List of match dictionaries (same shape as get_matches)
        """
        all_results = []

        for round_num in range(1, total_rounds + 1):
            def round_progress(percent, text, r=round_num):
                if progress_callback:
                    overall = int(((r - 1) / total_rounds * 100) + (percent / total_rounds))
                    progress_callback(overall, f"[Round {r}/{total_rounds}] {text}")

            try:
                round_results = self.get_matches(season, round_num, league_URL,
                                                progress_callback=round_progress)
                all_results.extend(round_results)
            except Exception as e:
                print(f"Error scraping Round {round_num}: {e}")
                continue

        if progress_callback:
            progress_callback(100, "Finished scraping season!")

        return all_results


    def get_season_stats(self, season, league_URL, total_rounds=38, progress_callback=None):
        """
        Scrape match data and stats for an entire season.

        Args:
            season (str): Season in format "YYYY-YYYY" or "YYYY"
            league_URL (str): FotMob fixtures URL for the league
            total_rounds (int): Number of rounds in this league's season
            progress_callback (callable, optional): Callback for progress updates

        Returns:
            list: List of dictionaries, two per match (one for Home, one for Away)
        """
        all_results = []

        for round_num in range(1, total_rounds + 1):
            if progress_callback:
                progress_callback(0, f"Starting Round {round_num}/{total_rounds}...")

            def round_progress(percent, text, r=round_num):
                if progress_callback:
                    overall = int(((r - 1) / total_rounds * 100) + (percent / total_rounds))
                    progress_callback(overall, f"[Round {r}/{total_rounds}] {text}")

            try:
                round_results = self.get_matches_with_stats(season, round_num, league_URL,
                                                            progress_callback=round_progress)
                all_results.extend(round_results)
            except Exception as e:
                print(f"Error scraping Round {round_num}: {e}")
                continue

        if progress_callback:
            progress_callback(100, "Finished scraping season!")

        return all_results
    
    
    def get_league_player_data(self, league_table_url, output_dir, progress_callback=None):
        """
        Scrapes full player data (profile + season stats) for every player
        on every team in a league, given the league's table page URL.

        This is a separate pipeline from get_matches/get_season_stats: it
        answers "who plays where and how good are they" rather than "what
        happened in matches". Writes one CSV per team plus a combined
        league-wide CSV, all incrementally so progress survives a crash.

        Resume: if interrupted, re-running with the same output_dir will
        skip any team whose CSV already exists and pick up where it left
        off. To force a full re-scrape, delete output_dir (or just the
        specific team CSVs you want redone).

        Args:
            league_table_url (str): FotMob league table URL, e.g.
                "https://www.fotmob.com/leagues/130/table/mls"
            output_dir (str): Directory to write per-team and combined CSVs into
            progress_callback (callable, optional): Callback for progress updates

        Returns:
            dict: Summary with keys league_name, season, teams_scraped,
                teams_skipped_resume, teams_failed, total_players,
                combined_csv_path, team_csv_paths. See
                league_player_data.scrape_league_player_data() for full detail.
        """
        self.setup_driver()
        return league_player_data.scrape_league_player_data(
            self.driver,
            league_table_url,
            output_dir,
            progress_callback
        )
    def get_club_player_data(self, club_url, output_dir, progress_callback=None):
        """
        Scrapes full player data for every player on a single club's squad.
 
        Accepts any FotMob team URL (overview, squad, fixtures, etc.) and
        normalizes it to the squad page automatically.
 
        Args:
            club_url (str): Any FotMob team URL, e.g.
                "https://www.fotmob.com/teams/9825/overview/bayern-munich"
            output_dir (str): Directory to write the club CSV into
            progress_callback (callable, optional): Progress callback
 
        Returns:
            dict: Summary with team_name, total_players, combined_csv_path.
                See league_player_data.scrape_club_player_data() for full detail.
        """
        self.setup_driver()
        return league_player_data.scrape_club_player_data(
            self.driver,
            club_url,
            output_dir,
            progress_callback
        )
    
    def get_league_team_stats(self, league_stats_url, season=None, progress_callback=None):
        """
        Scrapes stats for every team in a league.

        Args:
            league_stats_url (str): FotMob league stats URL, e.g.
                "https://www.fotmob.com/leagues/130/stats/mls/teams"
            progress_callback (callable, optional): Progress callback

        Returns:
            list[dict]: One dict per team with all stat categories as columns.
        """
        self.setup_driver()
        return team_stats_scraper.scrape_league_team_stats(
            self.driver, league_stats_url, season, progress_callback
        )
    
    def get_team_stats(self, team_stats_url, progress_callback=None):
        """
        Scrapes stats for a single team.

        Args:
            team_stats_url (str): Any FotMob team URL (normalized automatically)
            progress_callback (callable, optional): Progress callback

        Returns:
            dict: Single team stats with all stat categories as keys.
        """
        self.setup_driver()
        return team_stats_scraper.scrape_team_stats(
            self.driver, team_stats_url, progress_callback
        )
    
    def get_available_seasons(self, league_stats_url):
        self.setup_driver()
        return team_stats_scraper.get_available_seasons(
            self.driver, league_stats_url
        )

    def close(self):
        """Close the WebDriver instance."""
        driver.close_driver(self.driver)
