# pdf_extractor/finetune_commands/validate.py

import sys
from pathlib import Path
import openai
from pdf_extractor.config.extraction_config import ExtractionConfig
from pdf_extractor.utils.logging import get_logger
from pdf_extractor.validation.model_validator import ModelValidator
from .utils import find_matching_files

logger = get_logger(__name__)

def validate_command(
    config_path: str,
    model_name: str,
    json_folder: str,
    pdf_folder: str,
    template_path: str,
    error_limit: int = 5,
    dry_run: bool = False
) -> None:
    """Validate model performance against training data."""
    try:
        # Load configuration
        config = ExtractionConfig.from_json(config_path)
        openai.api_key = config.ml_engine.api_key

        # Find matching JSON and PDF files
        json_folder_path = Path(json_folder)
        pdf_folder_path = Path(pdf_folder)

        print("\nSearching for matching JSON-PDF pairs...")
        matched_files = find_matching_files(json_folder_path, pdf_folder_path)

        if not matched_files:
            raise ValueError("No matching JSON-PDF pairs found")

        print(f"\nFound {len(matched_files)} matching file pairs:")
        for json_file, pdf_file in matched_files:
            print(f"  • JSON: {json_file.relative_to(json_folder_path)}")
            print(f"    PDF: {pdf_file.relative_to(pdf_folder_path)}")

        if dry_run:
            print("\nDRY RUN - The following operations would be performed:\n")
            print(f"1. Using model '{model_name}' for validation")
            print(f"2. Template path: {template_path}")
            print(f"3. Error limit: {error_limit}")
            print("\n4. Validation metrics that will be calculated:")
            print("  • Accuracy: Overall percentage of correct field extractions")
            print("  • Precision: Percentage of extracted fields that are correct")
            print("  • Recall: Percentage of actual fields that were found")
            print("  • F1-score: Harmonic mean of precision and recall")
            print("  • Field coverage: Percentage of required fields found")
            print("  • Sample size: Total number of fields evaluated")
            print("  • Error examples: Will show up to {error_limit} detailed error cases")
            
            print("\n5. Files to be processed:")
            for json_file, pdf_file in matched_files:
                print(f"  • Will process JSON: {json_file.relative_to(json_folder_path)}")
                print(f"    with PDF: {pdf_file.relative_to(pdf_folder_path)}")
            print("\nDry run complete. To execute validation, run without --dry-run")
            return

        # Initialize validator with api_key and specified model
        validator = ModelValidator(
            api_key=config.ml_engine.api_key,
            model_name=model_name
        )

        # Run validation
        logger.info(f"\nValidating model {model_name}...")
        metrics = validator.validate_model_with_pairs(
            matched_files=matched_files,
            template_path=template_path,
            error_limit=error_limit
        )

        # Print results
        print("\nValidation Results:")
        print("-" * 20)
        print(metrics)

        # Provide recommendation based on all metrics
        issues = []
        if metrics.accuracy < 90:
            issues.append("accuracy is below 90%")
        if metrics.precision < 85:
            issues.append("precision is below 85%")
        if metrics.recall < 85:
            issues.append("recall is below 85%")
        if metrics.f1_score < 85:
            issues.append("F1-score is below 85%")

        if issues:
            print("\nRecommendation: Model performance needs improvement:")
            print(f"Issues found: {', '.join(issues)}")
            print("\nConsider:")
            print("1. Fine-tuning with more examples")
            print("2. Reviewing error examples for patterns")
            print("3. Checking data quality and consistency")
            if metrics.total_samples < 100:
                print("4. Collecting more training data")
        else:
            print("\n✓ Model performance meets all quality thresholds")

    except Exception as e:
        logger.error(f"Error during validation: {str(e)}")
        sys.exit(1)
