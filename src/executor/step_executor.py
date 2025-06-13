"""
Step executor that handles the actual browser interactions
"""
import re
import time
import datetime
import asyncio
import time
from typing import Dict, Any, Optional, List
from playwright.sync_api import Page, ElementHandle
from src.core.ai_element_finder import AIElementFinder
from src.utils.logger import setup_logger
import os
from jsonpath_ng import parse

logger = setup_logger(__name__)

class StepExecutor:
    """Execute individual test steps using AI-powered element detection"""

    def __init__(self, page: Page, ai_finder: AIElementFinder, config: Dict):
        self.page = page
        self.ai_finder = ai_finder
        self.config = config
        self.timeout = config.get('timeout', 30000)  # 30 seconds default
        self.wait_time = config.get('wait_time', 500)  # 500ms default
        self.api_executor = None
        api_config_path = config.get('api_config_path', 'config/api_config.yaml')
        if os.path.exists(api_config_path):
            from src.executor.api_executor import APIExecutor
            self.api_executor = APIExecutor(api_config_path, config.get('env', 'dev'))
            # Initialize async session
            # asyncio.run(self.api_executor.initialize())

        # Store for last API response
        self.last_api_response = None
        self.current_test_name = None
        self.current_frame = None
        self.main_frame = page.main_frame


    def _ensure_correct_frame(self):
        """Automatically switch to the correct frame if content is in an iframe"""
        try:
            # Check if there are iframes on the page
            iframes = self.page.locator('iframe').all()

            if not iframes:
                return self.page

            # For each iframe, check if it contains substantial content
            for iframe_element in iframes:
                try:
                    frame = iframe_element.content_frame()
                    if frame:
                        # Check if this frame has meaningful content
                        # Look for common indicators of main content
                        indicators = [
                            'body > div',  # Common container
                            'main',  # Main content area
                            '[role="main"]',  # ARIA main
                            '.container',  # Common container class
                            '.content',  # Common content class
                            'form',  # Forms often in iframes
                            '.ant-layout',  # Ant Design layout
                        ]

                        for indicator in indicators:
                            if frame.locator(indicator).count() > 0:
                                logger.debug(f"Found content indicator '{indicator}' in iframe, switching context")
                                self.current_frame = frame
                                return frame

                        # If no specific indicators, check if frame has more elements than main page
                        frame_elements = frame.locator('*').count()
                        main_elements = self.page.main_frame.locator('*').count()

                        if frame_elements > main_elements * 0.5:
                            logger.debug(
                                f"Iframe has substantial content ({frame_elements} elements), switching context")
                            self.current_frame = frame
                            return frame

                except Exception as e:
                    logger.debug(f"Could not check iframe: {e}")
                    continue

            # Return main frame if no suitable iframe found
            return self.page
        except Exception as e:
            logger.debug(f"Frame detection error: {e}")
            return self.page

    def _find_element_in_frames(self, selector: str, timeout: int = 5000):
        """Try to find element in main frame and all iframes"""
        start_time = time.time()

        # First try current frame if set
        if self.current_frame:
            try:
                element = self.current_frame.locator(selector)
                if element.count() > 0:
                    first = element.first
                    if first.is_visible():
                        return first, self.current_frame
            except:
                pass

        # Then try main frame
        try:
            element = self.page.locator(selector)
            if element.count() > 0:
                first = element.first
                if first.is_visible():
                    self.current_frame = None  # Reset to main frame
                    return first, self.page
        except:
            pass

        # Then try each iframe
        iframes = self.page.locator('iframe').all()
        for iframe_element in iframes:
            if time.time() - start_time > timeout / 1000:
                break

            try:
                frame = iframe_element.content_frame()
                if frame:
                    element = frame.locator(selector)
                    if element.count() > 0:
                        first = element.first
                        if first.is_visible():
                            self.current_frame = frame
                            logger.debug(f"Found element in iframe, auto-switching context")
                            return first, frame
            except:
                continue

        return None, None

    def _get_current_context(self):
        """Get the current frame context for operations"""
        if self.current_frame:
            return self.current_frame

        # Auto-detect frame on first use
        return self._ensure_correct_frame()

    def execute_step(self, action: str, parameters: Dict) -> Dict:
        """Execute a single step and return result"""
        try:
            logger.info(f"Executing action: {action} with params: {parameters}")

            # Map action to handler method
            handler = getattr(self, f"_handle_{action}", None)
            if handler:
                result = handler(parameters)

                # Wait after action based on configuration
                self._wait_after_action(action)

                return {
                    'status': 'passed',
                    'action': action,
                    'parameters': parameters,
                    'result': result
                }
            else:
                logger.warning(f"Unknown action: {action}")
                return {
                    'status': 'failed',
                    'action': action,
                    'parameters': parameters,
                    'error': f"Unknown action: {action}"
                }

        except Exception as e:
            logger.error(f"Step execution failed: {str(e)}")
            return {
                'status': 'failed',
                'action': action,
                'parameters': parameters,
                'error': str(e),
                'screenshot': self._take_screenshot()
            }

    def _ensure_api_executor_initialized(self):
        """Ensure API executor is initialized when needed"""
        if self.api_executor and not self.api_executor.session:
            # Create new event loop if needed
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is already running, create task
                    asyncio.create_task(self.api_executor.initialize())
                else:
                    # If no loop is running, use asyncio.run
                    asyncio.run(self.api_executor.initialize())
            except RuntimeError:
                # Create new loop
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.api_executor.initialize())

    def _wait_after_action(self, action: str):
        """Apply configurable wait after action execution"""
        # Get wait configuration
        wait_config = self.config.get('wait_after_actions', {})
        default_wait = wait_config.get('default', 0.5)
        action_specific_wait = wait_config.get(action, default_wait)

        # Apply wait if configured
        if action_specific_wait > 0:
            logger.debug(f"Waiting {action_specific_wait}s after {action} action")
            time.sleep(action_specific_wait)

    def _handle_navigate(self, params: Dict) -> Any:
        """Handle navigation actions"""
        url = params.get('url', '')

        # Remove 'page' suffix if present
        page_name = url.lower().replace(' page', '').strip()

        # Check if URL is a key in config pages
        pages = self.config.get('pages', {})
        if page_name in pages:
            url = pages[page_name]
        elif page_name.replace(' ', '_') in pages:
            url = pages[page_name.replace(' ', '_')]
        elif page_name.replace(' ', '-') in pages:
            url = pages[page_name.replace(' ', '-')]
        elif url in pages:
            url = pages[url]

        # Check if it's a relative URL
        if not url.startswith(('http://', 'https://')):
            base_url = self.config.get('base_url', '')
            if base_url:
                # Clean up URL construction
                base_url = base_url.rstrip('/')
                url = url.lstrip('/')
                url = f"{base_url}/{url}"

        logger.info(f"Navigating to: {url}")
        self.page.goto(url, wait_until='networkidle')
        self.page.wait_for_load_state('domcontentloaded')

        # Small wait for dynamic content
        time.sleep(self.wait_time / 1000)
        return {'url': self.page.url}

    def _handle_click(self, params: Dict) -> Any:
        """Handle click actions using multiple strategies"""
        element_desc = params.get('element', '')

        # Fix potential missing closing quote
        if element_desc.count('"') == 1 and element_desc.endswith('"') == False:
            element_desc += '"'

        logger.info(f"Attempting to click: {element_desc}")

        # Small wait to ensure dynamic content is loaded
        time.sleep(0.5)

        # Strategy 1: Try direct selector-based approaches first
        # This is faster and more reliable than AI detection

        # Extract potential text from quotes or use the full description
        import re

        # First, try to extract text between quotes
        # Handle both "text" and 'text' patterns
        search_texts = []

        # Pattern 1: Text within double quotes
        double_quote_match = re.search(r'"([^"]+)"', element_desc)
        if double_quote_match:
            search_texts.append(double_quote_match.group(1))

        # Pattern 2: Text within single quotes
        single_quote_match = re.search(r"'([^']+)'", element_desc)
        if single_quote_match:
            search_texts.append(single_quote_match.group(1))

        # Pattern 3: If no quotes found, try the whole text
        if not search_texts:
            # Remove common suffixes
            clean_text = element_desc.strip()
            for suffix in [' link', ' button', ' tab', ' menu', ' item']:
                if clean_text.lower().endswith(suffix):
                    clean_text = clean_text[:-len(suffix)].strip()
                    break
            search_texts.append(clean_text)

        # Also add the full original text as fallback
        if element_desc.strip() not in search_texts:
            search_texts.append(element_desc.strip())

        logger.info(f"Search texts to try: {search_texts}")

        # Try each potential text
        for search_text in search_texts:
            logger.info(f"Trying to find element with text: '{search_text}'")

            # Build a comprehensive list of selectors
            selectors = []

            # Most specific selectors first
            selectors.extend([
                # Exact text matches
                f'a:text-is("{search_text}")',
                f'button:text-is("{search_text}")',
                f'[role="button"]:text-is("{search_text}")',
                f'[role="link"]:text-is("{search_text}")',

                # Exact match for links (highest priority for link elements)
                f'a:has-text("{search_text}"):has-text("{search_text}")',  # Double check for exact match
                f'a[href*="{search_text}"]',  # Link with href containing the text

                # Common button patterns
                f'button:has-text("{search_text}")',
                f'input[type="button"][value*="{search_text}" i]',
                f'input[type="submit"][value*="{search_text}" i]',
                f'button[type="submit"]:has-text("{search_text}")',
                f'button[type="button"]:has-text("{search_text}")',

                # Links
                f'a:has-text("{search_text}")',
                f'a[href]:has-text("{search_text}")',
                f'a[title*="{search_text}" i]',

                # Links in table cells (important for data grids)
                f'td a:has-text("{search_text}")',
                f'th a:has-text("{search_text}")',
                f'.ant-table-cell a:has-text("{search_text}")',
                f'[role="gridcell"] a:has-text("{search_text}")',
                f'[role="cell"] a:has-text("{search_text}")',

                # Elements with click handlers
                f'[onclick]:has-text("{search_text}")',
                f'[ng-click]:has-text("{search_text}")',
                f'[data-click]:has-text("{search_text}")',
                f'[role="button"]:has-text("{search_text}")',
                f'[role="link"]:has-text("{search_text}")',
                f'[role="menuitem"]:has-text("{search_text}")',
                f'[role="tab"]:has-text("{search_text}")',

                # Table cells (clickable data)
                f'td:has-text("{search_text}")',
                f'th:has-text("{search_text}")',
                f'td a:has-text("{search_text}")',
                f'td button:has-text("{search_text}")',
                f'td:has-text("{search_text}") a',  # Link inside td with text
                f'tbody td:has-text("{search_text}")',  # Body cell with text

                # Common UI frameworks
                f'.btn:has-text("{search_text}")',  # Bootstrap
                f'.ant-btn:has-text("{search_text}")',  # Ant Design
                f'.MuiButton-root:has-text("{search_text}")',  # Material UI

                # Generic clickable classes
                f'.clickable:has-text("{search_text}")',
                f'.link:has-text("{search_text}")',
                f'[class*="click"]:has-text("{search_text}")',
                f'[class*="button"]:has-text("{search_text}")',

                # Structural elements that might be clickable
                f'li:has-text("{search_text}")',
                f'span:has-text("{search_text}")',
                f'div:has-text("{search_text}")',
                f'p:has-text("{search_text}")',

                # Generic visible element
                f'*:has-text("{search_text}"):visible'
            ])

            # If the text is long (might be truncated in UI), also try partial matches
            if len(search_text) > 15:
                # Try different partial lengths
                partials = [
                    search_text[:10],  # First 10 chars
                    search_text[:15],  # First 15 chars
                    search_text[:20] if len(search_text) > 20 else search_text,  # First 20 chars
                ]

                for partial in partials:
                    selectors.extend([
                        # Prioritize links in table cells for partial matches
                        f'td a:has-text("{partial}")',
                        f'.ant-table-cell a:has-text("{partial}")',
                        f'[role="gridcell"] a:has-text("{partial}")',
                        f'tbody a:has-text("{partial}")',

                        # Then general links
                        f'a:has-text("{partial}")',

                        # Then other elements
                        f'button:has-text("{partial}")',
                        f'td:has-text("{partial}")',
                        f'[onclick]:has-text("{partial}")',
                        f'*:has-text("{partial}"):visible'
                    ])

            # Try each selector
            for selector in selectors:
                try:
                    elements = self.page.locator(selector).all()

                    # Try each matching element
                    for element in elements:
                        if not element.is_visible():
                            continue

                        # For generic selectors, verify it's actually clickable
                        if selector.endswith(':visible') or 'div:' in selector or 'span:' in selector:
                            # Check if element has click-related attributes or is within a clickable parent
                            is_clickable = element.evaluate("""
                                (el) => {
                                    // Check if element itself is clickable
                                    if (el.onclick || el.href || el.type === 'button' || el.type === 'submit' ||
                                        el.tagName === 'A' || el.tagName === 'BUTTON' || 
                                        el.role === 'button' || el.role === 'link' ||
                                        el.style.cursor === 'pointer') {
                                        return true;
                                    }

                                    // Check if any parent (up to 3 levels) is clickable
                                    let parent = el.parentElement;
                                    let levels = 0;
                                    while (parent && levels < 3) {
                                        if (parent.onclick || parent.href || parent.tagName === 'A' || 
                                            parent.tagName === 'BUTTON' || parent.role === 'button' || 
                                            parent.role === 'link') {
                                            return true;
                                        }
                                        parent = parent.parentElement;
                                        levels++;
                                    }

                                    return false;
                                }
                            """)

                            if not is_clickable and ('div:' in selector or 'span:' in selector):
                                continue

                        # Ensure element is in viewport
                        element.scroll_into_view_if_needed()
                        time.sleep(0.3)

                        # Try to click
                        try:
                            element.click()
                            logger.info(f"Successfully clicked using selector: {selector}")

                            # Wait for any navigation or DOM changes
                            try:
                                self.page.wait_for_load_state('networkidle', timeout=3000)
                            except:
                                time.sleep(0.5)

                            return {'clicked': element_desc}
                        except Exception as click_error:
                            logger.debug(f"Click failed: {click_error}")
                            # Try force click
                            try:
                                element.click(force=True)
                                logger.info(f"Force clicked using selector: {selector}")
                                time.sleep(0.5)
                                return {'clicked': element_desc}
                            except:
                                continue

                except Exception as e:
                    logger.debug(f"Selector {selector} failed: {e}")
                    continue

        # Strategy 2: Use coordinate-based clicking for visible text
        try:
            for search_text in search_texts:
                text_elements = self.page.locator(f'text="{search_text}"').all()
                for text_element in text_elements:
                    if text_element.is_visible():
                        box = text_element.bounding_box()
                        if box:
                            self.page.mouse.click(box['x'] + box['width'] / 2, box['y'] + box['height'] / 2)
                            logger.info(f"Clicked using coordinates for text: {search_text}")
                            time.sleep(0.5)
                            return {'clicked': element_desc}
        except Exception as e:
            logger.debug(f"Coordinate click failed: {e}")

        # Strategy 3: Use AI detection as last resort
        logger.info("Falling back to AI detection")

        # Debug: Log all links found on the page
        try:
            all_links = self.page.locator('a:visible').all()
            logger.debug(f"Found {len(all_links)} visible links on page")
            for i, link in enumerate(all_links[:10]):  # Log first 10 links
                link_text = link.text_content()
                link_href = link.get_attribute('href')
                logger.debug(f"Link {i}: text='{link_text}', href='{link_href}'")

            # Also check table cells in first column
            first_col_cells = self.page.locator('td:first-child:visible').all()
            logger.debug(f"Found {len(first_col_cells)} first column cells")
            for i, cell in enumerate(first_col_cells[:5]):
                cell_text = cell.text_content()
                logger.debug(f"First column cell {i}: '{cell_text}'")
        except Exception as e:
            logger.debug(f"Debug logging failed: {e}")

        screenshot = self.page.screenshot()
        element_info = self.ai_finder.find_element(self.page, element_desc, screenshot)

        if element_info:
            if element_info.get('selector'):
                element = self.page.locator(element_info['selector'])
                element.wait_for(state='visible', timeout=self.timeout)
                element.scroll_into_view_if_needed()
                element.click()
            else:
                self.ai_finder.click_at_position(self.page, element_info['position'])

            try:
                # First wait for any immediate navigation
                self.page.wait_for_load_state('domcontentloaded', timeout=5000)
                # Then wait for network to settle
                self.page.wait_for_load_state('networkidle', timeout=10000)
                # Additional wait for dynamic content
                time.sleep(1)
            except:
                time.sleep(1)

            return {'clicked': element_desc}

        raise Exception(f"Element not found: {element_desc}")

    def _handle_input(self, params: Dict) -> Any:
        """Handle input/type actions"""
        element_desc = params.get('element', '')
        value = params.get('value', '')
        force_ai = params.get('force_ai', False)

        logger.info(f"Attempting to input into: {element_desc}")
        logger.info(f"Attempting to input into: {element_desc} (force_ai: {force_ai})")

        # First, wait a bit to ensure any dynamic fields have appeared
        self._wait_for_dynamic_elements(0.5)

        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                if force_ai:
                    logger.info(f"Force AI detection enabled for field: {element_desc}")
                    # Take screenshot for AI detection
                    screenshot = self.page.screenshot()
                    element_info = self.ai_finder.find_element(self.page, element_desc, screenshot)

                    if element_info:
                        if element_info.get('selector'):
                            element = self.page.locator(element_info['selector'])
                            element.wait_for(state='visible', timeout=self.timeout)

                            # Use your existing element handling logic
                            tag_name = element.evaluate("el => el.tagName.toLowerCase()")

                            if tag_name in ['input', 'textarea']:
                                element.clear()
                                element.fill(value)
                            else:
                                element.click()
                                time.sleep(0.1)
                                self.page.keyboard.press('Control+a' if os.name != 'darwin' else 'Meta+a')
                                self.page.keyboard.type(value)

                            return {'typed': value, 'element': element_desc}
                        else:
                            # Position-based clicking
                            self.ai_finder.click_at_position(self.page, element_info['position'])
                            time.sleep(0.1)
                            self.page.keyboard.type(value)
                            return {'typed': value, 'element': element_desc}
                    else:
                        raise Exception(f"AI detection failed to find element: {element_desc}")

                # Only treat as rich text if explicitly mentioned
                explicit_rich_text_keywords = ['rich text', 'wysiwyg', 'html editor', 'text editor', 'editor']
                is_likely_rich_text = any(keyword in element_desc.lower() for keyword in explicit_rich_text_keywords)

                if is_likely_rich_text:
                    logger.info(f"Field '{element_desc}' is likely a rich text editor based on keywords")

                # First, let's try to find the element by looking for labels
                # This helps with rich text editors that are associated with labels
                label_selectors = [
                    # Direct sibling selectors (most specific)
                    f'label:has-text("{element_desc}") + div [contenteditable="true"]',
                    f'label:has-text("{element_desc}") + div .ql-editor',

                    # Next sibling with some elements in between
                    f'label:has-text("{element_desc}") ~ div [contenteditable="true"]:first',
                    f'label:has-text("{element_desc}") ~ div .ql-editor:first',

                    # Parent-based but more specific - look for the closest parent with the label
                    f'div:has(> label:has-text("{element_desc}")) > div [contenteditable="true"]',
                    f'div:has(> label:has-text("{element_desc}")) > div .ql-editor',

                    # XPath-based for more precise traversal
                    f'label:has-text("{element_desc}") >> xpath=following-sibling::div[1] >> [contenteditable="true"]',
                    f'label:has-text("{element_desc}") >> xpath=following-sibling::div[1] >> .ql-editor',

                    # For Ant Design form items specifically
                    f'.ant-form-item:has(label:has-text("{element_desc}")) > .ant-form-item-control [contenteditable="true"]',
                    f'.ant-form-item:has(label:has-text("{element_desc}")) > .ant-form-item-control .ql-editor',

                    # More flexible patterns
                    f'.ant-form-item:has(label:text-is("{element_desc}")) [contenteditable="true"]',
                    f'.ant-form-item:has(label:text-is("{element_desc}")) .ql-editor',

                    # Dynamic field patterns - fields that appear after radio/checkbox selection
                    f'*[style*="display: block"] label:has-text("{element_desc}") + input',
                    f'*[style*="display: block"] label:has-text("{element_desc}") ~ input',
                    f'*:not([style*="display: none"]) label:has-text("{element_desc}") + input',
                    f'*:not([hidden]) label:has-text("{element_desc}") + input',

                    # Fields in conditionally shown containers
                    f'.show label:has-text("{element_desc}") + input',
                    f'.active label:has-text("{element_desc}") + input',
                    f'[class*="visible"] label:has-text("{element_desc}") + input',
                    f'[class*="expanded"] label:has-text("{element_desc}") + input',

                    # For number inputs specifically (quota limits are often numbers)
                    f'label:has-text("{element_desc}") + input[type="number"]',
                    f'label:has-text("{element_desc}") ~ input[type="number"]',
                    f'input[type="number"][aria-label*="{element_desc}" i]',

                    # Nested in form groups that may be dynamically shown
                    f'.form-group:not([style*="display: none"]) label:has-text("{element_desc}") + input',
                    f'[class*="form-field"]:not([style*="display: none"]) label:has-text("{element_desc}") + input',
                ]

                # Try label-based selectors first for rich text editors
                rich_text_found = False
                for selector in label_selectors:
                    try:
                        elements = self.page.locator(selector).all()
                        logger.debug(f"Trying selector '{selector}' - found {len(elements)} elements")
                        for element in elements:
                            if element.is_visible():
                                logger.info(f"Found rich text editor using selector: {selector}")
                                # Handle rich text editor input
                                return self._input_to_rich_text_editor(element, value, element_desc)
                    except Exception as e:
                        logger.debug(f"Label selector {selector} failed: {e}")
                        continue

                # Alternative approach: Find the label first, then look for the nearest editor
                try:
                    # Find the specific label
                    labels = self.page.locator(f'label').all()
                    logger.debug(f"Found {len(labels)} labels on page")

                    for label in labels:
                        label_text = label.text_content().strip()
                        # Check if this label matches our target (case-insensitive, trim spaces)
                        if element_desc.lower() in label_text.lower() or label_text.lower() in element_desc.lower():
                            logger.debug(f"Found matching label with text: '{label_text}'")

                        # Try multiple strategies to find the associated editor
                        # Strategy 1: Look in the next sibling div
                        try:
                            next_div = label.locator('xpath=following-sibling::div[1]').first
                            if next_div.count() > 0:
                                # Check for textarea first
                                textarea = next_div.locator('textarea').first
                                if textarea.count() > 0 and textarea.is_visible():
                                    logger.info("Found textarea in next sibling div")
                                    textarea.click()
                                    textarea.clear()
                                    textarea.fill(value)
                                    return {'typed': value, 'element': element_desc}

                                # Then check for contenteditable
                                editor = next_div.locator('[contenteditable="true"], .ql-editor').first
                                if editor.count() > 0 and editor.is_visible():
                                    logger.info("Found rich text editor in next sibling div")
                                    return self._input_to_rich_text_editor(editor, value, element_desc)
                        except:
                            pass

                        # Strategy 2: Look in parent's descendants
                        try:
                            parent = label.locator('xpath=..').first
                            if parent.count() > 0:
                                # Check for textarea first
                                textarea = parent.locator('textarea').first
                                if textarea.count() > 0 and textarea.is_visible():
                                    logger.info("Found textarea in parent container")
                                    textarea.click()
                                    textarea.clear()
                                    textarea.fill(value)
                                    return {'typed': value, 'element': element_desc}

                                editor = parent.locator('[contenteditable="true"], .ql-editor').first
                                if editor.count() > 0 and editor.is_visible():
                                    logger.info("Found rich text editor in parent container")
                                    return self._input_to_rich_text_editor(editor, value, element_desc)
                        except:
                            pass

                        # Strategy 3: Look for form item container
                        try:
                            form_item = label.locator(
                                'xpath=ancestor::*[contains(@class, "form-item") or contains(@class, "form-group") or contains(@class, "field")][1]').first
                            if form_item.count() > 0:
                                # Check for textarea first
                                textarea = form_item.locator('textarea').first
                                if textarea.count() > 0 and textarea.is_visible():
                                    logger.info("Found textarea in form item container")
                                    textarea.click()
                                    textarea.clear()
                                    textarea.fill(value)
                                    return {'typed': value, 'element': element_desc}

                                editor = form_item.locator('[contenteditable="true"], .ql-editor').first
                                if editor.count() > 0 and editor.is_visible():
                                    logger.info("Found rich text editor in form item container")
                                    return self._input_to_rich_text_editor(editor, value, element_desc)
                        except:
                            pass

                except Exception as e:
                    logger.debug(f"Alternative label-based approach failed: {e}")

                # If no rich text editor found via label selectors, use AI detection
                # Take screenshot for AI detection
                screenshot = self.page.screenshot()

                # Try additional generic selectors for various input types
                generic_input_selectors = [
                    # Try to find textarea by partial text match in nearby elements
                    f'textarea:near(:text("{element_desc}"))',
                    # Try placeholder match for textareas
                    f'textarea[placeholder*="{element_desc}" i]',
                    # Try aria-label for textareas
                    f'textarea[aria-label*="{element_desc}" i]',
                    # Look for any textarea in a form group that contains the text
                    f'*:has-text("{element_desc}") >> xpath=ancestor-or-self::*[contains(@class, "form") or contains(@class, "field") or contains(@class, "group")][1] >> textarea',
                ]

                for selector in generic_input_selectors:
                    try:
                        elements = self.page.locator(selector).all()
                        logger.debug(f"Trying generic selector '{selector}' - found {len(elements)} elements")
                        for element in elements:
                            if element.is_visible():
                                logger.info(f"Found element using generic selector: {selector}")
                                element.click()
                                element.clear()
                                element.fill(value)
                                return {'typed': value, 'element': element_desc}
                    except Exception as e:
                        logger.debug(f"Generic selector {selector} failed: {e}")
                        continue

                # Find element using AI
                element_info = self.ai_finder.find_element(self.page, element_desc, screenshot)

                if element_info:
                    if element_info.get('selector'):
                        element = self.page.locator(element_info['selector'])
                        element.wait_for(state='visible', timeout=self.timeout)

                        # Check element type to determine the input strategy
                        tag_name = element.evaluate("el => el.tagName.toLowerCase()")
                        is_contenteditable = element.evaluate(
                            "el => el.contentEditable === 'true' || el.contentEditable === 'plaintext-only'")

                        # Check for rich text editor patterns
                        is_rich_text_editor = element.evaluate("""
                                    (el) => {
                                        // Check for common rich text editor patterns
                                        const classNames = el.className || '';
                                        const id = el.id || '';
                                        const role = el.getAttribute('role') || '';

                                        // Check parent elements for editor containers
                                        let currentEl = el;
                                        let levelsUp = 0;
                                        while (currentEl && levelsUp < 3) {
                                            const currentClass = currentEl.className || '';
                                            const currentRole = currentEl.getAttribute('role') || '';

                                            // Common rich text editor indicators
                                            const editorPatterns = [
                                                'ql-editor', // Quill
                                                'ql-container', // Quill container
                                                'tox-edit-area', // TinyMCE
                                                'ck-editor', // CKEditor
                                                'ck-content', // CKEditor 5
                                                'froala-editor', // Froala
                                                'ProseMirror', // ProseMirror
                                                'editor-content', // Generic
                                                'rich-text', // Generic
                                                'wysiwyg', // Generic
                                                'text-editor', // Generic
                                                'ant-form-item-control-input-content' // Ant Design form item
                                            ];

                                            if (editorPatterns.some(pattern => 
                                                currentClass.includes(pattern) || 
                                                currentRole.includes('textbox')
                                            )) {
                                                return true;
                                            }

                                            currentEl = currentEl.parentElement;
                                            levelsUp++;
                                        }

                                        return false;
                                    }
                                """)

                        logger.debug(
                            f"Element analysis - tag: {tag_name}, contenteditable: {is_contenteditable}, rich_text: {is_rich_text_editor}")

                        # Handle based on element type
                        if tag_name in ['input', 'textarea'] and not is_contenteditable:
                            # Double-check: if this is likely a rich text field but we found a standard input,
                            # look harder for a rich text editor nearby
                            if is_likely_rich_text:
                                logger.warning(
                                    f"Found standard input for '{element_desc}' but expected rich text editor")

                                # Try to find rich text editor near this input
                                try:
                                    # Look for rich text editor in the same form item
                                    parent_form_item = element.locator(
                                        'xpath=ancestor::*[contains(@class, "ant-form-item")][1]').first
                                    if parent_form_item.count() > 0:
                                        rich_editor = parent_form_item.locator(
                                            '[contenteditable="true"], .ql-editor').first
                                        if rich_editor.count() > 0 and rich_editor.is_visible():
                                            logger.info("Found rich text editor in same form item, using that instead")
                                            return self._input_to_rich_text_editor(rich_editor, value, element_desc)
                                except:
                                    pass

                            # Standard input/textarea - use the existing logic
                            try:
                                element.clear()
                                element.fill(value)
                                logger.info(f"Filled standard {tag_name} with value")
                            except Exception as e:
                                logger.warning(f"Standard fill failed: {e}, trying alternative methods")
                                # Fallback: click and type
                                element.click()
                                time.sleep(0.1)
                                self.page.keyboard.press('Control+a' if os.name != 'darwin' else 'Meta+a')
                                self.page.keyboard.type(value)

                        elif is_contenteditable or is_rich_text_editor or tag_name == 'div':
                            # Handle contenteditable or rich text editor
                            return self._input_to_rich_text_editor(element, value, element_desc)

                        else:
                            # Unknown element type - try to find nested input
                            logger.info(f"Unknown element type: {tag_name}, searching for nested input elements")

                            # Look for actual input elements nearby
                            input_found = False

                            # First, check if this is a label or container
                            input_selectors = [
                                'input[type="text"]',
                                'input:not([type="hidden"])',
                                'textarea',
                                '[contenteditable="true"]',
                                '[role="textbox"]'
                            ]

                            # Try to find input as a child
                            for selector in input_selectors:
                                try:
                                    child_input = element.locator(selector).first
                                    if child_input.count() > 0:
                                        child_input.wait_for(state='visible')

                                        # Recursively handle the found input
                                        child_tag = child_input.evaluate("el => el.tagName.toLowerCase()")
                                        if child_tag in ['input', 'textarea']:
                                            child_input.clear()
                                            child_input.fill(value)
                                        else:
                                            child_input.click()
                                            time.sleep(0.1)
                                            self.page.keyboard.press('Control+a' if os.name != 'darwin' else 'Meta+a')
                                            self.page.keyboard.type(value)

                                        input_found = True
                                        logger.info(f"Found and filled nested {selector}")
                                        break
                                except:
                                    continue

                            # If no child input found, try siblings or nearby elements
                            if not input_found:
                                try:
                                    # Look for associated input using label
                                    parent = element.locator('..')
                                    for selector in input_selectors:
                                        sibling_input = parent.locator(selector).first
                                        if sibling_input.count() > 0:
                                            sibling_input.wait_for(state='visible')
                                            sibling_tag = sibling_input.evaluate("el => el.tagName.toLowerCase()")

                                            if sibling_tag in ['input', 'textarea']:
                                                sibling_input.clear()
                                                sibling_input.fill(value)
                                            else:
                                                sibling_input.click()
                                                time.sleep(0.1)
                                                self.page.keyboard.press(
                                                    'Control+a' if os.name != 'darwin' else 'Meta+a')
                                                self.page.keyboard.type(value)

                                            input_found = True
                                            logger.info(f"Found and filled sibling {selector}")
                                            break
                                except:
                                    pass

                            # Last resort: click the element and type
                            if not input_found:
                                logger.warning("No input element found, clicking and typing directly")
                                element.click()
                                time.sleep(0.2)
                                self.page.keyboard.press('Control+a' if os.name != 'darwin' else 'Meta+a')
                                self.page.keyboard.press('Delete')
                                self.page.keyboard.type(value)

                        return {'typed': value, 'element': element_desc}
                    else:
                        # Position-based clicking (existing logic)
                        self.ai_finder.click_at_position(self.page, element_info['position'])
                        time.sleep(0.1)
                        self.page.keyboard.type(value)
                        return {'typed': value, 'element': element_desc}
                else:
                    raise Exception(f"Input element not found: {element_desc}")

                return {'typed': value, 'element': element_desc}

            except Exception as e:
                if attempt < max_attempts - 1:
                    logger.debug(f"Input attempt {attempt + 1} failed, waiting for dynamic elements...")
                    self._wait_for_dynamic_elements(1.0)
                else:
                    # Final attempt failed
                    raise Exception(f"Input element not found after {max_attempts} attempts: {element_desc}")

    def _input_to_rich_text_editor(self, element, value: str, element_desc: str) -> Dict:
        """Handle input to rich text editor (Quill, TinyMCE, etc.)"""
        logger.info("Detected rich text editor or contenteditable element")

        # First, try to find the actual editable area if this is a container
        editable_element = None

        # Look for common editable child elements
        editable_selectors = [
            '[contenteditable="true"]',
            '.ql-editor',  # Quill
            '.ck-content',  # CKEditor 5
            '.tox-edit-area__iframe',  # TinyMCE (iframe)
            '[role="textbox"]',
            '.editor-content',
            '.ProseMirror'
        ]

        for selector in editable_selectors:
            try:
                child = element.locator(selector).first
                if child.count() > 0 and child.is_visible():
                    editable_element = child
                    logger.debug(f"Found editable child with selector: {selector}")
                    break
            except:
                continue

        # Use the found editable element or the original element
        target_element = editable_element if editable_element else element

        # Click to focus
        target_element.click()
        time.sleep(0.2)

        # Clear existing content
        try:
            # Method 1: Triple-click to select all and delete
            target_element.click(click_count=3)
            time.sleep(0.1)
            self.page.keyboard.press('Delete')
            logger.debug("Cleared content using triple-click")
        except:
            try:
                # Method 2: Ctrl/Cmd+A and Delete
                target_element.click()
                self.page.keyboard.press('Control+a' if os.name != 'darwin' else 'Meta+a')
                time.sleep(0.1)
                self.page.keyboard.press('Delete')
                logger.debug("Cleared content using Ctrl+A")
            except:
                logger.warning("Could not clear existing content")

        # Type the new content
        time.sleep(0.1)
        self.page.keyboard.type(value)
        logger.info("Typed content into rich text editor")

        # For some editors, we might need to click outside to "save" the content
        # This is optional and depends on the editor
        time.sleep(0.1)

        return {'typed': value, 'element': element_desc}

    def _find_trigger_element(self, description: str):
        """Find the trigger element that opens a dropdown menu"""
        # Common patterns for dropdown triggers
        trigger_selectors = [
            # Button with aria-expanded
            f'button[aria-expanded]:has-text("{description}")',
            f'button[aria-haspopup]:has-text("{description}")',
            # Generic button
            f'button:has-text("{description}")',
            # Link that might trigger dropdown
            f'a:has-text("{description}")',
            # Div with role button
            f'[role="button"]:has-text("{description}")',
            # Any clickable element
            f'[onclick]:has-text("{description}")',
            # Generic text search
            f'*:has-text("{description}"):visible'
        ]

        for selector in trigger_selectors:
            try:
                elements = self.page.locator(selector).all()
                for elem in elements:
                    if elem.is_visible():
                        return elem
            except:
                continue

        # Use AI finder as fallback
        element_info = self.ai_finder.find_element(self.page, description, self.page.screenshot())
        if element_info and element_info.get('selector'):
            try:
                element = self.page.locator(element_info['selector']).first
                if element.is_visible():
                    return element
            except:
                pass

        return None

    def _handle_select(self, params: Dict) -> Any:
        """Handle dropdown/select actions - supports multiple UI frameworks"""
        element_desc = params.get('element', '')
        option = params.get('option', '')

        dropdown_menu = None
        try:
            # Check for various dropdown menu patterns
            dropdown_selectors = [
                '.ant-dropdown:not(.ant-dropdown-hidden) .ant-dropdown-menu',
                '.ant-dropdown-menu:visible',
                '[role="menu"]:visible',
                '.dropdown-menu:visible',
                '.menu:visible',
                '[class*="menu"]:visible'
            ]

            for selector in dropdown_selectors:
                elements = self.page.locator(selector).all()
                for elem in elements:
                    if elem.is_visible():
                        dropdown_menu = elem
                        logger.info(f"Found open dropdown menu with selector: {selector}")
                        break
                if dropdown_menu:
                    break

            if dropdown_menu:
                # Look for the option in the open menu
                option_selectors = [
                    f'[role="menuitem"]:has-text("{option}")',
                    f'li[role="menuitem"]:has-text("{option}")',
                    f'.ant-dropdown-menu-item:has-text("{option}")',
                    f'li:has-text("{option}")',
                    f'a:has-text("{option}")',
                    f'[class*="menu-item"]:has-text("{option}")',
                    f'[class*="item"]:has-text("{option}")'
                ]

                for selector in option_selectors:
                    try:
                        option_elements = dropdown_menu.locator(selector).all()
                        for opt_elem in option_elements:
                            if opt_elem.is_visible():
                                opt_elem.click()
                                logger.info(f"Selected '{option}' from open dropdown menu")
                                time.sleep(0.5)
                                return {'selected': option, 'element': element_desc}
                    except:
                        continue

        except Exception as e:
            logger.debug(f"No open dropdown menu found: {e}")

        # If no open menu, we need to find and click the trigger element first
        # Use the element description to find the trigger
        logger.info(f"No open dropdown found, looking for trigger element: {element_desc}")

        # Take screenshot for AI detection
        screenshot = self.page.screenshot()

        # Find trigger element using AI or pattern matching
        if element_desc and element_desc.lower() not in ['dropdown', 'menu', 'select']:
            # Use the element description to find the trigger
            trigger_element = self._find_trigger_element(element_desc)

            if trigger_element:
                # Click the trigger to open dropdown
                trigger_element.click()
                logger.info(f"Clicked trigger element: {element_desc}")
                time.sleep(0.5)  # Wait for dropdown animation

                # Now look for the dropdown menu again
                for selector in dropdown_selectors:
                    elements = self.page.locator(selector).all()
                    for elem in elements:
                        if elem.is_visible():
                            dropdown_menu = elem
                            break
                    if dropdown_menu:
                        break

                if dropdown_menu:
                    # Try to select the option
                    for selector in option_selectors:
                        try:
                            option_elements = dropdown_menu.locator(selector).all()
                            for opt_elem in option_elements:
                                if opt_elem.is_visible():
                                    opt_elem.click()
                                    logger.info(f"Selected '{option}' after opening dropdown")
                                    return {'selected': option, 'element': element_desc}
                        except:
                            continue

        # If still no success, try finding any clickable element with the option text
        logger.info(f"Attempting to find option '{option}' anywhere on page")
        generic_option_selectors = [
            f'[role="menuitem"]:has-text("{option}"):visible',
            f'li:has-text("{option}"):visible',
            f'a:has-text("{option}"):visible',
            f'button:has-text("{option}"):visible',
            f'[class*="item"]:has-text("{option}"):visible',
            f'*:has-text("{option}"):visible'
        ]

        for selector in generic_option_selectors:
            try:
                elements = self.page.locator(selector).all()
                for elem in elements:
                    if elem.is_visible() and elem.is_enabled():
                        # Check if it's in a dropdown/menu context
                        parent_menu = elem.locator(
                            'xpath=ancestor::*[contains(@class, "dropdown") or contains(@class, "menu") or @role="menu"]').first
                        if parent_menu.count() > 0:
                            elem.click()
                            logger.info(f"Selected option '{option}' using selector: {selector}")
                            return {'selected': option, 'element': element_desc}
            except:
                continue

        # Ensure we're in the right frame
        context = self._get_current_context()

        # Take screenshot for AI detection
        screenshot = self.page.screenshot()

        # Find element using AI
        element_info = self.ai_finder.find_element(self.page, element_desc, screenshot)

        if element_info:
            if element_info.get('selector'):
                # Try to find in all frames
                element, frame = self._find_element_in_frames(element_info['selector'])

                if not element:
                    # Fallback to AI selector in current context
                    element = context.locator(element_info['selector'])
                    if element.count() == 0 or not element.first.is_visible():
                        raise Exception(f"Select element not found: {element_desc}")
                    element = element.first

                # Wait for element to be ready
                element.wait_for(state='visible', timeout=self.timeout)

                # Check element type and attributes to determine strategy
                tag_name = element.evaluate("el => el.tagName.toLowerCase()")
                class_name = element.get_attribute('class') or ''
                role = element.get_attribute('role') or ''

                # Log element details for debugging
                logger.debug(f"Found select element: tag={tag_name}, class={class_name}, role={role}")

                # Try different dropdown strategies based on detected type
                strategies = []

                # 1. Native HTML select
                if tag_name == 'select':
                    strategies.append(self._select_native_option)

                # 2. Ant Design
                if 'ant-select' in class_name or (tag_name == 'input' and role == 'combobox'):
                    strategies.append(self._select_ant_design_option)

                # 3. Material UI
                if 'MuiSelect' in class_name or 'MuiInputBase' in class_name:
                    strategies.append(self._select_material_ui_option)

                # 4. Bootstrap
                if 'custom-select' in class_name or 'form-select' in class_name or 'dropdown' in class_name:
                    strategies.append(self._select_bootstrap_option)

                # 5. React Select
                if 'react-select' in class_name:
                    strategies.append(self._select_react_select_option)

                # 6. Generic ARIA-based
                if role in ['combobox', 'listbox', 'button']:
                    strategies.append(self._select_aria_option)

                # 7. Always add generic fallback
                strategies.append(self._select_generic_option)

                # Try each strategy
                for strategy in strategies:
                    try:
                        result = strategy(element, option)
                        if result:
                            return {'selected': option, 'element': element_desc}
                    except Exception as e:
                        logger.debug(f"Strategy {strategy.__name__} failed: {e}")
                        continue

                # If all strategies fail, raise exception
                raise Exception(f"Could not select option '{option}' in dropdown '{element_desc}'")

            else:
                # Fallback to position-based clicking
                self.ai_finder.click_at_position(self.page, element_info['position'])
                time.sleep(0.5)

                # Look for option in all possible contexts
                option_found = False

                # Try current frame first
                if self.current_frame:
                    try:
                        option_element = self.current_frame.get_by_text(option).first
                        if option_element.is_visible():
                            option_element.click()
                            option_found = True
                    except:
                        pass

                # Try main page
                if not option_found:
                    try:
                        option_element = self.page.get_by_text(option).first
                        if option_element.is_visible():
                            option_element.click()
                            option_found = True
                    except:
                        pass

                if option_found:
                    return {'selected': option, 'element': element_desc}
                else:
                    raise Exception(f"Could not find option '{option}'")
        else:
            raise Exception(f"Select element not found: {element_desc}")

    def _select_native_option(self, element, option: str) -> bool:
        """Handle native HTML select elements"""
        try:
            element.select_option(label=option)
            return True
        except:
            try:
                element.select_option(value=option)
                return True
            except:
                element.select_option(option)
                return True

    def _select_ant_design_option(self, element, option: str) -> bool:
        """Handle Ant Design select components"""
        # Find the clickable parent if we have the input
        if element.evaluate("el => el.tagName.toLowerCase()") == 'input':
            # Try to find parent in the same frame context
            frame_context = self.current_frame if self.current_frame else self.page
            parent = frame_context.locator('.ant-select').filter(has=element)
            if parent.count() > 0:
                parent.first.click()
            else:
                element.click()
        else:
            element.click()

        time.sleep(0.5)  # Slightly longer wait for dropdown animation

        # Look for options in Ant Design dropdown
        # Ant dropdowns often render at the document root level
        option_selectors = [
            f'.ant-select-dropdown:visible .ant-select-item[title="{option}"]',
            f'.ant-select-dropdown:visible .ant-select-item-option[title="{option}"]',
            f'.ant-select-dropdown:visible .ant-select-item:has-text("{option}")',
            f'.ant-select-dropdown:visible [class*="ant-select-item"]:has-text("{option}")',
            f'.ant-dropdown:visible .ant-dropdown-menu-item:has-text("{option}")',
            f'[class*="dropdown"]:visible [class*="item"]:has-text("{option}")'
        ]

        # Try both main page and current frame for dropdown options
        contexts = [self.page]
        if self.current_frame:
            contexts.append(self.current_frame)

        for context in contexts:
            for selector in option_selectors:
                try:
                    elements = context.locator(selector).all()
                    for opt in elements:
                        if opt.is_visible():
                            opt.click()
                            logger.debug(f"Selected option '{option}' using selector: {selector}")
                            return True
                except:
                    continue

        # Try a more generic approach for Ant Design
        try:
            # Wait a bit for dropdown to fully render
            time.sleep(0.3)

            # Try to find by text in dropdown container
            dropdown_containers = [
                '.ant-select-dropdown',
                '.ant-dropdown',
                '[class*="dropdown"][class*="ant"]',
                'div[class*="menu"][style*="position"]'
            ]

            for container in dropdown_containers:
                for context in contexts:
                    try:
                        container_element = context.locator(container).first
                        if container_element.is_visible():
                            option_element = container_element.locator(f'text="{option}"').first
                            if option_element.is_visible():
                                option_element.click()
                                return True
                    except:
                        continue
        except:
            pass

        return False

    def _select_material_ui_option(self, element, option: str) -> bool:
        """Handle Material UI select components"""
        element.click()
        time.sleep(0.3)

        option_selectors = [
            f'[role="listbox"] [role="option"]:has-text("{option}")',
            f'.MuiMenu-paper [role="option"]:has-text("{option}")',
            f'.MuiList-root [role="option"]:has-text("{option}")'
        ]

        for selector in option_selectors:
            try:
                opt = self.page.locator(selector).first
                if opt.is_visible():
                    opt.click()
                    return True
            except:
                continue

        return False

    def _select_bootstrap_option(self, element, option: str) -> bool:
        """Handle Bootstrap dropdowns"""
        element.click()
        time.sleep(0.3)

        option_selectors = [
            f'.dropdown-menu.show .dropdown-item:has-text("{option}")',
            f'.dropdown-menu.show a:has-text("{option}")',
            f'.dropdown-menu.show li:has-text("{option}")'
        ]

        for selector in option_selectors:
            try:
                opt = self.page.locator(selector).first
                if opt.is_visible():
                    opt.click()
                    return True
            except:
                continue

        return False

    def _select_react_select_option(self, element, option: str) -> bool:
        """Handle React Select components"""
        element.click()
        time.sleep(0.3)

        # Try typing in React Select
        try:
            input_element = element.locator('input[type="text"]').first
            input_element.fill(option)
            time.sleep(0.3)
            self.page.keyboard.press('Enter')
            return True
        except:
            # Try clicking option
            option_selectors = [
                f'.react-select__menu .react-select__option:has-text("{option}")',
                f'.Select__menu .Select__option:has-text("{option}")'
            ]

            for selector in option_selectors:
                try:
                    opt = self.page.locator(selector).first
                    if opt.is_visible():
                        opt.click()
                        return True
                except:
                    continue

        return False

    def _select_aria_option(self, element, option: str) -> bool:
        """Handle ARIA-compliant dropdowns"""
        element.click()
        time.sleep(0.3)

        option_selectors = [
            f'[role="listbox"] [role="option"]:has-text("{option}")',
            f'[role="option"]:has-text("{option}")',
            f'[aria-selected="true"]:has-text("{option}")'
        ]

        for selector in option_selectors:
            try:
                opt = self.page.locator(selector).first
                if opt.is_visible():
                    opt.click()
                    return True
            except:
                continue

        return False

    def _select_generic_option(self, element, option: str) -> bool:
        """Generic fallback for any dropdown type"""
        # Click to open
        element.click()
        time.sleep(0.5)

        # Try various generic patterns
        option_selectors = [
            f'text="{option}"',
            f'*:has-text("{option}"):visible',
            f'li:has-text("{option}"):visible',
            f'a:has-text("{option}"):visible',
            f'div:has-text("{option}"):visible',
            f'span:has-text("{option}"):visible',
            f'[data-value="{option}"]',
            f'[value="{option}"]'
        ]

        for selector in option_selectors:
            try:
                # Get all matching elements and click the visible one
                elements = self.page.locator(selector).all()
                for elem in elements:
                    if elem.is_visible() and elem.is_enabled():
                        elem.click()
                        return True
            except:
                continue

        # Last resort - try typing
        try:
            element.fill(option)
            time.sleep(0.3)
            self.page.keyboard.press('Enter')
            return True
        except:
            pass

        return False

    def _handle_checkbox(self, params: Dict) -> Any:
        """Handle checkbox actions with enhanced patterns"""
        element_desc = params.get('element', '')
        state = params.get('state', 'checked')

        logger.info(
            f"Attempting to {'check' if state.lower() in ['checked', 'true', 'yes'] else 'uncheck'} checkbox: {element_desc}")

        # Small wait to ensure dynamic content is loaded
        time.sleep(0.5)

        # Determine if we should check or uncheck
        should_check = state.lower() in ['checked', 'true', 'yes']

        # Build comprehensive list of selectors for checkboxes
        selectors = []

        # Most specific selectors first
        selectors.extend([
            # Direct checkbox with label text
            f'label:has-text("{element_desc}") input[type="checkbox"]',
            f'label:has-text("{element_desc}") >> input[type="checkbox"]',

            # Checkbox within label
            f'label:has(input[type="checkbox"]):has-text("{element_desc}")',

            # Checkbox with aria-label
            f'input[type="checkbox"][aria-label*="{element_desc}" i]',

            # Checkbox with value matching text
            f'input[type="checkbox"][value*="{element_desc}" i]',

            # Label with for attribute pointing to checkbox
            f'label[for]:has-text("{element_desc}")',

            # Checkbox near text
            f'input[type="checkbox"]:near(:text("{element_desc}"))',

            # Common wrapper patterns
            f'.checkbox:has-text("{element_desc}") input[type="checkbox"]',
            f'[class*="checkbox"]:has-text("{element_desc}") input[type="checkbox"]',
            f'div:has-text("{element_desc}") input[type="checkbox"]',

            # Ant Design patterns
            f'.ant-checkbox-wrapper:has-text("{element_desc}") input[type="checkbox"]',
            f'.ant-checkbox-wrapper:has-text("{element_desc}") .ant-checkbox-input',

            # Material UI patterns
            f'.MuiCheckbox-root:near(:text("{element_desc}"))',
            f'.MuiFormControlLabel-root:has-text("{element_desc}") input[type="checkbox"]',

            # Bootstrap patterns
            f'.form-check:has-text("{element_desc}") input[type="checkbox"]',
            f'.custom-control:has-text("{element_desc}") input[type="checkbox"]',

            # Parent-child patterns
            f':has(> :text("{element_desc}")) > input[type="checkbox"]',
            f':has(> :text("{element_desc}")) input[type="checkbox"]',

            # Structural patterns for various layouts
            f'div:has(> label:has-text("{element_desc}")) input[type="checkbox"]',
            f'div:has(span:has-text("{element_desc}")) input[type="checkbox"]',

            # Table cell patterns (for checkboxes in tables)
            f'td:has-text("{element_desc}") input[type="checkbox"]',
            f'tr:has-text("{element_desc}") input[type="checkbox"]',
        ])

        # Try each selector
        for selector in selectors:
            try:
                elements = self.page.locator(selector).all()

                for element in elements:
                    if not element.is_visible():
                        continue

                    # Ensure element is in viewport
                    try:
                        element.scroll_into_view_if_needed()
                    except:
                        try:
                            element.evaluate("el => el.scrollIntoView({behavior: 'smooth', block: 'center'})")
                        except:
                            pass

                    time.sleep(0.3)

                    # Check current state
                    try:
                        is_checked = element.is_checked()
                    except:
                        # If is_checked() fails, try evaluating the checked property
                        try:
                            is_checked = element.evaluate("el => el.checked")
                        except:
                            is_checked = False

                    # Only click if state needs to change
                    if is_checked != should_check:
                        try:
                            # Try standard check/uncheck first
                            if should_check:
                                element.check()
                            else:
                                element.uncheck()
                        except:
                            # Fallback to click
                            element.click()

                        logger.info(
                            f"Successfully {'checked' if should_check else 'unchecked'} checkbox: {element_desc}")
                    else:
                        logger.info(f"Checkbox '{element_desc}' is already {'checked' if is_checked else 'unchecked'}")

                    time.sleep(0.5)
                    return {'checkbox': element_desc, 'state': 'checked' if should_check else 'unchecked'}

            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")
                continue

        # If standard selectors fail, try finding the label first
        logger.info("Trying alternative approach: finding label first")
        try:
            # Find all labels on the page
            labels = self.page.locator('label').all()

            for label in labels:
                label_text = label.text_content().strip()

                # Check if this label matches our target
                if element_desc.lower() in label_text.lower() or label_text.lower() in element_desc.lower():
                    logger.debug(f"Found matching label with text: '{label_text}'")

                    # Try to find checkbox within or associated with this label
                    # Method 1: Checkbox inside label
                    checkbox = label.locator('input[type="checkbox"]').first
                    if checkbox.count() > 0 and checkbox.is_visible():
                        is_checked = checkbox.is_checked()
                        if is_checked != should_check:
                            try:
                                if should_check:
                                    checkbox.check()
                                else:
                                    checkbox.uncheck()
                            except:
                                checkbox.click()
                        return {'checkbox': element_desc, 'state': 'checked' if should_check else 'unchecked'}

                    # Method 2: Checkbox referenced by 'for' attribute
                    for_attr = label.get_attribute('for')
                    if for_attr:
                        checkbox = self.page.locator(f'input[type="checkbox"]#{for_attr}')
                        if checkbox.count() > 0 and checkbox.is_visible():
                            is_checked = checkbox.is_checked()
                            if is_checked != should_check:
                                try:
                                    if should_check:
                                        checkbox.check()
                                    else:
                                        checkbox.uncheck()
                                except:
                                    checkbox.click()
                            return {'checkbox': element_desc, 'state': 'checked' if should_check else 'unchecked'}

                    # Method 3: Checkbox in parent or sibling
                    parent = label.locator('xpath=..')
                    checkbox = parent.locator('input[type="checkbox"]').first
                    if checkbox.count() > 0 and checkbox.is_visible():
                        is_checked = checkbox.is_checked()
                        if is_checked != should_check:
                            try:
                                if should_check:
                                    checkbox.check()
                                else:
                                    checkbox.uncheck()
                            except:
                                checkbox.click()
                        return {'checkbox': element_desc, 'state': 'checked' if should_check else 'unchecked'}

        except Exception as e:
            logger.debug(f"Alternative label-based approach failed: {e}")

        # If all else fails, try clicking on the label itself
        logger.info("Trying to click on label text directly")
        try:
            label_elements = self.page.locator(f'label:has-text("{element_desc}")').all()
            for label in label_elements:
                if label.is_visible():
                    label.click()
                    logger.info(f"Clicked on label for checkbox: {element_desc}")
                    time.sleep(0.5)
                    return {'checkbox': element_desc, 'state': state}
        except:
            pass

        # Last resort: Use AI detection
        logger.info("Falling back to AI detection for checkbox")
        screenshot = self.page.screenshot()
        element_info = self.ai_finder.find_element(self.page, f"checkbox {element_desc}", screenshot)

        if element_info:
            if element_info.get('selector'):
                element = self.page.locator(element_info['selector'])
                element.wait_for(state='visible', timeout=self.timeout)
                element.scroll_into_view_if_needed()
                time.sleep(0.3)

                try:
                    is_checked = element.is_checked()
                    if is_checked != should_check:
                        element.click()
                except:
                    element.click()

                return {'checkbox': element_desc, 'state': state}
            else:
                # Click at position
                self.ai_finder.click_at_position(self.page, element_info['position'])
                return {'checkbox': element_desc, 'state': state}

        raise Exception(f"Checkbox not found: {element_desc}")

    def _handle_radio(self, params: Dict) -> Any:
        """Handle radio button selection with dynamic element support"""
        element_desc = params.get('element', '')

        logger.info(f"Attempting to select radio button: {element_desc}")

        # Small wait to ensure dynamic content is loaded
        time.sleep(0.5)

        # Extract the option text from the description
        import re
        # Pattern to extract text between quotes
        match = re.search(r'"([^"]+)"', element_desc)
        option_text = match.group(1) if match else element_desc

        # Build comprehensive list of selectors for radio buttons
        selectors = []

        # Most specific selectors first - Generic patterns
        selectors.extend([
            # Standard HTML patterns
            f'label:has-text("{option_text}") input[type="radio"]',
            f'label:has-text("{option_text}") >> input[type="radio"]',
            f'label:has(input[type="radio"]):has-text("{option_text}")',

            # Radio button with aria-label
            f'input[type="radio"][aria-label*="{option_text}" i]',

            # Radio button with value
            f'input[type="radio"][value*="{option_text}" i]',
            f'input[type="radio"][value*="{option_text.lower()}" i]',
            f'input[type="radio"][value*="{option_text.lower().replace(" ", "_")}" i]',
            f'input[type="radio"][value*="{option_text.lower().replace(" ", "-")}" i]',
            f'input[type="radio"][value*="{option_text.lower().replace("-", "_")}" i]',

            # Label with for attribute
            f'label[for]:has-text("{option_text}")',

            # Radio button near text
            f'input[type="radio"]:near(:text("{option_text}"))',

            # Generic wrapper patterns
            f'[class*="radio"]:has-text("{option_text}") input[type="radio"]',
            f'[class*="radio"]:has-text("{option_text}")',
            f'*:has-text("{option_text}") input[type="radio"]',

            # Structural patterns
            f'div:has-text("{option_text}") input[type="radio"]',
            f'span:has-text("{option_text}") >> xpath=.. >> input[type="radio"]',

            # Role-based patterns
            f'[role="radio"]:near(:text("{option_text}"))',
            f'[role="radiogroup"] :text("{option_text}")',

            # Fieldset patterns
            f'fieldset:has-text("{option_text}") input[type="radio"]',

            # Parent-child patterns
            f':has(> :text("{option_text}")) > input[type="radio"]',
            f':has(> :text("{option_text}")) input[type="radio"]',
        ])

        # Try each selector
        for selector in selectors:
            try:
                elements = self.page.locator(selector).all()

                for element in elements:
                    if not element.is_visible():
                        continue

                    # Ensure element is in viewport
                    try:
                        # First try standard scroll
                        element.scroll_into_view_if_needed()
                    except:
                        # If that fails, try JavaScript scroll
                        try:
                            element.evaluate("el => el.scrollIntoView({behavior: 'smooth', block: 'center'})")
                        except:
                            # Last resort - scroll to approximate position
                            try:
                                box = element.bounding_box()
                                if box:
                                    self.page.evaluate(f"window.scrollTo(0, {box['y'] - 200})")
                            except:
                                pass

                    time.sleep(0.5)  # Wait for scroll to complete

                    # Check if it's already selected
                    try:
                        # For actual radio inputs
                        if element.evaluate("el => el.tagName.toLowerCase()") == 'input':
                            is_checked = element.is_checked()
                            if not is_checked:
                                element.check()
                            else:
                                logger.info(f"Radio button '{option_text}' is already selected")
                        else:
                            # For label or wrapper elements
                            element.click()
                    except:
                        # Fallback to click
                        element.click()

                    logger.info(f"Successfully selected radio button: {option_text}")

                    # IMPORTANT: Wait for dynamic elements to appear
                    self._wait_for_dynamic_elements()

                    return {'selected': option_text, 'type': 'radio'}

            except Exception as e:
                logger.debug(f"Selector {selector} failed: {e}")
                continue

        # If standard selectors fail, try AI detection
        logger.info("Falling back to AI detection for radio button")
        screenshot = self.page.screenshot()
        element_info = self.ai_finder.find_element(self.page, element_desc, screenshot)

        if element_info:
            if element_info.get('selector'):
                element = self.page.locator(element_info['selector'])
                element.wait_for(state='visible', timeout=self.timeout)
                element.scroll_into_view_if_needed()
                time.sleep(0.3)

                try:
                    element.check()
                except:
                    element.click()

                # Wait for dynamic elements
                self._wait_for_dynamic_elements()

                return {'selected': option_text, 'type': 'radio'}
            else:
                # Click at position
                self.ai_finder.click_at_position(self.page, element_info['position'])

                # Wait for dynamic elements
                self._wait_for_dynamic_elements()

                return {'selected': option_text, 'type': 'radio'}

        raise Exception(f"Radio button not found: {element_desc}")

    def _handle_verify_text(self, params: Dict) -> Any:
        """Verify text is present on page"""
        text = params.get('text', '')

        # Wait for text to appear
        try:
            self.page.wait_for_selector(f'text="{text}"', timeout=self.timeout)
            return {'verified': text}
        except:
            # Check if text is anywhere on page
            page_text = self.page.text_content('body')
            if text.lower() in page_text.lower():
                return {'verified': text}
            else:
                raise Exception(f"Text not found: {text}")

    def _handle_verify_element(self, params: Dict) -> Any:
        """Verify element is visible"""
        element_desc = params.get('element', '')

        # Take screenshot for AI detection
        screenshot = self.page.screenshot()

        # Find element using AI
        element_info = self.ai_finder.find_element(self.page, element_desc, screenshot)

        if element_info:
            return {'verified': element_desc, 'visible': True}
        else:
            raise Exception(f"Element not visible: {element_desc}")

    def _handle_wait(self, params: Dict) -> Any:
        """Handle wait actions"""
        duration = params.get('duration')
        element = params.get('element')
        text = params.get('text')

        if duration:
            # Convert to seconds if needed
            wait_time = float(duration)
            if wait_time > 100:  # Assume milliseconds
                wait_time = wait_time / 1000
            time.sleep(wait_time)
            return {'waited': f"{wait_time} seconds"}

        elif text:
            # Wait for text to appear
            try:
                self.page.wait_for_selector(f'text="{text}"', timeout=self.timeout)
                return {'waited_for_text': text}
            except:
                # Try partial text match
                self.page.wait_for_selector(f'text={text}', timeout=self.timeout)
                return {'waited_for_text': text}

        elif element:
            # Wait for element
            screenshot = self.page.screenshot()
            element_info = self.ai_finder.find_element(self.page, element, screenshot)

            if element_info and element_info.get('selector'):
                self.page.wait_for_selector(element_info['selector'], timeout=self.timeout)
                return {'waited_for': element}
            else:
                # Retry with polling
                start_time = time.time()
                while time.time() - start_time < self.timeout / 1000:
                    screenshot = self.page.screenshot()
                    element_info = self.ai_finder.find_element(self.page, element, screenshot)
                    if element_info:
                        return {'waited_for': element}
                    time.sleep(0.5)

                raise Exception(f"Element not found after wait: {element}")

    def _handle_screenshot(self, params: Dict) -> Any:
        """Take a screenshot"""
        name = params.get('name', f'screenshot_{int(time.time())}')
        path = f"reports/screenshots/{name}.png"

        self.page.screenshot(path=path)
        return {'screenshot': path}

    def _take_screenshot(self) -> str:
        """Take screenshot for error reporting"""
        try:
            timestamp = int(time.time())
            path = f"reports/screenshots/error_{timestamp}.png"
            self.page.screenshot(path=path)
            return path
        except:
            return None

    def _analyze_input_element(self, element) -> Dict:
        """
        Analyze an input element to understand its type and characteristics
        """
        try:
            # Get various attributes
            elem_type = element.get_attribute('type') or 'text'
            elem_class = element.get_attribute('class') or ''
            elem_role = element.get_attribute('role') or ''
            elem_tag = element.evaluate("el => el.tagName.toLowerCase()")

            # Check for number input patterns
            is_number_input = any([
                elem_type == 'number',
                elem_role == 'spinbutton',
                'number' in elem_class,
                element.get_attribute('inputmode') == 'numeric',
                element.get_attribute('aria-valuemin') is not None,
                element.get_attribute('aria-valuemax') is not None,
            ])

            # Check for special input types
            is_rich_text = any([
                element.get_attribute('contenteditable') == 'true',
                'editor' in elem_class.lower(),
                'ql-editor' in elem_class,
                elem_role == 'textbox' and elem_tag == 'div'
            ])

            # Check if it's part of a component
            is_component_input = any([
                'ant-input-number-input' in elem_class,
                'ant-picker-input' in elem_class,
                'MuiInput' in elem_class,
                element.locator('xpath=ancestor::*[contains(@class, "ant-input-number")]').count() > 0
            ])

            return {
                'type': elem_type,
                'tag': elem_tag,
                'is_number': is_number_input,
                'is_rich_text': is_rich_text,
                'is_component': is_component_input,
                'class': elem_class
            }
        except:
            return {
                'type': 'text',
                'tag': 'input',
                'is_number': False,
                'is_rich_text': False,
                'is_component': False,
                'class': ''
            }

    def _clear_input_intelligently(self, element, input_info: Dict):
        """
        Clear input based on its type
        """
        try:
            # For number inputs in components (like Ant Design)
            if input_info['is_component'] and input_info['is_number']:
                # Triple click and delete works best
                element.click(click_count=3)
                self.page.keyboard.press('Delete')

            # For contenteditable/rich text
            elif input_info['is_rich_text']:
                element.click()
                self.page.keyboard.press('Control+a' if os.name != 'darwin' else 'Meta+a')
                self.page.keyboard.press('Delete')

            # For standard inputs
            else:
                try:
                    element.clear()
                except:
                    # Fallback to keyboard method
                    element.click()
                    self.page.keyboard.press('Control+a' if os.name != 'darwin' else 'Meta+a')
                    self.page.keyboard.press('Delete')

        except Exception as e:
            logger.debug(f"Clear failed with {e}, trying select all and type")
            element.click()
            time.sleep(0.1)
            self.page.keyboard.press('Control+a' if os.name != 'darwin' else 'Meta+a')

    def _wait_for_dynamic_elements(self, wait_time: float = 1.0):
        """
        Wait for dynamic elements to appear after an action
        This is generic and works for all web applications
        """
        # Use configurable wait time
        dynamic_wait = self.config.get('dynamic_element_wait', wait_time)
        time.sleep(dynamic_wait)

        # Wait for any pending animations or transitions
        try:
            # Wait for any loading indicators to disappear
            loading_selectors = [
                '.loading', '.spinner', '.loader',
                '[class*="loading"]', '[class*="spinner"]',
                '.ant-spin', '.MuiCircularProgress-root',
                '[aria-busy="true"]'
            ]

            for selector in loading_selectors:
                try:
                    # Wait for loading elements to disappear
                    self.page.wait_for_selector(selector, state='hidden', timeout=1000)
                except:
                    # If selector not found or already hidden, continue
                    pass

            # Additional wait for DOM mutations to complete
            self.page.evaluate("""
                    new Promise(resolve => {
                        if (typeof requestIdleCallback !== 'undefined') {
                            requestIdleCallback(() => resolve(), { timeout: 500 });
                        } else {
                            setTimeout(resolve, 100);
                        }
                    });
                """)

        except Exception as e:
            logger.debug(f"Dynamic wait check failed: {e}")

    def _build_input_selectors(self, element_desc: str) -> List[str]:
        """
        Build a comprehensive list of selectors for finding input fields
        """
        # Clean the element description
        clean_desc = element_desc.strip()

        # Create variations of the text
        variations = [
            clean_desc,
            clean_desc.lower(),
            clean_desc.title(),
            clean_desc.replace(" ", "_"),
            clean_desc.replace(" ", "-"),
            clean_desc.replace(" ", ""),
        ]

        selectors = []

        for variant in variations:
            # Label-based selectors
            selectors.extend([
                f'label:has-text("{clean_desc}") + input:visible',
                f'label:has-text("{clean_desc}") + * input:visible',
                f'label:has-text("{clean_desc}") ~ input:visible',
                f'label:text-is("{clean_desc}") + input:visible',
                f'label:text-is("{clean_desc}") ~ input:visible',
            ])

            # Container-based selectors
            selectors.extend([
                f'div:has(> label:has-text("{clean_desc}")) input:visible',
                f'div:has(label:has-text("{clean_desc}")) input:visible:not([type="hidden"])',
                f'[class*="form"]:has(label:has-text("{clean_desc}")) input:visible',
                f'[class*="field"]:has(label:has-text("{clean_desc}")) input:visible',
            ])

            # Attribute-based selectors
            selectors.extend([
                f'input[placeholder*="{variant}" i]:visible',
                f'input[aria-label*="{variant}" i]:visible',
                f'input[name*="{variant}" i]:visible',
                f'input[id*="{variant}" i]:visible',
            ])

            # Number inputs
            selectors.extend([
                f'input[type="number"][placeholder*="{variant}" i]:visible',
                f'input[type="number"][aria-label*="{variant}" i]:visible',
                f'label:has-text("{clean_desc}") + input[type="number"]:visible',
                f'label:has-text("{clean_desc}") ~ input[type="number"]:visible',
            ])

        # Generic nearby selectors
        selectors.extend([
            f'input:near(:text("{clean_desc}")):visible',
            f'input[type="text"]:near(:text("{clean_desc}")):visible',
            f'input[type="number"]:near(:text("{clean_desc}")):visible',
        ])

        # Additional selectors for dynamic fields
        selectors.extend([
            # Fields in conditionally shown containers
            f'.show label:has-text("{clean_desc}") + input',
            f'.active label:has-text("{clean_desc}") + input',
            f'[class*="visible"] label:has-text("{clean_desc}") + input',
            f'[class*="expanded"] label:has-text("{clean_desc}") + input',

            # Dynamic field patterns - fields that appear after radio/checkbox selection
            f'*[style*="display: block"] label:has-text("{clean_desc}") + input',
            f'*[style*="display: block"] label:has-text("{clean_desc}") ~ input',
            f'*:not([style*="display: none"]) label:has-text("{clean_desc}") + input',
            f'*:not([hidden]) label:has-text("{clean_desc}") + input',

            # Nested in form groups that may be dynamically shown
            f'.form-group:not([style*="display: none"]) label:has-text("{clean_desc}") + input',
            f'[class*="form-field"]:not([style*="display: none"]) label:has-text("{clean_desc}") + input',

            # Ant Design specific patterns
            f'.ant-form-item:has(label:has-text("{clean_desc}")) input',
            f'.ant-form-item:has(label:text-is("{clean_desc}")) input',

            # Textarea patterns
            f'label:has-text("{clean_desc}") + textarea',
            f'label:has-text("{clean_desc}") ~ textarea',
            f'div:has(label:has-text("{clean_desc}")) textarea',
            f'textarea[placeholder*="{clean_desc}" i]',

            # Rich text editor patterns
            f'label:has-text("{clean_desc}") + div [contenteditable="true"]',
            f'label:has-text("{clean_desc}") ~ div [contenteditable="true"]',
            f'div:has(label:has-text("{clean_desc}")) [contenteditable="true"]',
            f'div:has(label:has-text("{clean_desc}")) .ql-editor',
        ])

        return selectors

    def _log_visible_inputs(self):
        """
        Log all visible input fields for debugging
        """
        try:
            visible_inputs = self.page.locator('input:visible').all()
            logger.debug(f"Found {len(visible_inputs)} visible input fields:")
            for i, input_elem in enumerate(visible_inputs[:10]):  # Log first 10
                try:
                    input_type = input_elem.get_attribute('type') or 'text'
                    placeholder = input_elem.get_attribute('placeholder') or ''
                    name = input_elem.get_attribute('name') or ''
                    aria_label = input_elem.get_attribute('aria-label') or ''

                    # Try to find associated label
                    label_text = ''
                    input_id = input_elem.get_attribute('id')
                    if input_id:
                        label = self.page.locator(f'label[for="{input_id}"]').first
                        if label.count() > 0:
                            label_text = label.text_content().strip()

                    logger.debug(
                        f"  Input {i}: type='{input_type}', "
                        f"placeholder='{placeholder}', name='{name}', "
                        f"aria-label='{aria_label}', label='{label_text}'"
                    )
                except:
                    pass
        except Exception as e:
            logger.debug(f"Failed to log visible inputs: {e}")

    def _fill_input_intelligently(self, element, value: str, input_info: Dict):
        """
        Fill input based on its type
        """
        try:
            # For component inputs, we might need special handling
            if input_info['is_component']:
                # Some components need the value typed rather than filled
                element.click()
                self.page.keyboard.type(value)

                # Trigger change events for frameworks
                element.evaluate('''el => {
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                }''')

            # For standard inputs
            else:
                element.fill(value)

            # For number inputs, ensure the value is accepted
            if input_info['is_number']:
                # Press Tab to trigger validation
                self.page.keyboard.press('Tab')

        except Exception as e:
            logger.debug(f"Fill failed with {e}, using keyboard type")
            self.page.keyboard.type(value)

    def _handle_search(self, params: Dict) -> Any:
        """Handle search actions"""
        query = params.get('query', '')
        field = params.get('field', 'search')

        # Find search field
        screenshot = self.page.screenshot()

        # Try to find search input with generic strategies
        search_selectors = [
            # ID-based (most specific)
            '#search',
            'input#search',
            f'#{field}',
            f'input#{field}',
            # Type-based
            'input[type="search"]',
            # Name-based
            'input[name="search"]',
            'input[name*="search" i]',
            f'input[name="{field}"]',
            f'input[name*="{field}" i]',
            # Class-based
            '.search-input',
            '.search-field',
            '.search-box input',
            'input.search',
            # Placeholder-based (generic search terms)
            'input[placeholder*="search" i]',
            'input[placeholder*="find" i]',
            'input[placeholder*="query" i]',
            # ARIA-based
            'input[aria-label*="search" i]',
            f'input[aria-label*="{field}" i]',
            # Role-based
            'input[role="searchbox"]',
            # Generic text inputs (excluding special types)
            'input[type="text"]:not([role="combobox"]):not([readonly]):not([disabled]):visible'
        ]

        element = None
        for selector in search_selectors:
            try:
                elements = self.page.locator(selector).all()
                # If multiple elements, prefer visible ones
                for el in elements:
                    if el.is_visible() and el.is_enabled():
                        element = el
                        logger.info(f"Found search input with selector: {selector}")
                        break
                if element:
                    break
            except:
                continue

        if not element:
            # Use AI finder as fallback
            element_info = self.ai_finder.find_element(self.page, field + " field", screenshot)
            if element_info and element_info.get('selector'):
                element = self.page.locator(element_info['selector'])
                logger.info(f"Found search input using AI finder")

        if element:
            # Clear and fill the search field
            element.click()
            element.clear()
            element.fill(query)

            # Wait a bit for any auto-complete or dynamic behavior
            time.sleep(0.5)

            # Try to submit search
            # First check if there's a search button nearby
            search_button_selectors = [
                # Generic search button selectors
                'button[type="submit"]:visible',
                'button:has-text("Search"):visible',
                'button:has-text("Find"):visible',
                'button:has-text("Go"):visible',
                'button[aria-label*="search" i]:visible',
                'input[type="submit"][value*="search" i]:visible',
                '[role="button"]:has-text("Search"):visible',
                'button.search-button:visible',
                'button.search-btn:visible',
                # Icon buttons (often have search icon)
                'button:has(svg):visible',
                'button:has(i.fa-search):visible',
                'button:has(i.icon-search):visible'
            ]

            button_found = False
            for btn_selector in search_button_selectors:
                try:
                    btn = self.page.locator(btn_selector)
                    if btn.count() > 0:
                        btn.first.click()
                        button_found = True
                        logger.info(f"Clicked search button: {btn_selector}")
                        break
                except:
                    continue

            # If no button found, press Enter
            if not button_found:
                element.press('Enter')
                logger.info("Pressed Enter to submit search")

            # Wait for results
            time.sleep(1)
            self.page.wait_for_load_state('networkidle')

            return {'searched': query}
        else:
            raise Exception(f"Search field not found: {field}")

    def _handle_verify_table(self, params: Dict) -> Any:
        """Handle table data verification"""
        # Check if we have data_table from the step
        data_table = params.get('data_table', [])
        table_identifier = params.get('table', 'table')

        if not data_table or len(data_table) < 2:
            raise Exception(
                "Table verification requires a data table with headers and at least one row of expected values")

        # First row is headers, remaining rows are expected values
        expected_headers = data_table[0]
        expected_rows = data_table[1:]

        # Find the table on the page
        table_selectors = [
            f'table#{table_identifier}',
            f'table.{table_identifier}',
            f'table[aria-label*="{table_identifier}" i]',
            f'#{table_identifier}',
            f'.{table_identifier}',
            'table.ant-table',
            'table[role="table"]',
            '.ant-table-wrapper table',
            'table'
        ]

        table_element = None
        for selector in table_selectors:
            try:
                elements = self.page.locator(selector).all()
                if elements:
                    table_element = elements[0]
                    logger.info(f"Found table with selector: {selector}")
                    break
            except:
                continue

        if not table_element:
            raise Exception(f"Table not found: {table_identifier}")

        # Get table headers to map column positions
        header_selectors = [
            'thead th',
            'thead td',
            'th',
            '.ant-table-thead th',
            'tr:first-child td',
            'tr:first-child th'
        ]

        actual_headers = []
        for header_selector in header_selectors:
            try:
                headers = table_element.locator(header_selector).all()
                if headers:
                    for header in headers:
                        header_text = header.text_content().strip()
                        if header_text:
                            actual_headers.append(header_text)
                    if actual_headers:
                        break
            except:
                continue

        logger.info(f"Found headers: {actual_headers}")

        # Map expected headers to column indices
        column_map = {}
        for expected_header in expected_headers:
            # Try exact match first
            for i, actual_header in enumerate(actual_headers):
                if actual_header.lower() == expected_header.lower():
                    column_map[expected_header] = i
                    break

            # If no exact match, try partial match
            if expected_header not in column_map:
                for i, actual_header in enumerate(actual_headers):
                    if expected_header.lower() in actual_header.lower() or actual_header.lower() in expected_header.lower():
                        column_map[expected_header] = i
                        break

        logger.info(f"Column mapping: {column_map}")

        # Get all rows from tbody
        # For Ant Design tables, we need to get all tr elements in tbody
        table_rows = []

        # Try different approaches to get data rows
        approaches = [
            # Approach 1: Direct tbody tr
            lambda: table_element.locator('tbody tr').all(),
            # Approach 2: Ant Design specific
            lambda: table_element.locator('.ant-table-tbody tr').all(),
            # Approach 3: All tr elements (then filter)
            lambda: table_element.locator('tr').all(),
        ]

        for approach in approaches:
            try:
                rows = approach()
                if rows:
                    logger.info(f"Found {len(rows)} potential rows")

                    # Filter to get only data rows
                    data_rows = []
                    for row in rows:
                        # Check if row has cells (td elements)
                        cell_count = row.locator('td').count()
                        if cell_count > 0:
                            # This is likely a data row
                            # Additional check: make sure it's not the header row
                            first_cell_text = row.locator('td').first.text_content().strip()
                            # If first cell text matches a header, skip this row
                            if first_cell_text not in actual_headers:
                                data_rows.append(row)
                                logger.info(f"Added data row with {cell_count} cells")

                    if data_rows:
                        table_rows = data_rows
                        logger.info(f"Found {len(table_rows)} data rows in table")
                        break
            except Exception as e:
                logger.debug(f"Approach failed: {e}")
                continue

        if not table_rows:
            # Last resort: try to get any row that contains the expected data
            logger.warning("Using fallback approach to find table rows")
            all_rows = self.page.locator('tr').all()
            for row in all_rows:
                try:
                    row_text = row.text_content()
                    # Check if this row contains any of our expected values
                    if any(expected_value in row_text for expected_row in expected_rows for expected_value in
                           expected_row):
                        if row.locator('td').count() > 0:
                            table_rows.append(row)
                            logger.info(f"Found matching row: {row_text[:100]}...")
                except:
                    continue

        if not table_rows:
            raise Exception("No data rows found in table")

        # Verify each expected row
        verification_results = []
        for row_index, expected_row in enumerate(expected_rows):
            if row_index >= len(table_rows):
                verification_results.append({
                    'row': row_index,
                    'status': 'failed',
                    'error': f'Row {row_index} not found in table'
                })
                continue

            actual_row = table_rows[row_index]

            # Get all cells in the row
            cells = actual_row.locator('td').all()
            logger.info(f"Row {row_index} has {len(cells)} cells")

            row_result = {'row': row_index, 'status': 'passed', 'details': []}

            # Verify each expected value
            for header_index, expected_value in enumerate(expected_row):
                if header_index >= len(expected_headers):
                    continue

                header = expected_headers[header_index]

                # Skip if header not found in column map
                if header not in column_map:
                    row_result['details'].append({
                        'header': header,
                        'status': 'skipped',
                        'message': f'Header "{header}" not found in table'
                    })
                    continue

                column_index = column_map[header]

                if column_index >= len(cells):
                    row_result['details'].append({
                        'header': header,
                        'status': 'failed',
                        'expected': expected_value,
                        'actual': 'Cell not found',
                        'message': f'Column {column_index} not found in row'
                    })
                    row_result['status'] = 'failed'
                    continue

                actual_cell = cells[column_index]

                # Get the cell text - try multiple methods
                actual_value = ''

                # Method 1: Direct text content
                try:
                    actual_value = actual_cell.text_content().strip()
                except:
                    pass

                # Method 2: Inner text (better for complex cells)
                if not actual_value:
                    try:
                        actual_value = actual_cell.inner_text().strip()
                    except:
                        pass

                # Method 3: Look for specific elements in the cell
                if not actual_value:
                    try:
                        # For status cells with badges/icons
                        status_selectors = [
                            'span',
                            'div',
                            '[class*="badge"]',
                            '[class*="status"]',
                            '[class*="tag"]',
                            '.ant-tag',
                            '.ant-badge'
                        ]

                        for selector in status_selectors:
                            elements = actual_cell.locator(selector).all()
                            for elem in elements:
                                text = elem.text_content().strip()
                                if text and text not in ['', ' ']:
                                    actual_value = text
                                    break
                            if actual_value:
                                break
                    except:
                        pass

                # Method 4: Get all text nodes
                if not actual_value:
                    try:
                        actual_value = actual_cell.evaluate("el => el.textContent").strip()
                    except:
                        pass

                logger.info(f"Cell {column_index} ({header}): actual='{actual_value}', expected='{expected_value}'")

                # Compare values (case-insensitive)
                if expected_value.strip() == '*' or expected_value.strip() == '':
                    # Wildcard or empty means skip verification for this cell
                    row_result['details'].append({
                        'header': header,
                        'status': 'skipped',
                        'actual': actual_value,
                        'message': 'Wildcard match'
                    })
                elif actual_value.lower() == expected_value.lower():
                    row_result['details'].append({
                        'header': header,
                        'status': 'passed',
                        'expected': expected_value,
                        'actual': actual_value
                    })
                else:
                    # Check for partial match
                    if expected_value.lower() in actual_value.lower() or actual_value.lower() in expected_value.lower():
                        row_result['details'].append({
                            'header': header,
                            'status': 'passed',
                            'expected': expected_value,
                            'actual': actual_value,
                            'message': 'Partial match'
                        })
                    else:
                        row_result['details'].append({
                            'header': header,
                            'status': 'failed',
                            'expected': expected_value,
                            'actual': actual_value
                        })
                        row_result['status'] = 'failed'

            verification_results.append(row_result)

        # Check if all verifications passed
        all_passed = all(result['status'] == 'passed' for result in verification_results)

        if not all_passed:
            # Generate detailed error message
            error_details = []
            for result in verification_results:
                if result['status'] == 'failed':
                    row_errors = []
                    for detail in result['details']:
                        if detail['status'] == 'failed':
                            row_errors.append(
                                f"{detail['header']}: expected '{detail['expected']}' but got '{detail['actual']}'")
                    if row_errors:
                        error_details.append(f"Row {result['row']}: {'; '.join(row_errors)}")

            raise Exception(f"Table verification failed. {'. '.join(error_details)}")

        logger.info(f"Table verification passed. Checked {len(expected_rows)} rows")
        return {'verified': 'table data', 'rows_checked': len(expected_rows)}

    def _handle_unknown(self, params: Dict) -> Any:
        """Handle unknown/custom actions"""
        # Log the unknown action
        logger.warning(f"Unknown action with params: {params}")

        # Try to interpret based on text
        text = params.get('text', '')

        # You can add custom logic here
        # For now, just return as unhandled
        raise Exception(f"Unknown action: {text}")

    def _handle_call_api(self, params: Dict) -> Any:
        """Handle simple API call"""
        api_name = params.get('api_name', '')

        if not self.api_executor:
            raise Exception("API executor not initialized. Please ensure api_config.yaml exists.")

        logger.info(f"Calling API: {api_name}")

        # Run async API call
        response = asyncio.run(self.api_executor.execute_api(
            api_name,
            test_name=self.current_test_name
        ))
        self.last_api_response = response

        return {
            'api': api_name,
            'status': response['status'],
            'response_time': response['response_time']
        }

    def _handle_call_api_with_data(self, params: Dict) -> Any:
        """Handle API call with data table"""
        api_name = params.get('api_name', '')
        data_table = params.get('data_table', [])

        if not self.api_executor:
            raise Exception("API executor not initialized. Please ensure api_config.yaml exists.")

        # Convert data table to parameters
        api_params = {}
        if len(data_table) >= 2:
            headers = data_table[0]
            values = data_table[1]

            for i, header in enumerate(headers):
                if i < len(values):
                    # Convert header to parameter name (lowercase, replace spaces with underscores)
                    param_name = header.lower().replace(' ', '_')
                    api_params[param_name] = values[i]

        logger.info(f"Calling API: {api_name} with params: {api_params}")

        # Run async API call
        response = asyncio.run(self.api_executor.execute_api(
            api_name,
            test_name=self.current_test_name,
            **api_params
        ))
        self.last_api_response = response

        return {
            'api': api_name,
            'status': response['status'],
            'response_time': response['response_time']
        }

    def _handle_authenticate(self, params: Dict) -> Any:
        """Handle authentication with username/password"""
        username = params.get('username', '')
        password = params.get('password', '')

        if not self.api_executor:
            raise Exception("API executor not initialized")

        logger.info(f"Authenticating user: {username}")

        # Store credentials in context
        self.api_executor.store_value('username', username)
        self.api_executor.store_value('password', password)

        # Call login API
        response = asyncio.run(self.api_executor.execute_api(
            'login',
            test_name=f"Authentication: {username}"
        ))
        self.last_api_response = response

        if response['status'] == 200:
            return {'authenticated': True, 'user': username}
        else:
            raise Exception(f"Authentication failed: {response.get('body', {}).get('message', 'Unknown error')}")

    def _handle_authenticate_with_env(self, params: Dict) -> Any:
        """Handle authentication using environment credentials"""
        credential_key = params.get('credential_key', '')

        # Get credentials from config
        credentials = self.config.get('credentials', {}).get(credential_key, {})
        if not credentials:
            raise Exception(f"Credentials '{credential_key}' not found in config")

        username = credentials.get('username', '')
        password = credentials.get('password', '')

        return self._handle_authenticate({'username': username, 'password': password})

    def _handle_authenticate_with_role(self, params: Dict) -> Any:
        """Handle authentication using role-based credentials"""
        role = params.get('role', '')

        # Get role-based credentials from config
        roles = self.config.get('roles', {})
        if role not in roles:
            raise Exception(f"Role '{role}' not found in configuration")

        role_config = roles[role]
        username = role_config.get('username', '')
        password = role_config.get('password', '')

        logger.info(f"Authenticating as role: {role} (user: {username})")

        # Store role information for reference
        if self.api_executor:
            self.api_executor.store_value('current_role', role)
            self.api_executor.store_value('current_user', username)

        return self._handle_authenticate({'username': username, 'password': password})

    def _handle_login_as_role(self, params: Dict) -> Any:
        """Handle UI login using role-based credentials"""
        role = params.get('role', '')

        # Get role-based credentials from config
        roles = self.config.get('roles', {})
        if role not in roles:
            raise Exception(f"Role '{role}' not found in configuration")

        role_config = roles[role]
        username = role_config.get('username', '')
        password = role_config.get('password', '')

        logger.info(f"Logging in as role: {role} (user: {username})")

        # Navigate to login page if not already there
        if 'login' not in self.page.url.lower():
            self._handle_navigate({'url': 'login page'})

        # Enter credentials
        self._handle_input({'element': 'Username', 'value': username})
        self._handle_input({'element': 'Password', 'value': password})

        # Click sign in
        self._handle_click({'element': 'Sign In'})

        # Wait for navigation
        time.sleep(2)

        return {'logged_in': True, 'role': role, 'user': username}

    def _handle_verify_api_status(self, params: Dict) -> Any:
        """Verify API response status code"""
        expected_status = int(params.get('status_code', 200))

        if not self.last_api_response:
            raise Exception("No API response to verify")

        actual_status = self.last_api_response['status']

        if actual_status != expected_status:
            raise AssertionError(f"Expected status {expected_status}, got {actual_status}")

        return {'verified': f'status {expected_status}'}

    def _handle_verify_api_contains(self, params: Dict) -> Any:
        """Verify API response contains text"""
        text = params.get('text', '')

        if not self.last_api_response:
            raise Exception("No API response to verify")

        response_text = str(self.last_api_response['body'])

        if text not in response_text:
            raise AssertionError(f"Response does not contain '{text}'")

        return {'verified': f"contains '{text}'"}

    def _handle_verify_api_field(self, params: Dict) -> Any:
        """Verify specific field in API response"""
        field_path = params.get('field_path', '')
        expected_value = params.get('expected_value', '')

        if not self.last_api_response:
            raise Exception("No API response to verify")

        if not isinstance(self.last_api_response['body'], dict):
            raise Exception("Response body is not JSON")

        # Use JSONPath to get actual value
        expression = parse(field_path)
        matches = expression.find(self.last_api_response['body'])

        if not matches:
            raise AssertionError(f"Field '{field_path}' not found in response")

        actual_value = str(matches[0].value)

        if actual_value != expected_value:
            raise AssertionError(f"Field '{field_path}': expected '{expected_value}', got '{actual_value}'")

        return {'verified': f"{field_path} = {expected_value}"}

    def _handle_verify_api_response_table(self, params: Dict) -> Any:
        """Verify API response matches data table"""
        data_table = params.get('data_table', [])

        if not self.last_api_response:
            raise Exception("No API response to verify")

        if not isinstance(self.last_api_response['body'], dict):
            raise Exception("Response body is not JSON")

        if len(data_table) < 2:
            raise Exception("Data table must have headers and at least one row")

        # Parse expected values from table
        headers = data_table[0]
        expected_values = data_table[1]

        for i, field_path in enumerate(headers):
            if i < len(expected_values):
                expected_value = expected_values[i]

                # Skip if wildcard
                if expected_value == '*':
                    continue

                # Use JSONPath to get actual value
                expression = parse(field_path)
                matches = expression.find(self.last_api_response['body'])

                if not matches:
                    raise AssertionError(f"Field '{field_path}' not found in response")

                actual_value = str(matches[0].value)

                if actual_value != expected_value:
                    raise AssertionError(f"Field '{field_path}': expected '{expected_value}', got '{actual_value}'")

        return {'verified': 'response matches expected values'}

    def _handle_store_api_field(self, params: Dict) -> Any:
        """Store specific field from API response"""
        field_path = params.get('field_path', '')
        variable_name = params.get('variable_name', '')

        if not self.last_api_response:
            raise Exception("No API response to store from")

        if not isinstance(self.last_api_response['body'], dict):
            raise Exception("Response body is not JSON")

        # Use JSONPath to get value
        expression = parse(field_path)
        matches = expression.find(self.last_api_response['body'])

        if not matches:
            raise Exception(f"Field '{field_path}' not found in response")

        value = matches[0].value

        # Store in API executor context
        if self.api_executor:
            self.api_executor.store_value(variable_name, value)

        logger.info(f"Stored {variable_name} = {value}")

        return {'stored': f'{variable_name} = {value}'}

    def _handle_store_api_response(self, params: Dict) -> Any:
        """Store entire API response"""
        variable_name = params.get('variable_name', '')

        if not self.last_api_response:
            raise Exception("No API response to store")

        # Store in API executor context
        if self.api_executor:
            self.api_executor.store_value(variable_name, self.last_api_response['body'])

        logger.info(f"Stored entire response as {variable_name}")

        return {'stored': f'response as {variable_name}'}

    def _handle_use_stored_value(self, params: Dict) -> Any:
        """Use a stored value as a parameter"""
        stored_name = params.get('stored_name', '')
        param_name = params.get('param_name', '')

        if not self.api_executor:
            raise Exception("API executor not initialized")

        # Get value from context
        value = self.api_executor.get_value(stored_name)
        if value is None:
            raise Exception(f"No stored value found for '{stored_name}'")

        # Store with new name
        self.api_executor.store_value(param_name, value)

        logger.info(f"Using stored {stored_name} as {param_name} = {value}")

        return {'used': f'{stored_name} as {param_name}'}

    def _handle_wait_api(self, params: Dict) -> Any:
        """Wait before or after API call"""
        duration = float(params.get('duration', 1))

        logger.info(f"Waiting {duration} seconds")
        time.sleep(duration)

        return {'waited': f'{duration} seconds'}

    def _handle_verify_api_response_time(self, params: Dict) -> Any:
        """Verify API response time is within limits"""
        max_time = float(params.get('max_time', 2.0))

        if not self.last_api_response:
            raise Exception("No API response to verify")

        actual_time = self.last_api_response.get('response_time', 0)

        if actual_time > max_time:
            raise AssertionError(
                f"Response time {actual_time:.2f}s exceeds maximum {max_time}s"
            )

        logger.info(f"Response time {actual_time:.2f}s is within {max_time}s limit")
        return {'verified': f'response time < {max_time}s'}

    def _handle_upload_file(self, params: Dict) -> Any:
        """Handle file upload to API"""
        file_path = params.get('file_path', '')
        api_name = params.get('api_name', '')
        data_table = params.get('data_table', [])

        if not self.api_executor:
            raise Exception("API executor not initialized")

        # Convert data table to parameters
        upload_params = {}
        if len(data_table) >= 2:
            headers = data_table[0]
            values = data_table[1]

            for i, header in enumerate(headers):
                if i < len(values):
                    param_name = header.lower().replace(' ', '_')
                    upload_params[param_name] = values[i]

        logger.info(f"Uploading file {file_path} to API: {api_name}")

        # Run async file upload
        response = asyncio.run(self.api_executor.execute_file_upload(
            api_name,
            file_path,
            test_name=self.current_test_name,
            **upload_params
        ))
        self.last_api_response = response

        return {
            'uploaded': file_path,
            'api': api_name,
            'status': response['status'],
            'response_time': response['response_time']
        }

    def _handle_verify_section_state(self, params: Dict) -> Any:
        """Verify if a section/step is enabled or disabled"""
        section_name = params.get('section', '')
        expected_state = params.get('state', 'enabled').lower()

        logger.info(f"Verifying section '{section_name}' is {expected_state}")

        # Try multiple strategies to find the section element
        section_selectors = [
            # Generic patterns
            f'*:has-text("{section_name}"):visible',
            f'[aria-label*="{section_name}" i]',
            f'[title*="{section_name}" i]',

            # Common wizard/stepper patterns
            f'.step:has-text("{section_name}")',
            f'.wizard-step:has-text("{section_name}")',
            f'li:has-text("{section_name}")',
            f'[role="tab"]:has-text("{section_name}")',
            f'[role="button"]:has-text("{section_name}")',

            # Ant Design patterns
            f'.ant-steps-item:has-text("{section_name}")',
            f'.ant-menu-item:has-text("{section_name}")',
            f'.ant-tabs-tab:has-text("{section_name}")',

            # Material UI patterns
            f'.MuiStep-root:has-text("{section_name}")',
            f'.MuiTab-root:has-text("{section_name}")',

            # Bootstrap patterns
            f'.nav-item:has-text("{section_name}")',
            f'.nav-link:has-text("{section_name}")',

            # Generic navigation patterns
            f'nav *:has-text("{section_name}")',
            f'[class*="nav"] *:has-text("{section_name}")',
            f'[class*="step"] *:has-text("{section_name}")',
        ]

        element_found = None
        for selector in section_selectors:
            try:
                elements = self.page.locator(selector).all()
                for element in elements:
                    if element.is_visible():
                        # Check if this element or its parent represents a section
                        element_found = element
                        logger.debug(f"Found section element with selector: {selector}")
                        break
                if element_found:
                    break
            except:
                continue

        if not element_found:
            raise Exception(f"Section '{section_name}' not found")

        # Now check the state of the section
        is_disabled = False

        # Method 1: Check common disabled attributes
        try:
            # Check the element itself
            is_disabled = (
                    element_found.get_attribute('disabled') == 'true' or
                    element_found.get_attribute('aria-disabled') == 'true' or
                    element_found.is_disabled()
            )
        except:
            pass

        # Method 2: Check parent elements for disabled state
        if not is_disabled:
            try:
                parent = element_found.locator('xpath=..')
                is_disabled = (
                        parent.get_attribute('disabled') == 'true' or
                        parent.get_attribute('aria-disabled') == 'true' or
                        'disabled' in (parent.get_attribute('class') or '')
                )
            except:
                pass

        # Method 3: Check CSS classes
        if not is_disabled:
            try:
                classes = element_found.get_attribute('class') or ''
                parent_classes = element_found.locator('xpath=..').get_attribute('class') or ''
                all_classes = f"{classes} {parent_classes}".lower()

                disabled_indicators = [
                    'disabled',
                    'inactive',
                    'not-allowed',
                    'cursor-not-allowed',
                    'pointer-events-none',
                    'opacity-50',
                    'opacity-60',
                    'text-gray',
                    'text-muted'
                ]

                is_disabled = any(indicator in all_classes for indicator in disabled_indicators)
            except:
                pass

        # Method 4: Check if clickable (enabled sections are usually clickable)
        if not is_disabled and expected_state == 'disabled':
            try:
                # Check if the element has click handlers or is interactive
                is_clickable = element_found.evaluate("""
                    (el) => {
                        const style = window.getComputedStyle(el);
                        return (
                            style.cursor === 'pointer' ||
                            el.onclick !== null ||
                            el.hasAttribute('href') ||
                            el.tagName === 'BUTTON' ||
                            el.tagName === 'A' ||
                            el.getAttribute('role') === 'button' ||
                            el.getAttribute('role') === 'link'
                        );
                    }
                """)
                # If it's clickable and we expect disabled, that might be wrong
                # But this is just additional info, not definitive
            except:
                pass

        # Method 5: Check visual indicators (opacity, color)
        try:
            opacity = element_found.evaluate("el => window.getComputedStyle(el).opacity")
            if float(opacity) < 0.7:  # Often disabled elements have reduced opacity
                is_disabled = True
        except:
            pass

        # Determine actual state
        actual_state = 'disabled' if is_disabled else 'enabled'

        # Verify against expected state
        if actual_state != expected_state:
            raise AssertionError(
                f"Section '{section_name}' is {actual_state}, expected {expected_state}"
            )

        logger.info(f"Verified section '{section_name}' is {expected_state}")
        return {'section': section_name, 'state': expected_state}

    def _handle_verify_sections_state(self, params: Dict) -> Any:
        """Verify multiple sections states from a data table"""
        data_table = params.get('data_table', [])

        if not data_table or len(data_table) < 2:
            raise Exception("Sections verification requires a data table with headers and values")

        # Expected format:
        # | Section Name | State |
        # | General Info | enabled |
        # | Participating Details | disabled |

        headers = data_table[0]

        # Find column indices
        section_col = None
        state_col = None

        for i, header in enumerate(headers):
            header_lower = header.lower()
            if 'section' in header_lower or 'name' in header_lower:
                section_col = i
            elif 'state' in header_lower or 'status' in header_lower:
                state_col = i

        if section_col is None or state_col is None:
            raise Exception("Data table must have 'Section' and 'State' columns")

        # Verify each section
        results = []
        for row in data_table[1:]:
            section_name = row[section_col] if section_col < len(row) else ''
            expected_state = row[state_col] if state_col < len(row) else 'enabled'

            try:
                result = self._handle_verify_section_state({
                    'section': section_name,
                    'state': expected_state
                })
                results.append(result)
            except Exception as e:
                raise Exception(f"Verification failed for section '{section_name}': {str(e)}")

        return {'verified': f'{len(results)} sections', 'results': results}

    def _handle_generate_date(self, params: Dict) -> Any:
        """Generate and store a date/datetime based on relative specifications"""
        date_spec = params.get('date_spec', 'today')
        variable_name = params.get('variable_name', 'generated_date')
        include_time = params.get('include_time', 'false').lower() == 'true'

        import datetime
        import re
        try:
            from dateutil.relativedelta import relativedelta
        except ImportError:
            # If dateutil is not installed, we can still handle basic cases
            relativedelta = None
            logger.warning("dateutil not installed, some date calculations may be limited")

        # Start with current datetime
        base_date = datetime.datetime.now()

        # Parse the date specification
        date_spec_lower = date_spec.lower()

        # Handle relative dates
        if 'today' in date_spec_lower:
            result_date = base_date
        elif 'tomorrow' in date_spec_lower:
            result_date = base_date + datetime.timedelta(days=1)
        elif 'yesterday' in date_spec_lower:
            result_date = base_date - datetime.timedelta(days=1)
        else:
            # Parse patterns like "5 days from now", "2 weeks from now", "3 months from now"

            # Pattern for "X time_unit from now" or "X time_unit ago"
            future_pattern = r'(\d+)\s*(day|week|month|year)s?\s*(?:from\s*now|hence|later)'
            past_pattern = r'(\d+)\s*(day|week|month|year)s?\s*(?:ago|before|earlier)'

            future_match = re.search(future_pattern, date_spec_lower)
            past_match = re.search(past_pattern, date_spec_lower)

            if future_match:
                amount = int(future_match.group(1))
                unit = future_match.group(2)

                if unit == 'day':
                    result_date = base_date + datetime.timedelta(days=amount)
                elif unit == 'week':
                    result_date = base_date + datetime.timedelta(weeks=amount)
                elif unit == 'month':
                    if relativedelta:
                        result_date = base_date + relativedelta(months=amount)
                    else:
                        # Approximate month as 30 days if dateutil not available
                        result_date = base_date + datetime.timedelta(days=amount * 30)
                elif unit == 'year':
                    if relativedelta:
                        result_date = base_date + relativedelta(years=amount)
                    else:
                        # Approximate year as 365 days if dateutil not available
                        result_date = base_date + datetime.timedelta(days=amount * 365)

            elif past_match:
                amount = int(past_match.group(1))
                unit = past_match.group(2)

                if unit == 'day':
                    result_date = base_date - datetime.timedelta(days=amount)
                elif unit == 'week':
                    result_date = base_date - datetime.timedelta(weeks=amount)
                elif unit == 'month':
                    if relativedelta:
                        result_date = base_date - relativedelta(months=amount)
                    else:
                        # Approximate month as 30 days if dateutil not available
                        result_date = base_date - datetime.timedelta(days=amount * 30)
                elif unit == 'year':
                    if relativedelta:
                        result_date = base_date - relativedelta(years=amount)
                    else:
                        # Approximate year as 365 days if dateutil not available
                        result_date = base_date - datetime.timedelta(days=amount * 365)

            else:
                # Default to today if pattern doesn't match
                result_date = base_date

        # Handle time specifications in the date_spec
        time_pattern = r'at\s*(\d{1,2}):?(\d{2})?\s*(am|pm)?'
        time_match = re.search(time_pattern, date_spec_lower)

        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            ampm = time_match.group(3)

            if ampm == 'pm' and hour < 12:
                hour += 12
            elif ampm == 'am' and hour == 12:
                hour = 0

            result_date = result_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            include_time = True

        # Format the result based on whether time is included
        if include_time:
            # Format matching your date picker: "2025/06/05 01:00"
            formatted_date = result_date.strftime('%Y/%m/%d %H:%M')
        else:
            formatted_date = result_date.strftime('%Y/%m/%d')

        # Store in context
        if hasattr(self, 'context'):
            self.context[variable_name] = formatted_date
        else:
            # Initialize context if it doesn't exist
            self.context = {variable_name: formatted_date}

        logger.info(f"Generated date: {formatted_date} and stored as '{variable_name}'")

        return {
            'generated_date': formatted_date,
            'variable_name': variable_name,
            'date_spec': date_spec
        }

    def _handle_select_datetime(self, params: Dict) -> Any:
        """Handle date-time picker selection with both date and time components"""
        datetime_value = params.get('datetime', '')
        element_desc = params.get('element', '')

        # Check if datetime_value is a variable reference
        if datetime_value.startswith('${') and datetime_value.endswith('}'):
            var_name = datetime_value[2:-1]
            if hasattr(self, 'context') and var_name in self.context:
                datetime_value = self.context[var_name]
                logger.info(f"Using stored datetime value: {datetime_value}")

        logger.info(f"Selecting datetime '{datetime_value}' in '{element_desc}' field")

        # Find the datetime picker input field
        datetime_input_selectors = [
            # Label-based selectors
            f'label:has-text("{element_desc}") + div input',
            f'label:has-text("{element_desc}") ~ div input',
            f'div:has(label:has-text("{element_desc}")) input',

            # Ant Design specific
            f'.ant-form-item:has(label:has-text("{element_desc}")) input.ant-picker-input',
            f'.ant-form-item:has(label:has-text("{element_desc}")) .ant-picker input',

            # Generic patterns
            f'input[placeholder*="date" i]:near(:text("{element_desc}"))',
            f'input[class*="picker" i]:near(:text("{element_desc}"))',
        ]

        element = None
        for selector in datetime_input_selectors:
            try:
                elements = self.page.locator(selector).all()
                for el in elements:
                    if el.is_visible():
                        element = el
                        logger.debug(f"Found datetime input with selector: {selector}")
                        break
                if element:
                    break
            except:
                continue

        if not element:
            # Use AI finder as fallback
            screenshot = self.page.screenshot()
            element_info = self.ai_finder.find_element(self.page, element_desc + " date time picker", screenshot)
            if element_info and element_info.get('selector'):
                element = self.page.locator(element_info['selector'])
            else:
                raise Exception(f"DateTime picker field '{element_desc}' not found")

        # Strategy 1: Try direct input first
        try:
            element.click()
            # Clear existing value
            element.click(click_count=3)  # Triple click to select all
            self.page.keyboard.press('Delete')

            # Type the new datetime
            element.fill(datetime_value)

            # Press Enter to confirm
            self.page.keyboard.press('Enter')

            # Small wait for the picker to process
            time.sleep(0.5)

            logger.info(f"DateTime selected using direct input: {datetime_value}")
            return {'datetime': datetime_value, 'field': element_desc}

        except Exception as e:
            logger.debug(f"Direct input failed: {e}, trying picker UI")

        # Strategy 2: Use the picker UI
        try:
            # Parse the datetime
            import datetime
            dt = None
            datetime_formats = [
                '%Y/%m/%d %H:%M',  # 2025/06/05 01:00
                '%Y-%m-%d %H:%M',  # 2025-06-05 01:00
                '%d/%m/%Y %H:%M',  # 05/06/2025 01:00
                '%m/%d/%Y %H:%M',  # 06/05/2025 01:00
            ]

            for fmt in datetime_formats:
                try:
                    dt = datetime.datetime.strptime(datetime_value, fmt)
                    break
                except:
                    continue

            if not dt:
                raise Exception(f"Could not parse datetime format: {datetime_value}")

            # Click to open picker
            element.click()
            time.sleep(0.5)

            # For Ant Design datetime picker, try to select date first
            year = dt.year
            month = dt.strftime('%b')  # Short month name
            day = str(dt.day)
            hour = str(dt.hour).zfill(2)
            minute = str(dt.minute).zfill(2)

            # Select the date
            # Try to click on the day
            day_selector = f'.ant-picker-cell-inner:text-is("{day}")'
            days = self.page.locator(day_selector).all()
            for day_elem in days:
                if day_elem.is_visible() and day_elem.is_enabled():
                    parent_classes = day_elem.evaluate("el => el.parentElement.className || ''")
                    if 'ant-picker-cell-disabled' not in parent_classes:
                        day_elem.click()
                        break

            time.sleep(0.3)

            # Now handle time selection
            # Look for time panel
            time_panel_selectors = [
                '.ant-picker-time-panel',
                '.ant-picker-time-panel-column',
                '[class*="time-panel"]',
            ]

            time_panel_found = False
            for panel_sel in time_panel_selectors:
                if self.page.locator(panel_sel).count() > 0:
                    time_panel_found = True
                    break

            if time_panel_found:
                # Select hour
                hour_selector = f'.ant-picker-time-panel-column:first-child li:has-text("{hour}")'
                hour_elem = self.page.locator(hour_selector).first
                if hour_elem.is_visible():
                    hour_elem.click()
                    time.sleep(0.2)

                # Select minute
                minute_selector = f'.ant-picker-time-panel-column:nth-child(2) li:has-text("{minute}")'
                minute_elem = self.page.locator(minute_selector).first
                if minute_elem.is_visible():
                    minute_elem.click()
                    time.sleep(0.2)

            # Click OK or confirm button
            ok_selectors = [
                'button:has-text("OK")',
                'button:has-text("Ok")',
                'button:has-text("Confirm")',
                '.ant-picker-ok button',
            ]

            for ok_sel in ok_selectors:
                try:
                    ok_btn = self.page.locator(ok_sel).first
                    if ok_btn.is_visible():
                        ok_btn.click()
                        break
                except:
                    continue

            logger.info(f"DateTime selected using picker UI: {datetime_value}")
            return {'datetime': datetime_value, 'field': element_desc}

        except Exception as e:
            logger.error(f"DateTime selection failed: {e}")
            raise Exception(f"Could not select datetime '{datetime_value}' in field '{element_desc}'")

    def _handle_select_date(self, params: Dict) -> Any:
        """Handle date picker selection"""
        date_value = params.get('date', '')
        element_desc = params.get('element', '')

        logger.info(f"Selecting date '{date_value}' in '{element_desc}' field")

        # Parse the date to understand the format
        import datetime
        date_formats = [
            '%Y-%m-%d',  # 2024-12-25
            '%d/%m/%Y',  # 25/12/2024
            '%m/%d/%Y',  # 12/25/2024
            '%d-%m-%Y',  # 25-12-2024
            '%Y/%m/%d',  # 2024/12/25
            '%d %B %Y',  # 25 December 2024
            '%B %d, %Y',  # December 25, 2024
            '%d %b %Y',  # 25 Dec 2024
            '%b %d, %Y',  # Dec 25, 2024
        ]

        parsed_date = None
        for fmt in date_formats:
            try:
                parsed_date = datetime.datetime.strptime(date_value, fmt)
                break
            except:
                continue

        if not parsed_date:
            logger.warning(f"Could not parse date '{date_value}', will try to input as-is")

        # Find the date picker input field
        date_input_selectors = [
            # Label-based selectors
            f'label:has-text("{element_desc}") + div input',
            f'label:has-text("{element_desc}") ~ div input',
            f'div:has(label:has-text("{element_desc}")) input',

            # Ant Design specific
            f'.ant-form-item:has(label:has-text("{element_desc}")) input.ant-picker-input',
            f'.ant-form-item:has(label:has-text("{element_desc}")) .ant-picker input',

            # Generic date picker patterns
            f'input[placeholder*="date" i]:near(:text("{element_desc}"))',
            f'input[type="date"]:near(:text("{element_desc}"))',
            f'input[class*="date" i]:near(:text("{element_desc}"))',
            f'input[class*="picker" i]:near(:text("{element_desc}"))',

            # Material UI patterns
            f'.MuiTextField-root:has-text("{element_desc}") input',
            f'.MuiDatePicker-root:near(:text("{element_desc}")) input',

            # Bootstrap patterns
            f'.form-group:has(label:has-text("{element_desc}")) input[type="date"]',
            f'.form-group:has(label:has-text("{element_desc}")) input.datepicker',
        ]

        element = None
        for selector in date_input_selectors:
            try:
                elements = self.page.locator(selector).all()
                for el in elements:
                    if el.is_visible():
                        element = el
                        logger.debug(f"Found date input with selector: {selector}")
                        break
                if element:
                    break
            except:
                continue

        if not element:
            # Use AI finder as fallback
            screenshot = self.page.screenshot()
            element_info = self.ai_finder.find_element(self.page, element_desc + " date picker", screenshot)
            if element_info and element_info.get('selector'):
                element = self.page.locator(element_info['selector'])
            else:
                raise Exception(f"Date picker field '{element_desc}' not found")

        # Strategy 1: Try direct input (works for HTML5 date inputs and some modern pickers)
        try:
            element.click()
            element.clear()
            element.fill(date_value)

            # Press Tab or Enter to confirm
            self.page.keyboard.press('Tab')
            logger.info(f"Date selected using direct input: {date_value}")
            return {'date': date_value, 'field': element_desc}
        except:
            logger.debug("Direct input failed, trying calendar selection")

        # Strategy 2: Click and use calendar popup
        try:
            element.click()
            time.sleep(0.5)  # Wait for calendar to open

            # Check if calendar popup is visible
            calendar_selectors = [
                '.ant-picker-dropdown:visible',
                '.ant-calendar:visible',
                '.MuiPickersCalendar-root:visible',
                '.datepicker-dropdown:visible',
                '.ui-datepicker:visible',
                '[role="dialog"]:has(.calendar)',
                '[role="dialog"]:has([class*="picker"])',
            ]

            calendar_found = False
            for cal_selector in calendar_selectors:
                if self.page.locator(cal_selector).count() > 0:
                    calendar_found = True
                    logger.debug(f"Found calendar popup: {cal_selector}")
                    break

            if calendar_found and parsed_date:
                # Navigate to the correct month/year if needed
                current_year = datetime.datetime.now().year
                target_year = parsed_date.year
                target_month = parsed_date.strftime('%B')  # Full month name
                target_day = str(parsed_date.day)

                # Try to select year first (if year selector exists)
                year_selectors = [
                    f'.ant-picker-year-btn:has-text("{target_year}")',
                    f'.ant-picker-header-year-btn',
                    f'[title*="year" i]',
                    f'.year-select',
                ]

                for year_sel in year_selectors:
                    try:
                        year_btn = self.page.locator(year_sel).first
                        if year_btn.is_visible():
                            year_btn.click()
                            time.sleep(0.3)
                            # Select the target year
                            self.page.locator(f'[title="{target_year}"]').first.click()
                            time.sleep(0.3)
                            break
                    except:
                        continue

                # Try to select month
                month_selectors = [
                    f'.ant-picker-month-btn:has-text("{target_month}")',
                    f'.ant-picker-header-month-btn',
                    f'[title*="month" i]',
                    f'.month-select',
                ]

                for month_sel in month_selectors:
                    try:
                        month_btn = self.page.locator(month_sel).first
                        if month_btn.is_visible():
                            month_btn.click()
                            time.sleep(0.3)
                            # Select the target month
                            self.page.locator(f'[title*="{target_month}" i]').first.click()
                            time.sleep(0.3)
                            break
                    except:
                        continue

                # Select the day
                day_selectors = [
                    f'.ant-picker-cell-inner:text-is("{target_day}")',
                    f'.ant-picker-calendar-date:text-is("{target_day}")',
                    f'[role="gridcell"] [aria-label*="{target_day}"]',
                    f'.ui-datepicker-calendar td:has-text("{target_day}")',
                    f'button:text-is("{target_day}")',
                    f'[aria-label*="{parsed_date.strftime("%B %d, %Y")}" i]',
                ]

                for day_sel in day_selectors:
                    try:
                        # Find all matching days and select the one that's not disabled
                        days = self.page.locator(day_sel).all()
                        for day in days:
                            if day.is_visible() and day.is_enabled():
                                # Check if it's not from previous/next month
                                parent_classes = day.evaluate("el => el.parentElement.className || ''")
                                if 'disabled' not in parent_classes and 'other-month' not in parent_classes:
                                    day.click()
                                    logger.info(f"Selected date from calendar: {date_value}")
                                    time.sleep(0.5)
                                    return {'date': date_value, 'field': element_desc}
                    except:
                        continue

            # If calendar selection failed, try typing again
            element.click()
            self.page.keyboard.press('Control+a' if os.name != 'darwin' else 'Meta+a')
            self.page.keyboard.type(date_value)
            self.page.keyboard.press('Enter')

        except Exception as e:
            logger.error(f"Date selection failed: {e}")
            raise Exception(f"Could not select date '{date_value}' in field '{element_desc}'")

        return {'date': date_value, 'field': element_desc}

    def _handle_select_date_range(self, params: Dict) -> Any:
        """Handle date range picker selection"""
        start_date = params.get('start_date', '')
        end_date = params.get('end_date', '')
        element_desc = params.get('element', '')

        # Check if dates are variable references
        if start_date.startswith('${') and start_date.endswith('}'):
            var_name = start_date[2:-1]
            if hasattr(self, 'context') and var_name in self.context:
                start_date = self.context[var_name]
                logger.info(f"Using stored start date value: {start_date}")

        if end_date.startswith('${') and end_date.endswith('}'):
            var_name = end_date[2:-1]
            if hasattr(self, 'context') and var_name in self.context:
                end_date = self.context[var_name]
                logger.info(f"Using stored end date value: {end_date}")

        logger.info(f"Selecting date range '{start_date}' to '{end_date}' in '{element_desc}' field")

        # Find the date range picker
        range_picker_selectors = [
            # Ant Design range picker
            f'.ant-form-item:has(label:has-text("{element_desc}")) .ant-picker-range',
            f'.ant-form-item:has(label:has-text("{element_desc}")) .ant-picker[class*="range"]',
            f'label:has-text("{element_desc}") ~ div .ant-picker-range',
            f'label:has-text("{element_desc}") + div .ant-picker-range',

            # More specific Ant Design patterns
            f'.ant-form-item:has(label:text-is("{element_desc}")) .ant-picker-range',
            f'.ant-row:has(label:has-text("{element_desc}")) .ant-picker-range',

            # Generic patterns
            f'[class*="range-picker" i]:near(:text("{element_desc}"))',
            f'[class*="date-range" i]:near(:text("{element_desc}"))',
            f'div:has(label:has-text("{element_desc}")) [class*="range"]',
            f'div:has(label:has-text("{element_desc}")) .ant-picker',
        ]

        element = None
        for selector in range_picker_selectors:
            try:
                el = self.page.locator(selector).first
                if el.is_visible():
                    element = el
                    logger.debug(f"Found date range picker with selector: {selector}")
                    break
            except:
                continue

        if not element:
            # Try AI finder as fallback
            screenshot = self.page.screenshot()
            element_info = self.ai_finder.find_element(self.page, element_desc + " date range picker", screenshot)
            if element_info and element_info.get('selector'):
                element = self.page.locator(element_info['selector'])
            else:
                raise Exception(f"Date range picker '{element_desc}' not found")

        # Click the range picker to open it
        element.click()
        time.sleep(0.5)

        # Strategy 1: Try to find and fill start/end inputs directly
        try:
            # For Ant Design range picker, there are usually two input elements
            inputs = element.locator('input').all()

            if len(inputs) >= 2:
                start_input = inputs[0]
                end_input = inputs[1]

                # Fill start date
                start_input.click()
                # Clear existing value
                start_input.click(click_count=3)  # Triple click to select all
                self.page.keyboard.press('Delete')
                start_input.fill(start_date)

                # Tab to end date
                self.page.keyboard.press('Tab')
                time.sleep(0.3)

                # Fill end date
                end_input.click()
                end_input.click(click_count=3)  # Triple click to select all
                self.page.keyboard.press('Delete')
                end_input.fill(end_date)

                # Press Enter to confirm
                self.page.keyboard.press('Enter')

                # Wait for picker to close
                time.sleep(0.5)

                logger.info(f"Date range selected: {start_date} to {end_date}")
                return {'start_date': start_date, 'end_date': end_date, 'field': element_desc}

        except Exception as e:
            logger.debug(f"Direct input method failed: {e}")

        # Strategy 2: Alternative approach using sequential fills
        try:
            # Click the picker again if needed
            if not self.page.locator('.ant-picker-dropdown:visible').count():
                element.click()
                time.sleep(0.5)

            # Type start date
            self.page.keyboard.type(start_date)
            time.sleep(0.3)

            # Press Tab or Enter to move to end date
            self.page.keyboard.press('Tab')
            time.sleep(0.3)

            # Type end date
            self.page.keyboard.type(end_date)
            time.sleep(0.3)

            # Press Enter to confirm
            self.page.keyboard.press('Enter')

            logger.info(f"Date range selected using keyboard: {start_date} to {end_date}")
            return {'start_date': start_date, 'end_date': end_date, 'field': element_desc}

        except Exception as e:
            logger.debug(f"Keyboard input method failed: {e}")

        raise Exception(f"Could not select date range in field '{element_desc}'")

    def cleanup(self):
        """Cleanup resources"""
        if self.api_executor:
            asyncio.run(self.api_executor.cleanup())