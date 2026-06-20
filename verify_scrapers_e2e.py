"""
End-to-end verification for player_scraper.py and team_scraper.py.

Unlike verify_fotmob_json.py (which dumped raw JSON structure), this
script calls the actual production functions and prints their real
output, so we can confirm the parsing logic works correctly before
wiring these into FotMobScraper.

Usage:
    python verify_scrapers_e2e.py

Place this in the same directory as player_scraper.py and team_scraper.py.
"""

import json
from utils import driver as driver_utils
import player_scraper
import team_scraper
import league_scraper

PLAYER_URL = "https://www.fotmob.com/players/1233655/alex-scott"
MESSI_URL = "https://www.fotmob.com/players/30981/lionel-messi"
GOALKEEPER_URL = None  # fill in if you want to test a keeper (different stat groups expected)
SQUAD_URL = "https://www.fotmob.com/teams/960720/squad/inter-miami-cf"
LEAGUE_TABLE_URL = "https://www.fotmob.com/leagues/130/table/mls"


def test_player_scraper(drv):
    print(f"\n{'#'*70}\n# TESTING player_scraper.scrape_player()\n{'#'*70}")

    print(f"\n{'='*70}\nRAW playerInformation + positionDescription (for field-name debugging)\n{'='*70}")
    player_scraper.debug_dump_player_keys(drv, PLAYER_URL)

    result = player_scraper.scrape_player(drv, PLAYER_URL)

    if not result:
        print("FAILED: scrape_player returned empty dict")
        return

    print(f"\nname: {result.get('name')}")
    print(f"team: {result.get('team')}")
    print(f"height_cm: {result.get('height_cm')}")
    print(f"shirt: {result.get('shirt')}")
    print(f"age: {result.get('age')}")
    print(f"country: {result.get('country')}")
    print(f"preferred_foot: {result.get('preferred_foot')}")
    print(f"market_value: {result.get('market_value')}")
    print(f"contract_end: {result.get('contract_end')}")
    print(f"season_league: {result.get('season_league')}")
    print(f"season_year: {result.get('season_year')}")

    print(f"\nseason_summary ({len(result.get('season_summary', {}))} stats):")
    for k, v in result.get("season_summary", {}).items():
        print(f"  {k}: {v}")

    print(f"\ndetailed_stats groups: {list(result.get('detailed_stats', {}).keys())}")
    for group, stats in result.get("detailed_stats", {}).items():
        print(f"\n  --- {group} ---")
        for k, v in stats.items():
            print(f"    {k}: {v}")

    print(f"\n{'='*70}\nflatten_player_for_csv() output:\n{'='*70}")
    flat = player_scraper.flatten_player_for_csv(result)
    for k, v in flat.items():
        print(f"  {k!r}: {v!r}")

    # Sanity checks
    print(f"\n{'='*70}\nSANITY CHECKS\n{'='*70}")
    checks = [
        ("name is non-empty", bool(result.get("name"))),
        ("team is non-empty", bool(result.get("team"))),
        ("season_summary has Goals", "Goals" in result.get("season_summary", {})),
        ("detailed_stats has Shooting", "Shooting" in result.get("detailed_stats", {})),
        ("Shooting has xG", "xG" in result.get("detailed_stats", {}).get("Shooting", {})),
        ("Passing has xA", "xA" in result.get("detailed_stats", {}).get("Passing", {})),
        ("market_value == '€38.1m'", result.get("market_value") == "€38.1m"),
        ("market_value_eur == 38093408", result.get("market_value_eur") == 38093408),
        ("position == 'Defensive Midfielder'", result.get("position") == "Defensive Midfielder"),
        ("position_short == 'DM'", result.get("position_short") == "DM"),
        ("contract_end == '2028-06-30'", result.get("contract_end") == "2028-06-30"),
    ]
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")


