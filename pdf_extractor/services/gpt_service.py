# pdf_extractor/services/gpt_service.py
import json
from typing import Dict, List
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
    
    def analyze_document(self, text_content: str, template: ExtractionTemplate) -> DocumentAnalysis:
        """Analyze document content using GPT."""
        
        # Extract the actual field keys from the template
        field_keys = [field.key for field in template.fields]
        
        # Format field keys as a comma-separated list for the prompt
        field_keys_str = ", ".join(field_keys)
        
        # For fine-tuned models, use the exact same format as in training
        if self.is_fine_tuned:
            # Include field keys in the prompt with ONLY specification, matching the training format exactly
            user_prompt = f"Extract ONLY the following fields from this document and format as JSON. Required fields: {field_keys_str}.\n\n{text_content}"
            
            messages = [
                {"role": "user", "content": user_prompt}
            ]
            
            logger.info("Using fine-tuned model prompt format with field keys")
        else:
            # For base models, use the system message with field patterns
            system_prompt = f"""You are a document analysis expert. This is a {template.document_type}.
Extract ONLY the following fields, maintaining their exact keys:
{chr(10).join(['- ' + key for key in field_keys])}
Return the specified fields in a JSON format with 'fields' as an array of objects,
each having 'key' and 'value' properties."""
            
            user_prompt = f"Extract ONLY the specified fields from this document as JSON:\n\n{text_content}"
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            logger.info("Using base model prompt format with system message")
        
        # Generate completion
        logger.info(f"Sending request to model: {self.model_name}")
        logger.debug(f"Prompt contains field keys: {field_keys_str}")
        
        content = self.gpt.generate_completion(messages)
        
        # Process response
        try:
            response_data = json.loads(content)
            logger.info(f"Successfully parsed JSON response with {len(response_data.get('fields', []))} fields")
        except json.JSONDecodeError:
            # Try to extract JSON from text
            logger.warning(f"Failed to parse response as JSON directly: {content}")
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
        fields = [ExtractedFieldGPT(**field) for field in response_data.get('fields', [])]
        logger.info(f"Extracted {len(fields)} fields from document")
        
        gpt_response = GPTResponse(fields=fields)
        
        return DocumentAnalysis.from_gpt_response(gpt_response, template, text_content)
