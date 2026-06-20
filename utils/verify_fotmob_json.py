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
