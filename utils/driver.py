"""WebDriver setup and management for FotMob scraper."""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from utils import config
import platform


def setup_driver():
    """
    Creates and configures a Chrome WebDriver instance.

    Sets a 30-second page load timeout (rather than relying on the default,
    which can be 120+ seconds depending on environment) so that a hung or
    unresponsive page fails fast instead of blocking the scraper for minutes
    per occurrence -- important when scraping hundreds of player pages back
    to back, where an occasional dead request is expected.

    Returns:
        webdriver.Chrome: Configured Chrome WebDriver instance
    """
    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-extensions')

    if platform.system() == "Linux":
        # Streamlit Cloud: Chromium installed via packages.txt at fixed path
        options.add_argument('--disable-setuid-sandbox')
        options.add_argument('--single-process')
        options.binary_location = "/usr/bin/chromium"
        service = Service("/usr/bin/chromedriver")
    else:
        # Local Windows/Mac: webdriver_manager handles driver download
        service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(30)
    return driver


def ensure_driver_alive(driver):
    """
    Checks if the driver is still alive and recreates it if necessary.

    Checking driver.current_url alone is not always a reliable signal --
    a renderer process can be locked up enough to fail on the next
    driver.get() while still answering trivial property reads like
    current_url successfully. Instead, this does a real (cheap) navigation
    to about:blank, which exercises the same code path that was observed
    hanging on real player pages, so a broken driver is reliably detected
    and replaced here rather than failing again on the next real page load.

    Args:
        driver: WebDriver instance to check

    Returns:
        webdriver.Chrome: Active WebDriver instance (existing if healthy,
            otherwise a freshly created one)
    """
    try:
        driver.get("about:blank")
        return driver
    except Exception:
        print("Driver appears unresponsive, recreating...")
        try:
            driver.quit()
        except Exception:
            pass  # driver may already be dead; nothing to clean up
        return setup_driver()


def close_driver(driver):
    """
    Closes the WebDriver instance.

    Args:
        driver: WebDriver instance to close
    """
    if driver:
        driver.quit()