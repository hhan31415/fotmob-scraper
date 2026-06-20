"""CSV export helpers for player data scraped via player_scraper + team_scraper.

Used by FotMobScraper.get_league_player_data() to write one CSV per team
plus a combined league-wide CSV, with resume support: a team is skipped
if its CSV already exists on disk.
"""

import csv
import os
import re


def safe_filename(name):
    """
    Converts a team/league name into a filesystem-safe filename fragment.

    Args:
        name (str): e.g. "Inter Miami CF"

    Returns:
        str: e.g. "inter_miami_cf"
    """
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower())
    return slug.strip("_")


def team_csv_path(output_dir, team_name):
    """
    Builds the expected output path for a single team's CSV.

    Args:
        output_dir (str): Directory where team CSVs are written
        team_name (str): e.g. "Inter Miami CF"

    Returns:
        str: Full path, e.g. "<output_dir>/inter_miami_cf.csv"
    """
    return os.path.join(output_dir, f"{safe_filename(team_name)}.csv")


def team_csv_exists(output_dir, team_name):
    """
    Checks whether a team's CSV has already been written, for resume support.

    Args:
        output_dir (str): Directory where team CSVs are written
        team_name (str): e.g. "Inter Miami CF"

    Returns:
        bool
    """
    return os.path.isfile(team_csv_path(output_dir, team_name))


def write_team_csv(output_dir, team_name, flat_player_rows):
    """
    Writes a single team's player rows to its own CSV file.

    Args:
        output_dir (str): Directory to write into (created if missing)
        team_name (str): e.g. "Inter Miami CF"
        flat_player_rows (list[dict]): Output of player_scraper.flatten_player_for_csv()
            for each player on the team

    Returns:
        str: Path to the written CSV
    """
    os.makedirs(output_dir, exist_ok=True)
    path = team_csv_path(output_dir, team_name)

    if not flat_player_rows:
        # Still create an empty file so resume logic doesn't re-scrape a
        # team that genuinely had no players (e.g. a scrape error we want
        # to retry rather than treat as "done")
        return path

    fieldnames = _union_fieldnames(flat_player_rows)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in flat_player_rows:
            writer.writerow(row)

    return path


def write_combined_csv(output_dir, combined_filename, all_flat_player_rows):
    """
    Writes every player across every team into a single combined CSV.

    Args:
        output_dir (str): Directory to write into
        combined_filename (str): e.g. "mls_2026_all_players.csv"
        all_flat_player_rows (list[dict]): Flattened rows for every player
            across all teams

    Returns:
        str: Path to the written CSV
    """
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, combined_filename)

    if not all_flat_player_rows:
        return path

    fieldnames = _union_fieldnames(all_flat_player_rows)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in all_flat_player_rows:
            writer.writerow(row)

    return path


def read_team_csv_as_rows(output_dir, team_name):
    """
    Reads a previously-written team CSV back into a list of dicts.
    Used when resuming: if a team was already scraped in a prior run,
    its rows are loaded from disk instead of re-scraping, so they can
    still be included in the final combined CSV.

    Args:
        output_dir (str): Directory where team CSVs are written
        team_name (str): e.g. "Inter Miami CF"

    Returns:
        list[dict]: Rows from the existing CSV, or [] if not found/empty
    """
    path = team_csv_path(output_dir, team_name)
    if not os.path.isfile(path):
        return []

    try:
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            return list(reader)
    except Exception as e:
        print(f"Could not read existing CSV for {team_name}: {e}")
        return []


def _union_fieldnames(rows):
    """
    Builds a stable, ordered list of all fieldnames across a list of dicts.
    Necessary because different players can have different stat groups
    (e.g. goalkeepers have 'Goalkeeping' stats, outfield players don't),
    so a plain rows[0].keys() would silently drop columns.

    Args:
        rows (list[dict])

    Returns:
        list[str]: Ordered, deduplicated fieldnames
    """
    seen = []
    seen_set = set()
    for row in rows:
        for key in row.keys():
            if key not in seen_set:
                seen_set.add(key)
                seen.append(key)
    return seen
