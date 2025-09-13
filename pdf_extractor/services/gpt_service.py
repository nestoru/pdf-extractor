# pdf_extractor/services/gpt_service.py
import json
from typing import Dict, List, Optional
from pdf_extractor.core.models import DocumentAnalysis, GPTResponse, ExtractionTemplate, ExtractedFieldGPT
from pdf_extractor.config.extraction_config import ExtractionConfig
from pdf_extractor.services.gpt_implementations import get_gpt_implementation
from pdf_extractor.utils.logging import get_logger

logger = get_logger(__name__)

class GPTService:
    """Service for handling GPT API interactions."""

    def __init__(self, api_key: str, model_name: str):
        """Initialize the GPT service with API key and model name."""
        self.api_key = api_key
        self.model_name = model_name
        self.gpt = get_gpt_implementation(api_key=api_key, model_name=model_name)
        self.is_fine_tuned = model_name.startswith('ft:')

    def analyze_document(
        self, 
        text_content: str, 
        template: ExtractionTemplate,
        alternative_names: Optional[Dict[str, str]] = None,
        extraction_rules: Optional[Dict[str, str]] = None,
        include_coordinates: bool = False
    ) -> DocumentAnalysis:
        """
        Analyze document content using GPT with optional alternative names and extraction rules.
        
        Args:
            text_content: The document text to analyze (may include coordinate markers)
            template: The extraction template with fields
            alternative_names: Optional dict mapping field names to alternative names
            extraction_rules: Optional dict mapping field names to extraction rules/tips
            include_coordinates: Whether to request coordinates in the response
        """

        # Extract the actual field keys from the template
        field_keys = [field.key for field in template.fields]

        # Build enhanced field descriptions if metadata is provided
        field_descriptions = []
        for field_key in field_keys:
            desc = f"- {field_key}"
            
            # Add alternative names if available
            if alternative_names and field_key in alternative_names:
                desc += f" (also known as: {alternative_names[field_key]})"
            
            # Add extraction rules if available
            if extraction_rules and field_key in extraction_rules:
                desc += f" [Extraction tip: {extraction_rules[field_key]}]"
            
            field_descriptions.append(desc)

        # Format field keys as a comma-separated list for the prompt
        field_keys_str = ", ".join(field_keys)
        field_descriptions_str = "\n".join(field_descriptions)

        # For fine-tuned models, include the enhanced information in a structured way
        if self.is_fine_tuned:
            # Build a more detailed prompt for fine-tuned models
            prompt_parts = [
                "Extract ONLY the following fields from this document and format as JSON.",
                "You MUST use the EXACT field names provided below without any modification or abbreviation.",
                f"Required fields: {field_keys_str}."
            ]
            
            # Add coordinate instructions if needed
            if include_coordinates:
                prompt_parts.extend([
                    "",
                    "IMPORTANT: The document includes coordinate markers in the format [text]<@page:x1,y1,x2,y2>.",
                    "When you find a field value, include its coordinate marker in your response.",
                    "For example, if you find 'Invoice Date' with value '2024-01-15' at coordinates <@0:100.5,200.3,180.2,215.8>,",
                    "return: {'key': 'Invoice Date', 'value': '[2024-01-15]<@0:100.5,200.3,180.2,215.8>'}"
                ])
            
            # Add field details if we have metadata
            if alternative_names or extraction_rules:
                prompt_parts.append("\nField extraction details:")
                prompt_parts.append(field_descriptions_str)
            
            prompt_parts.append(f"\n\n{text_content}")
            user_prompt = "\n".join(prompt_parts)

            messages = [
                {"role": "user", "content": user_prompt}
            ]

            logger.info(f"Using fine-tuned model with enhanced field metadata (coordinates: {include_coordinates})")
        else:
            # For base models, use the system message with enhanced field patterns
            system_prompt_parts = [
                f"You are a document analysis expert. This is a {template.document_type}.",
                "Extract ONLY the following fields, maintaining their exact keys without any modification:"
            ]
            
            # Add detailed field descriptions
            system_prompt_parts.append(field_descriptions_str)
            
            system_prompt_parts.extend([
                "",
                "Important instructions:",
                "1. Use the field names EXACTLY as provided (before any parentheses or brackets)",
                "2. Consider alternative names when searching for fields in the document",
                "3. Apply the extraction tips to identify the correct values",
            ])
            
            # Add coordinate-specific instructions if needed
            if include_coordinates:
                system_prompt_parts.extend([
                    "4. The document contains coordinate markers in format [text]<@page:x1,y1,x2,y2>",
                    "5. When you extract a value, preserve its coordinate marker in your response",
                    "6. Include the full marker with brackets and coordinates, e.g., '[value]<@0:100,200,300,220>'",
                    "7. IMPORTANT: Extract the ACTUAL values from the document, not placeholders or zeros",
                    "8. For negative numbers shown as (number), extract as negative, e.g., '(1,698,064)' becomes '-1698064'",
                    "9. Return the specified fields in a JSON format with 'fields' as an array of objects,",
                    "   each having 'key' and 'value' properties, where value includes the coordinate marker.",
                ])
            else:
                system_prompt_parts.extend([
                    "4. Return the specified fields in a JSON format with 'fields' as an array of objects,",
                    "   each having 'key' and 'value' properties.",
                    "5. For negative numbers shown as (number), extract as negative, e.g., '(1,698,064)' becomes '-1698064'",
                ])
            
            system_prompt_parts.append("6. Use the field names exactly as provided, not the alternative names.")
            
            system_prompt = "\n".join(system_prompt_parts)

            if include_coordinates:
                user_prompt = (
                    "Extract ONLY the specified fields from this document as JSON.\n"
                    "IMPORTANT: Include coordinate markers with each extracted value.\n"
                    f"Document:\n\n{text_content}"
                )
            else:
                user_prompt = f"Extract ONLY the specified fields from this document as JSON:\n\n{text_content}"

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            logger.info(f"Using base model with enhanced system message (coordinates: {include_coordinates})")

        # Generate completion
        logger.info(f"Sending request to model: {self.model_name}")
        logger.debug(f"Prompt contains {len(field_keys)} fields with {len(alternative_names or {})} alternative names and {len(extraction_rules or {})} rules")
        if include_coordinates:
            logger.debug("Requesting coordinate information in response")

        content = self.gpt.generate_completion(messages)

        # Process response
        try:
            response_data = json.loads(content)
            logger.info(f"Successfully parsed JSON response with {len(response_data.get('fields', []))} fields")
        except json.JSONDecodeError:
            # Try to extract JSON from text
            logger.warning(f"Failed to parse response as JSON directly: {content[:200]}...")
            try:
                # Look for JSON-like structure
                import re
                json_match = re.search(r'(\{.*\})', content, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                    logger.info(f"Extracted JSON string")
                    response_data = json.loads(json_str)
                else:
                    logger.error(f"Could not extract JSON from response")
                    # Return empty fields as fallback
                    response_data = {"fields": []}
            except Exception as e:
                logger.error(f"Error extracting JSON from response: {e}")
                # Return empty fields as fallback
                response_data = {"fields": []}

        # Process response into a standardized format
        fields = []
        for field in response_data.get('fields', []):
            try:
                extracted_field = ExtractedFieldGPT(**field)
                fields.append(extracted_field)
                
                # Log if coordinates were found in the value
                if include_coordinates and '<@' in str(extracted_field.value):
                    logger.debug(f"Field '{extracted_field.key}' includes coordinate information")
                    
            except Exception as e:
                logger.error(f"Error processing field {field}: {e}")
                continue
        
        logger.info(f"Extracted {len(fields)} fields from document")

        gpt_response = GPTResponse(fields=fields)

        return DocumentAnalysis.from_gpt_response(gpt_response, template, text_content)
