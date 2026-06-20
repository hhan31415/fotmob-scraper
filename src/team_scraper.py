"""Team and squad scraping functionality for FotMob.

Like player_scraper, this reads structured data from the embedded
__NEXT_DATA__ JSON blob rather than the rendered DOM.

Schema confirmed via verify_fotmob_json.py against a live squad page
(https://www.fotmob.com/teams/960720/squad/inter-miami-cf):

  props.pageProps.fallback['team-<id>']
    .details                  -> {id, name, shortName, country, primaryLeagueId,
                                   primaryLeagueName, latestSeason, ...}
    .squad.squad[]             -> list of position groups:
                                   [{title: "coach"/"keepers"/"defenders"/"midfielders"/
                                     "attackers", members: [{id, name, age, height,
                                     dateOfBirth, ccode, cname, role, ...}]}]
                                   NOTE: "coach" group has no playable position and
                                   should be excluded from the player list.

The fallback cache key is "team-<teamId>", where teamId comes from the
squad URL itself (e.g. /teams/960720/squad/inter-miami-cf -> 960720).
"""

from selenium.webdriver.common.by import By
import json
import re


def scrape_squad(driver, squad_url, progress_callback=None):
    """
    Scrapes a team's full squad list (players + basic metadata) from its
    FotMob squad page.

    Args:
        driver: WebDriver instance (already initialized)
        squad_url (str): FotMob squad URL, e.g.
            "https://www.fotmob.com/teams/960720/squad/inter-miami-cf"
        progress_callback (callable, optional): Progress callback function

    Returns:
        dict: {
            "team_id": int,
            "team_name": str,
            "country": str,
            "league_name": str,
            "season": str,
            "players": [
                {
                    "player_id": int,
                    "name": str,
                    "position_group": str,   # "keepers" | "defenders" | "midfielders" | "attackers"
                    "age": int or None,
                    "height_cm": int or None,
                    "country": str,          # cname, e.g. "Argentina"
                    "country_code": str,     # ccode, e.g. "ARG"
                    "player_url": str,       # built from id + name, ready for player_scraper
                }
            ]
        }
        Returns {} if the page could not be parsed.
    """
    try:
        if progress_callback:
            progress_callback(10, "Loading squad page...")

        print(f"Navigating to squad URL: {squad_url}")
        driver.get(squad_url)

        next_data = _extract_next_data(driver)
        if not next_data:
            print(f"Could not extract __NEXT_DATA__ for {squad_url}")
            return {}

        team_id = _extract_team_id(squad_url)

        if progress_callback:
            progress_callback(60, "Parsing squad data...")

        result = _parse_squad_data(next_data, team_id)

        if progress_callback:
            progress_callback(100, "Finished!")

        print(f"Found {len(result.get('players', []))} players for {result.get('team_name')}")
        return result

    except Exception as e:
        print(f"Error scraping squad {squad_url}: {e}")
        import traceback
        traceback.print_exc()
        return {}


def _extract_next_data(driver):
    """
    Pulls the __NEXT_DATA__ JSON blob out of the page source.
    Identical logic to player_scraper._extract_next_data.

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


def _extract_team_id(squad_url):
    """
    Extracts the numeric team ID from a FotMob squad/team URL.

    Args:
        squad_url (str): e.g. "https://www.fotmob.com/teams/960720/squad/inter-miami-cf"

    Returns:
        str or None
    """
    match = re.search(r"/teams/(\d+)", squad_url)
    return match.group(1) if match else None


def _parse_squad_data(next_data, team_id):
    """
    Walks the confirmed __NEXT_DATA__ structure for squad pages.

    The squad data lives under a dynamic key 'team-<id>' inside the SWR
    fallback cache (props.pageProps.fallback), rather than a fixed top-level
    key. We locate it by matching the 'team-' prefix rather than hardcoding
    team_id, in case the ID couldn't be parsed from the URL for some reason.

    Args:
        next_data (dict): Parsed __NEXT_DATA__ JSON
        team_id (str): Numeric team ID parsed from URL (fallback only)

    Returns:
        dict: See scrape_squad() docstring for shape
    """
    page_props = next_data.get("props", {}).get("pageProps", {})
    fallback = page_props.get("fallback", {})

    team_key = f"team-{team_id}" if team_id else None
    team_obj = fallback.get(team_key) if team_key else None

    # Fallback: scan for any key matching the 'team-<digits>' pattern
    if team_obj is None:
        for key, value in fallback.items():
            if re.match(r"^team-\d+$", key):
                team_obj = value
                break

    if team_obj is None:
        print("Could not locate 'team-<id>' key in fallback cache")
        return {}

    details = team_obj.get("details", {})
    result = {
        "team_id": details.get("id", team_id),
        "team_name": details.get("name"),
        "country": details.get("country"),
        "league_name": details.get("primaryLeagueName"),
        "season": details.get("latestSeason"),
        "players": [],
    }

    squad_data = team_obj.get("squad", {})
    position_groups = squad_data.get("squad", [])

    for group in position_groups:
        group_title = group.get("title")
        # Skip the coaching staff group; only interested in players
        if group_title == "coach":
            continue

        for member in group.get("members", []):
            player_id = member.get("id")
            name = member.get("name")
            if not player_id or not name:
                continue

            result["players"].append({
                "player_id": player_id,
                "name": name,
                "position_group": group_title,   # broad: keepers/defenders/midfielders/attackers
                # NOTE: squad page does NOT expose a specific position (e.g. "Striker" vs
                # "Centre-Back") -- it only repeats the broad group via `role`. The real
                # specific position is on the player page (positionDescription.primaryPosition),
                # which player_scraper.scrape_player() now captures as `position`.
                "age": member.get("age"),
                "height_cm": member.get("height"),
                "country": member.get("cname"),
                "country_code": member.get("ccode"),
                "player_url": _build_player_url(player_id, name),
            })

    return result


def _build_player_url(player_id, name):
    """
    Builds a canonical FotMob player URL from an ID and name, matching
    the format used elsewhere on the site: /players/<id>/<slugified-name>

    FotMob's slug doesn't strictly need to be correct for the page to load
    (it redirects/serves correctly based on ID alone), but matching the
    real format avoids unnecessary redirects.

    Args:
        player_id (int): FotMob player ID
        name (str): Player display name

    Returns:
        str: Full player URL
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"https://www.fotmob.com/players/{player_id}/{slug}"


def debug_dump_squad_keys(driver, squad_url):
    """
    Development utility: navigates to a squad page and prints the
    position groups + player counts found, to spot-check the parsing
    logic against a new team.

    Args:
        driver: WebDriver instance
        squad_url (str): FotMob squad URL
    """
    driver.get(squad_url)
    next_data = _extract_next_data(driver)
    if not next_data:
        print("Could not extract __NEXT_DATA__")
        return

    team_id = _extract_team_id(squad_url)
    result = _parse_squad_data(next_data, team_id)

    print(f"Team: {result.get('team_name')} ({result.get('country')})")
    print(f"League: {result.get('league_name')} | Season: {result.get('season')}")
    print(f"Total players: {len(result.get('players', []))}\n")

    by_group = {}
    for p in result.get("players", []):
        by_group.setdefault(p["position_group"], []).append(p["name"])

    for group, names in by_group.items():
        print(f"{group} ({len(names)}): {', '.join(names)}")
