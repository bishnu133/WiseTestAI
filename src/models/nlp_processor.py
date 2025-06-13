"""NLP processing for step understanding"""
import re
from typing import Dict, List, Tuple


class NLPProcessor:
    """Simple NLP processor for step parsing"""

    def __init__(self):
        self.action_keywords = {
            'navigate': ['open', 'go to', 'visit', 'navigate'],
            'click': ['click', 'press', 'tap', 'select'],
            'input': ['enter', 'type', 'fill', 'input'],
            'verify': ['see', 'verify', 'check', 'should'],
            'wait': ['wait', 'pause', 'sleep']
        }

    def extract_intent(self, text: str) -> str:
        """Extract action intent from text"""
        text_lower = text.lower()

        for action, keywords in self.action_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                return action

        return 'unknown'

    def extract_entities(self, text: str) -> Dict[str, str]:
        """Extract entities from text"""
        entities = {}

        # Extract quoted strings
        quoted = re.findall(r'["\']([^"\']+)["\']', text)
        if quoted:
            entities['target'] = quoted[0]
            if len(quoted) > 1:
                entities['value'] = quoted[1]

        # Extract numbers
        numbers = re.findall(r'\b(\d+)\b', text)
        if numbers:
            entities['number'] = numbers[0]

        return entities