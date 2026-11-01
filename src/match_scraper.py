"""Match list scraping functionality for FotMob.

Reads the fixtures page's __NEXT_DATA__ JSON, which lists every match of a
competition season in one place:
    props.pageProps.fixtures.allMatches[] ->
        {id, pageUrl, round, roundName, group, home{name,id}, away{name,id},
         status{utcTime, finished, started, cancelled, scoreStr, reason{short}}}
    props.pageProps.allAvailableSeasons -> ["2025/2026", ...] or ["2026", ...]

`round` is "1", "2", ... for league rounds and group-stage matchdays, and
"1/8", "1/4", "1/2", "bronze", "final" for knockouts (roundName holds the
label, e.g. "Round of 16"). Competitions without rounds (e.g. friendlies)
have no round, so their matches are grouped by month instead.
"""

from datetime import datetime
from .next_data import fetch_page_props


def fetch_competition(driver, league_URL, season=None):
    """
    Loads every match of one competition season.

    Args:
        driver: WebDriver instance (fallback if requests is blocked)
        league_URL (str): FotMob fixtures URL, e.g.
            "https://www.fotmob.com/leagues/77/fixtures/world-cup"
        season (str, optional): "2025-2026", "2025/2026" or "2026".
            Empty/None means FotMob's current season.

    Returns:
        dict: {name, season, seasons, matches}; matches is a list of match
            dicts (see _parse_match). Empty values if the page can't be read.
    """
    url = league_URL.split("?")[0]
    season_param = _season_param(season)
    if season_param:
        url = f"{url}?season={season_param}"

    print(f"Loading fixtures: {url}")
    page_props = fetch_page_props(url, driver)
    details = page_props.get("details") or {}
    all_matches = (page_props.get("fixtures") or {}).get("allMatches") or []

    return {
        "name": details.get("name"),
        "season": details.get("selectedSeason"),
        "seasons": page_props.get("allAvailableSeasons") or [],
        "matches": [_parse_match(m) for m in all_matches],
    }


def list_rounds(matches):
    """
    Returns the competition's rounds/stages in order, as (round_key, label)
    pairs, e.g. [("1", "Round 1"), ..., ("1/8", "Round of 16"), ("final", "Final")].
    """
    rounds = {}
    for m in matches:
        rounds.setdefault(m["round"], m["round_name"])
    return list(rounds.items())


#NEW added league_URL to customize and change the league to scrape
def scrape_matches(driver, season, round_num, league_URL, progress_callback=None):
    """
    Scrapes match data for one round or stage of a competition season.

    Args:
        driver: WebDriver instance
        season (str): Season, e.g. "2025-2026" or "2026"
        round_num (str or int): Round key from list_rounds (e.g. "1", "1/8",
            "final"); plain round numbers also work
        league_URL (str): FotMob fixtures URL
        progress_callback (callable, optional): Progress callback function

    Returns:
        list: List of match dictionaries
    """
    matches = scrape_all_matches(driver, season, league_URL, progress_callback)
    return [m for m in matches if m["round"] == str(round_num)]


def scrape_all_matches(driver, season, league_URL, progress_callback=None):
    """
    Scrapes match data for every match of a competition season.

    Returns:
        list: List of match dictionaries
    """
    if progress_callback:
        progress_callback(10, "Loading fixtures...")

    matches = fetch_competition(driver, league_URL, season)["matches"]

    if progress_callback:
        progress_callback(100, f"Found {len(matches)} matches")

    return matches


def _season_param(season):
    """FotMob lists seasons as "2025/2026" but the URL takes "2025-2026"."""
    return (season or "").strip().replace("/", "-")


def _parse_match(m):
    """
    Converts one allMatches entry into a flat match dict.

    Returns:
        dict: match_id, date (YYYY-MM-DD, UTC), kickoff_utc (HH:MM), round,
            round_name, group, home, away, home_id, away_id, score, status,
            finished, url
    """
    status = m.get("status") or {}
    utc_time = status.get("utcTime") or ""
    kickoff = _parse_utc(utc_time)

    if m.get("round") is not None:
        round_key = str(m["round"])
        round_name = m.get("roundName")
        if isinstance(round_name, int) or str(round_name).isdigit():
            round_name = f"Round {round_name}"
    elif kickoff:
        # No rounds (e.g. friendlies): group by month
        round_key = kickoff.strftime("%Y-%m")
        round_name = kickoff.strftime("%B %Y")
    else:
        round_key = round_name = "Unknown"

    return {
        "match_id": str(m.get("id")),
        "date": kickoff.strftime("%Y-%m-%d") if kickoff else "N/A",
        "kickoff_utc": kickoff.strftime("%H:%M") if kickoff else "N/A",
        "round": round_key,
        "round_name": round_name,
        "group": m.get("group"),
        "home": (m.get("home") or {}).get("name"),
        "away": (m.get("away") or {}).get("name"),
        "home_id": (m.get("home") or {}).get("id"),
        "away_id": (m.get("away") or {}).get("id"),
        "score": status.get("scoreStr") or "",
        "status": _status_label(status),
        "finished": bool(status.get("finished")),
        "url": f"https://www.fotmob.com{m.get('pageUrl', '')}",
    }


def _status_label(status):
    """FT / AET / Pen for finished matches, else Live / Cancelled / Upcoming."""
    reason = (status.get("reason") or {}).get("short")
    if reason:
        return reason
    if status.get("cancelled"):
        return "Cancelled"
    if status.get("started"):
        return "Live"
    return "Upcoming"


def _parse_utc(utc_time):
    try:
        return datetime.strptime(utc_time[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
