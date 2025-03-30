# pdf_extractor/fine_tuning/data_processor.py

from pathlib import Path
import json
from typing import List, Dict, Optional, Tuple, Set
import logging
from datetime import datetime
import shutil

logger = logging.getLogger(__name__)

class FineTuningDataProcessor:
    """
    Processes data for fine-tuning OpenAI models.
    Works with JSON files that have embedded pdf_content.
    No caching is used - always processes all files from scratch for reliability.
    """
    
    def process_json_file(
        self,
        json_path: Path,
        field_keys: List[str] = None
    ) -> Optional[Dict]:
        """
        Process a single JSON file with embedded pdf_content and return a training example.
        
        Args:
            json_path: Path to the JSON file with embedded pdf_content
            field_keys: List of field keys to include in the prompt (required)
            
        Returns:
            dict: A training example in the format expected by OpenAI's fine-tuning API,
                  or None if processing failed
        """
        try:
            # Load JSON data
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Verify pdf_content exists
            if "pdf_content" not in data or not data["pdf_content"].strip():
                logger.warning(f"JSON file missing or has empty pdf_content field: {json_path}")
                return None
                
            # Extract the content and fields
            user_content = data["pdf_content"]
            
            # Verify fields exist
            if "fields" not in data or not data["fields"]:
                logger.warning(f"JSON file missing or has empty fields: {json_path}")
                return None
            
            # Create prompt with field keys (field keys are now required)
            if field_keys and len(field_keys) > 0:
                field_keys_str = ", ".join(field_keys)
                user_prompt = f"Extract ONLY the following fields from this document and format as JSON. Required fields: {field_keys_str}.\n\n{user_content}"
            else:
                # Fallback, though this should not normally happen
                logger.warning(f"No field keys provided for {json_path}, using generic prompt")
                user_prompt = f"Extract the fields from this document and format as JSON:\n\n{user_content}"
                
            # Construct the training example in chat format
            training_example = {
                "messages": [
                    {
                        "role": "user",
                        "content": user_prompt
                    },
                    {
                        "role": "assistant",
                        "content": json.dumps({"fields": data["fields"]})
                    }
                ]
            }

            return training_example

        except Exception as e:
            logger.error(f"Error processing JSON file {json_path}: {e}")
            return None
        
    def collect_field_keys(self, json_files: List[Path]) -> List[str]:
        """
        Collect all unique field keys from the JSON files.
        
        Args:
            json_files: List of paths to JSON files
            
        Returns:
            list: List of unique field keys
        """
        all_keys = set()
        
        for json_file in json_files:
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                if "fields" in data and data["fields"]:
                    for field in data["fields"]:
                        if "key" in field and field["key"]:
                            all_keys.add(field["key"])
            except Exception as e:
                logger.error(f"Error extracting field keys from {json_file}: {e}")
        
        return sorted(list(all_keys))
        
    def prepare_training_data_from_jsons(
        self,
        json_files: List[Path],
        output_path: Path
    ) -> Tuple[List[Dict], Optional[Path]]:
        """
        Prepare training data from JSON files with embedded pdf_content.
        Field keys will always be included in the prompts.

        Args:
            json_files: List of paths to JSON files with embedded pdf_content
            output_path: Path to save the prepared training data
            
        Returns:
            tuple: (list of training examples, path to the training file)
        """
        output_path = Path(output_path)
        
        # Clean up any existing training files with the same name pattern
        self._cleanup_training_files(output_path)
        
        # Always collect field keys - this is now required
        logger.info("Collecting unique field keys from JSON files...")
        field_keys = self.collect_field_keys(json_files)
        logger.info(f"Found {len(field_keys)} unique field keys: {', '.join(field_keys)}")
        
        if not field_keys:
            logger.error("No field keys found in JSON files. Cannot create training data without field keys.")
            return [], None
        
        # Process each JSON file
        all_examples = []
        processed_count = 0
        skipped_count = 0
        
        for json_file in json_files:
            example = self.process_json_file(json_file, field_keys)
            if example:
                all_examples.append(example)
                processed_count += 1
            else:
                skipped_count += 1

        logger.info(f"Processed {processed_count} JSON files, skipped {skipped_count} due to errors or missing required fields")
        
        if not all_examples:
            logger.error("No valid training examples were created. Check your JSON files.")
            return [], None

        # Write the training file
        return self._write_training_file(all_examples, output_path)
    
    def _write_training_file(
        self,
        examples: List[Dict],
        output_path: Path
    ) -> Tuple[List[Dict], Optional[Path]]:
        """
        Write training examples to a JSONL file.
        
        Args:
            examples: List of training examples
            output_path: Path to save the training file
            
        Returns:
            tuple: (list of training examples, path to the training file)
        """
        try:
            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, "w", encoding="utf-8") as f:
                for example in examples:
                    f.write(json.dumps(example, ensure_ascii=False) + "\n")
                    
            logger.info(f"Created training file: {output_path} with {len(examples)} examples")
            return examples, output_path
            
        except Exception as e:
            logger.error(f"Failed to write training file '{output_path}': {e}")
            return [], None
            
    def _cleanup_training_files(self, output_path: Path) -> None:
        """
        Clean up any existing training files with the same base name pattern.
        This ensures we don't have multiple training files from previous runs.
        
        Args:
            output_path: The target output path for the new training file
        """
        # Get the pattern to match (e.g., "training_*.jsonl")
        pattern = f"{output_path.stem.split('_')[0]}_*.jsonl"
        
        # Find all matching files in the directory
        for existing_file in output_path.parent.glob(pattern):
            try:
                existing_file.unlink()
                logger.info(f"Removed existing training file: {existing_file}")
            except Exception as e:
                logger.warning(f"Could not remove existing file {existing_file}: {e}")