def test_squad_scraper(drv):
    print(f"\n\n{'#'*70}\n# TESTING team_scraper.scrape_squad()\n{'#'*70}")
    result = team_scraper.scrape_squad(drv, SQUAD_URL)

    if not result:
        print("FAILED: scrape_squad returned empty dict")
        return

    print(f"\nteam_name: {result.get('team_name')}")
    print(f"country: {result.get('country')}")
    print(f"league_name: {result.get('league_name')}")
    print(f"season: {result.get('season')}")
    print(f"total players: {len(result.get('players', []))}")

    print(f"\nFirst 5 players (full detail):")
    for p in result.get("players", [])[:5]:
        print(f"  {json.dumps(p, indent=2)}")

    print(f"\nAll players grouped by position_group:")
    by_group = {}
    for p in result.get("players", []):
        by_group.setdefault(p["position_group"], []).append(p["name"])
    for group, names in by_group.items():
        print(f"  {group} ({len(names)}): {', '.join(names)}")

    # NOTE: team_scraper no longer includes a 'position' field (it was just
    # a duplicate of position_group). Specific positions come from
    # player_scraper.scrape_player() instead, via positionDescription.

    # Sanity checks
    print(f"\n{'='*70}\nSANITY CHECKS\n{'='*70}")
    checks = [
        ("team_name is non-empty", bool(result.get("team_name"))),
        ("players list non-empty", len(result.get("players", [])) > 0),
        ("no 'coach' in position_groups", "coach" not in {p["position_group"] for p in result.get("players", [])}),
        ("all players have player_url", all(p.get("player_url") for p in result.get("players", []))),
        ("at least one keeper found", any(p["position_group"] == "keepers" for p in result.get("players", []))),
    ]
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")

    return result


def test_squad_to_player_pipeline(drv, squad_result):
    """
    Takes the first player found in the squad scrape and runs them
    through scrape_player(), to confirm the player_url built by
    team_scraper actually works as input to player_scraper.
    """
    print(f"\n\n{'#'*70}\n# TESTING squad_url -> scrape_player() pipeline\n{'#'*70}")
    if not squad_result or not squad_result.get("players"):
        print("Skipped: no squad result available")
        return

    test_player = squad_result["players"][0]
    print(f"Using player from squad: {test_player['name']} -> {test_player['player_url']}")

    result = player_scraper.scrape_player(drv, test_player["player_url"])
    if not result or not result.get("name"):
        print("FAILED: could not scrape player using URL built by team_scraper")
        return

    print(f"SUCCESS: scraped {result.get('name')} via squad-built URL")
    print(f"  team: {result.get('team')}")
    print(f"  season_summary keys: {list(result.get('season_summary', {}).keys())}")


def test_league_scraper(drv):
    print(f"\n\n{'#'*70}\n# TESTING league_scraper.scrape_league_teams()\n{'#'*70}")
    result = league_scraper.scrape_league_teams(drv, LEAGUE_TABLE_URL)

    if not result:
        print("FAILED: scrape_league_teams returned empty dict")
        return None

    print(f"\nleague_name: {result.get('league_name')}")
    print(f"country: {result.get('country')}")
    print(f"season: {result.get('season')}")
    print(f"groups: {result.get('groups')}")
    print(f"total unique teams: {len(result.get('teams', []))}")

    print(f"\nFirst 5 teams (full detail):")
    for t in result.get("teams", [])[:5]:
        print(f"  {json.dumps(t, indent=2)}")

    print(f"\nAll teams grouped:")
    by_group = {}
    for t in result.get("teams", []):
        by_group.setdefault(t["group"], []).append(t["team_name"])
    for group, names in by_group.items():
        print(f"  {group} ({len(names)}): {', '.join(names)}")

    team_ids = [t["team_id"] for t in result.get("teams", [])]
    duplicate_ids = len(team_ids) != len(set(team_ids))

    print(f"\n{'='*70}\nSANITY CHECKS\n{'='*70}")
    checks = [
        ("league_name == 'MLS'", result.get("league_name") == "MLS"),
        ("no duplicate team_ids", not duplicate_ids),
        ("Eastern in groups", "Eastern" in result.get("groups", [])),
        ("Western in groups", "Western" in result.get("groups", [])),
        ("teams list non-empty", len(result.get("teams", [])) > 0),
        ("reasonable team count (25-35)", 25 <= len(result.get("teams", [])) <= 35),
        ("all teams have squad_url", all(t.get("squad_url") for t in result.get("teams", []))),
        ("squad_url contains '/squad/'", all("/squad/" in (t.get("squad_url") or "") for t in result.get("teams", []))),
        ("Inter Miami CF present", any(t["team_name"] == "Inter Miami CF" for t in result.get("teams", []))),
    ]
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")

    return result


