# pdf_extractor/finetune_commands/validate.py

import sys
from pathlib import Path
from pdf_extractor.config.extraction_config import ExtractionConfig
from pdf_extractor.utils.logging import get_logger
from pdf_extractor.validation.model_validator import ModelValidator

logger = get_logger(__name__)

def validate_command(
    config_path: str,
    training_dir: str,
    model_name: str,
    template_path: str,
    error_limit: int = 5
) -> None:
    """Validate model performance against training data."""
    try:
        # Load configuration
        config = ExtractionConfig.from_json(config_path)

        # Initialize validator with api_key and specified model
        validator = ModelValidator(
            api_key=config.ml_engine.api_key,
            model_name=model_name
        )

        # Run validation
        logger.info(f"Validating model {model_name}...")
        metrics = validator.validate_model(
            training_dir=Path(training_dir),
            template_path=template_path,
            error_limit=error_limit
        )

        # Print results
        print("\nValidation Results:")
        print("-" * 20)
        print(metrics)

        # Provide recommendation
        if metrics.accuracy < 0.9:
            print("\nRecommendation: Model accuracy is below 90%. Consider:")
            print("1. Fine-tuning with more examples")
            print("2. Reviewing error examples for patterns")
            print("3. Checking data quality and consistency")
            if metrics.total_samples < 100:
                print("4. Collecting more training data")
        else:
            print("\n✓ Model performance meets quality threshold")

    except Exception as e:
        logger.error(f"Error during validation: {str(e)}")
        sys.exit(1)
