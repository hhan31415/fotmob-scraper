"""Team statistics scraper for FotMob.

Two entry points:
  - scrape_league_team_stats(driver, league_stats_url): scrapes all teams'
    stats for a league, one row per team, one column per stat category.
    Uses the __NEXT_DATA__ JSON to get stat categories + fetchAllUrls,
    then calls each fetchAllUrl via requests (no extra Selenium page loads).

  - scrape_team_stats(driver, team_stats_url): scrapes a single team's
    stats directly from the team stats page's __NEXT_DATA__ JSON.

Confirmed JSON schemas:
  League stats page (e.g. /leagues/130/stats/mls/teams):
    props.pageProps.stats.teams[] ->
      {header, name, fetchAllUrl, participant: {name, teamId, value, rank, stat}}
    fetchAllUrl (e.g. https://data.fotmob.com/stats/130/season/29580/rating_team.json):
      TopLists[0].StatList[] ->
        {ParticipantName, TeamId, StatValue, Rank, MatchesPlayed, ...}

  Team stats page (e.g. /teams/307691/stats/vancouver-whitecaps/teams):
    props.pageProps.fallback['team-{id}'].stats.teams[] ->
      {header, participant: {name, teamId, value, rank, stat}}
"""

from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
import json
import re
import requests
from . import league_scraper


# Shared requests session with FotMob-appropriate headers, reused across
# all fetchAllUrl calls within one scrape to avoid connection overhead
_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.fotmob.com/",
})


def scrape_league_team_stats(driver, league_stats_url, progress_callback=None):
    """
    Scrapes stats for every team in a league.

    Loads the league stats page once with Selenium to get the list of stat
    categories and their fetchAllUrls, then fetches each category's full
    team rankings via requests.get (no extra browser page loads).

    Args:
        driver: WebDriver instance (already initialized)
        league_stats_url (str): FotMob league stats URL, e.g.
            "https://www.fotmob.com/leagues/130/stats/mls/teams"
        progress_callback (callable, optional): Progress callback

    Returns:
        list[dict]: One dict per team, with keys:
            team_id, team_name, country_code, matches_played,
            + one key per stat header (e.g. "FotMob rating", "Goals per match")
            + one rank key per stat (e.g. "FotMob rating rank")
        Returns [] if the page could not be parsed.
    """
    if progress_callback:
        progress_callback(5, "Loading league stats page...")

    try:
        driver.get(league_stats_url)
    except (TimeoutException, WebDriverException):
        raise

    try:
        next_data = _extract_next_data(driver)
        if not next_data:
            print(f"Could not extract __NEXT_DATA__ from {league_stats_url}")
            return []

        page_props = next_data.get("props", {}).get("pageProps", {})
        stat_categories = page_props.get("stats", {}).get("teams", [])

        if not stat_categories:
            print("No team stat categories found in page")
            return []

        if progress_callback:
            progress_callback(15, f"Found {len(stat_categories)} stat categories, fetching all teams...")

        # team_id -> {team_name, country_code, matches_played, stat: value, ...}
        teams = {}

        for i, cat in enumerate(stat_categories):
            header = cat.get("header", f"stat_{i}")
            fetch_url = cat.get("fetchAllUrl")

            if progress_callback:
                pct = 15 + int((i / len(stat_categories)) * 80)
                progress_callback(pct, f"Fetching: {header}")

            if not fetch_url:
                # Fall back to topThree if no fetchAllUrl
                for entry in cat.get("topThree", []):
                    _add_team_stat(teams, entry, header)
                continue

            try:
                resp = _SESSION.get(fetch_url, timeout=10)
                resp.raise_for_status()
                data = resp.json()

                stat_list = data.get("TopLists", [{}])[0].get("StatList", [])
                for entry in stat_list:
                    team_id = entry.get("TeamId")
                    if not team_id:
                        continue
                    if team_id not in teams:
                        teams[team_id] = {
                            "team_id": team_id,
                            "team_name": entry.get("ParticipantName"),
                            "country_code": entry.get("ParticipantCountryCode"),
                            "matches_played": entry.get("MatchesPlayed"),
                        }
                    teams[team_id][header] = entry.get("StatValue")
                    teams[team_id][f"{header} rank"] = entry.get("Rank")

            except Exception as e:
                print(f"Failed to fetch {header} ({fetch_url}): {e}")
                # Fall back to topThree
                for entry in cat.get("topThree", []):
                    _add_team_stat(teams, entry, header)

        if progress_callback:
            progress_callback(95, "Fetching league table (points, wins, draws, losses)...")

        # Merge in table data (points/wins/draws/losses/GD/position), since
        # the stats page itself doesn't include these -- they only live on
        # the league table page. Built from the same league_stats_url's
        # league ID so it's always the matching table, not a separate input.
        table_url = _stats_url_to_table_url(league_stats_url)
        league_table_data = league_scraper.scrape_league_teams(driver, table_url)

        for team_row in league_table_data.get("teams", []):
            team_id = team_row.get("team_id")
            if team_id in teams:
                teams[team_id]["wins"] = team_row.get("wins")
                teams[team_id]["draws"] = team_row.get("draws")
                teams[team_id]["losses"] = team_row.get("losses")
                teams[team_id]["points"] = team_row.get("points")
                teams[team_id]["table_position"] = team_row.get("position")
                teams[team_id]["group"] = team_row.get("group")
                # Compute goal difference from scoresStr if available
                gd = _parse_goal_difference(team_row)
                if gd is not None:
                    teams[team_id]["goal_difference"] = gd
            elif team_id is not None:
                # Team appeared in table but had no stats entries at all
                # (extremely unlikely, but keep them so nothing's silently
                # dropped)
                teams[team_id] = {
                    "team_id": team_id,
                    "team_name": team_row.get("team_name"),
                    "country_code": None,
                    "matches_played": team_row.get("played"),
                    "wins": team_row.get("wins"),
                    "draws": team_row.get("draws"),
                    "losses": team_row.get("losses"),
                    "points": team_row.get("points"),
                    "table_position": team_row.get("position"),
                    "group": team_row.get("group"),
                }

        if progress_callback:
            progress_callback(100, f"Done. {len(teams)} teams.")

        return sorted(teams.values(), key=lambda t: t.get("table_position") or 999)

    except Exception as e:
        print(f"Error scraping league team stats from {league_stats_url}: {e}")
        import traceback
        traceback.print_exc()
        return []


