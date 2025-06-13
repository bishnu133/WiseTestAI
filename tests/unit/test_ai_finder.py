"""Unit tests for AI element finder"""
import pytest
from unittest.mock import Mock, MagicMock
from src.core.ai_element_finder import AIElementFinder


def test_pattern_matching():
    finder = AIElementFinder(model_type='pattern')

    # Mock page
    page = Mock()
    page.url = "http://example.com"

    # Mock element
    element = Mock()
    element.count.return_value = 1
    element.bounding_box.return_value = {'x': 100, 'y': 200, 'width': 100, 'height': 50}

    # Mock locator
    locator = Mock()
    locator.first = element
    page.locator.return_value = locator

    result = finder._pattern_match(page, 'click the "Submit" button')

    assert result is not None
    assert result['type'] == 'button'
    assert 'Submit' in result['selector']