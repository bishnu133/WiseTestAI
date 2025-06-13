"""Configuration management"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class ConfigManager:
    """Manages configuration loading and merging"""

    def __init__(self, config_path: str, environment: str):
        self.config_path = Path(config_path)
        self.environment = environment
        self.config = {}

    def load_config(self) -> Dict[str, Any]:
        """Load and merge configuration files"""
        # Load main config
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)

        # Load environment specific config
        env_config_path = self.config_path.parent / 'environments' / f'{self.environment}.yaml'
        if env_config_path.exists():
            with open(env_config_path, 'r') as f:
                env_config = yaml.safe_load(f)

                # Handle overrides section specially
                if 'overrides' in env_config:
                    overrides = env_config.pop('overrides')
                    # Apply overrides to base config first
                    self._apply_overrides(self.config, overrides)

                # Then merge the rest of env config
                self.config = self._merge_configs(self.config, env_config)
        else:
            logger.warning(f"Environment config not found: {env_config_path}")

        # Process environment variables
        self.config = self._process_env_vars(self.config)

        logger.info(f"Configuration loaded for environment: {self.environment}")
        return self.config

    def _merge_configs(self, base: Dict, override: Dict) -> Dict:
        """Deep merge two dictionaries"""
        result = base.copy()

        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value

        return result

    def _apply_overrides(self, base: Dict, overrides: Dict) -> None:
        """Apply overrides from environment config to base config"""
        for section, values in overrides.items():
            if section in base and isinstance(values, dict):
                if isinstance(base[section], dict):
                    # Merge the override values into the base section
                    for key, value in values.items():
                        base[section][key] = value
                else:
                    # Replace the entire value if base is not a dict
                    base[section] = values
            else:
                # Add new section if it doesn't exist in base
                base[section] = values

    def _process_env_vars(self, config: Any) -> Any:
        """Replace ${VAR} with environment variables"""
        if isinstance(config, dict):
            return {k: self._process_env_vars(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._process_env_vars(item) for item in config]
        elif isinstance(config, str) and config.startswith('${') and config.endswith('}'):
            var_name = config[2:-1]
            return os.environ.get(var_name, config)
        else:
            return config

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key (supports dot notation)"""
        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value