def _stats_url_to_table_url(stats_url):
    """
    Converts a league stats URL into its corresponding table URL, so the
    points/wins/draws/losses data is fetched from the matching league
    automatically rather than needing a separate URL input.

    e.g. "https://www.fotmob.com/leagues/130/stats/mls/teams"
      -> "https://www.fotmob.com/leagues/130/table/mls"
    """
    match = re.search(r"/leagues/(\d+)/stats/([^/]+)/teams", stats_url)
    if not match:
        # Fall back to a generic rewrite for any /leagues/{id}/{page}/{slug} shape
        return re.sub(
            r"(?:https://www\.fotmob\.com)?/leagues/(\d+)/[^/]+/([^/?]+).*",
            r"https://www.fotmob.com/leagues/\1/table/\2",
            stats_url
        )
    league_id, slug = match.group(1), match.group(2)
    return f"https://www.fotmob.com/leagues/{league_id}/table/{slug}"


def _parse_goal_difference(team_row):
    """
    Returns goal difference from a league_scraper team row. league_scraper
    now carries this through directly from the raw FotMob table JSON's
    goalConDiff field (confirmed: goalConDiff = goals for - goals against).
    """
    return team_row.get("goal_difference")


def scrape_team_stats(driver, team_stats_url, progress_callback=None):
    """
    Scrapes stats for a single team from its stats page.

    Reads directly from __NEXT_DATA__ -- no extra requests needed since
    the team's own value for each stat is already embedded in the page.

    Args:
        driver: WebDriver instance (already initialized)
        team_stats_url (str): FotMob team stats URL, e.g.
            "https://www.fotmob.com/teams/307691/stats/vancouver-whitecaps/teams"
            (will be normalized to /stats/.../teams automatically)
        progress_callback (callable, optional): Progress callback

    Returns:
        dict: Single team stats with keys:
            team_id, team_name, country_code,
            + one key per stat header
            + one rank key per stat
        Returns {} if the page could not be parsed.
    """
    # Normalize URL to the /teams stats page
    team_stats_url = _normalize_team_stats_url(team_stats_url)

    if progress_callback:
        progress_callback(10, "Loading team stats page...")

    try:
        driver.get(team_stats_url)
    except (TimeoutException, WebDriverException):
        raise

    try:
        next_data = _extract_next_data(driver)
        if not next_data:
            print(f"Could not extract __NEXT_DATA__ from {team_stats_url}")
            return {}

        page_props = next_data.get("props", {}).get("pageProps", {})
        fallback = page_props.get("fallback", {})

        # Find the team-{id} key in fallback
        team_key = next((k for k in fallback if k.startswith("team-")), None)
        if not team_key:
            print("No team key found in fallback")
            return {}

        team_id = int(team_key.replace("team-", ""))
        stat_categories = fallback[team_key].get("stats", {}).get("teams", [])

        if not stat_categories:
            print("No team stat categories found")
            return {}

        result = {"team_id": team_id}

        for cat in stat_categories:
            header = cat.get("header", "unknown")
            participant = cat.get("participant", {})
            if not participant:
                continue

            if not result.get("team_name"):
                result["team_name"] = participant.get("name")
                result["country_code"] = participant.get("ccode")

            result[header] = participant.get("value")
            result[f"{header} rank"] = participant.get("rank")

        if progress_callback:
            progress_callback(100, f"Done. {len(stat_categories)} stats for {result.get('team_name')}.")

        return result

    except Exception as e:
        print(f"Error scraping team stats from {team_stats_url}: {e}")
        import traceback
        traceback.print_exc()
        return {}


