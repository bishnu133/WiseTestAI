"""
AI-based element finder using lightweight models
Supports YOLO-World for zero-shot object detection
"""

import json
import numpy as np
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import cv2
import base64
from PIL import Image
import io
import re

class AIElementFinder:
    """
    AI-powered element detection with caching and fallback strategies
    """

    def __init__(self, model_type='yolo-world', cache_manager=None):
        self.model_type = model_type
        self.cache_manager = cache_manager
        self.element_cache = {}
        self.model = None
        self._initialize_model()

    def _initialize_model(self):
        """Initialize the AI model based on type"""
        if self.model_type == 'yolo-world':
            # Use YOLO-World for zero-shot detection
            # This is a lightweight model that doesn't require GPU
            try:
                from ultralytics import YOLO
                # Download nano version for efficiency
                self.model = YOLO('yolov8n-world.pt')
                self.model.set_classes(["button", "input", "link", "text", "image",
                                      "dropdown", "checkbox", "radio", "tab"])
            except:
                print("YOLO-World not available, falling back to pattern matching")
                self.model_type = 'pattern'
        elif self.model_type == 'pattern':
            # Use pattern matching as fallback
            self.model = None

    def find_element(self, page, description: str, screenshot=None) -> Optional[Dict]:
        """
        Find element using AI or pattern matching

        Args:
            page: Playwright page object
            description: Natural language description of element
            screenshot: Optional screenshot for AI processing

        Returns:
            Dictionary with element info or None
        """
        # Check cache first
        cache_key = f"{page.url}:{description}"
        if self.cache_manager and cache_key in self.element_cache:
            cached = self.element_cache[cache_key]
            # Verify element still exists
            try:
                element = page.locator(cached['selector'])
                if element.count() > 0:
                    return cached
            except:
                pass

        # Try pattern matching in main frame first
        element_info = self._pattern_match(page, description)
        if element_info:
            self._cache_element(cache_key, element_info)
            return element_info

        # Try pattern matching in iframes
        try:
            iframes = page.locator('iframe').all()
            for iframe_element in iframes:
                try:
                    frame = iframe_element.content_frame()
                    if frame:
                        element_info = self._pattern_match(frame, description)
                        if element_info:
                            element_info['in_iframe'] = True
                            self._cache_element(cache_key, element_info)
                            return element_info
                except:
                    continue
        except:
            pass

        # Try AI detection if available
        if self.model and screenshot:
            element_info = self._ai_detect(screenshot, description)
            if element_info:
                self._cache_element(cache_key, element_info)
                return element_info

        return None

    def _ai_detect(self, screenshot, description: str) -> Optional[Dict]:
        """Use AI model to detect elements"""
        try:
            # Convert screenshot to numpy array
            if isinstance(screenshot, str):
                # Base64 encoded
                img_data = base64.b64decode(screenshot)
                img = Image.open(io.BytesIO(img_data))
            else:
                img = screenshot

            # Run inference
            results = self.model(img, conf=0.5)

            # Process results
            for r in results:
                boxes = r.boxes
                if boxes is not None:
                    for box in boxes:
                        # Get class name
                        cls_id = int(box.cls)
                        cls_name = self.model.names[cls_id]

                        # Match with description
                        if self._matches_description(cls_name, description):
                            x1, y1, x2, y2 = box.xyxy[0].tolist()
                            center_x = (x1 + x2) / 2
                            center_y = (y1 + y2) / 2

                            return {
                                'type': cls_name,
                                'position': {'x': center_x, 'y': center_y},
                                'bounds': {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2},
                                'confidence': float(box.conf),
                                'selector': None  # Will use coordinates
                            }
        except Exception as e:
            print(f"AI detection error: {e}")

        return None

    def _pattern_match(self, page, description: str) -> Optional[Dict]:
        """
        Smart pattern matching based on description
        Uses multiple strategies to find elements
        """
        description_lower = description.lower()

        # Clean up the description - remove extra quotes and field/button suffixes
        description_clean = description.strip('"\'')
        description_clean = re.sub(r'\s*(field|button|input|textbox)$', '', description_clean, flags=re.IGNORECASE)

        # Extract key information
        patterns = {
            'button': r'(button|btn|click|submit|save|cancel|close|add|delete|remove)',
            'input': r'(input|field|textbox|enter|type|fill|search)',
            'link': r'(link|href|navigate|go to)',
            'dropdown': r'(dropdown|select|choose|option|listbox|combobox)',
            'checkbox': r'(checkbox|check|tick|mark)',
            'radio': r'(radio button|radio|option button|select one)',
            'text': r'(text|label|heading|title|contains)'
        }

        element_type = None
        for elem_type, pattern in patterns.items():
            if re.search(pattern, description_lower):
                element_type = elem_type
                break

        # Extract text content - use the cleaned description as the text to search for
        text_content = description_clean

        # Build selectors based on element type and content
        selectors = []

        if element_type == 'button':
            if text_content:
                selectors.extend([
                    # Try submit/button inputs first (most specific)
                    f'input[type="submit"][value*="{text_content}" i]',
                    f'input[type="button"][value*="{text_content}" i]',
                    # Then actual button elements
                    f'button:has-text("{text_content}")',
                    # Role-based buttons
                    f'[role="button"]:has-text("{text_content}")',
                    # Link styled as button
                    f'a.button:has-text("{text_content}")',
                    f'a.btn:has-text("{text_content}")',
                    # Generic class-based buttons
                    f'*[class*="btn"]:has-text("{text_content}")',
                    f'*[class*="button"]:has-text("{text_content}")'
                ])
            else:
                selectors.extend(['button', '[role="button"]', 'input[type="submit"]', 'input[type="button"]'])

        elif element_type == 'dropdown' or 'dropdown' in description_lower or 'select' in description_lower:
            # For dropdown/select elements - try multiple UI framework patterns
            if text_content:
                selectors.extend([
                    # Native HTML select elements (most specific)
                    f'select[name*="{text_content.lower().replace(" ", "")}" i]',
                    f'select[id*="{text_content.lower().replace(" ", "")}" i]',
                    f'select[aria-label*="{text_content}" i]',

                    # Ant Design selects
                    f'.ant-select:has-text("{text_content}")',
                    f'.ant-select[aria-label*="{text_content}" i]',
                    f'input[role="combobox"][id*="{text_content.lower().replace(" ", "-")}" i]',

                    # Material UI selects
                    f'.MuiSelect-root:has-text("{text_content}")',
                    f'.MuiInputBase-root:has-text("{text_content}")',
                    f'div[role="button"][aria-haspopup="listbox"]:has-text("{text_content}")',

                    # Bootstrap selects
                    f'.custom-select:has-text("{text_content}")',
                    f'.form-select:has-text("{text_content}")',
                    f'.dropdown-toggle:has-text("{text_content}")',

                    # React Select
                    f'.react-select__control:has-text("{text_content}")',
                    f'.Select__control:has-text("{text_content}")',

                    # Generic ARIA patterns
                    f'[role="combobox"][aria-label*="{text_content}" i]',
                    f'[role="listbox"][aria-label*="{text_content}" i]',
                    f'[role="button"][aria-haspopup="listbox"]:has-text("{text_content}")',

                    # Generic class patterns
                    f'div[class*="select"][aria-label*="{text_content}" i]',
                    f'div[class*="dropdown"][aria-label*="{text_content}" i]',
                    f'*[class*="select"]:has-text("{text_content}")',
                    f'*[class*="dropdown"]:has-text("{text_content}")',

                    # Label associations
                    f'label:has-text("{text_content}") + select',
                    f'label:has-text("{text_content}") + .ant-select',
                    f'label:has-text("{text_content}") + .MuiSelect-root',
                    f'label:has-text("{text_content}") + div[class*="select"]',
                    f'label:has-text("{text_content}") + div[class*="dropdown"]',
                    f'label:has-text("{text_content}") + [role="combobox"]',

                    # Fallback generic selectors
                    '.ant-select',
                    '.MuiSelect-root',
                    '.custom-select',
                    '.form-select',
                    '.react-select__control',
                    'select',
                    'input[role="combobox"]',
                    '[role="combobox"]',
                    '[role="listbox"]',
                    '[aria-haspopup="listbox"]'
                ])
            else:
                selectors.extend([
                    'select',
                    '.ant-select',
                    '.MuiSelect-root',
                    '.custom-select',
                    '.form-select',
                    '[role="combobox"]',
                    '[role="listbox"]'
                ])

        elif element_type == 'input' or element_type is None:
            # For input fields, try multiple strategies
            if text_content:
                # Try different ways to find input fields
                selectors.extend([
                    # By placeholder
                    f'input[placeholder*="{text_content}" i]',
                    # By aria-label
                    f'input[aria-label*="{text_content}" i]',
                    # By id
                    f'input[id*="{text_content.lower().replace(" ", "")}" i]',
                    f'input[id*="{text_content.lower().replace(" ", "_")}" i]',
                    f'input[id*="{text_content.lower().replace(" ", "-")}" i]',
                    # By name
                    f'input[name*="{text_content.lower().replace(" ", "")}" i]',
                    f'input[name*="{text_content.lower().replace(" ", "_")}" i]',
                    f'input[name*="{text_content.lower().replace(" ", "-")}" i]',
                    # By label
                    f'label:has-text("{text_content}") + input',
                    f'label:has-text("{text_content}") input',
                    # Generic input near text
                    f'input:near(:text("{text_content}"))',
                    # Try with different variations
                    f'input[placeholder*="{text_content.lower()}" i]',
                    f'input[aria-label*="{text_content.lower()}" i]',

                    # Rich text editor patterns - Add these
                    f'div.ant-form-item:has(label:has-text("{text_content}")) [contenteditable="true"]',
                    f'div.ant-form-item:has(label:has-text("{text_content}")) .ql-editor',
                    f'div:has(label:has-text("{text_content}")) [contenteditable="true"]',
                    f'div:has(label:has-text("{text_content}")) .ql-editor',
                    f'label:has-text("{text_content}") ~ div [contenteditable="true"]',
                    f'label:has-text("{text_content}") ~ div .ql-editor',
                    f'[aria-label*="{text_content}" i][contenteditable="true"]',
                    f'.editor-container:near(:text("{text_content}"))',
                    f'[role="textbox"]:near(:text("{text_content}"))',
                    # For cases where the label is separate from the editor
                    f'div:below(:text("{text_content}"), 100) [contenteditable="true"]',
                    f'div:below(:text("{text_content}"), 100) .ql-editor'
                ])

                # Special handling for common field names
                if 'username' in text_content.lower() or 'user' in text_content.lower():
                    selectors.extend([
                        'input[type="text"][name*="user" i]',
                        'input[type="text"][id*="user" i]',
                        'input[type="email"]',
                        'input[autocomplete="username"]'
                    ])
                elif 'password' in text_content.lower() or 'pass' in text_content.lower():
                    selectors.extend([
                        'input[type="password"]',
                        'input[name*="pass" i]',
                        'input[id*="pass" i]',
                        'input[autocomplete="current-password"]'
                    ])
                elif 'email' in text_content.lower():
                    selectors.extend([
                        'input[type="email"]',
                        'input[name*="email" i]',
                        'input[id*="email" i]'
                    ])
                elif 'search' in text_content.lower():
                    selectors.extend([
                        # Generic search selectors
                        'input[type="search"]',
                        'input#search',
                        '#search',
                        'input[name*="search" i]',
                        'input[id*="search" i]',
                        'input[placeholder*="search" i]',
                        'input[aria-label*="search" i]',
                        'input[role="searchbox"]',
                        '.search-input',
                        '.search-field',
                        'input.search'
                    ])
            else:
                selectors.extend(['input[type="text"]', 'input:not([type="hidden"])'])

        elif element_type == 'link':
            if text_content:
                selectors.extend([
                    f'a:has-text("{text_content}")',
                    f'a[href*="{text_content.lower().replace(" ", "")}" i]'
                ])
            else:
                selectors.append('a')

        # Try each selector
        for selector in selectors:
            try:
                elements = page.locator(selector)
                count = elements.count()

                if count > 0:
                    # If multiple elements found, try to find the most visible one
                    for i in range(count):
                        element = elements.nth(i)
                        if element.is_visible():
                            box = element.bounding_box()
                            if box:
                                return {
                                    'type': element_type or 'unknown',
                                    'selector': f"{selector} >> nth={i}",
                                    'position': {'x': box['x'] + box['width']/2, 'y': box['y'] + box['height']/2},
                                    'bounds': box,
                                    'confidence': 0.8
                                }
            except:
                continue

        # Generic text search as last resort
        if text_content:
            try:
                # First try to find as button/input
                if element_type == 'button' or 'button' in description_lower:
                    # Try role-based selector first
                    role_element = page.get_by_role("button", name=text_content)
                    if role_element.count() > 0:
                        return {
                            'type': 'button',
                            'selector': f'[role="button"]:has-text("{text_content}")',
                            'position': {'x': 0, 'y': 0},
                            'bounds': None,
                            'confidence': 0.9
                        }

                # Then try generic text search
                elements = page.locator(f'text="{text_content}"')
                count = elements.count()

                if count > 0:
                    # If multiple elements, prefer clickable ones
                    for i in range(count):
                        element = elements.nth(i)
                        tag_name = element.evaluate("el => el.tagName.toLowerCase()")

                        # Prefer button/input/a elements
                        if tag_name in ['button', 'input', 'a'] or element.get_attribute('role') == 'button':
                            box = element.bounding_box()
                            if box:
                                return {
                                    'type': 'button' if tag_name in ['button', 'input'] else tag_name,
                                    'selector': f'text="{text_content}" >> nth={i}',
                                    'position': {'x': box['x'] + box['width']/2, 'y': box['y'] + box['height']/2},
                                    'bounds': box,
                                    'confidence': 0.8
                                }

                    # If no clickable element found, return the first visible one
                    element = elements.first
                    if element.is_visible():
                        box = element.bounding_box()
                        if box:
                            return {
                                'type': 'text',
                                'selector': f'text="{text_content}" >> nth=0',
                                'position': {'x': box['x'] + box['width']/2, 'y': box['y'] + box['height']/2},
                                'bounds': box,
                                'confidence': 0.6
                            }
            except Exception as e:
                print(f"Error in text search: {e}")
                pass

        return None

    def _matches_description(self, element_type: str, description: str) -> bool:
        """Check if element type matches description"""
        description_lower = description.lower()
        type_keywords = {
            'button': ['button', 'click', 'submit', 'press'],
            'input': ['input', 'field', 'enter', 'type'],
            'link': ['link', 'navigate', 'href'],
            'dropdown': ['dropdown', 'select', 'choose'],
            'checkbox': ['checkbox', 'check', 'tick'],
            'radio': ['radio', 'option'],
            'text': ['text', 'label', 'contains']
        }

        if element_type in type_keywords:
            return any(keyword in description_lower for keyword in type_keywords[element_type])
        return False

    def _cache_element(self, key: str, element_info: Dict):
        """Cache element information"""
        if self.cache_manager:
            self.element_cache[key] = element_info
            self.cache_manager.save_cache(key, element_info)

    def click_at_position(self, page, position: Dict):
        """Click at specific coordinates"""
        page.mouse.click(position['x'], position['y'])

    def get_element_by_selector(self, page, selector: str):
        """Get element using selector"""
        return page.locator(selector).first