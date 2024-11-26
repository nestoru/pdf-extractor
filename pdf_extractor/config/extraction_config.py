from pathlib import Path
from typing import List, Optional
import json
from pydantic import BaseModel

class ModelConfig(BaseModel):
    """Configuration for a specific model."""
    name: str
    endpoint: Optional[str] = None

class MLEngineConfig(BaseModel):
    """Configuration for ML engine."""
    model: str  # Currently selected model
    api_key: str
    available_models: List[ModelConfig]

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

    def get_model_config(self) -> ModelConfig:
        """Get the configuration for the currently selected model."""
        for model_config in self.ml_engine.available_models:
            if model_config.name == self.ml_engine.model:
                return model_config
        raise ValueError(f"Selected model '{self.ml_engine.model}' not found in available models")
