"""
Test script for league_player_data.scrape_league_player_data().

Runs the REAL orchestration function end-to-end, but limited to a small
slice of teams (default: first 2) so it finishes in a few minutes instead
of over an hour. Also tests resume behavior by deleting one team's CSV
and re-running, confirming it gets re-scraped while the other is skipped.

Usage:
    python test_league_player_data.py

Place this next to league_player_data.py, csv_export.py, league_scraper.py,
team_scraper.py, and player_scraper.py.
"""

import os
import shutil
import csv as csv_module
from utils import driver as driver_utils
import league_scraper
import team_scraper
import player_scraper
import csv_export
import league_player_data

LEAGUE_TABLE_URL = "https://www.fotmob.com/leagues/130/table/mls"
TEST_OUTPUT_DIR = "test_output_league_players"
TEAM_LIMIT = 2  # keep small for a fast test; bump up once this passes


def limited_scrape(driver, league_table_url, output_dir, team_limit, progress_callback=None):
    """
    Thin wrapper around the real orchestration logic, limited to the first
    N teams. Duplicates a small amount of league_player_data's setup so we
    can slice the team list before the main loop runs, without modifying
    the production function just to test it.
    """
    league_data = league_scraper.scrape_league_teams(driver, league_table_url)
    if not league_data or not league_data.get("teams"):
        print("FAILED: could not get team list")
        return None

    print(f"League has {len(league_data['teams'])} teams total; limiting test to first {team_limit}")
    league_data["teams"] = league_data["teams"][:team_limit]

    # Reuse the real per-team loop by calling the actual module's internals
    # via a monkeypatched league_scraper.scrape_league_teams that returns
    # our truncated list -- simplest way to test the REAL function without
    # forking its logic.
    original_scrape_league_teams = league_scraper.scrape_league_teams
    league_scraper.scrape_league_teams = lambda drv, url: league_data

    try:
        summary = league_player_data.scrape_league_player_data(
            driver, league_table_url, output_dir, progress_callback
        )
    finally:
        league_scraper.scrape_league_teams = original_scrape_league_teams

    return summary


def inspect_csv(path, label):
    print(f"\n--- {label}: {path} ---")
    if not os.path.isfile(path):
        print("  FILE DOES NOT EXIST")
        return None

    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv_module.DictReader(f)
        rows = list(reader)

    print(f"  {len(rows)} rows, {len(reader.fieldnames or [])} columns")
    if rows:
        first = rows[0]
        print(f"  First row sample: name={first.get('name')!r}, team={first.get('team')!r}, "
              f"position={first.get('position')!r}, market_value={first.get('market_value')!r}, "
              f"team_id={first.get('team_id')!r}, league_group={first.get('league_group')!r}")
    return rows


def test_initial_run(drv):
    print(f"\n{'#'*70}\n# TEST 1: Initial run, limited to {TEAM_LIMIT} teams\n{'#'*70}")

    if os.path.isdir(TEST_OUTPUT_DIR):
        print(f"Clearing previous test output dir: {TEST_OUTPUT_DIR}")
        shutil.rmtree(TEST_OUTPUT_DIR)

    summary = limited_scrape(drv, LEAGUE_TABLE_URL, TEST_OUTPUT_DIR, TEAM_LIMIT)

    if not summary:
        print("FAILED: scrape returned nothing")
        return None

    print(f"\nSummary: {summary}")

    print(f"\n{'='*70}\nSANITY CHECKS\n{'='*70}")
    checks = [
        ("league_name == 'MLS'", summary.get("league_name") == "MLS"),
        ("teams_scraped == TEAM_LIMIT", summary.get("teams_scraped") == TEAM_LIMIT),
        ("teams_skipped_resume == 0 (fresh run)", summary.get("teams_skipped_resume") == 0),
        ("teams_failed == 0", summary.get("teams_failed") == 0),
        ("total_players > 0", summary.get("total_players", 0) > 0),
        ("combined_csv_path set", bool(summary.get("combined_csv_path"))),
        (f"team_csv_paths has {TEAM_LIMIT} entries", len(summary.get("team_csv_paths", {})) == TEAM_LIMIT),
    ]
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")

    # Inspect actual CSV contents
    for team_name, path in summary.get("team_csv_paths", {}).items():
        inspect_csv(path, f"Team CSV: {team_name}")

    combined_rows = inspect_csv(summary["combined_csv_path"], "Combined CSV")

    if combined_rows:
        team_ids_in_combined = set(r.get("team_id") for r in combined_rows)
        print(f"\n  Unique team_ids in combined CSV: {team_ids_in_combined}")
        print(f"  [{'PASS' if len(team_ids_in_combined) == TEAM_LIMIT else 'FAIL'}] combined CSV has rows from all {TEAM_LIMIT} teams")

    return summary


def test_resume_behavior(drv, first_summary):
    print(f"\n\n{'#'*70}\n# TEST 2: Resume behavior (delete one team's CSV, re-run)\n{'#'*70}")

    if not first_summary or not first_summary.get("team_csv_paths"):
        print("Skipped: no first run summary available")
        return

    team_names = list(first_summary["team_csv_paths"].keys())
    team_to_delete = team_names[0]
    team_to_keep = team_names[1] if len(team_names) > 1 else None

    deleted_path = first_summary["team_csv_paths"][team_to_delete]
    print(f"Deleting CSV for '{team_to_delete}' to simulate an interrupted run: {deleted_path}")
    os.remove(deleted_path)

    print(f"Re-running scrape on the same {TEAM_LIMIT} teams...")
    second_summary = limited_scrape(drv, LEAGUE_TABLE_URL, TEST_OUTPUT_DIR, TEAM_LIMIT)

    if not second_summary:
        print("FAILED: second scrape returned nothing")
        return

    print(f"\nSecond run summary: {second_summary}")

    print(f"\n{'='*70}\nSANITY CHECKS\n{'='*70}")
    checks = [
        (f"'{team_to_delete}' was re-scraped (teams_scraped == 1)", second_summary.get("teams_scraped") == 1),
        (f"{TEAM_LIMIT - 1} team(s) skipped via resume", second_summary.get("teams_skipped_resume") == TEAM_LIMIT - 1),
        ("CSV for deleted team exists again", os.path.isfile(deleted_path)),
    ]
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")


def main():
    drv = driver_utils.setup_driver()
    try:
        first_summary = test_initial_run(drv)
        test_resume_behavior(drv, first_summary)
    finally:
        driver_utils.close_driver(drv)

    print(f"\n\nTest output left in ./{TEST_OUTPUT_DIR} for manual inspection. Delete it when done.")


if __name__ == "__main__":
    main()
