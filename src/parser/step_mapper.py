"""
Step mapper for custom step definitions and mappings
Maps natural language steps to executable actions
"""

import re
from typing import Dict, List, Tuple, Callable, Any
from dataclasses import dataclass
from src.parser.feature_parser import Step
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class StepMapping:
    """Represents a step mapping definition"""
    pattern: str
    action: str
    param_mapping: Dict[str, str]
    compiled_pattern: re.Pattern = None

    def __post_init__(self):
        """Compile the regex pattern"""
        self.compiled_pattern = re.compile(self.pattern, re.IGNORECASE)


class StepMapper:
    """Maps parsed steps to executable actions with custom mappings support"""

    def __init__(self):
        self.custom_mappings = []
        self.builtin_mappings = self._initialize_builtin_mappings()
        self.action_aliases = self._initialize_action_aliases()

    def _initialize_builtin_mappings(self) -> List[StepMapping]:
        """Initialize built-in step mappings"""
        return [
            # Login shortcuts
            StepMapping(
                pattern=r'I (?:am )?logged in as "([^"]+)"',
                action='login',
                param_mapping={'username': '$1'}
            ),
            StepMapping(
                pattern=r'I (?:am )?logged in with (admin|user|guest) credentials',
                action='login_with_role',
                param_mapping={'role': '$1'}
            ),

            # Navigation shortcuts
            StepMapping(
                pattern=r'I (?:am on|go to|navigate to) the (\w+) page',
                action='navigate_to_page',
                param_mapping={'page': '$1'}
            ),

            # Form filling
            StepMapping(
                pattern=r'I fill in the following:?',
                action='fill_form_table',
                param_mapping={'use_data_table': 'true'}
            ),
            StepMapping(
                pattern=r'I fill (?:in )?the "([^"]+)" form with:?',
                action='fill_named_form',
                param_mapping={'form_name': '$1', 'use_data_table': 'true'}
            ),

            # Waiting shortcuts
            StepMapping(
                pattern=r'I wait for the page to load',
                action='wait_for_load',
                param_mapping={'state': 'networkidle'}
            ),
            StepMapping(
                pattern=r'the page (?:has )?(?:finished )?loading',
                action='wait_for_load',
                param_mapping={'state': 'domcontentloaded'}
            ),

            # Verification shortcuts
            StepMapping(
                pattern=r'I should be on the (\w+) page',
                action='verify_page',
                param_mapping={'page': '$1'}
            ),
            StepMapping(
                pattern=r'the "([^"]+)" (?:field|input) should (?:contain|have value) "([^"]+)"',
                action='verify_field_value',
                param_mapping={'field': '$1', 'expected_value': '$2'}
            ),

            # Element state
            StepMapping(
                pattern=r'the "([^"]+)" (?:button|element) should be (enabled|disabled)',
                action='verify_element_state',
                param_mapping={'element': '$1', 'state': '$2'}
            ),
            StepMapping(
                pattern=r'I should see (\d+) "([^"]+)" (?:elements|items)',
                action='verify_element_count',
                param_mapping={'count': '$1', 'element': '$2'}
            ),

            # Complex actions
            StepMapping(
                pattern=r'I add (\d+) "([^"]+)" to (?:the )?cart',
                action='add_to_cart',
                param_mapping={'quantity': '$1', 'product': '$2'}
            ),
            StepMapping(
                pattern=r'I search for "([^"]+)"',
                action='search',
                param_mapping={'query': '$1'}
            ),
            StepMapping(
                pattern=r'I upload (?:the )?file "([^"]+)"',
                action='upload_file',
                param_mapping={'file_path': '$1'}
            ),

            # Mouse actions
            StepMapping(
                pattern=r'I hover over (?:the )?"([^"]+)"',
                action='hover',
                param_mapping={'element': '$1'}
            ),
            StepMapping(
                pattern=r'I double[- ]?click (?:on )?(?:the )?"([^"]+)"',
                action='double_click',
                param_mapping={'element': '$1'}
            ),
            StepMapping(
                pattern=r'I right[- ]?click (?:on )?(?:the )?"([^"]+)"',
                action='right_click',
                param_mapping={'element': '$1'}
            ),

            # Keyboard actions
            StepMapping(
                pattern=r'I press (?:the )?(.+) key',
                action='press_key',
                param_mapping={'key': '$1'}
            ),
            StepMapping(
                pattern=r'I press (?:the )?key combination "([^"]+)"',
                action='key_combination',
                param_mapping={'keys': '$1'}
            ),

            # Scroll actions
            StepMapping(
                pattern=r'I scroll (up|down|to top|to bottom)',
                action='scroll',
                param_mapping={'direction': '$1'}
            ),
            StepMapping(
                pattern=r'I scroll to (?:the )?"([^"]+)"',
                action='scroll_to_element',
                param_mapping={'element': '$1'}
            ),

            # Frame/Window handling
            StepMapping(
                pattern=r'I switch to (?:the )?iframe "([^"]+)"',
                action='switch_to_iframe',
                param_mapping={'frame': '$1'}
            ),
            StepMapping(
                pattern=r'I switch to (?:the )?main frame',
                action='switch_to_main_frame',
                param_mapping={}
            ),
            StepMapping(
                pattern=r'I switch to (?:the )?new (?:window|tab)',
                action='switch_to_new_window',
                param_mapping={}
            ),
            StepMapping(
                pattern=r'I close (?:the )?current (?:window|tab)',
                action='close_window',
                param_mapping={}
            ),
        ]

    def _initialize_action_aliases(self) -> Dict[str, str]:
        """Initialize action aliases for flexibility"""
        return {
            'tap': 'click',
            'press': 'click',
            'choose': 'select',
            'pick': 'select',
            'write': 'input',
            'type': 'input',
            'fill': 'input',
            'check': 'verify_text',
            'validate': 'verify_text',
            'confirm': 'verify_text',
            'pause': 'wait',
            'sleep': 'wait',
        }

    def register_custom_mapping(self, pattern: str, action: str, param_mapping: Dict):
        """Register a custom step mapping"""
        mapping = StepMapping(pattern, action, param_mapping)
        self.custom_mappings.append(mapping)
        logger.info(f"Registered custom mapping: {pattern} -> {action}")

    def register_custom_mappings_from_config(self, mappings: List[Dict]):
        """Register multiple custom mappings from configuration"""
        for mapping_config in mappings:
            pattern = mapping_config.get('pattern')
            action = mapping_config.get('action')
            params = mapping_config.get('params', {})

            if pattern and action:
                self.register_custom_mapping(pattern, action, params)

    def get_action_for_step(self, step: Step) -> Tuple[str, Dict]:
        """Get executable action for a step"""
        # First check if we already have parsed action
        if step.action and step.action != 'unknown':
            # Apply aliases if needed
            action = self.action_aliases.get(step.action, step.action)
            return action, self._process_parameters(step.parameters, step)

        # Try custom mappings first (highest priority)
        for mapping in self.custom_mappings:
            match = mapping.compiled_pattern.match(step.text)
            if match:
                params = self._extract_parameters(match, mapping.param_mapping)
                # Add data table if present
                if step.data_table:
                    params['data_table'] = step.data_table
                return mapping.action, params

        # Try built-in mappings
        for mapping in self.builtin_mappings:
            match = mapping.compiled_pattern.match(step.text)
            if match:
                params = self._extract_parameters(match, mapping.param_mapping)
                # Add data table if present
                if step.data_table:
                    params['data_table'] = step.data_table
                return mapping.action, params

        # Return the original parsed action as fallback
        return step.action, self._process_parameters(step.parameters, step)

    def _extract_parameters(self, match: re.Match, param_mapping: Dict[str, str]) -> Dict:
        """Extract parameters from regex match"""
        params = {}
        groups = match.groups()

        for param_name, param_value in param_mapping.items():
            if param_value.startswith('$'):
                # Extract from regex group
                group_index = int(param_value[1:]) - 1
                if 0 <= group_index < len(groups):
                    params[param_name] = groups[group_index]
            else:
                # Static value
                params[param_name] = param_value

        return params

    def _process_parameters(self, params: Dict, step: Step) -> Dict:
        """Process and enhance parameters"""
        processed = params.copy()

        # Add data table if present
        if step.data_table:
            processed['data_table'] = step.data_table

        # Process special parameter values
        for key, value in processed.items():
            if isinstance(value, str):
                # Handle environment variables
                if value.startswith('${') and value.endswith('}'):
                    env_var = value[2:-1]
                    import os
                    processed[key] = os.environ.get(env_var, value)

                # Handle special keywords
                elif value.lower() in ['true', 'false']:
                    processed[key] = value.lower() == 'true'
                elif value.lower() in ['null', 'none']:
                    processed[key] = None

        return processed

    def get_available_actions(self) -> List[str]:
        """Get list of all available actions"""
        actions = set()

        # From custom mappings
        for mapping in self.custom_mappings:
            actions.add(mapping.action)

        # From built-in mappings
        for mapping in self.builtin_mappings:
            actions.add(mapping.action)

        # From action patterns (in feature_parser)
        actions.update(['navigate', 'click', 'input', 'select', 'checkbox',
                        'verify_text', 'verify_element', 'wait', 'screenshot'])

        return sorted(list(actions))

    def describe_mapping(self, pattern: str) -> Dict:
        """Describe what a pattern maps to"""
        # Check custom mappings
        for mapping in self.custom_mappings:
            if mapping.pattern == pattern:
                return {
                    'pattern': pattern,
                    'action': mapping.action,
                    'parameters': mapping.param_mapping,
                    'type': 'custom'
                }

        # Check built-in mappings
        for mapping in self.builtin_mappings:
            if mapping.pattern == pattern:
                return {
                    'pattern': pattern,
                    'action': mapping.action,
                    'parameters': mapping.param_mapping,
                    'type': 'builtin'
                }

        return None