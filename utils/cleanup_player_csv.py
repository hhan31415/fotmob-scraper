"""
Cleanup script for player data CSVs produced by league_player_data.py.

Applies four fixes identified during sanity-check of nashville_sc.csv:

1. BACKFILL NaN-when-zero bug: when a player has very few minutes, FotMob's
   firstSeasonStats.statsSection sometimes omits a whole stat-group entirely
   (e.g. no "Shooting" group at all), leaving Goals as NaN there even though
   mainLeague.stats ("Summary") correctly reports 0. We backfill these from
   the Summary columns where a clear match exists.

2. RENAME ambiguous columns: "Summary - X" and "Top stats - X" looked like
   exact duplicates but are NOT -- Summary reflects ALL competitions this
   season, Top stats reflects only the currently-selected competition
   (usually league play only, excluding cups). Verified via mismatches on
   Charles-Emile Brunet (2 assists/5 matches all-comps vs 0 assists/3
   matches league-only). Renamed for clarity instead of dropped.

3. REORDER columns into logical groups: identity -> all-competitions summary
   -> selected-competition summary -> position-specific detailed stats ->
   per90 versions, instead of the scattered order produced by incremental
   dict-building across different position groups.

4. CURRENCY: convert market_value_eur (EUR) to market_value_usd (USD) using
   a fixed rate documented below. NOTE: this is a fixed snapshot rate, not
   live-fetched -- update EUR_TO_USD_RATE if re-running this script later.

5. ROUNDING: round all float columns to 2 decimal places (stats like xG,
   per90 values, percentages) to avoid 15+ digit floating point noise.

Usage:
    python cleanup_player_csv.py <input.csv> [output.csv]

If output.csv is omitted, writes to <input>_cleaned.csv
"""

import sys
import re
import pandas as pd

# Rate as of 2026-06-19, per Xe/Bloomberg/Yahoo Finance (averaged ~1.147).
# This is a FIXED snapshot, not live -- update if accuracy over time matters.
EUR_TO_USD_RATE = 1.147

# Pairs of (all-competitions column, selected-competition column) to rename.
# Only renames columns that actually exist in a given file (keepers vs
# outfield players produce different column sets).
RENAME_MAP = {
    "Summary - Goals": "All Competitions - Goals",
    "Summary - Assists": "All Competitions - Assists",
    "Summary - Started": "All Competitions - Started",
    "Summary - Matches": "All Competitions - Matches",
    "Summary - Minutes played": "All Competitions - Minutes played",
    "Summary - Rating": "All Competitions - Rating",
    "Summary - Yellow cards": "All Competitions - Yellow cards",
    "Summary - Red cards": "All Competitions - Red cards",
    "Summary - Clean sheets": "All Competitions - Clean sheets",
    "Summary - Goals conceded": "All Competitions - Goals conceded",
    "Summary - Saved penalties": "All Competitions - Saved penalties",
    "Top stats - Goals": "Selected Competition - Goals",
    "Top stats - Assists": "Selected Competition - Assists",
    "Top stats - Rating": "Selected Competition - Rating",
    "Top stats - Matches": "Selected Competition - Matches",
    "Top stats - Started": "Selected Competition - Started",
    "Top stats - Minutes": "Selected Competition - Minutes",
    "Top stats - Conceded": "Selected Competition - Conceded",
    "Top stats - Clean sheets": "Selected Competition - Clean sheets",
    "Top stats - Penalties saved": "Selected Competition - Penalties saved",
}

# Backfill targets: when the position-specific column is NaN but an
# all-competitions equivalent exists, fill from it. Only applied where the
# stat genuinely represents the same underlying count (goals, assists,
# clean sheets, cards), not things like xG which has no Summary equivalent.
BACKFILL_MAP = {
    "Shooting - Goals": "All Competitions - Goals",
    "Passing - Assists": "All Competitions - Assists",
    "Defending - Clean sheets": "All Competitions - Clean sheets",
    "Goalkeeping - Clean sheets": "All Competitions - Clean sheets",
    "Goalkeeping - Goals conceded": "All Competitions - Goals conceded",
    "Discipline - Yellow cards": "All Competitions - Yellow cards",
    "Discipline - Red cards": "All Competitions - Red cards",
}

# Column ordering groups, in priority order. Anything not matched falls
# through to the end in original order.
IDENTITY_COLS = [
    "player_id", "name", "team", "team_id", "url", "position", "position_short",
    "position_group", "height_cm", "shirt", "age", "country", "preferred_foot",
    "market_value_usd", "market_value_eur", "market_value", "contract_end",
    "league_name", "league_group", "season_league", "season_year",
]


def fix_money(df):
    """Add market_value_usd from market_value_eur, formatted like the
    original '€X.Xm' style but in dollars."""
    if "market_value_eur" not in df.columns:
        return df

    df = df.copy()

    # Coerce to numeric before any arithmetic. Necessary because resumed
    # rows (read back from a prior run's CSV via csv.DictReader) come in
    # as plain strings, while freshly-scraped rows in the same combined
    # batch keep native int/float types. Mixing the two makes pandas infer
    # an object/string dtype for the whole column, and multiplying that by
    # a float fails with "can only string multiply by an integer" since
    # pandas falls back to Python's str-repeat operator instead of
    # elementwise numeric multiplication.
    df["market_value_eur"] = pd.to_numeric(df["market_value_eur"], errors="coerce")

    def format_usd(eur_value):
        if pd.isna(eur_value):
            return None
        usd = eur_value * EUR_TO_USD_RATE
        if usd >= 1_000_000:
            return f"${usd / 1_000_000:.1f}m"
        elif usd >= 1_000:
            return f"${usd / 1_000:.1f}k"
        else:
            return f"${usd:.0f}"

    df["market_value_usd_raw"] = (df["market_value_eur"] * EUR_TO_USD_RATE).round(2)
    df["market_value_usd"] = df["market_value_eur"].apply(format_usd)
    return df


