"""Player statistics scraping functionality for FotMob.

Reads structured data directly from FotMob's embedded __NEXT_DATA__ JSON
blob rather than parsing the rendered DOM. Player pages are always
server-rendered, so this is both faster and far more reliable than
CSS-selector scraping (no hashed class names, no waiting for JS hydration).

Schema confirmed via verify_fotmob_json.py against a live player page
(https://www.fotmob.com/players/1233655/alex-scott):

  props.pageProps.data
    .id, .name                          -> identity
    .primaryTeam.teamName                -> current club
    .playerInformation[]                 -> [{title, value: {numberValue, fallback}}]
                                             Height, Shirt, Age, Country, Preferred foot,
                                             Transfer value, Contract end
    .mainLeague.stats[]                  -> current league season summary
                                             [{title, value}] e.g. Goals, Assists, Matches,
                                             Minutes played, Rating, Yellow/Red cards
    .firstSeasonStats.topStatCard.items[]    -> headline stats incl. per90 + percentileRank
    .firstSeasonStats.statsSection.items[]   -> list of stat-groups (Shooting, Passing,
                                             Possession, Defending), each:
                                               {title, items: [{title, statValue, per90,
                                                percentileRank, statFormat}]}
                                             This is where xG, xGOT, xA, duels won %, etc. live.
    .statSeasons[]                       -> which seasons/tournaments are available
                                             (does NOT contain stat values itself)
"""

from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
import json
import re


def scrape_player(driver, player_url, progress_callback=None):
    """
    Scrapes full profile + season stats for a single player.

    Args:
        driver: WebDriver instance (already initialized)
        player_url (str): FotMob player URL, e.g.
            "https://www.fotmob.com/players/1233655/alex-scott"
        progress_callback (callable, optional): Progress callback function

    Returns:
        dict: Player data with keys:
            - player_id, name, team, url
            - height_cm, shirt, age, country, preferred_foot, market_value, contract_end
            - season_league, season_year
            - season_summary: dict of {stat_title: value} from mainLeague.stats
              (Goals, Assists, Matches, Started, Minutes played, Rating, cards)
            - detailed_stats: dict of {group_title: {stat_title: statValue}}
              e.g. {"Shooting": {"xG": "3.81", "xGOT": "2.68", ...}, "Passing": {...}}
            - detailed_stats_per90: same shape as detailed_stats but per-90 values
            - raw: full parsed player data object, kept so nothing is lost if a
              field is missed above
        Returns {} if the page loaded but data could not be parsed (e.g. a
        genuinely low-activity player missing whole stat sections in the JSON).

    Raises:
        TimeoutException, WebDriverException: if the page itself failed to
        load (driver hung/crashed/timed out). These are NOT swallowed here,
        unlike parsing errors, because the caller (league_player_data.py)
        needs to see them to trigger driver-health recovery -- otherwise a
        hung driver silently fails every subsequent player with no recovery,
        since this function would just return {} for every case alike.
    """
    try:
        if progress_callback:
            progress_callback(10, "Loading player page...")

        print(f"Navigating to player URL: {player_url}")
        driver.get(player_url)

    except (TimeoutException, WebDriverException):
        # Driver-level failure (hung renderer, crashed tab, etc.) -- let
        # this propagate so the caller can detect and recover the driver,
        # rather than swallowing it the same way as a data-parsing issue.
        raise

    try:
        next_data = _extract_next_data(driver)
        if not next_data:
            print(f"Could not extract __NEXT_DATA__ for {player_url}")
            return {}

        player_id = _extract_player_id(player_url)

        if progress_callback:
            progress_callback(60, "Parsing player data...")

        result = _parse_player_data(next_data, player_id, player_url)

        if progress_callback:
            progress_callback(100, "Finished!")

        return result

    except Exception as e:
        # Data-parsing errors (e.g. mainLeague is None for a near-zero-
        # minutes player) are genuinely benign -- the page loaded fine,
        # the driver is healthy, this specific player just has incomplete
        # data on FotMob's end. Swallow and return {} as before.
        print(f"Error parsing player data for {player_url}: {e}")
        import traceback
        traceback.print_exc()
        return {}


