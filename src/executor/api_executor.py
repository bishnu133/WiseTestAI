"""
src/executor/api_executor.py
Complete API Executor with enhanced logging, response time validation, and file upload support
"""

import json
import re
import time
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
import aiohttp
import asyncio
from jsonpath_ng import parse as jsonpath_parse
import yaml
from jinja2 import Template
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class APIExecutor:
    """Execute API calls based on configuration"""

    def __init__(self, config_path: str, env: str = 'dev'):
        self.env = env
        self.context = {}  # Store values between API calls
        self.auth_token = None
        self.session = None
        self.reporter = APITestReporter()

        # Load API configuration
        with open(config_path, 'r') as f:
            self.api_config = yaml.safe_load(f)

        # Get environment-specific settings
        self.env_config = self.api_config['environments'].get(env, {})
        self.base_url = self.env_config.get('base_url', '')
        self.timeout = self.env_config.get('timeout', 30)

        logger.info(f"API Executor initialized for environment: {env}")
        logger.info(f"Base URL: {self.base_url}")

    async def initialize(self):
        """Initialize async session"""
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def cleanup(self):
        """Cleanup resources"""
        if self.session:
            await self.session.close()

        # Generate final report
        report_path = f"reports/api_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        self.reporter.generate_html_report(report_path)
        logger.info(f"API test report generated: {report_path}")

    def store_value(self, key: str, value: Any):
        """Store a value in context for later use"""
        self.context[key] = value
        logger.debug(f"Stored {key} = {value}")

    def get_value(self, key: str, default: Any = None):
        """Get a value from context"""
        return self.context.get(key, default)

    def _resolve_variables(self, text: str) -> str:
        """Replace ${variable} placeholders with actual values"""
        if not isinstance(text, str):
            return text

        # Pattern to match ${variable} or ${variable:default}
        pattern = r'\$\{([^:}]+)(?::([^}]+))?\}'

        def replacer(match):
            var_name = match.group(1)
            default_value = match.group(2)

            # Check context first
            if var_name in self.context:
                return str(self.context[var_name])

            # Check for special variables
            if var_name == 'auth_token' and self.auth_token:
                return self.auth_token

            # Return default or raise error
            if default_value is not None:
                return default_value

            raise ValueError(f"Variable '{var_name}' not found in context")

        return re.sub(pattern, replacer, text)

    def _resolve_dict_variables(self, data: Dict) -> Dict:
        """Recursively resolve variables in a dictionary"""
        if not isinstance(data, dict):
            return data

        resolved = {}
        for key, value in data.items():
            if isinstance(value, str):
                resolved[key] = self._resolve_variables(value)
            elif isinstance(value, dict):
                resolved[key] = self._resolve_dict_variables(value)
            elif isinstance(value, list):
                resolved[key] = [self._resolve_variables(item) if isinstance(item, str) else item for item in value]
            else:
                resolved[key] = value

        return resolved

    def _get_api_config(self, api_name: str) -> Dict:
        """Get API configuration by name"""
        for category, apis in self.api_config['apis'].items():
            if api_name in apis:
                return apis[api_name]

        raise ValueError(f"API '{api_name}' not found in configuration")

    async def execute_api(self, api_name: str, test_name: str = None, **kwargs) -> Dict:
        """Execute an API call by name"""
        api_config = self._get_api_config(api_name)

        logger.info(f"Executing API: {api_config.get('name', api_name)}")

        # Store any provided parameters in context
        for key, value in kwargs.items():
            self.store_value(key, value)

        # Build request
        method = api_config['method']
        endpoint = self._resolve_variables(api_config['endpoint'])
        url = self.base_url + endpoint

        # Headers
        headers = self._resolve_dict_variables(api_config.get('headers', {}))

        # Check if auth is required
        if api_config.get('auth') == 'required' and not self.auth_token:
            raise ValueError("Authentication required but no auth token available")

        # Request body
        body = None
        if 'request' in api_config and 'body' in api_config['request']:
            body = self._resolve_dict_variables(api_config['request']['body'])

        # Query parameters
        params = None
        if 'request' in api_config and 'query' in api_config['request']:
            params = self._resolve_dict_variables(api_config['request']['query'])

        # Prepare request details for logging
        request_details = {
            'method': method,
            'url': url,
            'headers': headers,
            'params': params,
            'body': body
        }

        # Log request details
        logger.info(f"{method} {url}")
        logger.debug(f"Headers: {headers}")
        logger.debug(f"Params: {params}")
        logger.debug(f"Body: {body}")

        # Execute request
        start_time = time.time()
        try:
            async with self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=body,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                response_time = time.time() - start_time
                response_text = await response.text()

                try:
                    response_json = json.loads(response_text)
                except:
                    response_json = None

                result = {
                    'status': response.status,
                    'headers': dict(response.headers),
                    'body': response_json if response_json else response_text,
                    'response_time': response_time,
                    'url': str(response.url)
                }

                logger.info(f"Response: {response.status} in {response_time:.2f}s")
                logger.debug(f"Response body: {result['body']}")

                # Log to reporter
                self.reporter.log_api_call(
                    request_details,
                    result,
                    test_name or api_name
                )

                # Extract values from response
                if 'response' in api_config and 'extract' in api_config['response']:
                    self._extract_response_values(result['body'], api_config['response']['extract'])

                # Validate response
                if 'validation' in api_config:
                    self._validate_response(result, api_config['validation'])

                return result

        except asyncio.TimeoutError:
            error_msg = f"Request timeout after {self.timeout}s"
            logger.error(error_msg)

            # Log failed request
            self.reporter.log_api_call(
                request_details,
                {'status': 0, 'error': error_msg, 'response_time': self.timeout},
                test_name or api_name
            )
            raise
        except Exception as e:
            error_msg = f"Request failed: {str(e)}"
            logger.error(error_msg)

            # Log failed request
            self.reporter.log_api_call(
                request_details,
                {'status': 0, 'error': error_msg, 'response_time': time.time() - start_time},
                test_name or api_name
            )
            raise

    async def execute_file_upload(self, api_name: str, file_path: str, test_name: str = None, **kwargs) -> Dict:
        """Handle file upload APIs"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Get API config
        api_config = self._get_api_config(api_name)

        logger.info(f"Uploading file: {file_path} to {api_config.get('name', api_name)}")

        # Store parameters in context
        for key, value in kwargs.items():
            self.store_value(key, value)

        # Build URL
        method = api_config['method']
        endpoint = self._resolve_variables(api_config['endpoint'])
        url = self.base_url + endpoint

        # Prepare multipart form data
        data = aiohttp.FormData()

        # Add file
        with open(file_path, 'rb') as f:
            file_content = f.read()
            data.add_field('file',
                           file_content,
                           filename=os.path.basename(file_path),
                           content_type='application/octet-stream')

        # Add other fields from request body config
        if 'request' in api_config and 'body' in api_config['request']:
            body_params = self._resolve_dict_variables(api_config['request']['body'])
            for key, value in body_params.items():
                data.add_field(key, str(value))

        # Add additional fields from kwargs
        for key, value in kwargs.items():
            if key not in ['file_path', 'api_name', 'test_name']:
                data.add_field(key, str(value))

        # Headers (excluding Content-Type as it's set by FormData)
        headers = self._resolve_dict_variables(api_config.get('headers', {}))
        headers.pop('Content-Type', None)  # Remove if present

        # Check auth
        if api_config.get('auth') == 'required' and not self.auth_token:
            raise ValueError("Authentication required but no auth token available")

        # Prepare request details for logging
        request_details = {
            'method': method,
            'url': url,
            'headers': headers,
            'file': os.path.basename(file_path),
            'fields': kwargs
        }

        # Execute request
        start_time = time.time()
        try:
            async with self.session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=self.timeout * 2)  # Double timeout for uploads
            ) as response:
                response_time = time.time() - start_time
                response_text = await response.text()

                try:
                    response_json = json.loads(response_text)
                except:
                    response_json = response_text

                result = {
                    'status': response.status,
                    'headers': dict(response.headers),
                    'body': response_json,
                    'response_time': response_time,
                    'url': str(response.url)
                }

                logger.info(f"Upload response: {response.status} in {response_time:.2f}s")

                # Log to reporter
                self.reporter.log_api_call(
                    request_details,
                    result,
                    test_name or f"Upload: {api_name}"
                )

                # Extract values if configured
                if 'response' in api_config and 'extract' in api_config['response']:
                    self._extract_response_values(result['body'], api_config['response']['extract'])

                # Validate response
                if 'validation' in api_config:
                    self._validate_response(result, api_config['validation'])

                return result

        except Exception as e:
            error_msg = f"Upload failed: {str(e)}"
            logger.error(error_msg)

            # Log failed request
            self.reporter.log_api_call(
                request_details,
                {'status': 0, 'error': error_msg, 'response_time': time.time() - start_time},
                test_name or f"Upload: {api_name}"
            )
            raise

    def _extract_response_values(self, response_body: Any, extract_config: Dict):
        """Extract values from response using JSONPath"""
        if not isinstance(response_body, dict):
            return

        for key, jsonpath in extract_config.items():
            try:
                expression = jsonpath_parse(jsonpath)
                matches = expression.find(response_body)

                if matches:
                    value = matches[0].value
                    self.store_value(key, value)

                    # Special handling for auth_token
                    if key == 'auth_token':
                        self.auth_token = value
                        logger.info("Authentication token stored")
                else:
                    logger.warning(f"JSONPath '{jsonpath}' returned no matches")

            except Exception as e:
                logger.error(f"Failed to extract '{key}' using JSONPath '{jsonpath}': {str(e)}")

    def _validate_response(self, response: Dict, validation_config: Dict):
        """Validate response against configuration"""
        # Validate status code
        if 'status' in validation_config:
            expected_status = validation_config['status']
            actual_status = response['status']
            if actual_status != expected_status:
                raise AssertionError(f"Expected status {expected_status}, got {actual_status}")

        # Validate response body
        if 'body' in validation_config and isinstance(response['body'], dict):
            for validation in validation_config['body']:
                self._validate_json_path(response['body'], validation)

        # Validate response time
        if 'max_response_time' in validation_config:
            max_time = validation_config['max_response_time']
            actual_time = response['response_time']
            if actual_time > max_time:
                raise AssertionError(f"Response time {actual_time:.2f}s exceeds maximum {max_time}s")

    def _validate_json_path(self, data: Dict, validation: Dict):
        """Validate a single JSONPath expression"""
        jsonpath = validation.get('path')
        expression = jsonpath_parse(jsonpath)
        matches = expression.find(data)

        if 'exists' in validation:
            if validation['exists'] and not matches:
                raise AssertionError(f"Path '{jsonpath}' does not exist")
            elif not validation['exists'] and matches:
                raise AssertionError(f"Path '{jsonpath}' exists but should not")

        if 'equals' in validation:
            if not matches:
                raise AssertionError(f"Path '{jsonpath}' does not exist")

            actual_value = matches[0].value
            expected_value = validation['equals']

            if actual_value != expected_value:
                raise AssertionError(f"Path '{jsonpath}': expected '{expected_value}', got '{actual_value}'")


class APITestReporter:
    """Generate comprehensive API test reports"""

    def __init__(self):
        self.test_results = []

    def log_api_call(self, request: Dict, response: Dict, test_name: str):
        """Log each API call with full details"""
        result = {
            'test_name': test_name,
            'timestamp': datetime.now().isoformat(),
            'request': request,
            'response': {
                'status': response.get('status', 0),
                'time': response.get('response_time', 0),
                'headers': response.get('headers', {}),
                'body': response.get('body', {}),
                'error': response.get('error', None)
            },
            'status': 'passed' if response.get('status', 0) < 400 and not response.get('error') else 'failed'
        }

        self.test_results.append(result)

        # Log to console
        status_emoji = "✅" if result['status'] == 'passed' else "❌"
        logger.info(
            f"{status_emoji} {test_name}: {request.get('method', 'GET')} {request.get('url', '')} -> {response.get('status', 0)} in {response.get('response_time', 0):.2f}s")

    def generate_html_report(self, output_path: str):
        """Generate HTML report with all API test results"""
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>API Test Report</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
                .container { max-width: 1400px; margin: 0 auto; }
                .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 8px; margin-bottom: 30px; }
                .header h1 { margin: 0; font-size: 2.5em; }
                .header p { margin: 10px 0 0 0; opacity: 0.9; }
                .summary { display: flex; gap: 20px; margin: 20px 0; }
                .summary-item { flex: 1; background: white; padding: 20px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                .summary-item.passed { background: #d4edda; color: #155724; }
                .summary-item.failed { background: #f8d7da; color: #721c24; }
                .summary-item.total { background: #cce5ff; color: #004085; }
                .summary-item .number { font-size: 2.5em; font-weight: bold; }
                .summary-item .label { margin-top: 5px; font-size: 1.1em; }
                .api-call { background: white; border: 1px solid #dee2e6; margin: 20px 0; padding: 0; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                .api-call.passed .call-header { border-left: 5px solid #28a745; }
                .api-call.failed .call-header { border-left: 5px solid #dc3545; }
                .call-header { padding: 20px; background: #f8f9fa; cursor: pointer; border-radius: 8px 8px 0 0; }
                .call-header:hover { background: #e9ecef; }
                .call-details { padding: 20px; display: none; }
                .api-call.expanded .call-details { display: block; }
                .request, .response { margin: 15px 0; padding: 15px; background: #f8f9fa; border-radius: 5px; }
                .response.error { background: #f8d7da; }
                pre { white-space: pre-wrap; word-wrap: break-word; margin: 0; background: white; padding: 10px; border-radius: 3px; font-size: 0.9em; }
                .timing { color: #6c757d; font-size: 0.9em; float: right; }
                .method { display: inline-block; padding: 3px 8px; border-radius: 3px; font-weight: bold; font-size: 0.9em; }
                .method.GET { background: #cce5ff; color: #004085; }
                .method.POST { background: #d4edda; color: #155724; }
                .method.PUT { background: #fff3cd; color: #856404; }
                .method.DELETE { background: #f8d7da; color: #721c24; }
                .status-code { font-weight: bold; margin-left: 10px; }
                .status-code.success { color: #28a745; }
                .status-code.error { color: #dc3545; }
                .expand-btn { float: right; cursor: pointer; user-select: none; }
            </style>
            <script>
                function toggleDetails(element) {
                    element.closest('.api-call').classList.toggle('expanded');
                }
            </script>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>API Test Report</h1>
                    <p>Generated: {{ timestamp }} | Environment: {{ environment }}</p>
                </div>

                <div class="summary">
                    <div class="summary-item total">
                        <div class="number">{{ total }}</div>
                        <div class="label">Total API Calls</div>
                    </div>
                    <div class="summary-item passed">
                        <div class="number">{{ passed }}</div>
                        <div class="label">Passed</div>
                    </div>
                    <div class="summary-item failed">
                        <div class="number">{{ failed }}</div>
                        <div class="label">Failed</div>
                    </div>
                    <div class="summary-item">
                        <div class="number">{{ avg_time }}s</div>
                        <div class="label">Avg Response Time</div>
                    </div>
                </div>

                {% for result in results %}
                <div class="api-call {{ result.status }}">
                    <div class="call-header" onclick="toggleDetails(this)">
                        <span class="method {{ result.request.method }}">{{ result.request.method }}</span>
                        <strong>{{ result.test_name }}</strong>
                        <span class="status-code {% if result.response.status < 400 %}success{% else %}error{% endif %}">
                            {{ result.response.status }}
                        </span>
                        <span class="timing">{{ "%.2f"|format(result.response.time) }}s</span>
                        <span class="expand-btn">▼</span>
                    </div>
                    <div class="call-details">
                        <div class="request">
                            <h4>Request</h4>
                            <p><strong>URL:</strong> {{ result.request.url }}</p>
                            {% if result.request.headers %}
                            <p><strong>Headers:</strong></p>
                            <pre>{{ result.request.headers | tojson(indent=2) }}</pre>
                            {% endif %}
                            {% if result.request.params %}
                            <p><strong>Query Parameters:</strong></p>
                            <pre>{{ result.request.params | tojson(indent=2) }}</pre>
                            {% endif %}
                            {% if result.request.body %}
                            <p><strong>Body:</strong></p>
                            <pre>{{ result.request.body | tojson(indent=2) }}</pre>
                            {% endif %}
                            {% if result.request.file %}
                            <p><strong>File:</strong> {{ result.request.file }}</p>
                            {% endif %}
                        </div>
                        <div class="response {% if result.response.error %}error{% endif %}">
                            <h4>Response</h4>
                            <p><strong>Status:</strong> {{ result.response.status }} | <strong>Time:</strong> {{ "%.3f"|format(result.response.time) }}s</p>
                            {% if result.response.error %}
                            <p><strong>Error:</strong> {{ result.response.error }}</p>
                            {% else %}
                            {% if result.response.headers %}
                            <p><strong>Headers:</strong></p>
                            <pre>{{ result.response.headers | tojson(indent=2) }}</pre>
                            {% endif %}
                            {% if result.response.body %}
                            <p><strong>Body:</strong></p>
                            <pre>{{ result.response.body | tojson(indent=2) }}</pre>
                            {% endif %}
                            {% endif %}
                        </div>
                        <p style="color: #6c757d; font-size: 0.9em;">{{ result.timestamp }}</p>
                    </div>
                </div>
                {% endfor %}
            </div>
        </body>
        </html>
        """

        # Calculate statistics
        total = len(self.test_results)
        passed = len([r for r in self.test_results if r['status'] == 'passed'])
        failed = total - passed
        avg_time = sum(r['response']['time'] for r in self.test_results) / total if total > 0 else 0

        # Generate report using Jinja2
        template = Template(html_template)

        html_content = template.render(
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            environment=os.getenv('ENV', 'dev'),
            results=self.test_results,
            total=total,
            passed=passed,
            failed=failed,
            avg_time=f"{avg_time:.2f}"
        )

        # Ensure reports directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, 'w') as f:
            f.write(html_content)

        logger.info(f"HTML report generated: {output_path}")