# pdf_extractor/validation/model_validator.py
from pathlib import Path
import json
from typing import Dict, List, Tuple
import statistics
from dataclasses import dataclass
import tempfile
from pdf_extractor.core.extractor import PDFExtractor
from pdf_extractor.utils.logging import get_logger

logger = get_logger(__name__)

@dataclass
class ValidationMetrics:
    """Metrics from model validation."""
    total_samples: int
    total_fields: int
    correct_fields: int
    incorrect_fields: int
    accuracy: float
    field_accuracies: Dict[str, float]
    error_examples: List[Dict]
    model_name: str

    def __str__(self) -> str:
        """Format metrics for display."""
        lines = [
            "\nValidation Results for model: " + self.model_name,
            "-" * (24 + len(self.model_name)),
            f"Total Samples: {self.total_samples}",
            f"Total Fields: {self.total_fields}",
            f"Correct Fields: {self.correct_fields}",
            f"Incorrect Fields: {self.incorrect_fields}",
            f"Overall Accuracy: {self.accuracy:.2%}",
            "\nField-level Accuracies:",
        ]

        # Sort fields by accuracy descending
        sorted_fields = sorted(
            self.field_accuracies.items(),
            key=lambda x: x[1],
            reverse=True
        )

        for field, acc in sorted_fields:
            lines.append(f"  {field}: {acc:.2%}")

        if self.error_examples:
            lines.extend([
                "\nError Examples:",
                "--------------"
            ])

            for ex in self.error_examples:
                lines.extend([
                    f"\nDocument: {ex['document']}",
                    f"Field: {ex['field']}",
                    f"Expected: {ex['expected']}",
                    f"Got: {ex['actual']}"
                ])

        return "\n".join(lines)

class ModelValidator:
    """Validates model performance against ground truth data."""

    def __init__(self, api_key: str, model_name: str):
        """Initialize validator with API key and model name."""
        self.api_key = api_key
        self.model_name = model_name
        self.extractor = PDFExtractor(api_key=api_key, model_name=model_name)

    def _compare_values(self, expected: str, actual: str) -> bool:
        """Compare expected and actual values with basic normalization."""
        def normalize(value: str) -> str:
            return value.lower().strip().replace(" ", "")

        return normalize(str(expected)) == normalize(str(actual))

    def validate_model(
        self,
        training_dir: Path,
        template_path: str,
        error_limit: int = 5
    ) -> ValidationMetrics:
        """
        Validate model against training data.

        Args:
            training_dir: Directory containing training data (PDFs and JSON ground truth)
            template_path: Path to the fields template JSON file
            error_limit: Maximum number of error examples to collect

        Returns:
            ValidationMetrics object with results
        """
        total_samples = 0
        total_fields = 0
        correct_fields = 0
        field_results: Dict[str, List[bool]] = {}
        error_examples = []

        # Process each JSON file in the training directory
        for json_path in training_dir.glob("*.json"):
            try:
                # Load ground truth data
                with open(json_path, 'r', encoding='utf-8') as f:
                    ground_truth = json.load(f)

                # Get corresponding PDF
                pdf_path = json_path.parent / f"{json_path.stem}.pdf"

                if not pdf_path.exists():
                    logger.warning(f"PDF file not found: {pdf_path}")
                    continue

                # Create a temporary file for the extraction output
                with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=True) as tmp:
                    # Run extraction in validation mode
                    self.extractor.process_pdf(
                        str(pdf_path),
                        template_path,
                        None,  # No output PDF needed for validation
                        tmp.name,
                        validation_mode=True
                    )

                    # Read back the results
                    tmp.seek(0)
                    extracted = json.load(tmp)

                # Compare results
                ground_truth_fields = {
                    f['key']: f['value'] for f in ground_truth['fields']
                }
                extracted_fields = {
                    f['key']: f['value'] for f in extracted['fields']
                }

                total_samples += 1

                # Check each field in ground truth
                for key, expected in ground_truth_fields.items():
                    actual = extracted_fields.get(key, '')
                    is_correct = self._compare_values(expected, actual)

                    total_fields += 1
                    if is_correct:
                        correct_fields += 1

                    # Track field-level accuracy
                    if key not in field_results:
                        field_results[key] = []
                    field_results[key].append(is_correct)

                    # Collect error examples
                    if not is_correct and len(error_examples) < error_limit:
                        error_examples.append({
                            'document': json_path.name,
                            'field': key,
                            'expected': expected,
                            'actual': actual
                        })

            except Exception as e:
                logger.error(f"Error processing {json_path}: {str(e)}")
                continue

        # Calculate metrics
        accuracy = correct_fields / total_fields if total_fields > 0 else 0
        field_accuracies = {
            field: sum(results) / len(results)
            for field, results in field_results.items()
        }

        return ValidationMetrics(
            total_samples=total_samples,
            total_fields=total_fields,
            correct_fields=correct_fields,
            incorrect_fields=total_fields - correct_fields,
            accuracy=accuracy,
            field_accuracies=field_accuracies,
            error_examples=error_examples,
            model_name=self.model_name
        )