def _add_team_stat(teams, entry, header):
    """Helper: adds a topThree entry to the teams dict."""
    team_id = entry.get("teamId") or entry.get("TeamId")
    if not team_id:
        return
    if team_id not in teams:
        teams[team_id] = {
            "team_id": team_id,
            "team_name": entry.get("name") or entry.get("ParticipantName"),
            "country_code": entry.get("ccode") or entry.get("ParticipantCountryCode"),
            "matches_played": None,
        }
    teams[team_id][header] = (
        entry.get("value") or entry.get("StatValue")
    )
    teams[team_id][f"{header} rank"] = (
        entry.get("rank") or entry.get("Rank")
    )


def _normalize_team_stats_url(url):
    """
    Ensures a team URL points to the /stats/.../teams page.
    Accepts any FotMob team URL and rewrites the page segment.
    """
    url = url.strip()
    if not url.startswith("http"):
        url = "https://www.fotmob.com" + url

    # If it already ends in /teams, good
    if re.search(r"/teams/\d+/stats/[^/]+/teams$", url):
        return url

    # Rewrite any /teams/{id}/{page}/{slug} to /teams/{id}/stats/{slug}/teams
    rewritten = re.sub(
        r"/teams/(\d+)/[^/]+/([^/]+)$",
        r"/teams/\1/stats/\2/teams",
        url
    )
    return rewritten


def _extract_next_data(driver):
    """Extracts and parses the __NEXT_DATA__ JSON blob from the page."""
    try:
        script_el = driver.find_element(By.ID, "__NEXT_DATA__")
        raw_json = (script_el.get_attribute("innerHTML")
                    or script_el.get_attribute("textContent"))
    except Exception:
        page_source = driver.page_source
        match = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            page_source,
            re.DOTALL,
        )
        if not match:
            return None
        raw_json = match.group(1)

    try:
        return json.loads(raw_json)
    except json.JSONDecodeError as e:
        print(f"Failed to parse __NEXT_DATA__ JSON: {e}")
        return None