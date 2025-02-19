from typing import Tuple, List, Dict, Optional
from pydantic import BaseModel, Field

class FieldTemplate(BaseModel):
    """Represents a field to be extracted."""
    key: str
    value: str = ""

class ExtractionTemplate(BaseModel):
    """Template for document extraction."""
    document_type: str
    fields: List[FieldTemplate]
    text_content: str = ""

    def get_field_patterns(self) -> List[str]:
        """Generate field patterns from template, handling numbered fields."""
        patterns = []
        base_fields = {}
        
        for field in self.fields:
            if field.key.endswith('_1'):
                # This is a numbered field pattern
                base_key = field.key[:-2]  # Remove '_1'
                base_fields[base_key] = True
            elif field.key.endswith('_n'):
                # Skip _n fields as they're just placeholders
                continue
            else:
                patterns.append(field.key)
        
        # Add numbered patterns
        for base_key in base_fields:
            patterns.append(f"{base_key}_\\d+")
            
        return patterns

class ExtractedField(BaseModel):
    """Represents an extracted field from the document."""
    key: str
    value: str
    page: Optional[int] = None
    bbox: Optional[Tuple[float, float, float, float]] = None

class ExtractedFieldGPT(BaseModel):
    """Represents a field in the GPT response."""
    key: str
    value: str

class GPTResponse(BaseModel):
    """Represents the raw response from GPT."""
    fields: List[ExtractedFieldGPT]

class DocumentAnalysis(BaseModel):
    """Represents the analyzed document data."""
    document_type: str
    fields: List[ExtractedFieldGPT]
    text_content: str

    @classmethod
    def from_gpt_response(cls, gpt_response: GPTResponse, template: ExtractionTemplate, text_content: str) -> 'DocumentAnalysis':
        return cls(
            document_type=template.document_type,
            fields=gpt_response.fields,
            text_content=text_content
        )

class ProcessingResult(BaseModel):
    """Represents the final processing result."""
    document_type: str
    extracted_fields: List[ExtractedField]
    text_content: str
