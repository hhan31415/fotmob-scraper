"""Orchestration for scraping every player in a league: ties together
league_scraper (teams in the league), team_scraper (squad per team), and
player_scraper (stats per player), writing results incrementally to CSV
via csv_export so a crash or interruption doesn't lose completed teams.

This is intentionally a separate module from match_scraper/stats_scraper,
since it answers a different question ("who plays where, how good are they")
rather than "what happened in matches". The two pipelines don't share state
and can be run independently.
"""

import os
from . import league_scraper
from . import team_scraper
from . import player_scraper
from utils import csv_export
from utils import driver as driver_utils


def scrape_league_player_data(driver, league_table_url, output_dir, progress_callback=None):
    """
    Scrapes full player data (profile + season stats) for every player on
    every team in a league, given the league's table page URL.

    Resume behavior: before scraping a team's squad, checks whether
    <output_dir>/<team_slug>.csv already exists. If so, that team is
    skipped entirely (its rows are still loaded from disk and included in
    the final combined CSV). To force a full re-scrape, delete output_dir
    or the specific team CSVs you want redone.

    Driver health: a long scrape (hundreds of page loads) will occasionally
    hit a hung or crashed Chrome renderer. After any failed player scrape,
    this calls driver_utils.ensure_driver_alive() to detect and transparently
    recreate a broken driver before moving on, rather than letting every
    subsequent player burn the full page-load timeout against a dead driver.

    Args:
        driver: WebDriver instance (already initialized)
        league_table_url (str): FotMob league table URL, e.g.
            "https://www.fotmob.com/leagues/130/table/mls"
        output_dir (str): Directory to write per-team and combined CSVs into
        progress_callback (callable, optional): Progress callback function

    Returns:
        dict: {
            "league_name": str,
            "season": str,
            "teams_scraped": int,
            "teams_skipped_resume": int,
            "teams_failed": int,
            "total_players": int,
            "combined_csv_path": str,
            "team_csv_paths": {team_name: path, ...},
        }
    """
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

    # Write a small teams.csv reference table: team_id -> team_name, group,
    # table position, etc. This is the authoritative team_id/name mapping,
    # sourced directly from the league table page. It exists because the
    # player rows' own 'team' column reflects each player's FotMob
    # "primary club" (from their individual profile page), which can
    # legitimately differ from the squad they were actually scraped under
    # for dual-registered or reserve-squad players (e.g. a player rostered
    # on a first team's squad page whose profile lists a reserve/academy
    # side as primary club). team_id is always correct and consistent;
    # 'team' in the player CSVs is not reliable for grouping/joins -- use
    # this file instead.
    teams_csv_path = csv_export.write_teams_csv(output_dir, teams)
    summary["teams_csv_path"] = teams_csv_path

    for i, team in enumerate(teams):
        team_name = team["team_name"]
        squad_url = team["squad_url"]

        percent = int((i / total_teams) * 95) + 2  # reserve last 3% for combined CSV write
        if progress_callback:
            progress_callback(percent, f"Team {i+1}/{total_teams}: {team_name}")

        # --- Resume support: skip teams already scraped in a prior run ---
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
                sub_percent = percent  # keep team-level granularity; per-player would be too noisy
                progress_callback(sub_percent, f"Team {i+1}/{total_teams}: {team_name} - player {j+1}/{len(squad_players)}")

            try:
                player_data = player_scraper.scrape_player(driver, squad_player["player_url"])
            except Exception as e:
                print(f"Failed to scrape player {squad_player.get('name')}: {e}")
                # A failed scrape can mean the page itself was bad (fine,
                # just skip it) or that the driver/Chrome renderer has
                # hung/crashed (not fine -- every subsequent player would
                # also fail). Cheaply verify driver health here and
                # transparently recreate it if needed before continuing.
                driver = driver_utils.ensure_driver_alive(driver)
                continue

            if not player_data or not player_data.get("name"):
                print(f"Empty result for player {squad_player.get('name')}, skipping")
                continue

            # Enrich with squad-level context not present on the player page itself
            player_data["position_group"] = squad_player.get("position_group")
            player_data["team_id"] = team["team_id"]
            player_data["league_name"] = league_data.get("league_name")
            player_data["league_group"] = team.get("group")

            flat_row = player_scraper.flatten_player_for_csv(player_data)
            flat_row["position_group"] = player_data["position_group"]
            flat_row["team_id"] = player_data["team_id"]
            flat_row["league_name"] = player_data["league_name"]
            flat_row["league_group"] = player_data["league_group"]

            team_flat_rows.append(flat_row)

        # --- Write this team's CSV immediately, so progress survives a crash ---
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

    print(f"\nDone. {summary['teams_scraped']} teams scraped, {summary['teams_skipped_resume']} skipped (resume), {summary['teams_failed']} failed.")
    print(f"Combined CSV: {combined_path} ({summary['total_players']} players)")

    return summary