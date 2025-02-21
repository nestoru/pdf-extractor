# pdf_extractor/finetune_commands/status.py
import sys
import openai
from pdf_extractor.config.extraction_config import ExtractionConfig
from pdf_extractor.utils.logging import get_logger

logger = get_logger(__name__)

def get_job_status_command(config_path: str, job_id: str) -> None:
    """Get the status of a specific fine-tuning job."""
    try:
        config = ExtractionConfig.from_json(config_path)
        openai.api_key = config.ml_engine.api_key

        job = openai.FineTuningJob.retrieve(job_id)

        print(f"\nJob Status for {job_id}:")
        print("-" * (len(job_id) + 15))
        print(f"Status: {job.status}")
        print(f"Model: {job.model}")
        if hasattr(job, 'fine_tuned_model'):
            print(f"Fine-tuned Model: {job.fine_tuned_model}")
        print(f"Created at: {job.created_at}")
        if hasattr(job, 'finished_at') and job.finished_at:
            print(f"Finished at: {job.finished_at}")
        if hasattr(job, 'error') and job.error:
            print(f"Error: {job.error}")

        # Print training metrics if available
        if hasattr(job, 'results'):
            print("\nTraining Metrics:")
            for metric, value in job.results.items():
                print(f"  {metric}: {value}")

    except Exception as e:
        logger.error(f"Error getting job status: {str(e)}")
        sys.exit(1)
