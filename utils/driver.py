"""WebDriver setup and management for FotMob scraper."""

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from utils import config


def setup_driver():
    """
    Creates and configures a Chrome WebDriver instance.
    
    Returns:
        webdriver.Chrome: Configured Chrome WebDriver instance
    """
    # Use ChromeDriverManager to automatically install/update the driver
    service = Service(ChromeDriverManager().install())
    
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    return webdriver.Chrome(service=service, options=options)


def ensure_driver_alive(driver):
    """
    Checks if the driver is still alive and recreates it if necessary.
    
    Args:
        driver: WebDriver instance to check
        
    Returns:
        webdriver.Chrome: Active WebDriver instance
    """
    try:
        driver.current_url
        return driver
    except:
        return setup_driver()


def close_driver(driver):
    """
    Closes the WebDriver instance.
    
    Args:
        driver: WebDriver instance to close
    """
    if driver:
        driver.quit()
