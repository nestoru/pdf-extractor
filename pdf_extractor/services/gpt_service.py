import json
from typing import Dict, List
from pdf_extractor.core.models import DocumentAnalysis, GPTResponse, ExtractionTemplate, ExtractedFieldGPT
from pdf_extractor.config.extraction_config import ExtractionConfig
from pdf_extractor.services.gpt_implementations import get_gpt_implementation
from pdf_extractor.utils.logging import get_logger

logger = get_logger(__name__)

class GPTService:
    """Service for handling GPT API interactions."""
    
    def __init__(self, config: ExtractionConfig):
        """Initialize the GPT service with configuration."""
        self.config = config
        model_config = config.get_model_config()
        self.gpt = get_gpt_implementation(
            api_key=config.ml_engine.api_key,
            model_config=model_config
        )
    
    def analyze_document(self, text_content: str, template: ExtractionTemplate) -> DocumentAnalysis:
        """Analyze document content using configured GPT."""
        # Get field patterns to look for
        field_patterns = template.get_field_patterns()
        
        # Create pattern descriptions for GPT
        pattern_descriptions = []
        for pattern in field_patterns:
            if '\\d+' in pattern:
                # This is a repeating field
                base_pattern = pattern.replace('_\\d+', '')
                pattern_descriptions.append(
                    f"- {base_pattern}: Look for multiple instances, numbered sequentially "
                    f"(e.g., {base_pattern}_1, {base_pattern}_2, etc.)"
                )
            else:
                pattern_descriptions.append(f"- {pattern}")

        system_prompt = f"""You are a document analysis expert. This is a {template.document_type}. 
Extract only the following fields, maintaining their exact keys:

{chr(10).join(pattern_descriptions)}

For repeating items (like line items), identify all instances and number them sequentially.
Return only the specified fields in a JSON format with 'fields' as an array of objects, 
each having 'key' and 'value' properties."""

        user_prompt = f"Extract the specified fields from this document:\n\n{text_content}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # Debug logging
        logger.debug("=== GPT Request Details ===")
        logger.debug(f"Model: {self.config.ml_engine.model}")
        logger.debug("\n=== System Prompt ===\n")
        logger.debug(system_prompt)
        logger.debug("\n=== User Prompt ===\n")
        logger.debug(user_prompt)
        logger.debug("\n=== End Prompts ===\n")
        
        # Generate completion
        content = self.gpt.generate_completion(messages)
            
        # Debug logging for response
        logger.debug("\n=== GPT Response ===\n")
        logger.debug(json.dumps(json.loads(content), indent=2))
        logger.debug("\n=== End Response ===\n")
        
        # Process response
        response_data = json.loads(content)
        fields = [ExtractedFieldGPT(**field) for field in response_data['fields']]
        gpt_response = GPTResponse(fields=fields)
        
        return DocumentAnalysis.from_gpt_response(gpt_response, template, text_content)
