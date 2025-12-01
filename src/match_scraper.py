"""Match list scraping functionality for FotMob."""

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from datetime import datetime, timedelta
import time
from utils import config


def scrape_matches(driver, season, round_num, progress_callback=None):
    """
    Scrapes match data for a specific season and round.
    
    Args:
        driver: WebDriver instance
        season (str): Season in format "YYYY-YYYY"
        round_num (int): Round number
        progress_callback (callable, optional): Progress callback function
        
    Returns:
        list: List of match dictionaries
    """
    if progress_callback:
        progress_callback(10, "Initializing scraper...")

    url_round = int(round_num) - 1
    url = f"{config.BASE_URL}?group=by-round&season={season}&round={url_round}"
    print(f"Navigating to: {url}")
    driver.get(url)

    try:
        if progress_callback:
            progress_callback(30, "Loading page...")

        wait = WebDriverWait(driver, 10)
        
        # Scroll to load dynamic content
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(5)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)

        if progress_callback:
            progress_callback(70, "Parsing match data...")

        matches = []
        match_links = driver.find_elements(By.CSS_SELECTOR, "a[href*='/matches/']")
        
        if match_links:
            print(f"Found {len(match_links)} match links.")
            
            for link in match_links:
                match_data = _parse_match_link(link)
                if match_data:
                    matches.append(match_data)
        
        if progress_callback:
            progress_callback(90, "Assigning dates...")

        _assign_dates(driver, matches)

        if progress_callback:
            progress_callback(100, "Finished!")
        
        return matches

    except Exception as e:
        print(f"Error occurred: {e}")
        return []


def _parse_match_link(link):
    """
    Parses a single match link element to extract match data.
    
    Args:
        link: Selenium WebElement for match link
        
    Returns:
        dict or None: Match data dictionary or None if parsing fails
    """
    try:
        match_text = link.text
        match_url = link.get_attribute("href")
        
        if not match_text:
            return None
            
        lines = [l.strip() for l in match_text.split('\n') if l.strip()]
        
        score = None
        status = None
        match_time = None
        teams = []
        
        for line in lines:
            if line in ["AM", "PM"]:
                if match_time:
                    match_time = f"{match_time} {line}"
                continue
            elif ':' in line and len(line) <= 5 and all(c.isdigit() or c == ':' for c in line):
                match_time = line
            elif " - " in line and any(c.isdigit() for c in line):
                score = line
            elif line in ["FT", "Live", "HT", "Postponed", "Cancelled"] or \
                 line.endswith("'") or \
                 (len(line) <= 5 and "+" in line and any(c.isdigit() for c in line)) or \
                 (line.isdigit() and len(line) <= 3):
                status = line
            elif line not in ["FT", "Live", "HT", "Postponed", "Cancelled", "AM", "PM"] and \
                 " - " not in line and not (':' in line and len(line) <= 5):
                teams.append(line)
        
        if len(teams) >= 2:
            return {
                "home": teams[0],
                "away": teams[1],
                "score": score if score else (match_time if match_time else "N/A"),
                "status": status if status else ("Upcoming" if match_time else "N/A"),
                "url": match_url
            }
    except Exception as e:
        return None
    
    return None


def _assign_dates(driver, matches):
    """
    Assigns dates to matches by parsing date headers on the page.
    
    Args:
        driver: WebDriver instance
        matches (list): List of match dictionaries to update
    """
    try:
        elements = driver.find_elements(By.XPATH, "//*[self::h3 or self::a[contains(@href, '/matches/')]]")
        
        current_date = "N/A"
        match_idx = 0
        
        for element in elements:
            if element.tag_name == "h3":
                date_text = element.text.strip()
                if date_text.lower() == "today":
                    current_date = datetime.now().strftime("%A, %B %d, %Y")
                elif date_text.lower() == "tomorrow":
                    current_date = (datetime.now() + timedelta(days=1)).strftime("%A, %B %d, %Y")
                elif date_text.lower() == "yesterday":
                    current_date = (datetime.now() - timedelta(days=1)).strftime("%A, %B %d, %Y")
                else:
                    current_date = date_text
            elif element.tag_name == "a" and match_idx < len(matches):
                matches[match_idx]['date'] = current_date
                match_idx += 1
                
    except Exception as e:
        print(f"Error assigning dates: {e}")
