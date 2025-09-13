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
import re

logger = get_logger(__name__)

def validate_coordinate_format(pdf_content: str) -> tuple[bool, int, int]:
    """
    Validate that PDF content contains coordinate markers.
    
    Args:
        pdf_content: The PDF content string to validate
        
    Returns:
        tuple: (has_coordinates, total_markers, unique_pages)
    """
    # Pattern to match coordinate markers: <@page:x1,y1,x2,y2>
    coord_pattern = r'<@(\d+):[\d.]+,[\d.]+,[\d.]+,[\d.]+>'
    matches = re.findall(coord_pattern, pdf_content)
    
    has_coordinates = len(matches) > 0
    total_markers = len(matches)
    unique_pages = len(set(matches)) if matches else 0
    
    return has_coordinates, total_markers, unique_pages

def analyze_training_data_quality(json_files: list[Path]) -> dict:
    """
    Analyze the quality of training data for coordinate-aware training.
    
    Args:
        json_files: List of JSON file paths to analyze
        
    Returns:
        dict: Analysis results including statistics and warnings
    """
    stats = {
        'total_files': len(json_files),
        'with_coordinates': 0,
        'without_coordinates': 0,
        'avg_markers_per_file': 0,
        'total_unique_fields': set(),
        'files_missing_coords': [],
        'coordinate_coverage': {}
    }
    
    total_markers = 0
    
    for json_file in json_files:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if 'pdf_content' in data:
                has_coords, markers, pages = validate_coordinate_format(data['pdf_content'])
                
                if has_coords:
                    stats['with_coordinates'] += 1
                    total_markers += markers
                    stats['coordinate_coverage'][json_file.name] = {
                        'markers': markers,
                        'pages': pages
                    }
                else:
                    stats['without_coordinates'] += 1
                    stats['files_missing_coords'].append(json_file.name)
            
            # Collect field statistics
            if 'fields' in data:
                for field in data['fields']:
                    if 'key' in field:
                        stats['total_unique_fields'].add(field['key'])
        
        except Exception as e:
            logger.warning(f"Error analyzing {json_file}: {e}")
    
    if stats['with_coordinates'] > 0:
        stats['avg_markers_per_file'] = total_markers / stats['with_coordinates']
    
    return stats

