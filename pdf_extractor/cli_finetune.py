# pdf_extractor/cli_finetune.py
import sys
from pathlib import Path
import openai
from typing import Optional
from pdf_extractor.config.extraction_config import ExtractionConfig
from pdf_extractor.utils.logging import get_logger
from pdf_extractor.fine_tuning.data_processor import FineTuningDataProcessor
from pdf_extractor.fine_tuning.trainer import ModelTrainer
from pdf_extractor.validation.model_validator import ModelValidator

logger = get_logger(__name__)

def list_models_command(config_path: str) -> None:
    """List all available models, including fine-tuned ones."""
    try:
        config = ExtractionConfig.from_json(config_path)
        openai.api_key = config.ml_engine.api_key
        
        # Get OpenAI models
        models = openai.models.list()
        
        print("\nAvailable Models:")
        print("----------------")
        
        # List base models from config
        print("\nBase Models:")
        for model in config.ml_engine.available_models:
            if not model.endpoint:  # Base OpenAI models don't have endpoints
                print(f"  - {model.name}")
        
        # List fine-tuned models
        print("\nFine-tuned Models:")
        for model in models.data:
            if model.id.startswith('ft:'):
                print(f"  - {model.id}")
                if hasattr(model, 'created_at'):
                    print(f"    Created: {model.created_at}")
                if hasattr(model, 'owned_by'):
                    print(f"    Owner: {model.owned_by}")
        
        # List custom endpoint models from config
        print("\nCustom Endpoint Models:")
        for model in config.ml_engine.available_models:
            if model.endpoint:
                print(f"  - {model.name}")
                print(f"    Endpoint: {model.endpoint}")
                
    except Exception as e:
        logger.error(f"Error listing models: {str(e)}")
        sys.exit(1)

def get_job_status_command(config_path: str, job_id: str) -> None:
    """Get the status of a specific fine-tuning job."""
    try:
        config = ExtractionConfig.from_json(config_path)
        openai.api_key = config.ml_engine.api_key
        
        job = openai.fine_tuning.jobs.retrieve(job_id)
        
        print(f"\nJob Status for {job_id}:")
        print("-" * (len(job_id) + 15))
        print(f"Status: {job.status}")
        print(f"Model: {job.model}")
        if job.fine_tuned_model:
            print(f"Fine-tuned Model: {job.fine_tuned_model}")
        print(f"Created at: {job.created_at}")
        if hasattr(job, 'finished_at') and job.finished_at:
            print(f"Finished at: {job.finished_at}")
        if hasattr(job, 'error') and job.error:
            print(f"Error: {job.error}")
        
        # Print training metrics if available
        if hasattr(job, 'training_metrics'):
            print("\nTraining Metrics:")
            for metric, value in job.training_metrics.items():
                print(f"  {metric}: {value}")
        
    except Exception as e:
        logger.error(f"Error getting job status: {str(e)}")
        sys.exit(1)

def list_jobs_command(config_path: str, limit: Optional[int] = None) -> None:
    """List all fine-tuning jobs."""
    try:
        config = ExtractionConfig.from_json(config_path)
        openai.api_key = config.ml_engine.api_key
        
        # Get all fine-tuning jobs
        jobs = openai.fine_tuning.jobs.list(limit=limit)
        
        print("\nFine-tuning Jobs:")
        print("----------------")
        
        for job in jobs.data:
            print(f"\nJob ID: {job.id}")
            print(f"Status: {job.status}")
            print(f"Model: {job.model}")
            if job.fine_tuned_model:
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

def validate_model_command(
    config_path: str,
    training_dir: str,
    error_limit: int = 5
) -> None:
    """Validate model performance against training data."""
    try:
        # Load configuration
        config = ExtractionConfig.from_json(config_path)
        
        # Initialize validator
        validator = ModelValidator(config)
        
        # Run validation
        logger.info(f"Validating model {config.ml_engine.model}...")
        metrics = validator.validate_model(
            Path(training_dir),
            error_limit=error_limit
        )
        
        # Print results
        print(metrics)
        
        # Provide recommendation
        if metrics.accuracy < 0.9:
            print("\nRecommendation: Model accuracy is below 90%. Consider:")
            print("1. Fine-tuning with more examples")
            print("2. Reviewing error examples for patterns")
            print("3. Checking data quality and consistency")
            if metrics.total_samples < 100:
                print("4. Collecting more training data")
                
    except Exception as e:
        logger.error(f"Error during validation: {str(e)}")
        sys.exit(1)

