"""Custom action handlers for complex operations"""
from typing import Dict, Any
from playwright.sync_api import Page


class ActionHandler:
    """Handles complex custom actions"""

    def __init__(self, page: Page, config: Dict):
        self.page = page
        self.config = config

    def login(self, params: Dict) -> Dict:
        """Custom login action"""
        username = params.get('username', '')

        # Get user data from config
        users = self.config.get('test_data', {}).get('users', [])
        user_data = next((u for u in users if u['username'] == username), None)

        if not user_data:
            raise Exception(f"User not found in test data: {username}")

        # Navigate to login page
        login_url = self.config.get('pages', {}).get('login', '/login')
        if not login_url.startswith('http'):
            base_url = self.config.get('base_url', '')
            login_url = f"{base_url}{login_url}"

        self.page.goto(login_url)

        # Fill login form
        self.page.fill('input[name="username"], input[type="email"]', username)
        self.page.fill('input[name="password"], input[type="password"]', user_data['password'])
        self.page.click('button[type="submit"], input[type="submit"]')

        # Wait for navigation
        self.page.wait_for_load_state('networkidle')

        return {'logged_in': username}

    def add_to_cart(self, params: Dict) -> Dict:
        """Add items to cart"""
        quantity = int(params.get('quantity', 1))

        for i in range(quantity):
            self.page.click('button:has-text("Add to Cart")')
            self.page.wait_for_timeout(500)

        return {'added_to_cart': quantity}