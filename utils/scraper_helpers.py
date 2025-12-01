"""Helper functions for scraper logic."""


def calculate_match_points(home_goals, away_goals):
    """
    Calculate points for home and away teams based on goals.
    
    Args:
        home_goals (int): Goals scored by home team
        away_goals (int): Goals scored by away team
        
    Returns:
        tuple: (home_points, away_points)
    """
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
        tuple: (home_goals, away_goals) or (0, 0) if parsing fails
    """
    if score_str and ' - ' in score_str:
        try:
            parts = score_str.split(' - ')
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return int(parts[0]), int(parts[1])
        except:
            pass
    return 0, 0


def create_team_rows(match, round_num):
    """
    Create home and away team rows from a match dictionary.
    
    Args:
        match (dict): Match data dictionary
        round_num (int): Round number
        
    Returns:
        tuple: (home_row, away_row)
    """
    # Common match info
    base_info = {
        "Date": match['date'],
        "Round": round_num,
        "Match": f"{match['home']} - {match['away']}",
        "Score": match['score'],
        "Status": match['status'],
        "Url": match['url']
    }
    
    # Parse score to calculate goals and points
    home_goals, away_goals = parse_score(match['score'])
    home_points, away_points = calculate_match_points(home_goals, away_goals)
    
    # Create home row
    home_row = base_info.copy()
    home_row["Team"] = match['home']
    home_row["Side"] = "Home"
    home_row["Opponent"] = match['away']
    home_row["Goal scored"] = home_goals
    home_row["Goal conceded"] = away_goals
    home_row["points"] = home_points
    
    # Create away row
    away_row = base_info.copy()
    away_row["Team"] = match['away']
    away_row["Side"] = "Away"
    away_row["Opponent"] = match['home']
    away_row["Goal scored"] = away_goals
    away_row["Goal conceded"] = home_goals
    away_row["points"] = away_points
    
    return home_row, away_row
