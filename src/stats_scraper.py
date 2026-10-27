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

    Tries several selectors, from most to least specific. On failure, prints
    the text of every nav/tab element found so the actual label can be
    identified if FotMob changes its DOM again.
    """
    selectors = [
        # Direct text match (original selector)
        "//nav//*[normalize-space(text())='Stats']",
        # Full text of the element (handles nested spans)
        "//nav//*[self::a or self::button or self::span][normalize-space(.)='Stats']",
        # ARIA tab roles anywhere on the page
        "//*[@role='tab'][normalize-space(.)='Stats']",
        # Any link or button anywhere with exact text Stats
        "//*[self::a or self::button][normalize-space(.)='Stats']",
    ]

    for selector in selectors:
        try:
            el = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
            driver.execute_script("arguments[0].click();", el)
            time.sleep(3)  # give the stats panel time to render
            print(f"Stats tab clicked with: {selector}")
            return
        except Exception:
            continue

    # Debug output: show what tab-like elements actually exist
    try:
        candidates = driver.find_elements(
            By.XPATH, "//nav//a | //nav//button | //*[@role='tab']"
        )
        labels = [c.text.strip() for c in candidates if c.text.strip()]
        print(f"Stats tab not found. Tab-like elements on page: {labels[:30]}")
    except Exception:
        pass

    raise RuntimeError("Stats tab not found — FotMob may have changed its DOM structure")

def _extract_possession(driver, stats_data):
    """
    Extracts ball possession data.
    
    Args:
        driver: WebDriver instance
        stats_data (dict): Dictionary to update with possession data
    """
    try:
        possession_div = driver.find_element(By.CSS_SELECTOR, "[class*='PossessionDiv']")
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
     # Match on the stable part of the class name, not the hashed prefix,
    # and wait for the stats panel to actually render after the tab click
    selector = "[class*='StatGroupContainer']"
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )
    except Exception:
        pass

    stat_containers = driver.find_elements(By.CSS_SELECTOR, selector)
    print(f"Found {len(stat_containers)} stat containers")

    if not stat_containers:
        # Debug: show which stat-related classes exist on the page
        found = driver.find_elements(By.CSS_SELECTOR, "[class*='Stat']")
        classes = {el.get_attribute("class") for el in found[:30]}
        print(f"No containers found. Stat-like classes on page: {classes}")
    
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
                # Skip possession row -- already handled by _extract_possession
                # and misidentified as a section header due to its different class
                item_class = item.get_attribute("class") or ""
                if "PossessionRow" in item_class:
                    continue
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
        # Format: StatName \n HomeValue \n AwayValue
        # (confirmed from live DOM inspection of FotMob match stats page)
        stat_name = lines[0]
        home_val = lines[1]
        away_val = lines[2]
        return stat_name, home_val, away_val
    
    return None, None, None