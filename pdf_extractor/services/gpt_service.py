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

    def analyze_document(self, text_content: str, template: ExtractionTemplate) -> DocumentAnalysis:
        """Analyze document content using GPT."""
        # Get field patterns to look for
        field_patterns = template.get_field_patterns()

        # Create pattern descriptions for GPT
        pattern_descriptions = []
        for pattern in field_patterns:
            if '\\d+' in pattern:
                base_pattern = pattern.replace('_\\d+', '')
                pattern_descriptions.append(
                    f"- {base_pattern}: Look for multiple instances, numbered sequentially"
                )
            else:
                pattern_descriptions.append(f"- {pattern}")

        system_prompt = f"""You are a document analysis expert. This is a {template.document_type}.
Extract only the following fields, maintaining their exact keys:

{chr(10).join(pattern_descriptions)}

For repeating items, identify all instances and number them sequentially.
Return only the specified fields in a JSON format with 'fields' as an array of objects,
each having 'key' and 'value' properties."""

        user_prompt = f"Extract the specified fields from this document:\n\n{text_content}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # Generate completion
        content = self.gpt.generate_completion(messages)

        # Process response
        response_data = json.loads(content)
        fields = [ExtractedFieldGPT(**field) for field in response_data['fields']]
        gpt_response = GPTResponse(fields=fields)

        return DocumentAnalysis.from_gpt_response(gpt_response, template, text_content)
