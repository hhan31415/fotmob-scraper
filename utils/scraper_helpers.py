"""Helper functions for scraper logic."""

from utils.cleanup_player_csv import slugify

# Stat column prefix per period label from stats_scraper.PERIODS
# (full-match stats have no prefix)
PERIOD_PREFIXES = {
    "All": "",
    "1st half": "first_half",
    "2nd half": "second_half",
    "Extra time 1st half": "et_first_half",
    "Extra time 2nd half": "et_second_half",
}

# Stat names that are ambiguous without their section
STAT_RENAMES = {
    "own_half": "passes_own_half",
    "opposition_half": "passes_opposition_half",
}


def calculate_match_points(home_goals, away_goals):
    """
    Calculate points for home and away teams based on goals.

    Args:
        home_goals (int): Goals scored by home team
        away_goals (int): Goals scored by away team

    Returns:
        tuple: (home_points, away_points), or (None, None) if goals are unknown
    """
    if home_goals is None or away_goals is None:
        return None, None
    if home_goals > away_goals:
        return 3, 0
    elif away_goals > home_goals:
        return 0, 3
    else:
        return 1, 1


def parse_score(score_str):
    """
    Parse score string to extract goals.

    Args:
        score_str (str): Score string like "2 - 1"

    Returns:
        tuple: (home_goals, away_goals) or (None, None) if parsing fails
            (e.g. upcoming matches)
    """
    if score_str and ' - ' in score_str:
        try:
            parts = score_str.split(' - ')
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return int(parts[0]), int(parts[1])
        except:
            pass
    return None, None


def create_team_rows(match):
    """
    Create home and away team rows from a match dictionary.

    Args:
        match (dict): Match data dictionary from match_scraper

    Returns:
        tuple: (home_row, away_row) with snake_case keys
    """
    # Common match info
    base_info = {
        "match_id": match['match_id'],
        "date": match['date'],
        "kickoff_utc": match['kickoff_utc'],
        "round": match['round'],
        "round_name": match['round_name'],
    }
    if match.get('group'):
        base_info["group"] = match['group']
    base_info.update({
        "match": f"{match['home']} - {match['away']}",
        "score": match['score'],
        "status": match['status'],
        "url": match['url'],
    })

    # Parse score to calculate goals and points
    home_goals, away_goals = parse_score(match['score'])
    home_points, away_points = calculate_match_points(home_goals, away_goals)

    # Create home row
    home_row = base_info.copy()
    home_row["team"] = match['home']
    home_row["team_id"] = match['home_id']
    home_row["side"] = "home"
    home_row["opponent"] = match['away']
    home_row["opponent_id"] = match['away_id']
    home_row["goals_scored"] = home_goals
    home_row["goals_conceded"] = away_goals
    home_row["points"] = home_points

    # Create away row
    away_row = base_info.copy()
    away_row["team"] = match['away']
    away_row["team_id"] = match['away_id']
    away_row["side"] = "away"
    away_row["opponent"] = match['home']
    away_row["opponent_id"] = match['home_id']
    away_row["goals_scored"] = away_goals
    away_row["goals_conceded"] = home_goals
    away_row["points"] = away_points

    return home_row, away_row


def add_stats_to_rows(home_row, away_row, match_stats):
    """
    Adds FIFA ranks and per-period stats from stats_scraper to the team rows.

    Columns are "<period>_<stat>" in snake_case, with no prefix for full-match
    stats, e.g. "total_shots", "first_half_expected_goals_xg",
    "second_half_accurate_passes" (plus
    "..._total" for stats with an attempted count, e.g. 763 of 853 passes).
    Values are numeric. A stat listed in several sections (e.g. "Total shots"
    in Top stats and Shots) appears once. "xgot_non_penalty" is derived
    from the shotmap (see stats_scraper._xgot_non_penalty).

    Args:
        home_row, away_row (dict): Rows from create_team_rows, updated in place
        match_stats (dict): Result of stats_scraper.scrape_match_stats
    """
    home_rank, away_rank = (match_stats.get("fifa_rank") or [None, None])[:2]
    if home_rank is not None or away_rank is not None:
        home_row["fifa_rank"], home_row["opponent_fifa_rank"] = home_rank, away_rank
        away_row["fifa_rank"], away_row["opponent_fifa_rank"] = away_rank, home_rank

    for period, sections in (match_stats.get("periods") or {}).items():
        prefix = PERIOD_PREFIXES.get(period, slugify(period))
        seen = set()
        for stats in sections.values():
            for title, stat in stats.items():
                name = stat_column_name(title, stat.get("format"))
                if name in seen:
                    continue
                seen.add(name)
                col = f"{prefix}_{name}" if prefix else name
                home_row[col], away_row[col] = stat["value"][:2]
                if stat.get("total"):
                    home_row[f"{col}_total"], away_row[f"{col}_total"] = stat["total"][:2]

    # Non-penalty xGOT, from the shotmap (not a FotMob stat)
    for period, values in (match_stats.get("xgot_non_penalty") or {}).items():
        prefix = PERIOD_PREFIXES.get(period, slugify(period))
        col = f"{prefix}_xgot_non_penalty" if prefix else "xgot_non_penalty"
        home_row[col], away_row[col] = values[:2]


def stat_column_name(title, stat_format=None):
    """Snake_case column name for a FotMob stat title, e.g. "Distance covered" -> "distance_covered_m"."""
    name = slugify(title)
    name = STAT_RENAMES.get(name, name)
    if stat_format == "distance":
        name = f"{name}_m"
    return name
