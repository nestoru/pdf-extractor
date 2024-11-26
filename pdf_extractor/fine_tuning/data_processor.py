# fine_tuning/data_processor.py
from pathlib import Path
import json
from typing import List, Dict
import logging
from pdf_extractor.core.models import ProcessingResult, ExtractionTemplate

logger = logging.getLogger(__name__)

class FineTuningDataProcessor:
    """Processes data for fine-tuning OpenAI models."""
    
    @staticmethod
    def create_training_example(
        text_content: str,
        template: ExtractionTemplate,
        correct_fields: Dict[str, str]
    ) -> Dict:
        """Create a single training example in OpenAI's format."""
        # System message explaining the task
        system_msg = f"""You are a document analysis expert. This is a {template.document_type}. 
Extract only the following fields, maintaining their exact keys:

{chr(10).join([f"- {field.key}" for field in template.fields])}

For repeating items (like line items), identify all instances and number them sequentially.
Return only the specified fields in a JSON format with 'fields' as an array of objects, 
each having 'key' and 'value' properties."""

        # User message containing the document text
        user_msg = f"Extract the specified fields from this document:\n\n{text_content}"

        # Assistant message containing the correct extraction
        correct_fields_list = [
            {"key": k, "value": v} for k, v in correct_fields.items()
        ]
        assistant_msg = json.dumps({"fields": correct_fields_list})

        return {
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": assistant_msg}
            ]
        }

    @classmethod
    def prepare_training_data(
        cls,
        training_dir: Path,
        output_path: Path
    ) -> List[Dict]:
        """Prepare training data from a directory of verified extractions."""
        training_examples = []
        
        # Process each JSON file in the training directory
        for json_path in training_dir.glob("*.json"):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Get corresponding template file
                template_path = json_path.with_suffix('.template.json')
                if not template_path.exists():
                    logger.warning(f"Template not found for {json_path}")
                    continue
                    
                with open(template_path, 'r', encoding='utf-8') as f:
                    template_data = json.load(f)
                
                template = ExtractionTemplate(**template_data)
                
                # Create field dictionary from verified data
                correct_fields = {
                    field['key']: field['value']
                    for field in data['fields']
                }
                
                example = cls.create_training_example(
                    data['text_content'],
                    template,
                    correct_fields
                )
                training_examples.append(example)
                
            except Exception as e:
                logger.error(f"Error processing {json_path}: {str(e)}")
                continue
        
        # Save the prepared training data
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(training_examples, f, indent=2)
        
        return training_examples
