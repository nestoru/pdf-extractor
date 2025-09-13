# pdf_extractor/core/extractor.py
import json
import re
from pathlib import Path
from typing import Dict, Optional, Tuple, List
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

    def _create_coordinate_embedded_text(self, text_content: str, positions: List[Dict]) -> str:
        """
        Create text content with embedded coordinate markers.
        
        This embeds coordinate information directly in the text so the LLM can see
        where each piece of text appears in the document.
        
        Args:
            text_content: Original text content
            positions: List of position dictionaries with text, bbox, page info
            
        Returns:
            Text with embedded coordinate markers
        """
        # Group positions by page for better organization
        pages_text = {}
        for pos in positions:
            page = pos['page']
            if page not in pages_text:
                pages_text[page] = []
            
            # Create a coordinate marker for significant text (not just whitespace)
            if pos['text'].strip():
                # Format: [text]<@page:X,Y,X2,Y2>
                coord_marker = f"[{pos['text']}]<@{page}:{pos['bbox'][0]:.1f},{pos['bbox'][1]:.1f},{pos['bbox'][2]:.1f},{pos['bbox'][3]:.1f}>"
                pages_text[page].append(coord_marker)
        
        # Build the coordinate-embedded document
        embedded_parts = []
        embedded_parts.append("=== DOCUMENT WITH COORDINATE MARKERS ===")
        embedded_parts.append("Format: [text]<@page:x1,y1,x2,y2>")
        embedded_parts.append("")
        
        for page in sorted(pages_text.keys()):
            embedded_parts.append(f"--- PAGE {page + 1} ---")
            # Join text spans with space, grouping by approximate line position
            embedded_parts.append(" ".join(pages_text[page]))
            embedded_parts.append("")
        
        embedded_parts.append("=== END DOCUMENT ===")
        embedded_parts.append("")
        embedded_parts.append("=== ORIGINAL TEXT (for reference) ===")
        embedded_parts.append(text_content)
        
        return "\n".join(embedded_parts)

    def _parse_coordinate_from_response(self, value: str) -> Optional[Tuple[int, Tuple[float, float, float, float]]]:
        """
        Parse coordinate information from GPT response if it includes coordinate markers.
        
        Args:
            value: Value string that might contain coordinate marker
            
        Returns:
            Tuple of (page, bbox) if coordinates found, None otherwise
        """
        # Look for coordinate pattern in the value: <@page:x1,y1,x2,y2>
        coord_pattern = r'<@(\d+):([\d.]+),([\d.]+),([\d.]+),([\d.]+)>'
        match = re.search(coord_pattern, value)
        
        if match:
            page = int(match.group(1))
            bbox = (
                float(match.group(2)),
                float(match.group(3)),
                float(match.group(4)),
                float(match.group(5))
            )
            return page, bbox
        
        return None

    def _clean_value_from_coordinates(self, value: str) -> str:
        """
        Remove coordinate markers from value string.
        
        Args:
            value: Value potentially containing coordinate markers
            
        Returns:
            Clean value without coordinate markers
        """
        # Remove coordinate patterns and brackets
        coord_pattern = r'<@\d+:[\d.,]+>'
        cleaned = re.sub(coord_pattern, '', value)
        # Also remove the brackets used for marking
        cleaned = re.sub(r'^\[(.*?)\]$', r'\1', cleaned.strip())
        return cleaned.strip()

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

        # Extract text and positions
        if validation_mode:
            text_content = self.pdf_service.extract_text(input_pdf_path)
            coordinate_embedded_text = text_content  # No coordinates in validation mode
        else:
            text_content, positions = self.pdf_service.extract_text_and_positions(input_pdf_path)
            # Create text with embedded coordinates for GPT
            coordinate_embedded_text = self._create_coordinate_embedded_text(text_content, positions)
            logger.info(f"Created coordinate-embedded text with {len(positions)} position markers")

        # Analyze with GPT only for non-filename fields
        gpt_analysis = None
        extracted_fields = []
        
        if gpt_template.fields:  # Only call GPT if there are non-filename fields
            # Use coordinate-embedded text for GPT analysis
            gpt_analysis = self.gpt_service.analyze_document(
                coordinate_embedded_text,  # Send text with coordinates
                gpt_template,
                alternative_names=gpt_alternative_names,
                extraction_rules=gpt_extraction_rules,
                include_coordinates=not validation_mode  # Tell GPT to include coordinates
            )
            logger.info(f"GPT analysis returned {len(gpt_analysis.fields)} fields")
            
            # Process GPT fields and extract coordinates if present
            for field in gpt_analysis.fields:
                field_value = str(field.value)
                
                # Try to parse coordinates from the response
                coord_info = self._parse_coordinate_from_response(field_value)
                
                if coord_info:
                    page, bbox = coord_info
                    clean_value = self._clean_value_from_coordinates(field_value)
                    extracted_fields.append(
                        ExtractedField(
                            key=field.key,
                            value=clean_value,
                            page=page,
                            bbox=bbox
                        )
                    )
                    logger.info(f"Extracted field with GPT-provided coordinates: {field.key} = {clean_value} at page {page}")
                else:
                    # No coordinates in response, try to find them ourselves
                    if not validation_mode and positions:
                        found_position = False
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
                                found_position = True
                                logger.info(f"Found position for field: {field.key} = {field_value}")
                                break
                        
                        if not found_position:
                            # Add without coordinates
                            extracted_fields.append(
                                ExtractedField(
                                    key=field.key,
                                    value=field_value,
                                    page=None,
                                    bbox=None
                                )
                            )
                            logger.warning(f"Could not find position for field: {field.key} = {field_value}")
                    else:
                        # Validation mode or no positions available
                        extracted_fields.append(
                            ExtractedField(
                                key=field.key,
                                value=field_value,
                                page=None,
                                bbox=None
                            )
                        )
        else:
            logger.info("No non-filename fields to analyze with GPT")

        # Add filename fields (without coordinates as they're not in the PDF)
        for field_key, field_value in filename_fields.items():
            extracted_fields.append(
                ExtractedField(
                    key=field_key,
                    value=field_value,
                    page=None,
                    bbox=None
                )
            )
            logger.info(f"Added filename field: {field_key} = {field_value}")

        logger.info(f"Total extracted fields: {len(extracted_fields)}")

        # Create result - use coordinate-embedded text when not in validation mode
        result = ProcessingResult(
            document_type=template.document_type,
            extracted_fields=extracted_fields,
            text_content=coordinate_embedded_text if (not validation_mode and coordinate_embedded_text) else text_content
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
        # Log the fields being saved
        logger.info(f"Saving {len(result.extracted_fields)} extracted fields to {extracted_json_path}")
        for field in result.extracted_fields:
            logger.info(f"Field being saved: {field.key} = {field.value}, page={field.page}, bbox={field.bbox}")
        
        # Save extracted data to JSON with coordinates
        output_data = {
            'document_type': result.document_type,
            'fields': [
                {
                    'key': f.key, 
                    'value': f.value,
                    'page': f.page,
                    'bbox': list(f.bbox) if f.bbox else None
                }
                for f in result.extracted_fields
            ],
            'text_content': result.text_content
        }
        
        logger.info(f"Final JSON has {len(output_data['fields'])} fields with coordinates")
        
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
