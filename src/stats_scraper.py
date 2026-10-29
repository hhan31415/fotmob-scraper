"""Match statistics scraping functionality for FotMob."""

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException
import time

STATS_CONTAINER_SELECTOR = "[class*='StatGroupContainer']"
# The Facts tab also renders a StatGroupContainer, so check the tab state instead
STATS_TAB_SELECTED_XPATH = "//*[@role='tab'][@aria-selected='true'][normalize-space(.)='Stats']"


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
        # The ":tab=stats" fragment opens the stats panel directly, no click needed
        stats_url = _stats_tab_url(match_url)
        print(f"Navigating to match URL: {stats_url}")
        driver.get(stats_url)

        if progress_callback:
            progress_callback(20, "Loading match page...")

        wait = WebDriverWait(driver, 10)

        if progress_callback:
            progress_callback(40, "Opening stats tab...")

        # Fall back to clicking the Stats tab if the fragment didn't open it
        if not _wait_for_stats(driver, wait):
            _click_stats_tab(driver, wait)
            _wait_for_stats(driver, wait)

        if progress_callback:
            progress_callback(60, "Parsing stats data...")
        
        # The panel can re-render right after it appears; retry on stale elements
        for attempt in range(3):
            stats_data = {}
            try:
                _extract_possession(driver, stats_data)
                _extract_stat_sections(driver, stats_data)
                break
            except StaleElementReferenceException:
                print(f"Stats panel re-rendered, retrying (attempt {attempt + 1})")
                time.sleep(1)

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

def _stats_tab_url(match_url):
    """
    Appends ":tab=stats" to the match ID fragment (e.g. "#4813374:tab=stats").

    Returns the URL unchanged if it has no fragment or already names a tab.
    """
    if "#" not in match_url or ":tab=" in match_url:
        return match_url
    return f"{match_url}:tab=stats"


def _wait_for_stats(driver, wait):
    """Waits for the Stats tab to be selected and its panel to render. Returns True if it did."""
    try:
        wait.until(EC.presence_of_element_located((By.XPATH, STATS_TAB_SELECTED_XPATH)))
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, STATS_CONTAINER_SELECTOR)))
        return True
    except Exception:
        return False


def _click_stats_tab(driver, wait):
    """
    Clicks on the Stats tab to load statistics.

    Uses one XPath union so a single wait catches whichever selector matches
    first. On failure, prints the text of every nav/tab element found so the
    actual label can be identified if FotMob changes its DOM again.
    """
    selector = (
        # ARIA tab roles anywhere on the page (current FotMob DOM)
        "//*[@role='tab'][normalize-space(.)='Stats']"
        # Full text of a nav element (handles nested spans)
        " | //nav//*[self::a or self::button or self::span][normalize-space(.)='Stats']"
        # Any link or button anywhere with exact text Stats
        " | //*[self::a or self::button][normalize-space(.)='Stats']"
    )

    try:
        el = wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
        driver.execute_script("arguments[0].click();", el)
        print("Stats tab clicked")
        return
    except Exception:
        pass

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
    except StaleElementReferenceException:
        raise
    except Exception as e:
        print(f"Could not extract Ball possession: {e}")


def _extract_stat_sections(driver, stats_data):
    """
    Extracts all stat sections from the page.
    
    Args:
        driver: WebDriver instance
        stats_data (dict): Dictionary to update with stat sections
    """
    # Match on the stable part of the class name, not the hashed prefix.
    # scrape_match_stats has already waited for the panel to render.
    stat_containers = driver.find_elements(By.CSS_SELECTOR, STATS_CONTAINER_SELECTOR)
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
        except StaleElementReferenceException:
            raise
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

            except StaleElementReferenceException:
                raise
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