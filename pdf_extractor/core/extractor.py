# pdf_extractor/core/extractor.py
import json
from pathlib import Path
from typing import Dict
import openai
from pdf_extractor.services.gpt_service import GPTService
from pdf_extractor.services.pdf_service import PDFService
from pdf_extractor.core.models import ExtractionTemplate, ExtractedField, ProcessingResult
from pdf_extractor.utils.logging import get_logger

logger = get_logger(__name__)

class PDFExtractor:
    """Main PDF extraction orchestrator."""
    def __init__(self, api_key: str, model_name: str):
        """Initialize the PDF extractor with API key and model name."""
        self.api_key = api_key
        self.model_name = model_name
        self.gpt_service = GPTService(api_key=self.api_key, model_name=self.model_name)
        self.pdf_service = PDFService()

    def process_pdf(
        self,
        input_pdf_path: str,
        template_path: str,
        output_pdf_path: str | None,
        extracted_json_path: str,
        validation_mode: bool = False
    ) -> None:
        """
        Process PDF document and save results.
        
        Args:
            input_pdf_path: Path to input PDF
            template_path: Path to extraction template
            output_pdf_path: Path for annotated PDF output (None if not needed)
            extracted_json_path: Path for extracted data JSON
            validation_mode: If True, skip PDF annotation
        """
        logger.info(f"Processing PDF with model: {self.model_name}")
        openai.api_key = self.api_key

        # Load extraction template
        with open(template_path, 'r') as f:
            template_data = json.load(f)
        template = ExtractionTemplate(**template_data)

        # Extract text and positions (positions only needed if annotating)
        if validation_mode:
            text_content = self.pdf_service.extract_text(input_pdf_path)
            positions = None
        else:
            text_content, positions = self.pdf_service.extract_text_and_positions(input_pdf_path)

        # Analyze with GPT
        analysis = self.gpt_service.analyze_document(text_content, template)

        # For validation, we only need the extracted fields without positions
        if validation_mode:
            extracted_fields = [
                ExtractedField(
                    key=field.key,
                    value=str(field.value),
                    page=None,
                    bbox=None
                )
                for field in analysis.fields
            ]
        else:
            # Match fields with positions for annotation
            extracted_fields = []
            for field in analysis.fields:
                field_value = str(field.value)
                for pos in positions:
                    if field_value in pos['text']:
                        extracted_fields.append(
                            ExtractedField(
                                key=field.key,
                                value=field_value,
                                page=pos['page'],
                                bbox=pos['bbox']
                            )
                        )
                        break

        # Create result
        result = ProcessingResult(
            document_type=template.document_type,
            extracted_fields=extracted_fields,
            text_content=text_content
        )

        # Save results
        self._save_results(
            result, 
            input_pdf_path, 
            output_pdf_path, 
            extracted_json_path,
            validation_mode
        )

    def _save_results(
        self,
        result: ProcessingResult,
        input_pdf_path: str,
        output_pdf_path: str | None,
        extracted_json_path: str,
        validation_mode: bool = False
    ) -> None:
        """Save processing results to files."""
        # Save extracted data to JSON
        output_data = {
            'document_type': result.document_type,
            'fields': [
                {'key': f.key, 'value': f.value}
                for f in result.extracted_fields
            ],
            'text_content': result.text_content
        }
        with open(extracted_json_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)

        # Create annotated PDF only if not in validation mode and output path is provided
        if not validation_mode and output_pdf_path:
            self.pdf_service.create_annotated_pdf(
                input_pdf_path,
                output_pdf_path,
                result.document_type,
                result.extracted_fields
            )
