# Advanced Usage Guide

## Writing Complex Scenarios

### Data Tables
```gherkin
Scenario: Fill form with multiple fields
  When I fill in the form with:
    | Field      | Value           |
    | First Name | John            |
    | Last Name  | Doe             |
    | Email      | john@example.com|
    | Phone      | 555-0123        |
```

### Scenario Outlines
```gherkin
Scenario Outline: Login with different users
  When I enter "<username>" in the "Email" field
  And I enter "<password>" in the "Password" field
  And I click "Login"
  Then I should see "<result>"
  
  Examples:
    | username          | password  | result         |
    | admin@test.com    | Admin123  | Admin Panel    |
    | user@test.com     | User123   | User Dashboard |
```

## Custom Actions

### Creating Custom Action Handlers

Add to `src/executor/action_handler.py`:

```python
def custom_action(self, params: Dict) -> Dict:
    # Your custom logic here
    element = params.get('element')
    # Perform action
    return {'status': 'success'}
```

### Registering Custom Patterns

In configuration:
```yaml
custom_mappings:
  - pattern: "I perform custom action on (.+)"
    action: "custom_action"
    params:
      element: "$1"
```

## AI Model Tuning

### Adjusting Detection Sensitivity
```yaml
ai_model:
  confidence_threshold: 0.7  # Higher = more strict
  iou_threshold: 0.5        # Intersection over union
```

### Custom Element Types
```python
# In ai_element_finder.py
self.model.set_classes([
    "button", "input", "link", "dropdown",
    "custom_widget", "calendar", "modal"
])
```

## Performance Optimization

### Element Caching
```yaml
ai_model:
  use_cache: true
  cache_ttl: 3600  # 1 hour
```

### Parallel Execution
```bash
# Run 5 scenarios in parallel
python run.py --env prod --parallel 5
```

### Headless Mode
```bash
# Faster execution without UI
python run.py --env prod --headless
```

## CI/CD Integration

### GitHub Actions
```yaml
name: Test Automation
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - run: pip install -r requirements.txt
      - run: playwright install chromium
      - run: python run.py --env staging --headless
      - uses: actions/upload-artifact@v2
        with:
          name: test-reports
          path: reports/
```

### Jenkins Pipeline
```groovy
pipeline {
    agent any
    stages {
        stage('Test') {
            steps {
                sh 'pip install -r requirements.txt'
                sh 'playwright install chromium'
                sh 'python run.py --env ${ENV} --headless'
            }
        }
    }
    post {
        always {
            publishHTML([
                reportDir: 'reports',
                reportFiles: 'latest_report.html',
                reportName: 'Test Report'
            ])
        }
    }
}
```

## Debugging

### Enable Debug Logging
```yaml
logging:
  level: "DEBUG"
```

### Slow Motion Mode
```bash
# Slow down execution by 1 second
python run.py --env dev --slow-mo 1000
```

### Interactive Mode
```python
# Add breakpoint in step
import pdb; pdb.set_trace()
```

## API Testing Integration

### Combined UI and API Tests
```gherkin
Scenario: Verify API and UI consistency
  Given I make API call to "/api/products"
  And I save the response as "api_products"
  When I navigate to the products page
  Then UI products should match "api_products"
```

## Visual Testing

### Screenshot Comparison
```gherkin
Scenario: Visual regression test
  Given I navigate to the home page
  When I take a screenshot "homepage_current"
  Then screenshot should match "homepage_baseline"
```

## Best Practices

1. **Use Tags Effectively**
   - `@smoke` - Quick validation tests
   - `@regression` - Full regression suite
   - `@critical` - Business critical flows
   - `@wip` - Work in progress

2. **Organize Features**
   ```
   features/
   ├── authentication/
   │   ├── login.feature
   │   └── logout.feature
   ├── shopping/
   │   ├── search.feature
   │   └── checkout.feature
   ```

3. **Environment Management**
   - Use different configs for each environment
   - Store sensitive data in environment variables
   - Never commit passwords or tokens

4. **Maintainability**
   - Keep scenarios focused and atomic
   - Use descriptive step text
   - Leverage Background for common steps
   - Regular cache cleanup

5. **Performance**
   - Run smoke tests first
   - Use parallel execution wisely
   - Implement smart waits
   - Cache element selectors