# Getting Started with AITestRunner

## Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Step 1: Clone the Repository
```bash
git clone https://github.com/yourusername/aitestrunner.git
cd aitestrunner
```

### Step 2: Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Install Playwright Browsers
```bash
playwright install chromium
# Optional: Install other browsers
playwright install firefox
playwright install webkit
```

### Step 5: Install AI Model (Optional)
For AI-powered element detection:
```bash
pip install ultralytics
```

## Your First Test

### 1. Create a Feature File
Create `features/first_test.feature`:

```gherkin
Feature: My First Test
  
  Scenario: Visit Google
    Given I navigate to "https://www.google.com"
    When I enter "AITestRunner" in the search field
    And I click the "Google Search" button
    Then I should see "Search Results"
```

### 2. Create Configuration
Create `config/config.yaml`:

```yaml
project:
  name: "My First Project"
  
browser:
  type: "chromium"
  headless: false
```

### 3. Run the Test
```bash
python run.py --env dev
```

## Understanding the Output

- Tests will run in the browser (visible mode)
- Results will be displayed in the console
- HTML report will be generated in `reports/` directory
- Screenshots (on failure) will be saved in `reports/screenshots/`

## Next Steps

1. Learn about [Configuration Options](configuration.md)
2. Explore [Advanced Features](advanced_usage.md)
3. Write more complex scenarios
4. Set up CI/CD integration