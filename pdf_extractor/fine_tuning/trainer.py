# fine_tuning/trainer.py
import openai
import json
from pathlib import Path
from typing import Optional
import time
import logging
from pdf_extractor.config.extraction_config import ExtractionConfig

logger = logging.getLogger(__name__)

class ModelTrainer:
    """Handles fine-tuning of OpenAI models."""
    
    def __init__(self, config: ExtractionConfig, base_model_name: str):
        """Initialize trainer with configuration and base model name."""
        self.config = config
        self.base_model_name = base_model_name
        openai.api_key = config.ml_engine.api_key
        
        # Validate base model exists in config
        if not any(model.name == base_model_name for model in config.ml_engine.available_models):
            raise ValueError(f"Model {base_model_name} not found in available_models")
    
    def create_fine_tuning_job(
        self,
        training_file_path: str,
        custom_model_name: str
    ) -> str:
        """Create and start a fine-tuning job."""
        # Upload the training file
        with open(training_file_path, 'rb') as f:
            file_response = openai.files.create(
                file=f,
                purpose='fine-tune'
            )
        file_id = file_response.id
        
        # Create fine-tuning job
        job = openai.fine_tuning.jobs.create(
            training_file=file_id,
            model=self.base_model_name,
            suffix=custom_model_name
        )
        
        return job.id
    
    def monitor_fine_tuning_job(self, job_id: str) -> dict:
        """Monitor the progress of a fine-tuning job."""
        while True:
            job = openai.fine_tuning.jobs.retrieve(job_id)
            
            status = job.status
            logger.info(f"Fine-tuning status: {status}")
            
            if status == 'succeeded':
                # Add the new model to the configuration
                new_model_config = {
                    "name": job.fine_tuned_model
                }
                self.config.ml_engine.available_models.append(new_model_config)
                
                # Save updated configuration
                config_path = Path("config.json")  # You might want to make this configurable
                with open(config_path, 'w') as f:
                    json.dump(self.config.dict(), f, indent=4)
                
                return job
            elif status == 'failed':
                return job
                
            time.sleep(60)  # Check every minute