def backfill_nan_zero_gap(df):
    """Fill position-specific stat NaNs from the all-competitions Summary
    columns where they represent the same count, fixing the 'whole stat
    group missing from JSON for low-minute players' issue."""
    for target_col, source_col in BACKFILL_MAP.items():
        if target_col in df.columns and source_col in df.columns:
            df[target_col] = df[target_col].fillna(df[source_col])
    return df


def rename_ambiguous_columns(df):
    """Rename Summary/Top stats columns to reflect their actual scope
    (all competitions vs selected competition only).

    Idempotent: safe to call on a dataframe that's a MIX of freshly-scraped
    rows (still using the raw 'Summary - X' / 'Top stats - X' names) and
    rows read back from already-cleaned CSVs during a resumed run (which
    already have the final 'All Competitions - X' / 'Selected Competition - X'
    names). Without this, renaming a mixed dataframe produces two columns
    with the identical final name side by side, which breaks any later
    df[col] = df[col].fillna(df[other_col]) call with a
    "value parameter must be a scalar, dict or Series" TypeError, since
    indexing a duplicate-named column returns a DataFrame instead of a
    Series.
    """
    existing_renames = {k: v for k, v in RENAME_MAP.items() if k in df.columns}
    df = df.rename(columns=existing_renames)

    # If renaming produced any duplicate column names (because the target
    # name already existed from a previously-cleaned/resumed row), merge
    # them: take the first non-null value across the duplicate columns for
    # each row, then drop down to a single column with that name.
    if df.columns.duplicated().any():
        merged = {}
        for col_name in df.columns[df.columns.duplicated(keep=False)].unique():
            same_named = df.loc[:, df.columns == col_name]
            merged[col_name] = same_named.bfill(axis=1).iloc[:, 0]

        df = df.loc[:, ~df.columns.duplicated(keep="first")]
        for col_name, series in merged.items():
            df[col_name] = series

    return df


def coerce_numeric_columns(df, exclude=None):
    """
    Coerces any column that looks numeric (i.e. converts cleanly via
    pd.to_numeric for non-null values) from object/string dtype to a real
    numeric dtype.

    This exists because of a resume-related dtype mixing issue: rows from
    a fresh scrape keep native Python int/float types, while rows read
    back from a prior run's CSV (via csv.DictReader, in
    read_team_csv_as_rows) come back as plain strings for every field.
    When combined into one dataframe, any numeric column can silently end
    up as object dtype instead of int64/float64. That's not just a
    cosmetic issue -- it breaks arithmetic (e.g. "can only string multiply
    by an integer" in fix_money) and breaks dtype-based column selection
    (e.g. round_floats' select_dtypes(include=["float64"]) silently skips
    contaminated columns instead of rounding them, since they technically
    aren't float64 anymore).

    Rather than patching each downstream function one at a time as new
    instances of this surface, this runs once, early, on the full combined
    dataframe and fixes the dtype at the source.

    Args:
        df (pd.DataFrame)
        exclude (set[str], optional): Column names to never coerce (e.g.
            identity/text fields that might coincidentally look numeric
            for some rows, like a country code or zero-padded ID -- none
            currently apply here, but kept as a safety valve)

    Returns:
        pd.DataFrame
    """
    exclude = exclude or set()
    df = df.copy()

    for col in df.columns:
        if col in exclude:
            continue
        if df[col].dtype != object:
            continue  # already numeric, bool, etc -- nothing to do

        coerced = pd.to_numeric(df[col], errors="coerce")

        # Only adopt the coerced version if it didn't turn genuinely
        # non-numeric data (names, position strings, URLs, etc.) into
        # all-NaN. A column where every non-null original value converts
        # successfully is numeric; a column where conversion mostly fails
        # is genuinely text and should be left alone.
        original_non_null = df[col].notna().sum()
        coerced_non_null = coerced.notna().sum()

        if original_non_null > 0 and coerced_non_null == original_non_null:
            df[col] = coerced

    return df


def round_floats(df, decimals=2):
    """Round all float columns to a fixed number of decimals."""
    float_cols = df.select_dtypes(include=["float64", "float32"]).columns
    df[float_cols] = df[float_cols].round(decimals)
    return df


def reorder_columns(df):
    """Reorder columns: identity fields first, then everything else in
    its current relative order (per90 columns naturally stay near their
    non-per90 counterparts since we don't otherwise reshuffle)."""
    present_identity = [c for c in IDENTITY_COLS if c in df.columns]
    remaining = [c for c in df.columns if c not in present_identity]
    return df[present_identity + remaining]


def clean_player_csv(input_path, output_path):
    df = pd.read_csv(input_path)

    original_shape = df.shape

    df = rename_ambiguous_columns(df)
    df = coerce_numeric_columns(df, exclude={"name", "team", "url", "position",
                                               "position_short", "position_group",
                                               "preferred_foot", "country",
                                               "contract_end", "market_value",
                                               "market_value_usd", "season_league",
                                               "season_year", "league_name",
                                               "league_group"})
    df = backfill_nan_zero_gap(df)
    df = fix_money(df)
    df = round_floats(df, decimals=2)
    df = reorder_columns(df)

    df.to_csv(output_path, index=False)

    print(f"Cleaned: {input_path} -> {output_path}")
    print(f"  Shape: {original_shape} -> {df.shape}")
    print(f"  EUR->USD rate used: {EUR_TO_USD_RATE}")

    return df


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python cleanup_player_csv.py <input.csv> [output.csv]")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else re.sub(r"\.csv$", "_cleaned.csv", input_path)

    clean_player_csv(input_path, output_path)