def train_command(
    config_path: str,
    base_model_name: str,
    json_folder: str,
    custom_model_name: str,
    dry_run: bool = False,
    validate_coordinates: bool = True
) -> None:
    """
    Handle fine-tuning command for OpenAI GPT models using JSON files with coordinate-aware content.
    Field keys will be extracted from JSON files and included in the training prompts.
    
    Args:
        config_path: Path to configuration file
        base_model_name: Base model to fine-tune
        json_folder: Folder containing JSON files with embedded pdf_content
        custom_model_name: Custom name for the fine-tuned model
        dry_run: If True, only show what would be done
        validate_coordinates: If True, validate that training data includes coordinate markers
    """
    try:
        # Load configuration
        config = ExtractionConfig.from_json(config_path)
        openai.api_key = config.ml_engine.api_key

        if dry_run:
            print("\n" + "="*60)
            print("DRY RUN MODE - No operations will be performed")
            print("="*60 + "\n")

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

        print(f"\n2. Found {len(json_files)} JSON files. Validating structure...")
        
        # Verify that each JSON has the required fields
        valid_jsons = []
        invalid_jsons = []
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                errors = []
                if "pdf_content" not in data or not data["pdf_content"].strip():
                    errors.append("missing/empty pdf_content")
                if "fields" not in data or not data["fields"]:
                    errors.append("missing/empty fields")
                
                if errors:
                    invalid_jsons.append((json_file, ", ".join(errors)))
                else:
                    valid_jsons.append(json_file)
                    
            except Exception as e:
                invalid_jsons.append((json_file, f"Error parsing: {str(e)}"))

        # Report on valid/invalid files
        if invalid_jsons:
            print(f"\n⚠ {len(invalid_jsons)} JSON files are invalid and will be skipped:")
            for json_file, error in invalid_jsons[:5]:
                print(f"  • {json_file.name}: {error}")
            if len(invalid_jsons) > 5:
                print(f"  • ... and {len(invalid_jsons) - 5} more")
                
        if not valid_jsons:
            raise ValueError("No valid JSON files with required fields found.")
        
        print(f"✓ Found {len(valid_jsons)} valid JSON files")

        # Analyze training data quality for coordinate-aware training
        if validate_coordinates:
            print("\n3. Analyzing training data quality for coordinate-aware training...")
            analysis = analyze_training_data_quality(valid_jsons)
            
            print(f"\n   Coordinate Analysis:")
            print(f"   • Files with coordinates: {analysis['with_coordinates']}/{analysis['total_files']}")
            print(f"   • Files without coordinates: {analysis['without_coordinates']}/{analysis['total_files']}")
            
            if analysis['with_coordinates'] > 0:
                print(f"   • Average coordinate markers per file: {analysis['avg_markers_per_file']:.1f}")
                
                # Show top files by coordinate coverage
                if analysis['coordinate_coverage']:
                    sorted_coverage = sorted(
                        analysis['coordinate_coverage'].items(),
                        key=lambda x: x[1]['markers'],
                        reverse=True
                    )[:3]
                    print(f"\n   Top files by coordinate density:")
                    for filename, coverage in sorted_coverage:
                        print(f"   • {filename}: {coverage['markers']} markers across {coverage['pages']} page(s)")
            
            if analysis['without_coordinates'] > 0:
                print(f"\n   ⚠ WARNING: {analysis['without_coordinates']} files lack coordinate markers")
                print("   This may reduce the model's ability to understand spatial relationships.")
                if analysis['files_missing_coords'][:3]:
                    print("   Files missing coordinates (first 3):")
                    for filename in analysis['files_missing_coords'][:3]:
                        print(f"   • {filename}")
                
                if not dry_run:
                    response = input("\n   Continue with training despite missing coordinates? (y/n): ")
                    if response.lower() != 'y':
                        print("Training cancelled.")
                        return

        # Generate timestamp for unique model name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        training_file = json_folder_path / f"training_{timestamp}.jsonl"

        # Create data processor and collect field keys
        processor = FineTuningDataProcessor()
        
        print("\n4. Collecting field keys from JSON files...")
        field_keys = processor.collect_field_keys(valid_jsons)
        print(f"✓ Found {len(field_keys)} unique field keys")
        
        # Display field keys in a more organized way
        if len(field_keys) <= 20:
            print("\n   All field keys:")
            for i in range(0, len(field_keys), 3):
                batch = field_keys[i:i+3]
                print(f"   • {' | '.join(batch)}")
        else:
            print(f"\n   Sample field keys (showing 15 of {len(field_keys)}):")
            for i in range(0, min(15, len(field_keys)), 3):
                batch = field_keys[i:i+3]
                print(f"   • {' | '.join(batch)}")
            print(f"   • ... and {len(field_keys) - 15} more")
        
        # Training configuration details
        print("\n5. Training Configuration:")
        print(f"   • Base model: {base_model_name}")
        print(f"   • Custom model name: {custom_model_name}_{timestamp}")
        print(f"   • Training file: {training_file.name}")
        print(f"   • Training examples: {len(valid_jsons)}")
        
        # Show example prompt structure
        print("\n   Training prompt structure:")
        print("   ┌─ User Message ─────────────────────────────────────┐")
        print("   │ Extract ONLY the following fields from this        │")
        print("   │ document and format as JSON.                       │")
        print(f"   │ Required fields: [list of {len(field_keys)} field keys]      │")
        print("   │                                                     │")
        print("   │ [PDF content with coordinate markers]              │")
        print("   │ Example: [text]<@0:72.2,37.1,101.5,60.9>          │")
        print("   └─────────────────────────────────────────────────────┘")
        print("   ┌─ Assistant Response ────────────────────────────────┐")
        print("   │ {\"fields\": [{\"key\": \"...\", \"value\": \"...\"}]}      │")
        print("   └─────────────────────────────────────────────────────┘")

        if dry_run:
            print("\n" + "="*60)
            print("Dry run complete. To execute training, run without --dry-run")
            print("="*60)
            return

        # Prepare training data using JSON files
        print("\n6. Preparing training data...")
        examples, training_file_path = processor.prepare_training_data_from_jsons(
            valid_jsons,
            training_file
        )

        if not examples or not training_file_path:
            raise ValueError("Failed to prepare training data")

        print(f"✓ Created training file: {training_file_path}")
        print(f"✓ Number of training examples: {len(examples)}")

        # Check if we have enough examples
        min_examples = 10
        if len(examples) < min_examples:
            raise ValueError(
                f"Insufficient training examples. Found {len(examples)}, "
                f"minimum required is {min_examples}"
            )

        # Estimate token usage (rough estimate)
        avg_tokens_per_example = 1500  # Conservative estimate for coordinate-rich content
        estimated_tokens = len(examples) * avg_tokens_per_example
        print(f"\n   Estimated token usage: ~{estimated_tokens:,} tokens")
        
        # Check existing models
        print("\n7. Checking for existing models...")
        models = openai.Model.list()
        existing_model_found = False
        existing_models = []
        
        for model in models.data:
            if model.id.startswith('ft:') and custom_model_name in model.id:
                existing_models.append(model.id)
                try:
                    # Extract timestamp from model ID
                    model_id_parts = model.id.split(custom_model_name)
                    if len(model_id_parts) > 1:
                        model_timestamp_raw = model_id_parts[-1].lstrip('-_')
                        model_date = model_timestamp_raw[:8]
                        current_date = timestamp[:8]
                        
                        if model_date >= current_date:
                            logger.info(f"Found existing model with same/newer date: {model.id}")
                            existing_model_found = True
                except Exception as e:
                    logger.warning(f"Could not parse timestamp from model: {model.id}, error: {e}")
        
        if existing_models:
            print(f"   Found {len(existing_models)} existing model(s) with similar name:")
            for model_id in existing_models[:3]:
                print(f"   • {model_id}")
            
            if existing_model_found:
                print("\n   ⚠ A model with the same or newer timestamp already exists.")
                response = input("   Do you want to continue and create a new model? (y/n): ")
                if response.lower() != 'y':
                    print("Training cancelled.")
                    return

        # Initialize trainer and start fine-tuning
        print("\n8. Starting fine-tuning job...")
        trainer = ModelTrainer(config, base_model_name)
        model_name_with_timestamp = f"{custom_model_name}_{timestamp}"
        job_id = trainer.create_fine_tuning_job(
            str(training_file_path),
            model_name_with_timestamp
        )

        logger.info(f"Fine-tuning job started with ID: {job_id}")
        
        print("\n" + "="*60)
        print("✓ FINE-TUNING JOB STARTED SUCCESSFULLY")
        print("="*60)
        print(f"\nJob Details:")
        print(f"  • Job ID: {job_id}")
        print(f"  • Model name: {model_name_with_timestamp}")
        print(f"  • Training examples: {len(examples)}")
        print(f"  • Coordinate-aware: {'Yes' if analysis['with_coordinates'] > 0 else 'No'}")
        
        print(f"\nNext Steps:")
        print(f"  1. Monitor status: pdf-extractor-finetune status {config_path} {job_id}")
        print(f"  2. List all jobs: pdf-extractor-finetune list-jobs {config_path}")
        print(f"  3. Once complete, the model will be available as: ft:...")
        
        print("\nThe fine-tuning process typically takes 20-60 minutes depending on the dataset size.")

    except KeyboardInterrupt:
        print("\n\nTraining cancelled by user.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error during fine-tuning: {str(e)}")
        print(f"\n❌ Error: {str(e)}")
        sys.exit(1)
