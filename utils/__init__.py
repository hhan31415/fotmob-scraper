"""Utility modules for the FotMob scraper.

This package contains infrastructure and helper utilities:
- config: Configuration settings
- driver: WebDriver setup and management
"""

from . import config
from . import driver

__all__ = ['config', 'driver']
