"""Browser management and lifecycle"""
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page
from typing import Dict, Optional
import os
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class BrowserManager:
    """Manages browser instances and contexts"""

    def __init__(self, options: Dict):
        self.options = options
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def start(self) -> Page:
        """Start browser and return page instance"""
        logger.info(f"Starting {self.options.get('browser', 'chromium')} browser")

        self.playwright = sync_playwright().start()

        # Select browser type
        browser_type = getattr(self.playwright, self.options.get('browser', 'chromium'))

        # Launch options
        launch_options = {
            'headless': self.options.get('headless', False),
            'slow_mo': self.options.get('slow_mo', 0),
        }

        # Video recording path
        if self.options.get('video', False):
            os.makedirs('reports/videos', exist_ok=True)

        self.browser = browser_type.launch(**launch_options)

        # Context options
        context_options = {
            'viewport': {'width': 1920, 'height': 1080},
            'ignore_https_errors': True,
        }

        if self.options.get('video', False):
            context_options['record_video_dir'] = 'reports/videos'
            context_options['record_video_size'] = {'width': 1920, 'height': 1080}

        self.context = self.browser.new_context(**context_options)
        self.page = self.context.new_page()

        # Enable console logging
        self.page.on("console", lambda msg: logger.debug(f"Browser console: {msg.text}"))

        return self.page

    def stop(self):
        """Stop browser and cleanup"""
        if self.page:
            self.page.close()
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def get_page(self) -> Optional[Page]:
        """Get current page instance"""
        return self.page

    def new_page(self) -> Page:
        """Create new page in existing context"""
        if self.context:
            return self.context.new_page()
        return None

    def take_screenshot(self, name: str = None) -> str:
        """Take screenshot of current page"""
        if not self.page:
            return None

        os.makedirs('reports/screenshots', exist_ok=True)
        path = f"reports/screenshots/{name or 'screenshot'}.png"
        self.page.screenshot(path=path, full_page=True)
        return path