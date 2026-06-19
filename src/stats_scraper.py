"""Match statistics scraping functionality for FotMob."""

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time


def scrape_match_stats(driver, match_url, progress_callback=None):
    """
    Scrapes detailed statistics for a specific match.
    
    Args:
        driver: WebDriver instance
        match_url (str): URL of the match page
        progress_callback (callable, optional): Progress callback function
        
    Returns:
        dict: Dictionary of stats organized by section
    """
    stats_data = {}
    
    try:
        print(f"Navigating to match URL: {match_url}")
        driver.get(match_url)
        
        if progress_callback:
            progress_callback(20, "Loading match page...")
        
        wait = WebDriverWait(driver, 10)
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)
        
        if progress_callback:
            progress_callback(40, "Opening stats tab...")
        
        # Click on Stats tab
        _click_stats_tab(driver, wait)

        # Scroll to load all content
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(1)
        
        if progress_callback:
            progress_callback(60, "Parsing stats data...")
        
        # Extract ball possession
        _extract_possession(driver, stats_data)
        
        # Extract all stat sections
        _extract_stat_sections(driver, stats_data)
        
        # Clean up empty sections
        stats_data = {k: v for k, v in stats_data.items() if v}
        
        if progress_callback:
            progress_callback(100, "Finished!")
        
        print(f"Extracted {len(stats_data)} sections with stats")
        for section, stats in stats_data.items():
            print(f"  {section}: {len(stats)} stats")
                    
        return stats_data
        
    except Exception as e:
        print(f"Error scraping match stats: {e}")
        import traceback
        traceback.print_exc()
        return {}


def _click_stats_tab(driver, wait):
    """
    Clicks on the Stats tab to load statistics.
    
    Args:
        driver: WebDriver instance
        wait: WebDriverWait instance
    """
    """
    Tried out different ways to click the stats button, the last one worked the best
    STATS_SELECTORS = [
        # Most likely: an anchor tag with exact text "Stats"
        (By.XPATH, "//a[normalize-space(text())='Stats']"),
        # Tab role (ARIA)
        (By.XPATH, "//*[@role='tab' and normalize-space(text())='Stats']"),
        # List item containing "Stats"
        (By.XPATH, "//li[normalize-space(text())='Stats']"),
        # Any element with exact text, scoped to a nav/tab bar
        (By.XPATH, "//nav//*[normalize-space(text())='Stats']"),
    ]
    """
    el = wait.until(EC.element_to_be_clickable((By.XPATH, "//nav//*[normalize-space(text())='Stats']")))
    driver.execute_script("arguments[0].click();", el)
    time.sleep(3)
    #print(f"Stats tab clicked with: {selector}")

    raise RuntimeError("Stats tab not found — FotMob may have changed its DOM structure")


def _extract_possession(driver, stats_data):
    """
    Extracts ball possession data.
    
    Args:
        driver: WebDriver instance
        stats_data (dict): Dictionary to update with possession data
    """
    try:
        possession_div = driver.find_element(By.CSS_SELECTOR, "div.css-1xzakdb-PossessionDiv")
        possession_spans = possession_div.find_elements(By.TAG_NAME, "span")
        
        if len(possession_spans) >= 2:
            home_possession = possession_spans[0].text.strip()
            away_possession = possession_spans[1].text.strip()
            
            if "Top stats" not in stats_data:
                stats_data["Top stats"] = {}
            
            stats_data["Top stats"]["Ball possession"] = [home_possession, away_possession]
            print(f"Extracted Ball possession: {home_possession} | {away_possession}")
    except Exception as e:
        print(f"Could not extract Ball possession: {e}")


def _extract_stat_sections(driver, stats_data):
    """
    Extracts all stat sections from the page.
    
    Args:
        driver: WebDriver instance
        stats_data (dict): Dictionary to update with stat sections
    """
    stat_containers = driver.find_elements(By.CSS_SELECTOR, "ul.css-1pxkecz-StatGroupContainer")
    print(f"Found {len(stat_containers)} stat containers")
    
    for container in stat_containers:
        # Default section name
        current_section = "Top stats"
        
        # Check for explicit header
        try:
            header = container.find_element(By.CSS_SELECTOR, "header h2")
            if header:
                current_section = header.text.strip()
        except:
            pass
        
        # Iterate through all list items
        items = container.find_elements(By.CSS_SELECTOR, "li")
        
        for item in items:
            try:
                # Check if this item is a section header
                is_header = _is_section_header(item)
                
                if is_header:
                    new_section = item.text.strip()
                    if new_section:
                        current_section = new_section
                        if current_section not in stats_data:
                            stats_data[current_section] = {}
                    continue
                
                # Parse stat row
                stat_name, home_val, away_val = _parse_stat_row(item)
                
                if stat_name:
                    # Ensure section exists
                    if current_section not in stats_data:
                        stats_data[current_section] = {}
                    
                    stats_data[current_section][stat_name] = [home_val, away_val]
                    
            except Exception as e:
                continue


def _is_section_header(item):
    """
    Checks if a list item is a section header.
    
    Args:
        item: Selenium WebElement
        
    Returns:
        bool: True if item is a header, False otherwise
    """
    try:
        item.find_element(By.CSS_SELECTOR, "[class*='StatBox'], [class*='StatValue']")
        return False
    except:
        # No stat box found, likely a header
        return bool(item.text.strip())


def _parse_stat_row(item):
    """
    Parses a stat row to extract stat name and values.
    
    Args:
        item: Selenium WebElement
        
    Returns:
        tuple: (stat_name, home_value, away_value) or (None, None, None)
    """
    text = item.text.strip()
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    
    if len(lines) >= 3:
        # Format: HomeValue \n StatName \n AwayValue
        stat_name = lines[1]
        home_val = lines[0]
        away_val = lines[2]
        return stat_name, home_val, away_val
    
    return None, None, None
