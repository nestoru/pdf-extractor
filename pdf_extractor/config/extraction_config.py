# pdf_extractor/config/extraction_config.py
from pathlib import Path
import json
from pydantic import BaseModel

class MLEngineConfig(BaseModel):
    """Configuration for ML engine."""
    api_key: str

class ExtractionConfig(BaseModel):
    """Configuration for PDF extraction process."""
    ml_engine: MLEngineConfig

    @classmethod
    def from_json(cls, json_path: str) -> 'ExtractionConfig':
        """Load configuration from JSON file."""
        try:
            config_path = Path(json_path)
            if not config_path.is_file():
                raise ValueError(f"Configuration file not found: {json_path}")

            with open(config_path, 'r') as f:
                config_data = json.load(f)

            return cls(**config_data)

        except Exception as e:
            raise ValueError(f"Failed to load configuration: {str(e)}")
