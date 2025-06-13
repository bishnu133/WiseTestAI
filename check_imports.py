"""
Diagnostic script to check all imports
"""
import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.getcwd())

def check_import(module_path, class_name=None):
    """Check if a module can be imported"""
    try:
        if class_name:
            exec(f"from {module_path} import {class_name}")
            print(f"✓ Successfully imported {class_name} from {module_path}")
        else:
            exec(f"import {module_path}")
            print(f"✓ Successfully imported {module_path}")
        return True
    except Exception as e:
        print(f"✗ Failed to import {module_path}: {e}")
        return False

print("Checking AITestRunner imports...\n")

# Check core modules
print("=== Core Modules ===")
check_import("src.core.config_manager", "ConfigManager")
check_import("src.core.browser_manager", "BrowserManager")
check_import("src.core.cache_manager", "CacheManager")
check_import("src.core.ai_element_finder", "AIElementFinder")

# Check parser modules
print("\n=== Parser Modules ===")
check_import("src.parser.feature_parser", "FeatureParser")
check_import("src.parser.step_mapper", "StepMapper")

# Check executor modules
print("\n=== Executor Modules ===")
check_import("src.executor.test_executor", "TestExecutor")
check_import("src.executor.step_executor", "StepExecutor")
check_import("src.executor.action_handler", "ActionHandler")

# Check other modules
print("\n=== Other Modules ===")
check_import("src.reports.html_reporter", "HTMLReporter")
check_import("src.utils.logger", "setup_logger")

# Check external dependencies
print("\n=== External Dependencies ===")
check_import("playwright")
check_import("click")
check_import("yaml")
check_import("pytest")

print("\n=== Checking file existence ===")
required_files = [
    "run.py",
    "src/__init__.py",
    "src/core/__init__.py",
    "src/parser/__init__.py",
    "src/executor/__init__.py",
    "src/reports/__init__.py",
    "src/utils/__init__.py",
]

for file_path in required_files:
    if os.path.exists(file_path):
        print(f"✓ {file_path} exists")
    else:
        print(f"✗ {file_path} missing")