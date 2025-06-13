#!/usr/bin/env python3
"""
WiseTestRunner - AI-Powered Scriptless Test Automation Framework
Main entry point for executing BDD scenarios using AI-based element detection
"""

import click
import sys
import os
from pathlib import Path
from src.core.config_manager import ConfigManager
from src.core.browser_manager import BrowserManager
from src.parser.feature_parser import FeatureParser
from src.executor.test_executor import TestExecutor
from src.reports.html_reporter import HTMLReporter
from src.utils.logger import setup_logger

# Initialize logger
logger = setup_logger(__name__)


@click.command()
@click.option('--env', '-e', default='dev', help='Environment to run tests (dev/staging/prod)')
@click.option('--tags', '-t', multiple=True, help='Tags to filter scenarios')
@click.option('--features', '-f', default='features', help='Path to features directory')
@click.option('--headless', is_flag=True, help='Run in headless mode')
@click.option('--parallel', '-p', default=1, type=int, help='Number of parallel executions')
@click.option('--report', '-r', default='html', help='Report format (html/json/both)')
@click.option('--config', '-c', default='config/config.yaml', help='Path to config file')
@click.option('--browser', '-b', default='chromium', help='Browser to use (chromium/firefox/webkit)')
@click.option('--slow-mo', default=0, type=int, help='Slow down execution by milliseconds')
@click.option('--screenshot', is_flag=True, help='Take screenshots on failure')
@click.option('--video', is_flag=True, help='Record video of execution')
@click.option('--cache', default=True, is_flag=True, help='Use element cache')
@click.option('--ai-model', default='yolo-world', help='AI model to use (yolo-world/mobilenet/none)')
def main(env, tags, features, headless, parallel, report, config, browser,
         slow_mo, screenshot, video, cache, ai_model):
    """
    AITestRunner - Execute BDD scenarios without writing automation scripts

    Examples:
        # Run all tests in dev environment
        python run.py --env dev

        # Run specific tagged scenarios
        python run.py --env prod --tags @smoke @critical

        # Run with video recording
        python run.py --env staging --video --screenshot
    """

    try:
        logger.info(f"Starting AITestRunner v1.0.0")
        logger.info(f"Environment: {env}")
        logger.info(f"Browser: {browser}")
        logger.info(f"AI Model: {ai_model}")

        # Load configuration
        config_manager = ConfigManager(config, env)
        config_data = config_manager.load_config()

        # Parse feature files
        feature_parser = FeatureParser(features)
        test_suites = feature_parser.parse_features(tags)

        if not test_suites:
            logger.warning("No test scenarios found matching the criteria")
            return

        logger.info(f"Found {len(test_suites)} test suites to execute")

        # Initialize browser manager
        browser_options = {
            'headless': headless,
            'browser': browser,
            'slow_mo': slow_mo,
            'screenshot': screenshot,
            'video': video
        }

        browser_manager = BrowserManager(browser_options)

        # Initialize test executor
        executor = TestExecutor(
            config_data=config_data,
            browser_manager=browser_manager,
            use_cache=cache,
            ai_model=ai_model,
            parallel=parallel
        )

        # Execute tests
        results = executor.execute_suites(test_suites)

        # Generate reports
        reporter = HTMLReporter() if report in ['html', 'both'] else None
        if reporter:
            report_path = reporter.generate_report(results)
            logger.info(f"Report generated: {report_path}")

        # Exit with appropriate code
        failed_count = sum(1 for r in results if r['status'] == 'failed')
        if failed_count > 0:
            logger.error(f"Tests completed with {failed_count} failures")
            sys.exit(1)
        else:
            logger.info("All tests passed successfully!")
            sys.exit(0)

    except Exception as e:
        logger.error(f"Execution failed: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    main()