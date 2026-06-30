"""League table scraping functionality for FotMob.

Gets the full list of teams in a league/season by reading the league table
page's embedded __NEXT_DATA__ JSON. Handles leagues with multiple table
groups (e.g. MLS Eastern/Western conferences, or a separate Supporters
Shield ranking of the same teams) by deduplicating on team ID.

Schema confirmed via verify_fotmob_json.py against a live league table page
(https://www.fotmob.com/leagues/130/table/mls):

  props.pageProps
    .details                  -> {id, name, country, selectedSeason, ...}
    .table[0].data.tables[]   -> list of table GROUPS (e.g. Eastern, Western,
                                  possibly Supporters Shield -- a re-ranking
                                  of the same teams, not new teams)
      each group:
        leagueName             -> e.g. "Eastern"
        table.all[]             -> list of TEAMS in that group:
          {name, shortName, id, pageUrl, played, wins, draws, losses,
           scoresStr, goalConDiff, pts, idx, qualColor}
          pageUrl is a TEAM OVERVIEW url (.../overview/<slug>), NOT a squad
          url -- must be converted to .../squad/<slug> for team_scraper.
"""

from selenium.webdriver.common.by import By
import json
import re


def scrape_league_teams(driver, league_table_url, progress_callback=None):
    """
    Scrapes the full list of teams in a league from its table page,
    deduplicated across any conference/group splits.

    Args:
        driver: WebDriver instance (already initialized)
        league_table_url (str): FotMob league table URL, e.g.
            "https://www.fotmob.com/leagues/130/table/mls"
        progress_callback (callable, optional): Progress callback function

    Returns:
        dict: {
            "league_id": int,
            "league_name": str,
            "country": str,
            "season": str,
            "groups": [str, ...],     # e.g. ["Eastern", "Western"], or
                                       # [] if the league has a single table
            "teams": [
                {
                    "team_id": int,
                    "team_name": str,
                    "short_name": str,
                    "group": str or None,   # which table group this team
                                             # was first seen in
                    "squad_url": str,        # ready for team_scraper.scrape_squad()
                    "overview_url": str,
                    "played": int, "wins": int, "draws": int, "losses": int,
                    "points": int, "position": int,
                }
            ]
        }
        Returns {} if the page could not be parsed.
    """
    try:
        if progress_callback:
            progress_callback(10, "Loading league table page...")

        print(f"Navigating to league table URL: {league_table_url}")
        driver.get(league_table_url)

        next_data = _extract_next_data(driver)
        if not next_data:
            print(f"Could not extract __NEXT_DATA__ for {league_table_url}")
            return {}

        if progress_callback:
            progress_callback(60, "Parsing league table...")

        result = _parse_league_table(next_data)

        if progress_callback:
            progress_callback(100, "Finished!")

        print(f"Found {len(result.get('teams', []))} unique teams across {len(result.get('groups', [])) or 1} group(s) for {result.get('league_name')}")
        return result

    except Exception as e:
        print(f"Error scraping league table {league_table_url}: {e}")
        import traceback
        traceback.print_exc()
        return {}


def _extract_next_data(driver):
    """
    Pulls the __NEXT_DATA__ JSON blob out of the page source.
    Identical logic to player_scraper._extract_next_data and
    team_scraper._extract_next_data.

    Args:
        driver: WebDriver instance

    Returns:
        dict or None
    """
    try:
        script_el = driver.find_element(By.ID, "__NEXT_DATA__")
        raw_json = script_el.get_attribute("innerHTML") or script_el.get_attribute("textContent")
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


