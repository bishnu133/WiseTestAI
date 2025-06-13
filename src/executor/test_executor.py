"""Main test execution orchestrator"""
import concurrent.futures
from typing import List, Dict, Any
from src.core.browser_manager import BrowserManager
from src.core.ai_element_finder import AIElementFinder
from src.core.cache_manager import CacheManager
from src.executor.step_executor import StepExecutor
from src.parser.feature_parser import Feature, Scenario
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class TestExecutor:
    """Orchestrates test execution"""

    def __init__(self, config_data: Dict, browser_manager: BrowserManager,
                 use_cache: bool = True, ai_model: str = 'yolo-world',
                 parallel: int = 1):
        self.config = config_data
        self.browser_manager = browser_manager
        self.use_cache = use_cache
        self.ai_model = ai_model
        self.parallel = parallel
        self.results = []

        # Initialize cache manager
        self.cache_manager = CacheManager() if use_cache else None
        if self.cache_manager and 'project' in config_data:
            self.cache_manager.set_project(config_data['project'].get('name', 'default'))

    def execute_suites(self, test_suites: List[Feature]) -> List[Dict]:
        """Execute all test suites"""
        all_scenarios = []

        # Collect all scenarios
        for feature in test_suites:
            for scenario in feature.scenarios:
                all_scenarios.append({
                    'feature': feature,
                    'scenario': scenario
                })

        # Execute scenarios
        if self.parallel > 1:
            # Parallel execution
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.parallel) as executor:
                futures = []
                for item in all_scenarios:
                    future = executor.submit(self._execute_scenario,
                                             item['feature'], item['scenario'])
                    futures.append(future)

                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    self.results.append(result)
        else:
            # Sequential execution
            for item in all_scenarios:
                result = self._execute_scenario(item['feature'], item['scenario'])
                self.results.append(result)

        return self.results

    def _execute_scenario(self, feature: Feature, scenario: Scenario) -> Dict:
        """Execute a single scenario"""
        logger.info(f"Executing scenario: {scenario.name}")

        # Start browser
        page = self.browser_manager.start()

        # Initialize AI finder
        ai_finder = AIElementFinder(self.ai_model, self.cache_manager)

        # Initialize step executor
        step_executor = StepExecutor(page, ai_finder, self.config)

        scenario_result = {
            'feature': feature.name,
            'scenario': scenario.name,
            'status': 'passed',
            'steps': [],
            'error': None,
            'duration': 0
        }

        try:
            # Execute background steps if any
            if feature.background:
                for step in feature.background.steps:
                    # Create parameters with data table if present
                    params = step.parameters.copy() if step.parameters else {}
                    if hasattr(step, 'data_table') and step.data_table:
                        params['data_table'] = step.data_table

                    step_result = step_executor.execute_step(step.action, params)
                    if step_result['status'] == 'failed':
                        raise Exception(f"Background step failed: {step.text}")

            # Execute scenario steps
            for step in scenario.steps:
                logger.info(f"Executing step: {step.text}")

                # Create parameters with data table if present
                params = step.parameters.copy() if step.parameters else {}
                if hasattr(step, 'data_table') and step.data_table:
                    params['data_table'] = step.data_table

                step_result = step_executor.execute_step(step.action, params)
                step_result['text'] = step.text
                scenario_result['steps'].append(step_result)

                if step_result['status'] == 'failed':
                    scenario_result['status'] = 'failed'
                    scenario_result['error'] = step_result.get('error')
                    break

        except Exception as e:
            logger.error(f"Scenario execution failed: {str(e)}")
            scenario_result['status'] = 'failed'
            scenario_result['error'] = str(e)

        finally:
            # Take final screenshot
            if scenario_result['status'] == 'failed':
                screenshot = self.browser_manager.take_screenshot(
                    f"{feature.name}_{scenario.name}_failed".replace(' ', '_')
                )
                scenario_result['screenshot'] = screenshot

            # Stop browser
            self.browser_manager.stop()

        return scenario_result