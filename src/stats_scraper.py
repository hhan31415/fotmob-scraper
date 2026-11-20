"""Match statistics scraping functionality for FotMob.

Reads the match page's __NEXT_DATA__ JSON (no tab clicking needed):
    props.pageProps.general.matchId
    props.pageProps.header.teams[] -> {name, id, score, fifaRank}
        fifaRank is the team's FIFA ranking at the time of the match
        (national teams only; None for clubs)
    props.pageProps.content.stats.Periods -> {All, FirstHalf, SecondHalf,
        FirstExtraHalf, SecondExtraHalf}
        each -> stats[] sections {title, key, stats[]}
        each stat -> {title, key, stats: [home_display, away_display],
                      rawStats: [{value, total?}, {value, total?}], format, type}
        type "title" rows are section headers, not stats.

Matches must be requested by ID (https://www.fotmob.com/match/<id>): the
slug URL without its "#<id>" fragment returns the pairing's latest match.
"""

import re
from .next_data import fetch_page_props

# FotMob period key -> label used in the app and in CSV column prefixes.
# "All" includes extra time, so extra-time halves are kept for matches that
# have them (they're missing from regular-time matches).
PERIODS = [
    ("All", "All"),
    ("FirstHalf", "1st half"),
    ("SecondHalf", "2nd half"),
    ("FirstExtraHalf", "Extra time 1st half"),
    ("SecondExtraHalf", "Extra time 2nd half"),
]


def scrape_match_stats(driver, match_url, progress_callback=None):
    """
    Scrapes detailed statistics for a specific match.

    Args:
        driver: WebDriver instance (fallback if requests is blocked)
        match_url (str): URL of the match page, e.g.
            "https://www.fotmob.com/matches/liverpool-vs-afc-bournemouth/2he69q#4813374"
        progress_callback (callable, optional): Progress callback function

    Returns:
        dict: {
            "match_id": str,
            "fifa_rank": [home, away] (None for clubs),
            "periods": {"All" | "1st half" | "2nd half" | "Extra time ..." (if played):
                {section: {stat: {"display": [h, a], "value": [h, a],
                                  "total": [h, a] or None, "format": str}}}},
            "xgot_non_penalty": {period label: [h, a]} (empty without a shotmap),
            "players": [per-player stats, see _parse_players]
        }
        or {} if the match can't be read or has no stats.
    """
    match_id = _match_id(match_url)
    url = f"https://www.fotmob.com/match/{match_id}" if match_id else match_url

    if progress_callback:
        progress_callback(20, "Loading match page...")

    page_props = fetch_page_props(url, driver)
    if not page_props:
        print(f"Could not read match page: {url}")
        return {}

    try:
        found_id = str((page_props.get("general") or {}).get("matchId"))
        if match_id and found_id != match_id:
            print(f"Warning: asked for match {match_id}, page returned {found_id}")

        if progress_callback:
            progress_callback(60, "Parsing stats data...")

        teams = (page_props.get("header") or {}).get("teams") or [{}, {}]
        periods_raw = ((page_props.get("content") or {}).get("stats") or {}).get("Periods") or {}

        periods = {}
        for key, label in PERIODS:
            sections = _parse_period(periods_raw.get(key))
            if sections:
                periods[label] = sections

        if progress_callback:
            progress_callback(100, "Finished!")

        print(f"Extracted {len(periods)} periods for match {found_id}")
        for label, sections in periods.items():
            print(f"  {label}: {sum(len(s) for s in sections.values())} stats in {len(sections)} sections")

        shots = ((page_props.get("content") or {}).get("shotmap") or {}).get("shots") or []

        return {
            "match_id": found_id,
            "fifa_rank": [t.get("fifaRank") for t in teams[:2]],
            "periods": periods,
            "xgot_non_penalty": _xgot_non_penalty(shots, teams[0].get("id"), periods),
            "players": _parse_players(page_props, teams[0].get("id")),
        }

    except Exception as e:
        print(f"Error parsing match stats: {e}")
        import traceback
        traceback.print_exc()
        return {}


def _match_id(match_url):
    """Pulls the match ID from "...#4813374" or ".../match/4813374"."""
    found = re.search(r"#(\d+)", match_url) or re.search(r"/match/(\d+)", match_url)
    return found.group(1) if found else None


def _parse_period(period):
    """
    Parses one period's sections.

    Returns:
        dict: {section_title: {stat_title: {"display", "value", "total", "format"}}}
    """
    sections = {}
    for section in (period or {}).get("stats") or []:
        stats = {}
        for stat in section.get("stats") or []:
            if stat.get("type") == "title":
                continue
            display = list(stat.get("stats") or [None, None])
            raw = stat.get("rawStats") or [{}, {}]
            values = [_raw_value(r, "value", d) for r, d in zip(raw, display)]
            totals = [_raw_value(r, "total") for r in raw]
            stats[stat.get("title")] = {
                "display": display,
                "value": values,
                "total": totals if any(t is not None for t in totals) else None,
                "format": stat.get("format"),
            }
        if stats:
            sections[section.get("title")] = stats
    return sections


