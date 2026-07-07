"""Orchestration for scraping every player in a league.

Ties together league_scraper (teams in the league), team_scraper (squad
per team), and player_scraper (stats per player), writing results
incrementally to CSV via csv_export so a crash or interruption doesn't
lose completed teams.

Key flags on every player row:
  - played_in_league: True if the player appeared in the target league
    this season (checked via statSeasons[].tournaments[].tournamentId).
    Handles reserve players (e.g. Brunet whose mainLeague is MLS Next Pro
    but who played some MLS matches) and inactive players (e.g. Joe Willis
    who has no 2026 MLS entry at all) with one unified check.
  - skip_no_league_matches: if True, players with played_in_league=False
    are excluded from the CSV entirely. Stats are always nulled for these
    players regardless of this flag.
"""

import os
import re
from . import league_scraper
from . import team_scraper
from . import player_scraper
from utils import csv_export
from utils import driver as driver_utils


def detect_url_type(url):
    url = url.strip()
    if "/leagues/" in url:
        normalized = re.sub(r"/leagues/(\d+)/[^/]+/(.+)", r"/leagues/\1/table/\2", url)
        if not normalized.startswith("http"):
            normalized = "https://www.fotmob.com" + normalized
        return "league", normalized
    elif "/teams/" in url:
        normalized = re.sub(r"/teams/(\d+)/[^/]+/(.+)", r"/teams/\1/squad/\2", url)
        if not normalized.startswith("http"):
            normalized = "https://www.fotmob.com" + normalized
        return "club", normalized
    return "unknown", url


def scrape_league_player_data(
    driver,
    league_table_url,
    output_dir,
    skip_no_league_matches=False,
    progress_callback=None,
):
    summary = {
        "league_name": None,
        "season": None,
        "teams_scraped": 0,
        "teams_skipped_resume": 0,
        "teams_failed": 0,
        "total_players": 0,
        "combined_csv_path": None,
        "teams_csv_path": None,
        "team_csv_paths": {},
    }

    if progress_callback:
        progress_callback(2, "Fetching league team list...")

    league_data = league_scraper.scrape_league_teams(driver, league_table_url)
    if not league_data or not league_data.get("teams"):
        print(f"Could not get team list from {league_table_url}")
        return summary

    summary["league_name"] = league_data.get("league_name")
    summary["season"] = league_data.get("season")

    teams = league_data["teams"]
    total_teams = len(teams)
    all_flat_rows = []

    expected_season = league_data.get("season")

    teams_csv_path = csv_export.write_teams_csv(output_dir, teams)
    summary["teams_csv_path"] = teams_csv_path

    for i, team in enumerate(teams):
        team_name = team["team_name"]
        squad_url = team["squad_url"]

        percent = int((i / total_teams) * 95) + 2
        if progress_callback:
            progress_callback(percent, f"Team {i+1}/{total_teams}: {team_name}")

        if csv_export.team_csv_exists(output_dir, team_name):
            print(f"Skipping {team_name} (already scraped, found existing CSV)")
            existing_rows = csv_export.read_team_csv_as_rows(output_dir, team_name)
            all_flat_rows.extend(existing_rows)
            summary["teams_skipped_resume"] += 1
            summary["team_csv_paths"][team_name] = csv_export.team_csv_path(output_dir, team_name)
            continue

        try:
            squad_data = team_scraper.scrape_squad(driver, squad_url)
        except Exception as e:
            print(f"Failed to scrape squad for {team_name}: {e}")
            driver = driver_utils.ensure_driver_alive(driver)
            summary["teams_failed"] += 1
            continue

        if not squad_data or not squad_data.get("players"):
            print(f"No players found for {team_name}, skipping")
            summary["teams_failed"] += 1
            continue

        team_flat_rows = []
        squad_players = squad_data["players"]

        for j, squad_player in enumerate(squad_players):
            if progress_callback:
                progress_callback(
                    percent,
                    f"Team {i+1}/{total_teams}: {team_name} - player {j+1}/{len(squad_players)}"
                )

            try:
                player_data = player_scraper.scrape_player(
                    driver,
                    squad_player["player_url"],
                    expected_season=expected_season,
                )
            except Exception as e:
                print(f"Failed to scrape player {squad_player.get('name')}: {e}")
                driver = driver_utils.ensure_driver_alive(driver)
                continue

            if not player_data or not player_data.get("name"):
                print(f"Empty result for {squad_player.get('name')}, skipping")
                continue

            # Unified league participation check:
            # played_in_league=True  -> player appeared in target league this season
            # played_in_league=False -> reserve/inactive player, stats nulled
            # played_in_league=None  -> could not determine (no league_id given)
            played_in_league = player_data.get("is_current_season")

            if played_in_league is False:
                player_data["season_summary"] = {}
                player_data["detailed_stats"] = {}
                player_data["detailed_stats_per90"] = {}
                player_data["season_league"] = None
                player_data["season_year"] = None

            if skip_no_league_matches and played_in_league is False:
                print(f"Skipping {player_data.get('name')} "
                      f"(no matches in target league this season)")
                continue

            player_data["position_group"] = squad_player.get("position_group")
            player_data["team_id"] = team["team_id"]
            player_data["league_name"] = league_data.get("league_name")
            player_data["league_group"] = team.get("group")
            player_data["played_in_league"] = played_in_league
            player_data["is_loan_or_reserve"] = (
                player_data.get("team") != team_name
            )

            flat_row = player_scraper.flatten_player_for_csv(player_data)
            flat_row["position_group"] = player_data["position_group"]
            flat_row["team_id"] = player_data["team_id"]
            flat_row["league_name"] = player_data["league_name"]
            flat_row["league_group"] = player_data["league_group"]
            flat_row["played_in_league"] = played_in_league
            flat_row["is_loan_or_reserve"] = player_data["is_loan_or_reserve"]

            team_flat_rows.append(flat_row)

        team_csv_path = csv_export.write_team_csv(output_dir, team_name, team_flat_rows)
        summary["team_csv_paths"][team_name] = team_csv_path
        summary["teams_scraped"] += 1
        summary["total_players"] += len(team_flat_rows)
        all_flat_rows.extend(team_flat_rows)

        print(f"Wrote {len(team_flat_rows)} players for {team_name} -> {team_csv_path}")

    if progress_callback:
        progress_callback(98, "Writing combined CSV...")

    league_slug = csv_export.safe_filename(summary["league_name"] or "league")
    season_slug = csv_export.safe_filename(str(summary["season"] or "season"))
    combined_filename = f"{league_slug}_{season_slug}_all_players.csv"

    combined_path = csv_export.write_combined_csv(output_dir, combined_filename, all_flat_rows)
    summary["combined_csv_path"] = combined_path
    summary["total_players"] = len(all_flat_rows)

    if progress_callback:
        progress_callback(100, f"Finished! {summary['total_players']} players across {total_teams} teams.")

    print(f"\nDone. {summary['teams_scraped']} teams scraped, "
          f"{summary['teams_skipped_resume']} skipped (resume), "
          f"{summary['teams_failed']} failed.")
    print(f"Combined CSV: {combined_path} ({summary['total_players']} players)")

    return summary


