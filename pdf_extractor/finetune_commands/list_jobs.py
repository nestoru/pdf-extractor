# pdf_extractor/finetune_commands/list_jobs.py
import sys
from typing import Optional
import openai
from pdf_extractor.config.extraction_config import ExtractionConfig
from pdf_extractor.utils.logging import get_logger

logger = get_logger(__name__)

def list_jobs_command(config_path: str, limit: Optional[int] = None) -> None:
    """List all fine-tuning jobs."""
    try:
        config = ExtractionConfig.from_json(config_path)
        openai.api_key = config.ml_engine.api_key

        # Get all fine-tuning jobs
        response = openai.FineTuningJob.list(limit=limit)

        print("\nFine-tuning Jobs:")
        print("----------------")

        for job in response.data:
            print(f"\nJob ID: {job.id}")
            print(f"Status: {job.status}")
            print(f"Model: {job.model}")
            if hasattr(job, 'fine_tuned_model'):
                print(f"Fine-tuned Model: {job.fine_tuned_model}")
            print(f"Created at: {job.created_at}")
            if hasattr(job, 'finished_at') and job.finished_at:
                print(f"Finished at: {job.finished_at}")
            if hasattr(job, 'error') and job.error:
                print(f"Error: {job.error}")
            print("-" * 50)

    except Exception as e:
        logger.error(f"Error listing jobs: {str(e)}")
        sys.exit(1)
