"""WebDriver setup and management for FotMob scraper."""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from utils import config
import platform
import shutil


def setup_driver():
    """
    Creates and configures a Chrome WebDriver instance.

    Sets a 30-second page load timeout so that a hung or unresponsive page
    fails fast instead of blocking the scraper for minutes per occurrence.

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
        # Streamlit Cloud / Linux: use system-installed Chromium
        options.add_argument('--disable-setuid-sandbox')
        options.add_argument('--single-process')
        options.add_argument('--no-zygote')

        chromium_path = (shutil.which("chromium") or
                         shutil.which("chromium-browser") or
                         "/usr/bin/chromium")
        chromedriver_path = (shutil.which("chromedriver") or
                             "/usr/bin/chromedriver")

        options.binary_location = chromium_path
        service = Service(chromedriver_path)
    else:
        # Local Windows/Mac: webdriver_manager handles driver download
        service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(30)
    return driver


def ensure_driver_alive(driver):
    """
    Checks if the driver is still alive and recreates it if necessary.

    Uses driver.get("about:blank") as the health check rather than
    driver.current_url, since a locked renderer can still answer property
    reads while failing on the next real page load.

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
            pass
        return setup_driver()


def close_driver(driver):
    """
    Closes the WebDriver instance.

    Args:
        driver: WebDriver instance to close
    """
    if driver:
        driver.quit()