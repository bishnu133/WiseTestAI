# Configuration Guide

## Main Configuration File

The main configuration file (`config/config.yaml`) contains global settings:

```yaml
project:
  name: "Project Name"
  version: "1.0.0"
  
browser:
  type: "chromium"  # Options: chromium, firefox, webkit
  headless: false
  viewport:
    width: 1920
    height: 1080
    
ai_model:
  type: "yolo-world"  # Options: yolo-world, pattern, none
  confidence_threshold: 0.6
  
execution:
  parallel: 1
  retry_count: 2
  screenshot_on_failure: true
```

## Environment Configuration

Environment-specific settings go in `config/environments/{env}.yaml`:

```yaml
base_url: "https://staging.example.com"

test_users:
  admin:
    username: "admin@test.com"
    password: "AdminPass123"
```

## Using Environment Variables

You can use environment variables in configuration:

```yaml
database:
  password: "${DB_PASSWORD}"
```

## Custom Step Mappings

Define custom step patterns:

```yaml
custom_mappings:
  - pattern: "I login as admin"
    action: "custom_login"
    params:
      role: "admin"
```

## Page Shortcuts

Define URL shortcuts:

```yaml
pages:
  home: "/"
  login: "/auth/login"
  dashboard: "/dashboard"
```

Use in features:
```gherkin
Given I navigate to the login page
```

## AI Model Configuration

### YOLO-World (Recommended)
```yaml
ai_model:
  type: "yolo-world"
  confidence_threshold: 0.6
  model_size: "nano"  # nano, small, medium
```

### Pattern Matching (Lightweight)
```yaml
ai_model:
  type: "pattern"
  use_cache: true
```

### Disable AI
```yaml
ai_model:
  type: "none"
```

## Execution Settings

### Parallel Execution
```yaml
execution:
  parallel: 3  # Run 3 scenarios in parallel
```

### Retry Configuration
```yaml
execution:
  retry_count: 2
  retry_delay: 1000  # milliseconds
```

### Wait Strategies
```yaml
execution:
  wait_time: 500  # Default wait between actions
  timeout: 30000  # Element timeout
```

## Reporting Configuration

```yaml
reporting:
  format: "html"  # html, json, both
  output_dir: "custom_reports"
  include_screenshots: true
  include_logs: true
  timestamp_format: "%Y-%m-%d_%H-%M-%S"
```