def _parse_league_table(next_data):
    """
    Walks the confirmed __NEXT_DATA__ structure for league table pages.

    Args:
        next_data (dict): Parsed __NEXT_DATA__ JSON

    Returns:
        dict: See scrape_league_teams() docstring for shape
    """
    page_props = next_data.get("props", {}).get("pageProps", {})
    details = page_props.get("details", {})

    result = {
        "league_id": details.get("id"),
        "league_name": details.get("name"),
        "country": details.get("country"),
        "season": details.get("selectedSeason") or details.get("latestSeason"),
        "groups": [],
        "teams": [],
    }

    table_wrapper = page_props.get("table", [])
    if not table_wrapper:
        print("No 'table' key found in pageProps")
        return result

    # table[0].data.tables[] holds the actual group(s)
    table_data = table_wrapper[0].get("data", {}) if isinstance(table_wrapper, list) else {}
    groups = table_data.get("tables", [])

    seen_team_ids = set()

    for group in groups:
        group_name = group.get("leagueName")
        if group_name:
            result["groups"].append(group_name)

        team_rows = (group.get("table") or {}).get("all", [])

        for row in team_rows:
            team_id = row.get("id")
            if team_id is None or team_id in seen_team_ids:
                # Skip duplicates -- handles cases like a "Supporters Shield"
                # group that re-ranks teams already seen in Eastern/Western
                continue
            seen_team_ids.add(team_id)

            overview_url = row.get("pageUrl", "")
            squad_url = _overview_url_to_squad_url(overview_url)

            result["teams"].append({
                "team_id": team_id,
                "team_name": row.get("name"),
                "short_name": row.get("shortName"),
                "group": group_name,
                "squad_url": squad_url,
                "overview_url": f"https://www.fotmob.com{overview_url}" if overview_url else None,
                "played": row.get("played"),
                "wins": row.get("wins"),
                "draws": row.get("draws"),
                "losses": row.get("losses"),
                "points": row.get("pts"),
                "position": row.get("idx"),
                "goal_difference": row.get("goalConDiff"),
            })

    # If there were no sub-groups at all (single-table league), some leagues
    # may put team rows directly under table_data without a 'tables' wrapper.
    # Fall back to checking for a direct 'table' key on table_data itself.
    if not groups:
        direct_rows = (table_data.get("table") or {}).get("all", [])
        for row in direct_rows:
            team_id = row.get("id")
            if team_id is None or team_id in seen_team_ids:
                continue
            seen_team_ids.add(team_id)

            overview_url = row.get("pageUrl", "")
            squad_url = _overview_url_to_squad_url(overview_url)

            result["teams"].append({
                "team_id": team_id,
                "team_name": row.get("name"),
                "short_name": row.get("shortName"),
                "group": None,
                "squad_url": squad_url,
                "overview_url": f"https://www.fotmob.com{overview_url}" if overview_url else None,
                "played": row.get("played"),
                "wins": row.get("wins"),
                "draws": row.get("draws"),
                "losses": row.get("losses"),
                "points": row.get("pts"),
                "position": row.get("idx"),
                "goal_difference": row.get("goalConDiff"),
            })

    return result


def _overview_url_to_squad_url(overview_url):
    """
    Converts a team overview URL into a squad URL.

    e.g. "/teams/960720/overview/inter-miami-cf"
      -> "https://www.fotmob.com/teams/960720/squad/inter-miami-cf"

    Args:
        overview_url (str): Relative team overview URL from pageUrl field

    Returns:
        str or None
    """
    if not overview_url:
        return None

    squad_path = re.sub(r"/overview/", "/squad/", overview_url)

    if squad_path.startswith("http"):
        return squad_path
    return f"https://www.fotmob.com{squad_path}"


def detect_league_rounds(driver, league_fixtures_url):
    """
    Detects the total number of rounds in a league by reading the max
    round number from the fixtures page's __NEXT_DATA__ JSON.

    Args:
        driver: WebDriver instance (already initialized)
        league_fixtures_url (str): FotMob league fixtures URL, e.g.
            "https://www.fotmob.com/leagues/130/fixtures/mls"

    Returns:
        int: Total number of rounds, or None if detection failed
    """
    try:
        driver.get(league_fixtures_url)
        next_data = _extract_next_data(driver)
        if not next_data:
            return None

        page_props = next_data.get("props", {}).get("pageProps", {})
        all_matches = (
            page_props.get("fixtures", {})
            .get("allMatches", [])
        )

        if not all_matches:
            return None

        rounds = []
        for match in all_matches:
            r = match.get("round")
            if r is not None:
                try:
                    rounds.append(int(r))
                except (ValueError, TypeError):
                    pass

        return max(rounds) if rounds else None

    except Exception as e:
        print(f"Could not detect round count from {league_fixtures_url}: {e}")
        return None



    """
    Development utility: navigates to a league table page and prints
    the groups found plus team counts per group, to spot-check against
    a new league (e.g. confirming single-table leagues like Premier
    League don't break the parsing logic).

    Args:
        driver: WebDriver instance
        league_table_url (str): FotMob league table URL
    """
    driver.get(league_table_url)
    next_data = _extract_next_data(driver)
    if not next_data:
        print("Could not extract __NEXT_DATA__")
        return

    result = _parse_league_table(next_data)

    print(f"League: {result.get('league_name')} ({result.get('country')}) - {result.get('season')}")
    print(f"Groups: {result.get('groups')}")
    print(f"Total unique teams: {len(result.get('teams', []))}\n")

    by_group = {}
    for t in result.get("teams", []):
        by_group.setdefault(t["group"], []).append(t["team_name"])

    for group, names in by_group.items():
        print(f"{group or '(no group)'} ({len(names)}): {', '.join(names)}")