def _extract_next_data(driver):
    """
    Pulls the __NEXT_DATA__ JSON blob out of the page source.

    Args:
        driver: WebDriver instance

    Returns:
        dict or None: Parsed JSON, or None if not found/parseable
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


def _extract_player_id(player_url):
    """
    Extracts the numeric player ID from a FotMob player URL.

    Args:
        player_url (str): e.g. "https://www.fotmob.com/players/1233655/alex-scott"

    Returns:
        str or None
    """
    match = re.search(r"/players/(\d+)", player_url)
    return match.group(1) if match else None


def _parse_player_data(next_data, player_id, player_url):
    """
    Walks the confirmed __NEXT_DATA__ structure and builds a flat dict
    suitable for a CSV row.

    Args:
        next_data (dict): Parsed __NEXT_DATA__ JSON
        player_id (str): Numeric player ID (from URL, used as fallback)
        player_url (str): Original URL (kept for reference/debugging)

    Returns:
        dict: See scrape_player() docstring for shape
    """
    data = next_data.get("props", {}).get("pageProps", {}).get("data", {})

    result = {
        "player_id": data.get("id", player_id),
        "url": player_url,
        "name": data.get("name"),
        "team": None,
        "position": None,
        "position_short": None,
        "height_cm": None,
        "shirt": None,
        "age": None,
        "country": None,
        "preferred_foot": None,
        "market_value": None,
        "market_value_eur": None,
        "contract_end": None,
        "season_league": None,
        "season_year": None,
        "season_summary": {},
        "detailed_stats": {},
        "detailed_stats_per90": {},
        "raw": data,
    }

    # --- Current team ---
    primary_team = data.get("primaryTeam") or {}
    result["team"] = primary_team.get("teamName")

    # --- playerInformation: [{title, value: {...}}] ---
    # Confirmed shapes (via live debug dump):
    #   Height:         {"numberValue": 178, "fallback": "178 cm"}
    #   Shirt:          {"numberValue": 8, "fallback": 8}
    #   Age:            {"numberValue": 22, "fallback": "22"}
    #   Preferred foot: {"key": "right", "fallback": "Right"}
    #   Country:        {"key": None, "fallback": "England"}
    #   Market value:   {"numberValue": 38093408, "fallback": "€38.1m"}   <- title is "Market value", NOT "Transfer value"
    #   Contract end:   {"dateValue": "2028-06-30", "fallback": {utcTime, timezone}}
    for item in data.get("playerInformation", []):
        title = item.get("title")
        value = item.get("value", {})

        if isinstance(value, dict):
            # "fallback" is the display string for most fields, but for
            # Contract end it's itself a dict, so dateValue is preferred there.
            display_value = value.get("dateValue") or value.get("fallback") or value.get("numberValue")
        else:
            display_value = value

        if title == "Height":
            result["height_cm"] = display_value
        elif title == "Shirt":
            result["shirt"] = display_value
        elif title == "Age":
            result["age"] = display_value
        elif title == "Country":
            result["country"] = display_value
        elif title == "Preferred foot":
            result["preferred_foot"] = display_value
        elif title == "Market value":
            # Keep both the raw number (for sorting/analysis) and the
            # human-readable string (e.g. "€38.1m") for display/CSV.
            result["market_value"] = value.get("fallback") if isinstance(value, dict) else value
            result["market_value_eur"] = value.get("numberValue") if isinstance(value, dict) else None
        elif title == "Contract end":
            result["contract_end"] = display_value

    # --- positionDescription: specific primary position, e.g. "Striker" ---
    position_desc = data.get("positionDescription") or {}
    primary_position = position_desc.get("primaryPosition") or {}
    result["position"] = primary_position.get("label")
    result["position_short"] = None
    for pos in position_desc.get("positions", []):
        if pos.get("isMainPosition"):
            result["position_short"] = (pos.get("strPosShort") or {}).get("label")
            break

    # --- mainLeague: current-season summary stats ---
    main_league = data.get("mainLeague") or {}
    result["season_league"] = main_league.get("leagueName")
    result["season_year"] = main_league.get("season")
    for stat in main_league.get("stats", []):
        title = stat.get("title")
        if title:
            result["season_summary"][title] = stat.get("value")

    # --- firstSeasonStats: detailed Shooting/Passing/Possession/Defending breakdown ---
    first_season_stats = data.get("firstSeasonStats") or {}
    stats_section = first_season_stats.get("statsSection") or {}

    for group in stats_section.get("items", []):
        group_title = group.get("title")
        if not group_title:
            continue
        group_values = {}
        group_per90 = {}
        for stat_item in group.get("items", []):
            stat_title = stat_item.get("title")
            if not stat_title:
                continue
            group_values[stat_title] = stat_item.get("statValue")
            group_per90[stat_title] = stat_item.get("per90")
        result["detailed_stats"][group_title] = group_values
        result["detailed_stats_per90"][group_title] = group_per90

    # --- topStatCard: headline summary (Goals, Assists, Rating, Matches, Started, Minutes) ---
    top_stat_card = first_season_stats.get("topStatCard") or {}
    top_stats = {}
    for stat_item in top_stat_card.get("items", []):
        stat_title = stat_item.get("title")
        if stat_title:
            top_stats[stat_title] = stat_item.get("statValue")
    if top_stats:
        result["detailed_stats"]["Top stats"] = top_stats

    return result


def flatten_player_for_csv(player_dict):
    """
    Flattens the nested player dict from scrape_player() into a single-level
    dict suitable for a CSV row (e.g. via csv.DictWriter).

    Nested detailed_stats groups get prefixed column names, e.g.
    detailed_stats["Shooting"]["xG"] -> column "Shooting - xG".

    Args:
        player_dict (dict): Output of scrape_player()

    Returns:
        dict: Flat dict of {column_name: value}, with 'raw' dropped
    """
    flat = {
        "player_id": player_dict.get("player_id"),
        "name": player_dict.get("name"),
        "team": player_dict.get("team"),
        "url": player_dict.get("url"),
        "position": player_dict.get("position"),
        "position_short": player_dict.get("position_short"),
        "height_cm": player_dict.get("height_cm"),
        "shirt": player_dict.get("shirt"),
        "age": player_dict.get("age"),
        "country": player_dict.get("country"),
        "preferred_foot": player_dict.get("preferred_foot"),
        "market_value": player_dict.get("market_value"),
        "market_value_eur": player_dict.get("market_value_eur"),
        "contract_end": player_dict.get("contract_end"),
        "season_league": player_dict.get("season_league"),
        "season_year": player_dict.get("season_year"),
    }

    for stat_name, value in player_dict.get("season_summary", {}).items():
        flat[f"Summary - {stat_name}"] = value

    for group_title, stats in player_dict.get("detailed_stats", {}).items():
        for stat_name, value in stats.items():
            flat[f"{group_title} - {stat_name}"] = value

    for group_title, stats in player_dict.get("detailed_stats_per90", {}).items():
        for stat_name, value in stats.items():
            flat[f"{group_title} - {stat_name} (per90)"] = value

    return flat


def debug_dump_player_keys(driver, player_url):
    """
    Development utility: navigates to a player page and prints the
    statsSection groups found, plus the raw playerInformation list and
    positionDescription, to spot-check field names against new players.

    Args:
        driver: WebDriver instance
        player_url (str): FotMob player URL
    """
    driver.get(player_url)
    next_data = _extract_next_data(driver)
    if not next_data:
        print("Could not extract __NEXT_DATA__")
        return

    data = next_data.get("props", {}).get("pageProps", {}).get("data", {})

    print(f"Player: {data.get('name')}")

    print(f"\n--- Raw playerInformation ---")
    for item in data.get("playerInformation", []):
        print(f"  {item}")

    print(f"\n--- Raw positionDescription ---")
    print(f"  {data.get('positionDescription')}")

    stats_section = (data.get("firstSeasonStats") or {}).get("statsSection") or {}
    print(f"\nStat groups found: {[g.get('title') for g in stats_section.get('items', [])]}")
    for group in stats_section.get("items", []):
        print(f"\n--- {group.get('title')} ---")
        for stat_item in group.get("items", []):
            print(f"  {stat_item.get('title')}: {stat_item.get('statValue')} (per90: {stat_item.get('per90')})")