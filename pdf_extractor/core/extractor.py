# pdf_extractor/core/extractor.py
import json
from pathlib import Path
from typing import Dict, Optional, Tuple
import openai
from pdf_extractor.services.gpt_service import GPTService
from pdf_extractor.services.pdf_service import PDFService
from pdf_extractor.services.sharepoint_schema_builder import SharePointSchemaBuilder
from pdf_extractor.core.models import ExtractionTemplate, ExtractedField, ProcessingResult
from pdf_extractor.utils.logging import get_logger

logger = get_logger(__name__)

class PDFExtractor:
    """Main PDF extraction orchestrator."""
    def __init__(self, api_key: str, model_name: str, config_path: str):
        """
        Initialize the PDF extractor with API key and model name.
        
        Args:
            api_key: OpenAI API key
            model_name: Model name to use
            config_path: Path to config file with SharePoint credentials
        """
        self.api_key = api_key
        self.model_name = model_name
        self.config_path = config_path
        self.gpt_service = GPTService(api_key=self.api_key, model_name=self.model_name)
        self.pdf_service = PDFService()
        self.sharepoint_builder = SharePointSchemaBuilder(config_path)
        logger.info("SharePoint schema builder initialized")

    def _build_extraction_schema(self, sharepoint_url: str) -> Tuple[ExtractionTemplate, Optional[Dict[str, str]], Optional[Dict[str, str]]]:
        """
        Build extraction schema from SharePoint Excel data file.
        
        Returns:
            Tuple of (template, alternative_names, extraction_rules)
        """
        logger.info("Building extraction schema from SharePoint data file")
        return self.sharepoint_builder.build_extraction_schema(sharepoint_url)

    def _is_filename_field(self, field_key: str) -> bool:
        """Check if a field is a filename-related field."""
        field_key_lower = field_key.lower()
        return any(keyword in field_key_lower for keyword in ['filename', 'file_name', 'file name', 'document_name', 'document name'])

    def _extract_filename_fields(self, template: ExtractionTemplate, input_pdf_path: str) -> Dict[str, str]:
        """
        Extract filename fields directly without GPT analysis.
        
        Args:
            template: The extraction template
            input_pdf_path: Path to the input PDF file
            
        Returns:
            Dict mapping filename field keys to the filename value
        """
        filename_fields = {}
        filename = Path(input_pdf_path).stem
        
        for field in template.fields:
            if self._is_filename_field(field.key):
                filename_fields[field.key] = filename
                logger.info(f"Directly extracted filename field: {field.key} = {filename}")
        
        return filename_fields

    def _filter_non_filename_fields(self, template: ExtractionTemplate) -> ExtractionTemplate:
        """
        Create a new template with filename fields removed for GPT analysis.
        
        Args:
            template: Original template
            
        Returns:
            New template without filename fields
        """
        non_filename_fields = [
            field for field in template.fields 
            if not self._is_filename_field(field.key)
        ]
        
        logger.info(f"Filtered template from {len(template.fields)} to {len(non_filename_fields)} fields (removed filename fields)")
        
        return ExtractionTemplate(
            document_type=template.document_type,
            fields=non_filename_fields
        )

    def _filter_metadata_for_non_filename_fields(self, metadata: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        """
        Filter metadata (alternative names or extraction rules) to exclude filename fields.
        
        Args:
            metadata: Dictionary of field metadata
            
        Returns:
            Filtered metadata excluding filename fields
        """
        if not metadata:
            return None
            
        filtered_metadata = {
            field_key: value for field_key, value in metadata.items()
            if not self._is_filename_field(field_key)
        }
        
        return filtered_metadata if filtered_metadata else None

    def process_pdf(
        self,
        input_pdf_path: str,
        sharepoint_url: str,
        output_pdf_path: str | None,
        extracted_json_path: str,
        validation_mode: bool = False
    ) -> None:
        """
        Process PDF document and save results.

        Args:
            input_pdf_path: Path to input PDF
            sharepoint_url: SharePoint URL of the Excel data file
            output_pdf_path: Path for annotated PDF output (None if not needed)
            extracted_json_path: Path for extracted data JSON
            validation_mode: If True, skip PDF annotation
        """
        logger.info(f"Processing PDF with model: {self.model_name}")
        openai.api_key = self.api_key

        # Build extraction schema from SharePoint Excel data file
        template, alternative_names, extraction_rules = self._build_extraction_schema(sharepoint_url)
        
        # Extract filename fields directly (no GPT needed)
        filename_fields = self._extract_filename_fields(template, input_pdf_path)
        
        # Filter template and metadata to exclude filename fields for GPT analysis
        gpt_template = self._filter_non_filename_fields(template)
        gpt_alternative_names = self._filter_metadata_for_non_filename_fields(alternative_names)
        gpt_extraction_rules = self._filter_metadata_for_non_filename_fields(extraction_rules)

        # Extract text and positions (positions only needed if annotating)
        if validation_mode:
            text_content = self.pdf_service.extract_text(input_pdf_path)
            positions = None
        else:
            text_content, positions = self.pdf_service.extract_text_and_positions(input_pdf_path)

        # Analyze with GPT only for non-filename fields
        gpt_analysis = None
        if gpt_template.fields:  # Only call GPT if there are non-filename fields
            gpt_analysis = self.gpt_service.analyze_document(
                text_content, 
                gpt_template,
                alternative_names=gpt_alternative_names,
                extraction_rules=gpt_extraction_rules
            )
            logger.info(f"GPT analysis returned {len(gpt_analysis.fields)} fields")
        else:
            logger.info("No non-filename fields to analyze with GPT")

        # Combine GPT results with filename fields
        all_fields = []
        
        # Add filename fields
        for field_key, field_value in filename_fields.items():
            from pdf_extractor.core.models import ExtractedFieldGPT
            all_fields.append(ExtractedFieldGPT(key=field_key, value=field_value))
        
        # Add GPT analysis fields
        if gpt_analysis:
            all_fields.extend(gpt_analysis.fields)

        # Log all final fields
        logger.info(f"Combined analysis returned {len(all_fields)} fields total")
        for field in all_fields:
            logger.info(f"Final field: {field.key} = {field.value}")

        # For validation, we only need the extracted fields without positions
        if validation_mode:
            extracted_fields = [
                ExtractedField(
                    key=field.key,
                    value=str(field.value),
                    page=None,
                    bbox=None
                )
                for field in all_fields
            ]
            logger.info(f"Created {len(extracted_fields)} extracted fields for validation mode")
        else:
            # Match fields with positions for annotation
            extracted_fields = []
            for field in all_fields:
                field_value = str(field.value)
                field_matched = False
                
                # Skip position matching for filename fields since they're not in the PDF text
                if self._is_filename_field(field.key):
                    # Add filename fields without position data
                    extracted_fields.append(
                        ExtractedField(
                            key=field.key,
                            value=field_value,
                            page=None,
                            bbox=None
                        )
                    )
                    logger.info(f"Added filename field without position: {field.key} = {field_value}")
                    continue
                
                # Regular position matching for non-filename fields
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
                        field_matched = True
                        logger.info(f"Field matched with position: {field.key} = {field_value}")
                        break
                
                # If field wasn't matched with a position, add it without position data
                if not field_matched:
                    logger.warning(f"Field not matched with position: {field.key} = {field_value}")
                    extracted_fields.append(
                        ExtractedField(
                            key=field.key,
                            value=field_value,
                            page=None,
                            bbox=None
                        )
                    )
            
            logger.info(f"Created {len(extracted_fields)} extracted fields with position matching")

        # Create result
        result = ProcessingResult(
            document_type=template.document_type,
            extracted_fields=extracted_fields,
            text_content=text_content
        )
        
        logger.info(f"Created ProcessingResult with {len(result.extracted_fields)} fields")

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
        # Log the fields being saved to help troubleshoot
        logger.info(f"Saving {len(result.extracted_fields)} extracted fields to {extracted_json_path}")
        for field in result.extracted_fields:
            logger.info(f"Field being saved: {field.key} = {field.value}")
        
        # Save extracted data to JSON
        output_data = {
            'document_type': result.document_type,
            'fields': [
                {'key': f.key, 'value': f.value}
                for f in result.extracted_fields
            ],
            'text_content': result.text_content
        }
        
        logger.info(f"Final JSON has {len(output_data['fields'])} fields")
        
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