def _xgot_non_penalty(shots, home_team_id, periods):
    """
    Non-penalty xGOT per period: total xGOT minus the xGOT of penalty shots.

    Uses content.shotmap.shots[] -> {teamId, period, situation, expectedGoalsOnTarget}.
    Shot periods are FirstHalf / SecondHalf / FirstHalfExtra / SecondHalfExtra /
    PenaltyShootout; shootout kicks are excluded (they're not in the xGOT stat).
    Shots off target have no xGOT and count as 0. With the shootout excluded,
    the shotmap's xGOT sums match the "xG on target (xGOT)" stat.

    Returns:
        dict: {period label: [home, away]} for the periods in `periods`,
            or {} if the match has no shotmap.
    """
    if not shots:
        return {}

    shot_periods = {
        "FirstHalf": "1st half",
        "SecondHalf": "2nd half",
        "FirstHalfExtra": "Extra time 1st half",
        "SecondHalfExtra": "Extra time 2nd half",
    }
    totals = {label: [0.0, 0.0] for label in periods}
    for shot in shots:
        label = shot_periods.get(shot.get("period"))
        if label is None:
            continue  # penalty shootout
        side = 0 if shot.get("teamId") == home_team_id else 1
        xgot = shot.get("expectedGoalsOnTarget") or 0
        if shot.get("situation") == "Penalty":
            xgot = 0
        for period in ("All", label):
            if period in totals:
                totals[period][side] += xgot

    return {label: [round(h, 2), round(a, 2)] for label, (h, a) in totals.items()}


# lineup usualPlayingPositionId -> label
USUAL_POSITIONS = {0: "GK", 1: "DF", 2: "MF", 3: "FW"}


def _parse_players(page_props, home_team_id):
    """
    Parses per-player match stats (the stats in FotMob's player popup).

    Uses content.playerStats {player_id: {name, id, teamId, isGoalkeeper,
    shirtNumber, stats[] sections {title, stats: {title: {key, stat: {value,
    total?, type}}}}, shotmap[]}} and content.lineup.{homeTeam,awayTeam}.
    {starters, subs}[] for starter/sub, age, country and market value.
    Player stats are full-match only (FotMob has no per-half player stats).
    Players who didn't play (unused subs, 0 minutes) are skipped.

    Returns:
        list[dict]: {player_id, player, team_id, side, shirt_number,
            is_goalkeeper, started, usual_position, age, country,
            market_value, stats: {title: {"value", "total"}}, xgot_non_penalty}
    """
    content = page_props.get("content") or {}
    player_stats = content.get("playerStats") or {}
    lineup = content.get("lineup") or {}

    lineup_info = {}
    for team_key in ("homeTeam", "awayTeam"):
        for group in ("starters", "subs"):
            for p in (lineup.get(team_key) or {}).get(group) or []:
                lineup_info[p.get("id")] = (group == "starters", p)

    players = []
    for p in player_stats.values():
        stats = {}
        for section in p.get("stats") or []:
            for title, entry in (section.get("stats") or {}).items():
                stat = (entry or {}).get("stat") or {}
                if stat.get("type") == "boolean" or title in stats:
                    continue  # "Shotmap" flag; stats repeated across sections
                stats[title] = {"value": stat.get("value"), "total": stat.get("total")}

        minutes = (stats.get("Minutes played") or {}).get("value")
        if not minutes:
            continue

        started, info = lineup_info.get(p.get("id"), (None, {}))
        shots = [s for s in p.get("shotmap") or [] if s.get("period") != "PenaltyShootout"]
        players.append({
            "player_id": p.get("id"),
            "player": p.get("name"),
            "team_id": p.get("teamId"),
            "side": "home" if p.get("teamId") == home_team_id else "away",
            "shirt_number": p.get("shirtNumber"),
            "is_goalkeeper": bool(p.get("isGoalkeeper")),
            "started": started,
            "usual_position": USUAL_POSITIONS.get(info.get("usualPlayingPositionId")),
            "age": info.get("age"),
            "country": info.get("countryName"),
            "market_value": info.get("marketValue"),
            "stats": stats,
            # Same rule as the team value: penalties and shootout kicks excluded
            "xgot_non_penalty": round(sum(s.get("expectedGoalsOnTarget") or 0 for s in shots
                                          if s.get("situation") != "Penalty"), 2),
        })
    return players


def _raw_value(raw, field, fallback=None):
    """Numeric rawStats field, falling back to the display value."""
    if isinstance(raw, dict) and raw.get(field) is not None:
        return raw[field]
    return fallback
