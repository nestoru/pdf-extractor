# pdf_extractor/finetune_commands/list_models.py
import sys
import openai
from pdf_extractor.config.extraction_config import ExtractionConfig
from pdf_extractor.utils.logging import get_logger

logger = get_logger(__name__)

def list_models_command(config_path: str) -> None:
    """List all available models, including fine-tuning eligible ones."""
    try:
        config = ExtractionConfig.from_json(config_path)
        openai.api_key = config.ml_engine.api_key

        # Get all OpenAI models
        response = openai.Model.list()

        # Organize models by type
        base_models = []
        fine_tuned_models = []
        for model in response.data:
            if model.id.startswith('ft:'):
                fine_tuned_models.append(model)
            else:
                base_models.append(model)

        # Print base models first
        print("\nAvailable Base Models:")
        print("--------------------")
        if base_models:
            for model in base_models:
                print(f"  - {model.id}")
        else:
            print("  No base models found")

        # Print fine-tuned models
        print("\nYour Fine-tuned Models:")
        print("--------------------")
        if fine_tuned_models:
            for model in fine_tuned_models:
                print(f"  - {model.id}")
                if hasattr(model, 'created'):
                    print(f"    Created: {model.created}")
                if hasattr(model, 'owned_by'):
                    print(f"    Owner: {model.owned_by}")
        else:
            print("  No fine-tuned models found")

    except Exception as e:
        logger.error(f"Error listing models: {str(e)}")
        sys.exit(1)