def fine_tune_openai_gpt_command(
    config_path: str,
    base_model_name: str,
    training_dir: str,
    custom_model_name: str
) -> None:
    """Handle fine-tuning command for OpenAI GPT models."""
    try:
        # Load configuration
        config = ExtractionConfig.from_json(config_path)
        
        # Verify base model exists and is available
        base_model_exists = False
        for model in config.ml_engine.available_models:
            if model.name == base_model_name and not model.endpoint:
                base_model_exists = True
                break
        
        if not base_model_exists:
            raise ValueError(f"Base model '{base_model_name}' not found in available models")
        
        # Prepare training data
        training_dir_path = Path(training_dir)
        if not training_dir_path.is_dir():
            raise ValueError(f"Training directory not found: {training_dir}")
            
        prepared_data_path = training_dir_path / "prepared_training_data.json"
        processor = FineTuningDataProcessor()
        examples = processor.prepare_training_data(
            training_dir_path,
            prepared_data_path
        )
        
        if len(examples) < 10:  # Minimum required by OpenAI
            raise ValueError(
                f"Insufficient training examples. Found {len(examples)}, "
                "minimum required is 10"
            )
        
        # Initialize trainer with specified base model
        trainer = ModelTrainer(config, base_model_name)
        
        # Start fine-tuning
        job_id = trainer.create_fine_tuning_job(
            str(prepared_data_path),
            custom_model_name
        )
        
        logger.info(f"Fine-tuning job started with ID: {job_id}")
        print(f"\nUse 'pdf-extractor-finetune status {config_path} {job_id}' to monitor the job status")
        
    except Exception as e:
        logger.error(f"Error during fine-tuning: {str(e)}")
        sys.exit(1)

def main():
    """Main entry point for the PDF extraction fine-tuning tool."""
    try:
        if len(sys.argv) < 2:
            print("Usage:")
            print("  pdf-extractor-finetune list-models <config.json>")
            print("  pdf-extractor-finetune list-jobs <config.json> [limit]")
            print("  pdf-extractor-finetune status <config.json> <job_id>")
            print("  pdf-extractor-finetune train <config.json> "
                  "<openai_model_name> <training_dir> <custom_model_name>")
            print("  pdf-extractor-finetune validate <config.json> "
                  "<training_dir> [error_limit]")
            sys.exit(1)
            
        command = sys.argv[1]
        
        if command == "list-models":
            if len(sys.argv) != 3:
                print("Usage: pdf-extractor-finetune list-models <config.json>")
                sys.exit(1)
            list_models_command(sys.argv[2])
            
        elif command == "list-jobs":
            if len(sys.argv) not in [3, 4]:
                print("Usage: pdf-extractor-finetune list-jobs <config.json> [limit]")
                sys.exit(1)
            limit = int(sys.argv[3]) if len(sys.argv) == 4 else None
            list_jobs_command(sys.argv[2], limit)
            
        elif command == "status":
            if len(sys.argv) != 4:
                print("Usage: pdf-extractor-finetune status <config.json> <job_id>")
                sys.exit(1)
            get_job_status_command(sys.argv[2], sys.argv[3])
            
        elif command == "train":
            if len(sys.argv) != 6:
                print("Usage: pdf-extractor-finetune train <config.json> "
                      "<openai_model_name> <training_dir> <custom_model_name>")
                sys.exit(1)
            fine_tune_openai_gpt_command(
                config_path=sys.argv[2],
                base_model_name=sys.argv[3],
                training_dir=sys.argv[4],
                custom_model_name=sys.argv[5]
            )
            
        elif command == "validate":
            if len(sys.argv) not in [4, 5]:
                print("Usage: pdf-extractor-finetune validate <config.json> "
                      "<training_dir> [error_limit]")
                sys.exit(1)
            error_limit = int(sys.argv[4]) if len(sys.argv) == 5 else 5
            validate_model_command(
                config_path=sys.argv[2],
                training_dir=sys.argv[3],
                error_limit=error_limit
            )
            
        else:
            print(f"Unknown command: {command}")
            print("Available commands: list-models, list-jobs, status, train, validate")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