def test_full_pipeline(drv, league_result):
    """
    Full chain test: league -> first team's squad -> first player.
    Proves all three modules compose correctly end-to-end.
    """
    print(f"\n\n{'#'*70}\n# TESTING FULL PIPELINE: league -> squad -> player\n{'#'*70}")
    if not league_result or not league_result.get("teams"):
        print("Skipped: no league result available")
        return

    test_team = league_result["teams"][0]
    print(f"Using team from league: {test_team['team_name']} -> {test_team['squad_url']}")

    squad_result = team_scraper.scrape_squad(drv, test_team["squad_url"])
    if not squad_result or not squad_result.get("players"):
        print("FAILED: could not scrape squad using URL built by league_scraper")
        return

    print(f"SUCCESS: scraped squad for {squad_result.get('team_name')} ({len(squad_result['players'])} players)")

    test_player = squad_result["players"][0]
    print(f"Using player from squad: {test_player['name']} -> {test_player['player_url']}")

    player_result = player_scraper.scrape_player(drv, test_player["player_url"])
    if not player_result or not player_result.get("name"):
        print("FAILED: could not scrape player using URL built by team_scraper")
        return

    print(f"SUCCESS: scraped {player_result.get('name')} via full league->squad->player chain")
    print(f"  team: {player_result.get('team')}")
    print(f"  position: {player_result.get('position')}")
    print(f"  market_value: {player_result.get('market_value')}")

    print(f"\n{'='*70}\nFULL PIPELINE SANITY CHECK\n{'='*70}")
    print(f"  [{'PASS' if player_result.get('name') == test_player['name'] else 'FAIL'}] scraped player name matches squad entry name")


def test_messi_market_value(drv):
    print(f"\n\n{'#'*70}\n# CHECKING market_value field on a player who should have one (Messi)\n{'#'*70}")
    player_scraper.debug_dump_player_keys(drv, MESSI_URL)
    result = player_scraper.scrape_player(drv, MESSI_URL)
    print(f"\nParsed market_value: {result.get('market_value')!r}")
    print(f"Parsed market_value_eur: {result.get('market_value_eur')!r}")
    print(f"Parsed contract_end: {result.get('contract_end')!r}")
    print(f"Parsed position: {result.get('position')!r}")
    print(f"Parsed position_short: {result.get('position_short')!r}")

    checks = [
        ("market_value == '€14.2m'", result.get("market_value") == "€14.2m"),
        ("market_value_eur == 14203769", result.get("market_value_eur") == 14203769),
        ("position == 'Striker'", result.get("position") == "Striker"),
        ("position_short == 'ST'", result.get("position_short") == "ST"),
        ("contract_end == '2028-12-31'", result.get("contract_end") == "2028-12-31"),
    ]
    print(f"\n{'='*70}\nSANITY CHECKS\n{'='*70}")
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")


def main():
    drv = driver_utils.setup_driver()
    try:
        test_player_scraper(drv)
        test_messi_market_value(drv)
        squad_result = test_squad_scraper(drv)
        test_squad_to_player_pipeline(drv, squad_result)
        league_result = test_league_scraper(drv)
        test_full_pipeline(drv, league_result)
    finally:
        driver_utils.close_driver(drv)


if __name__ == "__main__":
    main()
