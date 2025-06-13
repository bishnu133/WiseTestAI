"""
Feature parser with NLP capabilities
Parses Gherkin feature files and maps to executable steps
"""

import re
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

class StepType(Enum):
    GIVEN = "given"
    WHEN = "when"
    THEN = "then"
    AND = "and"
    BUT = "but"

@dataclass
class Step:
    type: StepType
    text: str
    action: str
    parameters: Dict
    line_number: int
    data_table: Optional[List[List[str]]] = None

@dataclass
class Scenario:
    name: str
    description: str
    steps: List[Step]
    tags: List[str]
    examples: Optional[Dict] = None
    line_number: int = 0

@dataclass
class Feature:
    name: str
    description: str
    scenarios: List[Scenario]
    tags: List[str]
    background: Optional[Scenario] = None
    file_path: str = ""

class FeatureParser:
    """Parse Gherkin feature files with NLP understanding"""

    def __init__(self, features_dir: str):
        self.features_dir = Path(features_dir)
        self.action_patterns = self._initialize_action_patterns()

    def _initialize_action_patterns(self) -> Dict:
        """Initialize NLP patterns for step mapping"""
        return {
            # Navigation patterns
            'navigate': {
                'patterns': [
                    r'(?:i )?(?:open|navigate to|go to|visit|access) (?:the )?(?:url |page |site )?(.+)',
                    r'(?:i am|user is) on (?:the )?(.+) page',
                    r'(?:the )?(?:url|page) is (.+)'
                ],
                'action': 'navigate',
                'params': ['url']
            },

            # Select/Dropdown patterns - MUST BE BEFORE CLICK
            'select': {
                'patterns': [
                    r'(?:i )?select\s+["\']*(.+?)["\']*\s+from\s+(?:the\s+)?["\']*(.+?)["\']*\s*(?:dropdown|select|list|listbox|combobox)?$',
                    r'(?:i )?select\s+["\']*(.+?)["\']*\s+in\s+(.+?)$',
                    r'(?:i )?choose\s+["\']*(.+?)["\']*\s+(?:from|in)\s+(?:the\s+)?["\']*(.+?)["\']*$',
                    r'(?:from|in)\s+(?:the\s+)?["\']*(.+?)["\']*\s+(?:dropdown\s+|select\s+)?(?:i\s+)?select\s+["\']*(.+?)["\']*$'
                ],
                'action': 'select',
                'params': ['option', 'element']
            },

            # Click patterns
            'click': {
                'patterns': [
                    r'(?:i )?click(?:\s+on)?\s+(?:the\s+)?["\']*(.+?)["\']*(?:\s*(?:button|link|element))?$',
                    r'(?:i )?(?:press|tap)\s+(?:the\s+)?["\']*(.+?)["\']*(?:\s*(?:button|link))?$',
                    r'(?:the )?(?:user )?clicks?\s+(?:on\s+)?(?:the\s+)?["\']*(.+?)["\']*$'
                ],
                'action': 'click',
                'params': ['element']
            },

            # Input patterns
            'input': {
                'patterns': [
                    r'(?:i )?(?:enter|type|input|fill|write)\s+["\']*(.+?)["\']*\s+(?:in|into)\s+(?:the\s+)?["\']*(.+?)["\']*(?:\s*(?:field|input|textbox))?(?:\s*\[force ai\])?$',
                    r'(?:i )?(?:enter|type|input|fill|write)\s+["\']*(.+?)["\']*\s+(?:in|into)\s+(?:the\s+)?["\']*(.+?)["\']*(?:\s*(?:field|input|textbox))?$',
                    r'(?:i )?(?:fill|enter)\s+(?:the\s+)?["\']*(.+?)["\']*(?:\s*(?:field|input))?\s+with\s+["\']*(.+?)["\']*$',
                    r'(?:the )?(?:user )?(?:enters|types|inputs)\s+["\']*(.+?)["\']*\s+(?:in|into)\s+(?:the\s+)?["\']*(.+?)["\']*$'
                ],
                'action': 'input',
                'params': ['value', 'element']
            },

            # Checkbox patterns
            'checkbox': {
                'patterns': [
                    # Main patterns for checkbox selection
                    r'(?:i )?(?:check|tick|mark|select)\s+(?:the\s+)?["\']*(.+?)["\']*\s+(?:checkbox|check\s*box)$',
                    r'(?:i )?(?:uncheck|untick|unmark|deselect)\s+(?:the\s+)?["\']*(.+?)["\']*\s+(?:checkbox|check\s*box)$',
                    r'(?:i )?(?:select|choose)\s+["\']*(.+?)["\']*\s+checkbox$',
                    r'(?:i )?(?:deselect)\s+["\']*(.+?)["\']*\s+checkbox$',
                    r'(?:the\s+)?["\']*(.+?)["\']*\s+(?:checkbox|check\s*box)\s+(?:should\s+)?(?:be\s+)?(checked|unchecked)$',
                    r'(?:i )?(?:enable|disable)\s+(?:the\s+)?["\']*(.+?)["\']*\s+(?:checkbox|check\s*box)$',

                    # Support for various wordings
                    r'(?:i )?(?:click|toggle)\s+(?:on\s+)?(?:the\s+)?["\']*(.+?)["\']*\s+(?:checkbox|check\s*box)$',
                    r'(?:i )?(?:set|make)\s+(?:the\s+)?["\']*(.+?)["\']*\s+(?:checkbox|check\s*box)\s+(?:to\s+)?(checked|unchecked)$',
                ],
                'action': 'checkbox',
                'params': ['element', 'state']
            },

            # Radio button patterns
            'radio': {
                'patterns': [
                    r'(?:i )?select\s+["\']*(.+?)["\']*\s+radio\s*(?:button)?$',
                    r'(?:i )?(?:choose|pick|select)\s+(?:the\s+)?["\']*(.+?)["\']*\s+(?:radio\s+)?option$',
                    r'(?:i )?(?:click|select)\s+(?:on\s+)?(?:the\s+)?["\']*(.+?)["\']*\s+radio\s*(?:button)?$',
                    r'(?:the )?radio\s*(?:button)?\s+["\']*(.+?)["\']*\s+is\s+selected$',
                    r'(?:i )?(?:select|choose)\s+radio\s*(?:button)?\s+["\']*(.+?)["\']*$'
                ],
                'action': 'radio',
                'params': ['element']
            },

            # Verification patterns
            'verify_text': {
                'patterns': [
                    r'(?:i )?(?:should\s+)?see\s+(?:the\s+)?(?:text\s+|message\s+)?["\']*(.+?)["\']*$',
                    r'(?:the )?(?:page|screen)\s+(?:should\s+)?(?:contain|display|show)s?\s+(?:the\s+)?(?:text\s+|message\s+)?["\']*(.+?)["\']*$',
                    r'(?:i )?(?:verify|check|validate)\s+(?:that\s+)?(?:the\s+)?(?:text\s+|message\s+)?["\']*(.+?)["\']*\s+is\s+(?:displayed|shown|visible)$'
                ],
                'action': 'verify_text',
                'params': ['text']
            },

            # Element visibility patterns
            'verify_element': {
                'patterns': [
                    r'(?:i )?(?:should\s+)?see\s+(?:the\s+)?(?:element\s+|button\s+|link\s+|field\s+)?["\']*(.+?)["\']*\s+element$',
                    r'(?:i )?(?:should\s+)?see\s+(?:the\s+)?["\']*(.+?)["\']*\s+(?:element|button|link|field)$',
                    r'(?:the )?(?:element\s+|button\s+|link\s+|field\s+)?["\']*(.+?)["\']*\s+(?:should\s+)?(?:be|is)\s+(?:displayed|visible|shown)$',
                    r'(?:i )?(?:verify|check)\s+(?:that\s+)?(?:the\s+)?["\']*(.+?)["\']*\s+is\s+(?:displayed|visible|present)$'
                ],
                'action': 'verify_element',
                'params': ['element']
            },

            # Wait patterns
            'wait': {
                'patterns': [
                    r'(?:i )?wait\s+(?:for\s+)?(\d+)\s+(?:seconds?|secs?|milliseconds?|ms)$',
                    r'(?:i )?wait\s+(?:for|until)\s+(?:the\s+)?(?:element\s+|button\s+|link\s+)?["\']*(.+?)["\']*\s+(?:is|to\s+be)\s+(?:displayed|visible|shown)$',
                    r'(?:i )?wait\s+for\s+text\s+["\']*(.+?)["\']*\s+to\s+(?:load|appear|be\s+visible)$',
                    r'(?:i )?pause\s+(?:for\s+)?(\d+)\s+(?:seconds?|secs?)$'
                ],
                'action': 'wait',
                'params': ['duration', 'element', 'text']
            },

            # Search patterns
            'search': {
                'patterns': [
                    r'(?:i )?search\s+(?:for\s+|with\s+)?(?:text\s+)?["\']*(.+?)["\']*$',
                    r'(?:i )?search\s+(?:for\s+|with\s+)?["\']*(.+?)["\']*\s+in\s+(?:the\s+)?["\']*(.+?)["\']*(?:\s+field)?$',
                    r'(?:i )?(?:enter|type)\s+["\']*(.+?)["\']*\s+in\s+(?:the\s+)?search\s+(?:box|field|bar)$',
                    r'(?:i )?search\s+in\s+(?:the\s+)?["\']*(.+?)["\']*\s+(?:field\s+)?(?:for|with)\s+["\']*(.+?)["\']*$'
                ],
                'action': 'search',
                'params': ['query', 'field']
            },

            # Table verification patterns
            'verify_table': {
                'patterns': [
                    r'(?:i )?(?:verify|check|validate)\s+(?:that\s+)?(?:the\s+)?table\s+(?:data|contains|shows).*$',
                    r'(?:i )?(?:verify|check|validate)\s+(?:the\s+)?["\']*(.+?)["\']*\s+table\s+(?:data|contains|shows).*$',
                    r'(?:the\s+)?table\s+(?:should\s+)?(?:contain|show|display)s?.*$',
                    r'(?:the\s+)?["\']*(.+?)["\']*\s+table\s+(?:should\s+)?(?:contain|show|display)s?.*$',
                    r'(?:i )?(?:should\s+)?see\s+(?:the\s+)?following\s+(?:data\s+)?in\s+(?:the\s+)?table.*$',
                    r'(?:i )?validate\s+(?:the\s+)?table\s+(?:with\s+)?(?:the\s+)?following\s+(?:data|values).*$'
                ],
                'action': 'verify_table',
                'params': ['table']
            },

            # Screenshot patterns
            'screenshot': {
                'patterns': [
                    r'(?:i )?(?:take|capture)\s+(?:a\s+)?screenshot(?:\s+(?:of|for)\s+["\']*(.+?)["\']*)?$',
                    r'(?:i )?screenshot\s+(?:the\s+)?(?:page|screen)(?:\s+as\s+["\']*(.+?)["\']*)?$'
                ],
                'action': 'screenshot',
                'params': ['name']
            },

            # Section state verification patterns
            'verify_section_state': {
                'patterns': [
                    r'(?:i )?(?:verify|check|validate)\s+(?:that\s+)?(?:the\s+)?["\']*(.+?)["\']*\s+(?:section|step|tab)\s+is\s+(enabled|disabled|active|inactive)$',
                    r'(?:the\s+)?["\']*(.+?)["\']*\s+(?:section|step|tab)\s+(?:should\s+)?(?:be|is)\s+(enabled|disabled|active|inactive)$',
                    r'(?:i )?(?:should\s+)?see\s+(?:that\s+)?(?:the\s+)?["\']*(.+?)["\']*\s+(?:section|step|tab)\s+is\s+(enabled|disabled|active|inactive)$',
                ],
                'action': 'verify_section_state',
                'params': ['section', 'state']
            },

            'verify_sections_state': {
                'patterns': [
                    r'(?:i )?(?:verify|check|validate)\s+(?:the\s+)?(?:following\s+)?sections?\s+(?:states?|status)?:?$',
                    r'(?:the\s+)?(?:following\s+)?sections?\s+(?:should\s+)?(?:have|be)\s+(?:the\s+)?(?:following\s+)?(?:states?|status)?:?$',
                    r'(?:i )?(?:should\s+)?see\s+(?:the\s+)?(?:following\s+)?sections?\s+(?:with\s+)?(?:states?|status)?:?$',
                ],
                'action': 'verify_sections_state',
                'params': []
            },

            # Date picker patterns
            'select_date': {
                'patterns': [
                    r'(?:i )?(?:select|choose|pick|enter)\s+date\s+["\']*(.+?)["\']*\s+(?:in|for)\s+(?:the\s+)?["\']*(.+?)["\']*(?:\s+field)?$',
                    r'(?:i )?(?:select|set)\s+["\']*(.+?)["\']*\s+(?:as\s+)?(?:the\s+)?date\s+(?:in|for)\s+["\']*(.+?)["\']*$',
                    r'(?:i )?(?:enter|input|fill)\s+["\']*(.+?)["\']*\s+in\s+(?:the\s+)?["\']*(.+?)["\']*\s+date\s*(?:picker|field)?$',
                    r'(?:the\s+)?["\']*(.+?)["\']*\s+date\s+(?:should\s+)?be\s+["\']*(.+?)["\']*$',
                ],
                'action': 'select_date',
                'params': ['date', 'element']
            },

            # Date range picker patterns
            'select_date_range': {
                'patterns': [
                    # Main patterns for date range selection
                    r'(?:i )?(?:select|choose|pick)\s+date\s+range\s+["\']*(.+?)["\']*\s+to\s+["\']*(.+?)["\']*\s+(?:in|for)\s+(?:the\s+)?["\']*(.+?)["\']*(?:\s+field)?$',
                    r'(?:i )?(?:select|set)\s+["\']*(.+?)["\']*\s+to\s+["\']*(.+?)["\']*\s+(?:as\s+)?(?:the\s+)?date\s+range\s+(?:in|for)\s+["\']*(.+?)["\']*$',
                    r'(?:i )?(?:enter|input)\s+date\s+range\s+["\']*(.+?)["\']*\s+(?:to|-)\s+["\']*(.+?)["\']*\s+(?:in|for)\s+["\']*(.+?)["\']*$',
                    # Support for variable syntax
                    r'(?:i )?(?:select|choose|pick)\s+date\s+range\s+\$\{(.+?)\}\s+to\s+\$\{(.+?)\}\s+(?:in|for)\s+(?:the\s+)?["\']*(.+?)["\']*(?:\s+field)?$',
                ],
                'action': 'select_date_range',
                'params': ['start_date', 'end_date', 'element']
            },

            # Date generation patterns
            'generate_date': {
                'patterns': [
                    # Basic generation
                    r'(?:i )?generate\s+(?:a\s+)?date\s+["\']*(.+?)["\']*\s+(?:and\s+)?store\s+(?:it\s+)?as\s+["\']*(.+?)["\']*$',
                    r'(?:i )?(?:get|create)\s+(?:a\s+)?["\']*(.+?)["\']*\s+date\s+(?:and\s+)?store\s+(?:it\s+)?as\s+["\']*(.+?)["\']*$',
                    r'(?:i )?store\s+["\']*(.+?)["\']*\s+as\s+["\']*(.+?)["\']*$',

                    # With time specification
                    r'(?:i )?generate\s+(?:a\s+)?datetime\s+["\']*(.+?)["\']*\s+(?:and\s+)?store\s+(?:it\s+)?as\s+["\']*(.+?)["\']*$',
                    r'(?:i )?(?:get|create)\s+(?:a\s+)?["\']*(.+?)["\']*\s+datetime\s+(?:and\s+)?store\s+(?:it\s+)?as\s+["\']*(.+?)["\']*$',
                ],
                'action': 'generate_date',
                'params': ['date_spec', 'variable_name']
            },

            # DateTime picker patterns (replaces the simple date picker)
            'select_datetime': {
                'patterns': [
                    r'(?:i )?(?:select|choose|pick|enter)\s+datetime\s+["\']*(.+?)["\']*\s+(?:in|for)\s+(?:the\s+)?["\']*(.+?)["\']*(?:\s+field)?$',
                    r'(?:i )?(?:select|set)\s+["\']*(.+?)["\']*\s+(?:as\s+)?(?:the\s+)?datetime\s+(?:in|for)\s+["\']*(.+?)["\']*$',
                    r'(?:i )?(?:enter|input|fill)\s+["\']*(.+?)["\']*\s+in\s+(?:the\s+)?["\']*(.+?)["\']*\s+datetime\s*(?:picker|field)?$',

                    # Also match simple "date" since your picker includes time
                    r'(?:i )?(?:select|choose|pick|enter)\s+date\s+["\']*(.+?)["\']*\s+(?:in|for)\s+(?:the\s+)?["\']*(.+?)["\']*(?:\s+field)?$',
                    r'(?:i )?(?:enter|input|fill)\s+["\']*(.+?)["\']*\s+in\s+(?:the\s+)?["\']*(.+?)["\']*\s+date\s*(?:picker|field)?$',
                ],
                'action': 'select_datetime',
                'params': ['datetime', 'element']
            },

            # API Call patterns
            'call_api': {
                'patterns': [
                    r'(?:i )?call (?:the )?["\'](.*?)["\'] (?:api|API|endpoint)$',
                    r'(?:i )?(?:make|send|execute) (?:a )?(?:api|API) (?:call|request) (?:to )?["\'](.*?)["\']$'
                ],
                'action': 'call_api',
                'params': ['api_name']
            },

            # API Call with data patterns
            'call_api_with_data': {
                'patterns': [
                    r'(?:i )?call (?:the )?["\'](.*?)["\'] (?:api|API) with:?$',
                    r'(?:i )?(?:make|send) (?:a )?(?:api|API) (?:call|request) (?:to )?["\'](.*?)["\'] with:?$'
                ],
                'action': 'call_api_with_data',
                'params': ['api_name']
            },

            # API Authentication patterns
            'authenticate': {
                'patterns': [
                    r'(?:i )?authenticate with (?:username )?["\'](.*?)["\'] and (?:password )?["\'](.*?)["\']$',
                    r'(?:i )?login with (?:username )?["\'](.*?)["\'] and (?:password )?["\'](.*?)["\']$'
                ],
                'action': 'authenticate',
                'params': ['username', 'password']
            },

            'authenticate_with_env': {
                'patterns': [
                    r'(?:i )?authenticate using (?:the )?["\'](.*?)["\'] credentials$',
                    r'(?:i )?login using (?:the )?["\'](.*?)["\'] credentials$'
                ],
                'action': 'authenticate_with_env',
                'params': ['credential_key']
            },

            # API Response Validation patterns
            'verify_api_status': {
                'patterns': [
                    r'(?:the )?(?:api|API) response status (?:should be|is) (\d+)$',
                    r'(?:the )?(?:api|API) (?:should )?(?:return|respond with) (?:status )?(\d+)$'
                ],
                'action': 'verify_api_status',
                'params': ['status_code']
            },

            'verify_api_contains': {
                'patterns': [
                    r'(?:the )?(?:api|API) response (?:should )?contains? ["\'](.*?)["\']$',
                    r'(?:the )?response (?:should )?(?:contain|include)s? ["\'](.*?)["\']$'
                ],
                'action': 'verify_api_contains',
                'params': ['text']
            },

            'verify_api_field': {
                'patterns': [
                    r'(?:the )?(?:api|API) response field ["\'](.*?)["\'] (?:should be|equals) ["\'](.*?)["\']$',
                    r'(?:the )?field ["\'](.*?)["\'] (?:should be|equals) ["\'](.*?)["\']$'
                ],
                'action': 'verify_api_field',
                'params': ['field_path', 'expected_value']
            },

            'verify_api_response_table': {
                'patterns': [
                    r'(?:i )?verify (?:the )?(?:api|API) response matches:?$',
                    r'(?:the )?(?:api|API) response (?:should )?match(?:es)?:?$'
                ],
                'action': 'verify_api_response_table',
                'params': []
            },

            'verify_api_response_time': {
                'patterns': [
                    r'(?:the )?(?:api|API) response time should be less than (\d+(?:\.\d+)?) seconds?$',
                    r'(?:the )?response (?:should )?(?:take|complete) (?:less than|under) (\d+(?:\.\d+)?) seconds?$'
                ],
                'action': 'verify_api_response_time',
                'params': ['max_time']
            },

            # Store API Response patterns
            'store_api_field': {
                'patterns': [
                    r'(?:i )?store (?:the )?(?:api|API) response field ["\'](.*?)["\'] as ["\'](.*?)["\']$',
                    r'(?:i )?save (?:the )?field ["\'](.*?)["\'] as ["\'](.*?)["\']$'
                ],
                'action': 'store_api_field',
                'params': ['field_path', 'variable_name']
            },

            'store_api_response': {
                'patterns': [
                    r'(?:i )?store (?:the )?(?:api|API) response as ["\'](.*?)["\']$',
                    r'(?:i )?save (?:the )?response as ["\'](.*?)["\']$'
                ],
                'action': 'store_api_response',
                'params': ['variable_name']
            },

            'use_stored_value': {
                'patterns': [
                    r'(?:i )?use (?:the )?stored ["\'](.*?)["\'] (?:value )?(?:as|for) ["\'](.*?)["\']$'
                ],
                'action': 'use_stored_value',
                'params': ['stored_name', 'param_name']
            },

            # Wait for API patterns
            'wait_api': {
                'patterns': [
                    r'(?:i )?wait (\d+(?:\.\d+)?) seconds?(?: (?:before|after) (?:the )?(?:api|API) call)?$'
                ],
                'action': 'wait_api',
                'params': ['duration']
            },

            # File Upload patterns
            'upload_file': {
                'patterns': [
                    r'(?:i )?upload file ["\'](.*?)["\'] to ["\'](.*?)["\'] (?:api|API)$',
                    r'(?:i )?upload ["\'](.*?)["\'] to ["\'](.*?)["\'] (?:api|API)$'
                ],
                'action': 'upload_file',
                'params': ['file_path', 'api_name']
            },

            # Role-based Authentication patterns
            'authenticate_with_role': {
                'patterns': [
                    r'(?:i )?authenticate as (?:a )?["\'](.*?)["\'](?:\s+role)?$',
                    r'(?:i )?login as (?:a )?["\'](.*?)["\'](?:\s+role)?$',
                    r'(?:i )?(?:am|are) authenticated as (?:a )?["\'](.*?)["\']$'
                ],
                'action': 'authenticate_with_role',
                'params': ['role']
            },

            'login_as_role': {
                'patterns': [
                    r'(?:i )?(?:am logged in|log in|login) as (?:a )?["\'](.*?)["\'](?:\s+(?:user|role))?$',
                    r'(?:i )?sign in as (?:a )?["\'](.*?)["\'](?:\s+(?:user|role))?$'
                ],
                'action': 'login_as_role',
                'params': ['role']
            }
        }

    def parse_features(self, tags: List[str] = None) -> List[Feature]:
        """Parse all feature files in directory"""
        features = []

        # Find all .feature files
        feature_files = list(self.features_dir.glob("**/*.feature"))

        for feature_file in feature_files:
            feature = self._parse_feature_file(feature_file)
            if feature:
                # Filter by tags if provided
                if tags:
                    filtered_scenarios = []
                    for scenario in feature.scenarios:
                        if any(tag in scenario.tags for tag in tags):
                            filtered_scenarios.append(scenario)
                    if filtered_scenarios:
                        feature.scenarios = filtered_scenarios
                        features.append(feature)
                else:
                    features.append(feature)

        return features

    def _parse_feature_file(self, file_path: Path) -> Optional[Feature]:
        """Parse a single feature file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            feature = None
            current_scenario = None
            current_step = None
            background = None
            in_examples = False
            examples_data = []
            tags = []  # Initialize tags list

            for line_num, line in enumerate(lines, 1):
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue

                # Parse tags
                if line.startswith('@'):
                    tags = [tag.strip() for tag in line.split() if tag.startswith('@')]
                    continue

                # Parse feature
                if line.startswith('Feature:'):
                    feature_name = line[8:].strip()
                    feature = Feature(
                        name=feature_name,
                        description="",
                        scenarios=[],
                        tags=tags.copy() if tags else [],
                        file_path=str(file_path)
                    )
                    # Don't clear tags here - keep them for inheritance

                # Parse background
                elif line.startswith('Background:'):
                    background = Scenario(
                        name="Background",
                        description="",
                        steps=[],
                        tags=[]
                    )
                    current_scenario = background

                # Parse scenario
                elif line.startswith('Scenario:') or line.startswith('Scenario Outline:'):
                    if current_scenario and current_scenario != background:
                        feature.scenarios.append(current_scenario)

                    scenario_name = line.split(':', 1)[1].strip()
                    # Combine feature tags with scenario tags
                    scenario_tags = tags.copy() if tags else []
                    if feature and feature.tags:
                        # Add feature tags that aren't already in scenario tags
                        for ftag in feature.tags:
                            if ftag not in scenario_tags:
                                scenario_tags.append(ftag)

                    current_scenario = Scenario(
                        name=scenario_name,
                        description="",
                        steps=[],
                        tags=scenario_tags,
                        line_number=line_num
                    )
                    tags = []  # Clear tags after using them
                    in_examples = False

                # Parse examples
                elif line.startswith('Examples:'):
                    in_examples = True
                    examples_data = []

                # Parse example data
                elif in_examples and line.startswith('|'):
                    row_data = [cell.strip() for cell in line.split('|')[1:-1]]
                    examples_data.append(row_data)

                # Parse steps
                elif any(line.startswith(prefix) for prefix in ['Given ', 'When ', 'Then ', 'And ', 'But ']):
                    step_parts = line.split(' ', 1)
                    step_type = StepType(step_parts[0].lower())
                    step_text = step_parts[1] if len(step_parts) > 1 else ""

                    # Parse the step into action and parameters
                    action, params = self._parse_step_text(step_text)

                    step = Step(
                        type=step_type,
                        text=step_text,
                        action=action,
                        parameters=params,
                        line_number=line_num
                    )

                    if current_scenario:
                        current_scenario.steps.append(step)
                    current_step = step

                # Parse data tables
                elif line.startswith('|') and current_step and not in_examples:
                    if current_step.data_table is None:
                        current_step.data_table = []
                    row_data = [cell.strip() for cell in line.split('|')[1:-1]]
                    current_step.data_table.append(row_data)

            # Add last scenario
            if current_scenario and current_scenario != background:
                if in_examples and examples_data:
                    current_scenario.examples = self._process_examples(examples_data)
                feature.scenarios.append(current_scenario)

            # Set background
            if background:
                feature.background = background

            return feature

        except Exception as e:
            print(f"Error parsing feature file {file_path}: {e}")
            return None

    def _parse_step_text(self, step_text: str) -> Tuple[str, Dict]:
        """Parse step text using NLP patterns"""
        # step_text = step_text.strip()
        original_step_text = step_text.strip()

        # Check for force AI flag FIRST, before any pattern matching
        force_ai = False
        if '[force ai]' in original_step_text.lower():
            force_ai = True
            # Remove the force AI flag from the text for pattern matching
            step_text = original_step_text.replace('[force ai]', '').replace('[FORCE AI]', '').replace('[Force AI]',
                                                                                                       '').strip()
        else:
            step_text = original_step_text

        # Try to match against known patterns - ORDER MATTERS!
        # Check select patterns BEFORE click patterns
        pattern_order = ['navigate', 'select_date_range', 'checkbox', 'select', 'radio', 'click', 'input',
                         'generate_date', 'select_datetime', 'select_date',
                         'verify_text', 'verify_element', 'verify_section_state', 'verify_sections_state',
                         'wait', 'search', 'verify_table', 'screenshot',
                         'call_api_with_data', 'call_api', 'authenticate', 'authenticate_with_env',
                         'authenticate_with_role', 'login_as_role',
                         'verify_api_status', 'verify_api_contains', 'verify_api_field',
                         'verify_api_response_table', 'verify_api_response_time',
                         'store_api_field', 'store_api_response', 'use_stored_value',
                         'wait_api', 'upload_file']

        for action_type in pattern_order:
            pattern_info = self.action_patterns[action_type]
            for pattern in pattern_info['patterns']:
                match = re.match(pattern, step_text, re.IGNORECASE)
                if match:
                    params = {}
                    groups = match.groups()

                    # Map matched groups to parameter names
                    for i, param_name in enumerate(pattern_info['params']):
                        if i < len(groups) and groups[i]:
                            params[param_name] = groups[i].strip('"\'')

                    # Add force_ai flag if present
                    if force_ai:
                        params['force_ai'] = True

                    # Map matched groups to parameter names
                    for i, param_name in enumerate(pattern_info['params']):
                        if i < len(groups) and groups[i]:
                            params[param_name] = groups[i].strip('"\'')

                    # For checkbox action, ensure state is set if not captured by pattern
                    if action_type == 'checkbox' and 'state' not in params:
                        # Default to checked based on the verb used
                        if any(word in step_text.lower() for word in
                               ['uncheck', 'untick', 'unmark', 'deselect', 'disable']):
                            params['state'] = 'unchecked'
                        else:
                            params['state'] = 'checked'

                    return pattern_info['action'], params

        # If no pattern matches, try to extract basic info
        return self._fallback_parse(step_text)

    def _fallback_parse(self, step_text: str) -> Tuple[str, Dict]:
        """Fallback parsing when no pattern matches"""
        # Look for quoted strings
        quoted_strings = re.findall(r'["\']([^"\']+)["\']', step_text)

        # Determine action based on keywords
        step_lower = step_text.lower()

        # Check for select FIRST
        if any(word in step_lower for word in ['select', 'choose', 'pick']) and ' in ' in step_lower:
            if len(quoted_strings) >= 1:
                # Extract the element part after "in"
                in_pos = step_lower.rfind(' in ')
                element_part = step_text[in_pos + 4:].strip()
                return 'select', {'option': quoted_strings[0], 'element': element_part}
            else:
                return 'select', {'option': '', 'element': step_text}
        elif any(word in step_lower for word in ['select', 'choose', 'pick']) and ' from ' in step_lower:
            if len(quoted_strings) >= 2:
                return 'select', {'option': quoted_strings[0], 'element': quoted_strings[1]}
            else:
                return 'select', {'option': quoted_strings[0] if quoted_strings else '', 'element': step_text}
        elif any(word in step_lower for word in ['click', 'press', 'tap']):
            return 'click', {'element': quoted_strings[0] if quoted_strings else step_text}
        elif any(word in step_lower for word in ['enter', 'type', 'input', 'fill']):
            if len(quoted_strings) >= 2:
                return 'input', {'value': quoted_strings[0], 'element': quoted_strings[1]}
            else:
                return 'input', {'value': quoted_strings[0] if quoted_strings else '', 'element': step_text}
        elif any(word in step_lower for word in ['search']):
            return 'search', {'query': quoted_strings[0] if quoted_strings else step_text}
        elif any(word in step_lower for word in ['see', 'verify', 'check', 'should']):
            return 'verify_text', {'text': quoted_strings[0] if quoted_strings else step_text}
        elif any(word in step_lower for word in ['navigate', 'go', 'open', 'visit']):
            return 'navigate', {'url': quoted_strings[0] if quoted_strings else step_text}
        elif any(word in step_lower for word in ['wait']):
            return 'wait', {'text': quoted_strings[0] if quoted_strings else step_text}
        elif any(word in step_lower for word in ['table', 'verify table', 'validate table']):
            if 'table' in step_lower:
                # Extract table name if specified
                if quoted_strings:
                    return 'verify_table', {'table': quoted_strings[0]}
                else:
                    return 'verify_table', {}
        else:
            return 'unknown', {'text': step_text}

    def _process_examples(self, examples_data: List[List[str]]) -> Dict:
        """Process examples table into dictionary"""
        if not examples_data or len(examples_data) < 2:
            return {}

        headers = examples_data[0]
        examples = {'headers': headers, 'rows': []}

        for row in examples_data[1:]:
            if len(row) == len(headers):
                examples['rows'].append(dict(zip(headers, row)))

        return examples