def scrape_club_player_data(
    driver,
    club_url,
    output_dir,
    skip_no_league_matches=False,
    progress_callback=None,
):
    """
    Scrapes full player data for every player on a single club's squad.

    Args:
        driver: WebDriver instance (already initialized)
        club_url (str): Any FotMob team URL (normalized to /squad/ automatically)
        output_dir (str): Directory to write the club CSV into
        skip_no_league_matches (bool): If True, players who have not played
            in the club's primary league this season are excluded.
        progress_callback (callable, optional): Progress callback function

    Returns:
        dict with team_name, total_players, combined_csv_path, etc.
    """
    _, squad_url = detect_url_type(club_url)

    if progress_callback:
        progress_callback(5, "Loading squad page...")

    try:
        squad_data = team_scraper.scrape_squad(driver, squad_url)
    except Exception as e:
        print(f"Failed to scrape squad for {club_url}: {e}")
        driver = driver_utils.ensure_driver_alive(driver)
        return {}

    if not squad_data or not squad_data.get("players"):
        print(f"No players found at {squad_url}")
        return {}

    team_name = squad_data.get("team_name", "unknown_team")
    team_id = squad_data.get("team_id")
    squad_players = squad_data["players"]
    total = len(squad_players)
    expected_season = squad_data.get("season")
    # Use the team's primary league ID for the participation check

    flat_rows = []

    for j, squad_player in enumerate(squad_players):
        percent = int((j / total) * 90) + 5
        if progress_callback:
            progress_callback(
                percent,
                f"{team_name}: player {j+1}/{total} - {squad_player.get('name')}"
            )

        try:
            player_data = player_scraper.scrape_player(
                driver,
                squad_player["player_url"],
                expected_season=expected_season,
            )
        except Exception as e:
            print(f"Failed to scrape player {squad_player.get('name')}: {e}")
            driver = driver_utils.ensure_driver_alive(driver)
            continue

        if not player_data or not player_data.get("name"):
            print(f"Empty result for {squad_player.get('name')}, skipping")
            continue

        played_in_league = player_data.get("is_current_season")

        if played_in_league is False:
            player_data["season_summary"] = {}
            player_data["detailed_stats"] = {}
            player_data["detailed_stats_per90"] = {}
            player_data["season_league"] = None
            player_data["season_year"] = None

        if skip_no_league_matches and played_in_league is False:
            print(f"Skipping {player_data.get('name')} "
                  f"(no matches in target league this season)")
            continue

        player_data["position_group"] = squad_player.get("position_group")
        player_data["team_id"] = team_id
        player_data["league_name"] = squad_data.get("league_name")
        player_data["league_group"] = None
        player_data["played_in_league"] = played_in_league
        player_data["is_loan_or_reserve"] = (
                player_data.get("team") != team_name
            )

        flat_row = player_scraper.flatten_player_for_csv(player_data)
        flat_row["position_group"] = player_data["position_group"]
        flat_row["team_id"] = player_data["team_id"]
        flat_row["league_name"] = player_data["league_name"]
        flat_row["league_group"] = player_data["league_group"]
        flat_row["played_in_league"] = played_in_league
        flat_row["is_loan_or_reserve"] = player_data["is_loan_or_reserve"]
        flat_rows.append(flat_row)

    if progress_callback:
        progress_callback(97, "Writing CSV...")

    team_csv = csv_export.write_team_csv(output_dir, team_name, flat_rows)
    combined_filename = f"{csv_export.safe_filename(team_name)}_players.csv"
    combined_path = csv_export.write_combined_csv(output_dir, combined_filename, flat_rows)

    if progress_callback:
        progress_callback(100, f"Done! {len(flat_rows)} players for {team_name}.")

    print(f"Wrote {len(flat_rows)} players for {team_name} -> {combined_path}")

    return {
        "team_name": team_name,
        "total_players": len(flat_rows),
        "combined_csv_path": combined_path,
        "team_csv_paths": {team_name: team_csv},
        "league_name": squad_data.get("league_name"),
        "season": squad_data.get("season"),
        "teams_scraped": 1,
        "teams_skipped_resume": 0,
        "teams_failed": 0,
    }