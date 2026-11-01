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
    
    def get_competition(self, league_URL, season=None):
        """
        Load a competition season's name, available seasons and full match list.

        Args:
            league_URL (str): FotMob fixtures URL
            season (str, optional): e.g. "2025-2026" or "2026"; None = current

        Returns:
            dict: {name, season, seasons, matches}. See match_scraper.fetch_competition.
        """
        self.setup_driver()
        return match_scraper.fetch_competition(self.driver, league_URL, season)

    #NEW Added league_URL to use for match_scraper.scape_matches()
    def get_matches(self, season, round_num, league_URL, progress_callback=None):
        """
        Scrape match data for one round or stage of a competition season.
        
        Args:
            season (str): Season, e.g. "2024-2025" or "2026"
            round_num (str or int): Round key, e.g. "1", "1/8" (Round of 16), "final"
            league_URL (str): FotMob fixtures URL
            progress_callback (callable, optional): Callback for progress updates
            
        Returns:
            list: List of match dictionaries with keys:
                - match_id, date, kickoff_utc, round, round_name, group
                - home, away, home_id, away_id
                - score: Match score ("" if not played)
                - status: FT, AET, Pen, Live, Upcoming, Cancelled, ...
                - finished: True once the match is over
                - url: Match URL
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
            dict: {match_id, fifa_rank: [home, away], periods: {"All" | "1st half" |
                "2nd half": {section: {stat: {display, value, total, format}}}}}.
                See stats_scraper.scrape_match_stats.
        """
        self.setup_driver()
        return stats_scraper.scrape_match_stats(
            self.driver,
            match_url,
            progress_callback
        )

    def get_matches_with_stats(self, season, round_num, league_URL, progress_callback=None):
        """
        Scrape matches and their stats for one round or stage.
        
        Args:
            season (str): Season, e.g. "2025-2026" or "2026"
            round_num (str or int): Round key, e.g. "1", "1/8", "final"
            league_URL (str): FotMob fixtures URL
            progress_callback (callable, optional): Callback for progress updates
            
        Returns:
            list: List of dictionaries, two per match (one for home, one for away)
        """
        if progress_callback:
            progress_callback(0, "Fetching match list...")
            
        matches = self.get_matches(season, round_num, league_URL)
        return self._add_match_stats(matches, progress_callback)

    def get_matches_season(self, season, league_URL, progress_callback=None):
        """
        Scrape match list (no stats) for an entire competition season,
        including group stages and knockout rounds.

        Args:
            season (str): Season, e.g. "2025-2026" or "2026"
            league_URL (str): FotMob fixtures URL for the competition
            progress_callback (callable, optional): Callback for progress updates

        Returns:
            list: List of match dictionaries (same shape as get_matches)
        """
        self.setup_driver()
        return match_scraper.scrape_all_matches(
            self.driver, season, league_URL, progress_callback
        )

    def get_season_stats(self, season, league_URL, progress_callback=None):
        """
        Scrape match data and stats for an entire competition season.

        Args:
            season (str): Season, e.g. "2025-2026" or "2026"
            league_URL (str): FotMob fixtures URL for the competition
            progress_callback (callable, optional): Callback for progress updates

        Returns:
            list: List of dictionaries, two per match (one for home, one for away)
        """
        if progress_callback:
            progress_callback(0, "Fetching match list...")

        matches = self.get_matches_season(season, league_URL)
        return self._add_match_stats(matches, progress_callback)

    def _add_match_stats(self, matches, progress_callback=None):
        """
        Builds home/away rows for each match and adds stats for finished ones.

        Returns:
            list: List of dictionaries, two per match (one for home, one for away)
        """
        from utils.scraper_helpers import create_team_rows, add_stats_to_rows

        total_matches = len(matches)
        results = []

        for i, match in enumerate(matches):
            if progress_callback:
                percent = int((i / total_matches) * 100)
                progress_callback(percent, f"Scraping match {i+1}/{total_matches}: {match['home']} vs {match['away']}")

            home_row, away_row = create_team_rows(match)

            # Only scrape stats once the match is over (FT, AET, Pen)
            if match['finished']:
                try:
                    stats = self.get_match_stats(match['url'])
                    add_stats_to_rows(home_row, away_row, stats)
                except Exception as e:
                    print(f"Failed to get stats for {match['home']} vs {match['away']}: {e}")

            results.append(home_row)
            results.append(away_row)

        if progress_callback:
            progress_callback(100, "Finished scraping all matches!")

        return results
    
    
    def get_league_player_data(self, league_table_url, output_dir,
                            skip_reserves=False, skip_zero_match=False,
                            progress_callback=None):
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
            skip_reserves (bool): skips reserve/loan players
            skip_zero_match (bool): skips players with zero matches

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
            skip_reserves=skip_reserves,
            skip_zero_match=skip_zero_match,
            progress_callback=progress_callback,
        )
    def get_club_player_data(self, club_url, output_dir, skip_reserves=False, skip_zero_match=False, progress_callback=None):
        """
        Scrapes full player data for every player on a single club's squad.
 
        Accepts any FotMob team URL (overview, squad, fixtures, etc.) and
        normalizes it to the squad page automatically.
 
        Args:
            club_url (str): Any FotMob team URL, e.g.
                "https://www.fotmob.com/teams/9825/overview/bayern-munich"
            output_dir (str): Directory to write the club CSV into
            skip_reserves (bool): Skips reserve and loan players
            skip_zero_match (bool): Skips players with zero matches
            progress_callback (callable, optional): Progress callback
 
        Returns:
            dict: Summary with team_name, total_players, combined_csv_path.
                See league_player_data.scrape_club_player_data() for full detail.
        """
        self.setup_driver()
        return league_player_data.scrape_club_player_data(
            self.driver, club_url, output_dir,
            skip_reserves=skip_reserves,
            skip_zero_match=skip_zero_match,
            progress_callback=progress_callback,
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
