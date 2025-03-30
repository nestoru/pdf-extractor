# pdf_extractor/finetune_commands/train.py

import sys
from pathlib import Path
import json
import openai
from pdf_extractor.config.extraction_config import ExtractionConfig
from pdf_extractor.utils.logging import get_logger
from pdf_extractor.fine_tuning.data_processor import FineTuningDataProcessor
from pdf_extractor.fine_tuning.trainer import ModelTrainer
from .utils import check_model_eligibility
from datetime import datetime

logger = get_logger(__name__)

def train_command(
    config_path: str,
    base_model_name: str,
    json_folder: str,
    custom_model_name: str,
    dry_run: bool = False
) -> None:
    """
    Handle fine-tuning command for OpenAI GPT models using JSON files with embedded pdf_content.
    Field keys will be extracted from JSON files and included in the training prompts.
    
    Args:
        config_path: Path to configuration file
        base_model_name: Base model to fine-tune
        json_folder: Folder containing JSON files with embedded pdf_content
        custom_model_name: Custom name for the fine-tuned model
        dry_run: If True, only show what would be done
    """
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

        # Find all JSON files in the folder
        json_folder_path = Path(json_folder)
        json_files = list(json_folder_path.glob("**/*.json"))

        if not json_files:
            raise ValueError(f"No JSON files found in {json_folder}")

        print(f"\n2. Found {len(json_files)} JSON files. Checking for required pdf_content field...")
        
        # Verify that each JSON has the required pdf_content field
        valid_jsons = []
        invalid_jsons = []
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if "pdf_content" in data and data["pdf_content"].strip() and "fields" in data:
                    valid_jsons.append(json_file)
                else:
                    if "pdf_content" not in data or not data["pdf_content"].strip():
                        error = "missing pdf_content"
                    elif "fields" not in data:
                        error = "missing fields"
                    else:
                        error = "unknown issue"
                    invalid_jsons.append((json_file, error))
            except Exception as e:
                invalid_jsons.append((json_file, f"Error parsing: {str(e)}"))

        # Report on valid/invalid files
        if invalid_jsons:
            print(f"⚠ {len(invalid_jsons)} JSON files are invalid and will be skipped:")
            for json_file, error in invalid_jsons[:5]:  # Show only first 5 to avoid too much output
                print(f"  • {json_file.name}: {error}")
            if len(invalid_jsons) > 5:
                print(f"  • ... and {len(invalid_jsons) - 5} more")
                
        if not valid_jsons:
            raise ValueError("No valid JSON files with required pdf_content field found.")
        
        print(f"✓ Found {len(valid_jsons)} valid JSON files with pdf_content field.")

        # Generate timestamp for unique model name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        training_file = json_folder_path / f"training_{timestamp}.jsonl"

        # Create data processor and collect field keys
        processor = FineTuningDataProcessor()
        
        print("\n3. Collecting field keys from JSON files...")
        field_keys = processor.collect_field_keys(valid_jsons)
        print(f"✓ Found {len(field_keys)} unique field keys:")
        # Print field keys in groups of 5 for readability
        for i in range(0, len(field_keys), 5):
            print(f"  • {', '.join(field_keys[i:i+5])}")
        
        # Training prompt example
        field_keys_str = ", ".join(field_keys[:5]) + (", ..." if len(field_keys) > 5 else "")
        print("\n4. Training file preparation:")
        print(f"  • Will create: {training_file}")
        print("  • Format: JSONL with objects containing:")
        print(f'    - User prompt: "Extract ONLY the following fields from this document and format as JSON. Required fields: {field_keys_str}."')
        print("    - Assistant response: JSON with extracted fields")

        print(f"\n5. Fine-tuning job configuration:")
        print(f"  • Base model: {base_model_name}")
        print(f"  • Custom model name: {custom_model_name}_{timestamp}")
        print("  • Training examples will be uploaded to OpenAI")
        print("  • A new fine-tuning job will be created")

        if dry_run:
            print("\nDry run complete. To execute these operations, run without --dry-run")
            return

        # Prepare training data using JSON files
        print("\nPreparing training data...")
        examples, training_file_path = processor.prepare_training_data_from_jsons(
            valid_jsons,
            training_file
        )

        if not examples or not training_file_path:
            raise ValueError("Failed to prepare training data")

        print(f"✓ Created training file: {training_file_path}")
        print(f"✓ Number of training examples: {len(examples)}")

        # Check if we have enough examples
        if len(examples) < 10:
            raise ValueError(
                f"Insufficient training examples. Found {len(examples)}, "
                "minimum required is 10"
            )

        # Check existing models (with proper date comparison)
        print("\nChecking existing models...")
        models = openai.Model.list()
        existing_model_found = False
        
        for model in models.data:
            if model.id.startswith('ft:') and custom_model_name in model.id:
                try:
                    # Get just the timestamp part - handle both dash and underscore formats
                    model_id_parts = model.id.split(custom_model_name)
                    if len(model_id_parts) > 1:
                        model_timestamp_raw = model_id_parts[-1].lstrip('-_')
                        
                        # Extract just the date part (first 8 chars) for comparison
                        model_date = model_timestamp_raw[:8]  # Gets "20250114"
                        current_date = timestamp[:8]  # Gets "20250326"
                        
                        if model_date > current_date:
                            logger.info(f"Model already exists with newer timestamp: {model.id}")
                            existing_model_found = True
                            break
                except Exception as e:
                    logger.warning(f"Could not parse timestamp from model: {model.id}, error: {e}")
                    continue
        
        if existing_model_found:
            print("A model with a newer timestamp already exists. Exiting.")
            return

        # Initialize trainer and start fine-tuning
        print("\nStarting fine-tuning job...")
        trainer = ModelTrainer(config, base_model_name)
        model_name_with_timestamp = f"{custom_model_name}_{timestamp}"
        job_id = trainer.create_fine_tuning_job(
            str(training_file_path),
            model_name_with_timestamp
        )

        logger.info(f"Fine-tuning job started with ID: {job_id}")
        print(f"\n✓ Fine-tuning job started successfully")
        print(f"✓ Job ID: {job_id}")
        print(f"\nUse 'pdf-extractor-finetune status {config_path} {job_id}' to monitor the job status")

    except Exception as e:
        logger.error(f"Error during fine-tuning: {str(e)}")
        sys.exit(1)
