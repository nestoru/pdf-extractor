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

    def create_fine_tuning_job(
        self,
        training_file_path: str,
        custom_model_name: str
    ) -> str:
        """Create and start a fine-tuning job."""
        # Upload the training file
        with open(training_file_path, 'rb') as f:
            file_response = openai.File.create(
                file=f,
                purpose='fine-tune'
            )
        file_id = file_response.id

        # Create fine-tuning job
        job = openai.FineTuningJob.create(
            training_file=file_id,
            model=self.base_model_name,
            suffix=custom_model_name
        )

        return job.id

    def monitor_fine_tuning_job(self, job_id: str) -> dict:
        """Monitor the progress of a fine-tuning job."""
        while True:
            job = openai.FineTuningJob.retrieve(job_id)

            status = job.status
            logger.info(f"Fine-tuning status: {status}")

            if status in ['succeeded', 'failed']:
                return job

            time.sleep(60)  # Check every minute
