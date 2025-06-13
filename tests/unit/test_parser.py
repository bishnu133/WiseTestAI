"""Unit tests for feature parser"""
import pytest
from src.parser.feature_parser import FeatureParser, StepType


def test_parse_simple_step():
    parser = FeatureParser("features")
    action, params = parser._parse_step_text('I click the "Login" button')

    assert action == 'click'
    assert params['element'] == 'Login'


def test_parse_input_step():
    parser = FeatureParser("features")
    action, params = parser._parse_step_text('I enter "john@example.com" in the "email" field')

    assert action == 'input'
    assert params['value'] == 'john@example.com'
    assert params['element'] == 'email'