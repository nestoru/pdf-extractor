import json
from pathlib import Path
from typing import Dict
from pdf_extractor.config.extraction_config import ExtractionConfig
from pdf_extractor.core.models import ExtractionTemplate, ExtractedField, ProcessingResult
from pdf_extractor.services.gpt_service import GPTService
from pdf_extractor.services.pdf_service import PDFService
from pdf_extractor.utils.logging import get_logger

logger = get_logger(__name__)

class PDFExtractor:
    """Main PDF extraction orchestrator."""
    
    def __init__(self, config: ExtractionConfig):
        """Initialize the PDF extractor with configuration."""
        self.config = config
        self.gpt_service = GPTService(config)
        self.pdf_service = PDFService()
    
    def process_pdf(
        self,
        input_pdf_path: str,
        fields_template_path: str,
        output_pdf_path: str,
        extracted_json_path: str
    ) -> None:
        """Process PDF document and save results."""
        logger.info(f"Processing PDF: {input_pdf_path}")
        
        # Load extraction template
        with open(fields_template_path, 'r') as f:
            template_data = json.load(f)
        template = ExtractionTemplate(**template_data)
        
        # Extract text and positions
        text_content, positions = self.pdf_service.extract_text_and_positions(input_pdf_path)
        
        # Analyze with GPT using template
        analysis = self.gpt_service.analyze_document(text_content, template)
        
        # Match fields with positions
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
        self._save_results(result, input_pdf_path, output_pdf_path, extracted_json_path)

    def _save_results(
        self,
        result: ProcessingResult,
        input_pdf_path: str,
        output_pdf_path: str,
        extracted_json_path: str
    ) -> None:
        """Save processing results to files."""
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
        
        self.pdf_service.create_annotated_pdf(
            input_pdf_path,
            output_pdf_path,
            result.document_type,
            result.extracted_fields
        )
