"""
Debug the specific feature file parsing
"""
import sys
import os
sys.path.insert(0, os.getcwd())

from src.parser.feature_parser import FeatureParser
from pathlib import Path

# Find and parse the login feature
parser = FeatureParser("features")
features = parser.parse_features(['@smoke'])

print(f"Found {len(features)} features with @smoke tag")

for feature in features:
    print(f"\nFeature: {feature.name}")
    print(f"Feature tags: {feature.tags}")

    for scenario in feature.scenarios:
        print(f"\n  Scenario: {scenario.name}")
        print(f"  Scenario tags: {scenario.tags}")

        for i, step in enumerate(scenario.steps):
            print(f"\n    Step {i}: {step.text}")
            print(f"      Type: {step.type}")
            print(f"      Action: {step.action}")
            print(f"      Parameters: {step.parameters}")
            print(f"      Has data table: {step.data_table is not None}")
            if step.data_table:
                print(f"      Data table rows: {len(step.data_table)}")
                for row in step.data_table:
                    print(f"        {row}")

# Also check if the pattern matches
print("\n" + "="*50)
print("Testing pattern matching for table step:")
step_text = "the table should show:"
action, params = parser._parse_step_text(step_text)
print(f"Step text: '{step_text}'")
print(f"Parsed action: {action}")
print(f"Parsed params: {params}")

# Check all table patterns
print("\n" + "="*50)
print("Checking all table verification patterns:")
import re
patterns = parser.action_patterns['verify_table']['patterns']
for i, pattern in enumerate(patterns):
    if re.match(pattern, step_text, re.IGNORECASE):
        print(f"Pattern {i} MATCHES: {pattern}")
    else:
        print(f"Pattern {i} no match: {pattern}")