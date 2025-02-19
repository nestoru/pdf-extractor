# pdf_extractor/finetune_commands/train.py

import sys
from pathlib import Path
import openai
from pdf_extractor.config.extraction_config import ExtractionConfig
from pdf_extractor.utils.logging import get_logger
from pdf_extractor.fine_tuning.data_processor import FineTuningDataProcessor
from pdf_extractor.fine_tuning.trainer import ModelTrainer
from .utils import check_model_eligibility, find_matching_files
from datetime import datetime

logger = get_logger(__name__)

def train_command(
    config_path: str,
    base_model_name: str,
    json_folder: str,
    pdf_folder: str,
    custom_model_name: str,
    dry_run: bool = False
) -> None:
    """Handle fine-tuning command for OpenAI GPT models."""
    try:
        # Load configuration
        config = ExtractionConfig.from_json(config_path)
        openai.api_key = config.ml_engine.api_key

        if dry_run:
            print("\nDRY RUN - The following operations would be performed:\n")

        # Check if model is eligible for fine-tuning
        print(f"1. Checking eligibility for model '{base_model_name}'...")
        if not check_model_eligibility(config, base_model_name):
            logger.error(f"Model '{base_model_name}' is not eligible for fine-tuning")
            sys.exit(1)
        print("✓ Model is eligible for fine-tuning")

        # Find matching JSON and PDF files
        json_folder_path = Path(json_folder)
        pdf_folder_path = Path(pdf_folder)

        print("\n2. Searching for matching JSON-PDF pairs...")
        matched_files = find_matching_files(json_folder_path, pdf_folder_path)

        if not matched_files:
            raise ValueError("No matching JSON-PDF pairs found")

        print(f"\nFound {len(matched_files)} matching file pairs:")
        for json_file, pdf_file in matched_files:
            print(f"  • JSON: {json_file.relative_to(json_folder_path)}")
            print(f"    PDF: {pdf_file.relative_to(pdf_folder_path)}")

        # Cache directory information
        cache_dir = json_folder_path / ".cache"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        training_file = json_folder_path / f"training_{timestamp}.jsonl"

        print("\n3. Cache and training file operations:")
        print(f"  • Cache directory: {cache_dir}")
        print("  • Will create or update cache files:")
        for json_file, pdf_file in matched_files:
            cache_file = cache_dir / f"{pdf_file.stem}_training.json"
            print(f"    - {cache_file.name}")
            print(f"      (Processing {pdf_file.name} with {json_file.name})")

        print(f"\n4. Training file preparation:")
        print(f"  • Will create: {training_file}")
        print("  • Format: JSONL with JSON objects containing:")
        print("    - PDF text as user messages")
        print("    - Extracted fields as assistant messages")

        print("\n5. Fine-tuning job configuration:")
        print(f"  • Base model: {base_model_name}")
        print(f"  • Custom model name: {custom_model_name}_{timestamp}")
        print("  • Training examples will be uploaded to OpenAI")
        print("  • A new fine-tuning job will be created")

        if dry_run:
            print("\nDry run complete. To execute these operations, run without --dry-run")
            return

        # Rest of the implementation...
        # Prepare training data using matched files
        print("\nPreparing training data...")
        processor = FineTuningDataProcessor()
        examples, training_file = processor.prepare_training_data_from_pairs(
            matched_files,
            json_folder_path / "prepared_training_data.json"
        )

        if not examples or not training_file:
            raise ValueError("Failed to prepare training data")

        print(f"✓ Created training file: {training_file}")
        print(f"✓ Number of training examples: {len(examples)}")

        # Check existing models
        print("\nChecking existing models...")
        models = openai.Model.list()
        for model in models.data:
            if model.id.startswith('ft:') and custom_model_name in model.id:
                model_timestamp = model.id.split('_')[-1]
                if model_timestamp >= training_timestamp:
                    logger.info(f"Model already exists with same or newer timestamp: {model.id}")
                    return

        if len(examples) < 10:
            raise ValueError(
                f"Insufficient training examples. Found {len(examples)}, "
                "minimum required is 10"
            )

        # Initialize trainer and start fine-tuning
        print("\nStarting fine-tuning job...")
        trainer = ModelTrainer(config, base_model_name)
        model_name_with_timestamp = f"{custom_model_name}_{training_timestamp}"
        job_id = trainer.create_fine_tuning_job(
            str(training_file),
            model_name_with_timestamp
        )

        logger.info(f"Fine-tuning job started with ID: {job_id}")
        print(f"\n✓ Fine-tuning job started successfully")
        print(f"✓ Job ID: {job_id}")
        print(f"\nUse 'pdf-extractor-finetune status {config_path} {job_id}' to monitor the job status")

    except Exception as e:
        logger.error(f"Error during fine-tuning: {str(e)}")
        sys.exit(1)
