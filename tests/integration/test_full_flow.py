"""Integration tests for complete flow"""
import pytest
from pathlib import Path
from src.core.config_manager import ConfigManager
from src.parser.feature_parser import FeatureParser


def test_config_loading():
    config_manager = ConfigManager("config/config.yaml", "dev")
    config = config_manager.load_config()

    assert 'project' in config
    assert 'browser' in config
    assert config['browser']['type'] == 'chromium'


def test_feature_parsing():
    # Create test feature file
    test_feature = '''
Feature: Test Feature

  @smoke
  Scenario: Test Scenario
    Given I navigate to the home page
    When I click the "Login" button
    Then I should see "Welcome"
    '''

    # Write to temp file
    Path("temp_features").mkdir(exist_ok=True)
    with open("temp_features/test.feature", "w") as f:
        f.write(test_feature)

    parser = FeatureParser("temp_features")
    features = parser.parse_features()

    assert len(features) == 1
    assert features[0].name == "Test Feature"
    assert len(features[0].scenarios) == 1
    assert len(features[0].scenarios[0].steps) == 3

    # Cleanup
    Path("temp_features/test.feature").unlink()
    Path("temp_features").rmdir()