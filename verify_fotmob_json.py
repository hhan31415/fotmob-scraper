"""
Standalone verification script — run this BEFORE wiring player/team
scraping into FotMobScraper.

It does three things:
  1. Confirms __NEXT_DATA__ can be extracted from a player page.
  2. Dumps the player JSON's top-level keys + previews, so we can find
     exactly where the detailed per-90 stats (xG, xGOT, duels won %, etc.)
     live in the schema.
  3. Confirms __NEXT_DATA__ can be extracted from a squad page and dumps
     its shape too.

Usage:
    python verify_fotmob_json.py

Requires your existing `utils.driver` module (same driver setup the
rest of the project uses).
"""

import json
import re
import sys
from selenium.webdriver.common.by import By

from utils import driver as driver_utils

PLAYER_URL = "https://www.fotmob.com/players/1233655/alex-scott"
SQUAD_URL = "https://www.fotmob.com/teams/960720/squad/inter-miami-cf"


def extract_next_data(driver):
    """Same extraction logic as player_scraper._extract_next_data."""
    try:
        script_el = driver.find_element(By.ID, "__NEXT_DATA__")
        raw_json = script_el.get_attribute("innerHTML") or script_el.get_attribute("textContent")
    except Exception as e:
        print(f"  [find_element by ID failed: {e}] falling back to regex on page_source")
        page_source = driver.page_source
        match = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            page_source,
            re.DOTALL,
        )
        if not match:
            print("  [regex fallback also failed — no __NEXT_DATA__ found at all]")
            return None
        raw_json = match.group(1)

    try:
        return json.loads(raw_json)
    except json.JSONDecodeError as e:
        print(f"  [JSON parse failed: {e}]")
        print(f"  First 500 chars of raw string: {raw_json[:500]}")
        return None


def preview(value, max_len=300):
    try:
        s = json.dumps(value)
    except TypeError:
        s = str(value)
    return s[:max_len] + ("..." if len(s) > max_len else "")


def dump_keys(obj, label, max_depth_keys=True):
    print(f"\n{'='*70}\n{label}\n{'='*70}")
    if not isinstance(obj, dict):
        print(f"  Not a dict, got {type(obj)}: {preview(obj)}")
        return
    for key, value in obj.items():
        print(f"\n  KEY: {key}  (type={type(value).__name__})")
        if isinstance(value, dict):
            print(f"    sub-keys: {list(value.keys())}")
            print(f"    preview: {preview(value, 200)}")
        elif isinstance(value, list):
            print(f"    length: {len(value)}")
            if value:
                print(f"    first item: {preview(value[0], 200)}")
        else:
            print(f"    value: {preview(value, 200)}")


def verify_player_page(driver):
    print(f"\n\n##### VERIFYING PLAYER PAGE: {PLAYER_URL} #####")
    driver.get(PLAYER_URL)

    next_data = extract_next_data(driver)
    if not next_data:
        print("FAILED: could not extract __NEXT_DATA__ from player page.")
        return

    print("SUCCESS: __NEXT_DATA__ found and parsed.")

    page_props = next_data.get("props", {}).get("pageProps", {})
    print(f"\npageProps top-level keys: {list(page_props.keys())}")

    data = page_props.get("data", page_props)
    dump_keys(data, "PLAYER DATA OBJECT (props.pageProps.data)")

    # Specifically hunt for anything that smells like detailed season stats
    print(f"\n{'='*70}\nSEARCHING FOR DETAILED STATS (xG, xGOT, duels, etc.)\n{'='*70}")
    candidates = ["statSeasons", "mainLeague", "playerStats", "statsSeasonsAndTournaments", "topStats", "statsSections"]
    for c in candidates:
        if c in data:
            print(f"\n--- Found candidate key: '{c}' ---")
            print(preview(data[c], 1000))
        else:
            print(f"\n--- '{c}' not present in data ---")

    # Deep-dive into firstSeasonStats, which looks like the real source
    # of the Shooting/Passing/Possession/Defending breakdown
    print(f"\n{'='*70}\nDEEP DIVE: firstSeasonStats\n{'='*70}")
    fss = data.get("firstSeasonStats")
    if fss:
        print(f"sectionOrder: {fss.get('sectionOrder')}")
        stats_section = fss.get("statsSection")
        print(f"\nstatsSection type: {type(stats_section).__name__}")
        print(f"statsSection full dump (up to 4000 chars):\n{preview(stats_section, 4000)}")

        top_stat_card = fss.get("topStatCard")
        print(f"\ntopStatCard full dump (up to 1500 chars):\n{preview(top_stat_card, 1500)}")
    else:
        print("firstSeasonStats not present!")


def verify_squad_page(driver):
    print(f"\n\n##### VERIFYING SQUAD PAGE: {SQUAD_URL} #####")
    driver.get(SQUAD_URL)

    next_data = extract_next_data(driver)
    if not next_data:
        print("FAILED: could not extract __NEXT_DATA__ from squad page.")
        return

    print("SUCCESS: __NEXT_DATA__ found and parsed.")

    page_props = next_data.get("props", {}).get("pageProps", {})
    print(f"\npageProps top-level keys: {list(page_props.keys())}")

    dump_keys(page_props, "SQUAD PAGE pageProps OBJECT")

    # Hunt for the squad list specifically
    print(f"\n{'='*70}\nSEARCHING FOR SQUAD LIST\n{'='*70}")
    candidates = ["squad", "data", "team", "players"]
    for c in candidates:
        if c in page_props:
            print(f"\n--- Found candidate key: '{c}' ---")
            print(preview(page_props[c], 1000))
        else:
            print(f"\n--- '{c}' not present in pageProps ---")

    # The squad data is likely nested under fallback['team-<id>']
    print(f"\n{'='*70}\nDEEP DIVE: pageProps.fallback\n{'='*70}")
    fallback = page_props.get("fallback", {})
    print(f"fallback top-level keys: {list(fallback.keys())}")

    for key in fallback.keys():
        if key.startswith("team-"):
            team_obj = fallback[key]
            print(f"\n--- fallback['{key}'] ---")
            if isinstance(team_obj, dict):
                print(f"  sub-keys: {list(team_obj.keys())}")
                for sub_key, sub_val in team_obj.items():
                    print(f"\n  {key}.{sub_key}  (type={type(sub_val).__name__})")
                    if isinstance(sub_val, dict):
                        print(f"    sub-keys: {list(sub_val.keys())}")
                    elif isinstance(sub_val, list):
                        print(f"    length: {len(sub_val)}")
                        if sub_val:
                            print(f"    first item preview: {preview(sub_val[0], 300)}")
                    print(f"    preview: {preview(sub_val, 300)}")
            else:
                print(f"  Not a dict: {preview(team_obj, 500)}")


def main():
    drv = driver_utils.setup_driver()
    try:
        verify_player_page(drv)
        verify_squad_page(drv)
    finally:
        driver_utils.close_driver(drv)


if __name__ == "__main__":
    main()
