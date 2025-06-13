# WiseAITestRunner - AI-Powered Scriptless Test Automation

WiseAITestRunner is an innovative test automation framework that eliminates the need for writing test scripts. Simply write your test scenarios in Gherkin format, and let AI handle the element detection and test execution.

## Features

- 🤖 AI-powered element detection using lightweight models
- 📝 Natural language test scenarios (Gherkin/BDD)
- 🚀 Zero scripting required
- 🔧 Easy configuration with YAML files
- 🌐 Multi-environment support
- 📊 Beautiful HTML reports
- 🎯 Smart element caching for faster execution
- 🎬 Video recording and screenshots
- ⚡ Parallel test execution

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/aitestrunner.git
cd aitestrunner

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

### Setup

1. Configure your environments in `config/environments/`
2. Write your feature files in `features/`
3. Run tests:

```bash
# Run all tests in dev environment
python run.py --env dev

# Run specific tagged tests
python run.py --env prod --tags @smoke

# Run with video recording
python run.py --env staging --video --screenshot
```

### Writing Tests

Create a feature file in `features/`:

```gherkin
Feature: User Login
  
  Scenario: Successful login
    Given I navigate to the login page
    When I enter "user@example.com" in the "email" field
    And I enter "password123" in the "password" field
    And I click the "Sign In" button
    Then I should see "Welcome back!"
```

That's it! No need to write any automation code.

## Configuration

Main configuration (`config/config.yaml`):

```yaml
project:
  name: "My Project"
  
browser:
  type: "chromium"
  headless: false
  
ai_model:
  type: "yolo-world"  # or "pattern" for lightweight mode
```

## Supported Actions

- Navigation: `I navigate to "url"`
- Click: `I click the "button text"`
- Input: `I enter "value" in the "field name"`
- Verification: `I should see "text"`
- Wait: `I wait for 2 seconds`
- And many more...

## License

MIT License - feel free to use in your projects!