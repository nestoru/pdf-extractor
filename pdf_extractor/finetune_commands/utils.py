# pdf_extractor/finetune_commands/utils.py

from pathlib import Path
from typing import List, Tuple
import openai
from pdf_extractor.config.extraction_config import ExtractionConfig
from pdf_extractor.utils.logging import get_logger

logger = get_logger(__name__)

def find_matching_files(json_folder: Path, pdf_folder: Path) -> List[Tuple[Path, Path]]:
    """
    Recursively find matching JSON and PDF files.
    Returns list of tuples (json_path, pdf_path).
    """
    matched_files = []

    # Recursively get all JSON files
    for json_file in json_folder.rglob("*.json"):
        # Get relative path from json_folder
        rel_path = json_file.relative_to(json_folder)
        # Construct corresponding PDF path
        pdf_path = pdf_folder / rel_path.with_suffix('.pdf')

        if pdf_path.exists():
            matched_files.append((json_file, pdf_path))

    return matched_files

def check_model_eligibility(config: ExtractionConfig, model_name: str) -> bool:
    """Check if a model can be fine-tuned."""
    try:
        # Try to get model details
        model = openai.Model.retrieve(model_name)

        # Try to create a fine-tuning job (will fail early if model isn't fine-tunable)
        try:
            openai.FineTuningJob.create(
                model=model_name,
                training_file="test",  # Dummy value for validation
                validation_required=True
            )
        except openai.error.InvalidRequestError as e:
            # If the error is about the training file and not about model eligibility,
            # then the model is fine-tunable
            if "training_file" in str(e).lower():
                return True
            logger.error(f"Model '{model_name}' is not eligible for fine-tuning: {str(e)}")
            return False
        except Exception:
            # Any other error means the model is not fine-tunable
            return False

        return True

    except Exception as e:
        logger.error(f"Error checking model eligibility: {str(e)}")
        return False
