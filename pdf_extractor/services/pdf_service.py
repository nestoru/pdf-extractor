from pathlib import Path
from typing import Tuple, List, Dict
import fitz
from pdf_extractor.core.models import ExtractedField
from pdf_extractor.utils.logging import get_logger

logger = get_logger(__name__)

class PDFService:
    """Service for handling PDF operations."""
    
    @staticmethod
    def extract_text_and_positions(pdf_path: str) -> Tuple[str, List[Dict]]:
        """Extract text content and position information from PDF."""
        doc = fitz.open(pdf_path)
        try:
            full_text = []
            positions = []
            
            for page_num, page in enumerate(doc):
                text_dict = page.get_text("dict")
                page_text = page.get_text()
                full_text.append(page_text)
                
                for block in text_dict["blocks"]:
                    if "lines" in block:
                        for line in block["lines"]:
                            for span in line["spans"]:
                                positions.append({
                                    'page': page_num,
                                    'bbox': span['bbox'],
                                    'text': span['text'].strip(),
                                    'origin': span['origin'],
                                    'font_size': span['size']  # Add font size information
                                })
            
            return "\n".join(full_text), positions
            
        finally:
            doc.close()

    @staticmethod
    def find_exact_value_position(positions: List[Dict], value: str) -> Dict:
        """Find the exact position of a value in the text positions."""
        # First try exact match
        for pos in positions:
            if pos['text'] == value:
                return pos
                
        # If no exact match, try finding the value within spans
        for pos in positions:
            if value in pos['text']:
                # Calculate the exact position within the span
                x0, y0 = pos['origin']
                text = pos['text']
                start_idx = text.index(value)
                
                # Estimate the position based on character widths
                char_width = (pos['bbox'][2] - pos['bbox'][0]) / len(text)
                
                return {
                    'page': pos['page'],
                    'bbox': (
                        x0 + (start_idx * char_width),  # x0
                        pos['bbox'][1],                 # y0
                        x0 + ((start_idx + len(value)) * char_width),  # x1
                        pos['bbox'][3]                  # y1
                    ),
                    'text': value,
                    'font_size': pos['font_size']  # Include font size
                }
        return None

    @staticmethod
    def create_annotated_pdf(
        input_path: str,
        output_path: str,
        doc_type: str,
        fields: List[ExtractedField]
    ) -> None:
        """Create annotated PDF with highlights and field labels."""
        doc = fitz.open(input_path)
        try:
            positions = []
            for page in doc:
                text_dict = page.get_text("dict")
                for block in text_dict["blocks"]:
                    if "lines" in block:
                        for line in block["lines"]:
                            for span in line["spans"]:
                                positions.append({
                                    'page': page.number,
                                    'bbox': span['bbox'],
                                    'text': span['text'].strip(),
                                    'origin': span['origin'],
                                    'font_size': span['size']
                                })
            
            for field in fields:
                try:
                    page = doc[field.page]
                    
                    # Find exact position for this value
                    value_pos = PDFService.find_exact_value_position(
                        [p for p in positions if p['page'] == field.page], 
                        field.value
                    )
                    
                    if value_pos:
                        # Add highlight only for the value
                        highlight = page.add_highlight_annot(value_pos['bbox'])
                        highlight.set_colors(stroke=(1, 0.8, 0))  # Yellow highlight
                        highlight.set_opacity(0.5)  # Make highlight semi-transparent
                        highlight.update()
                        
                        # Position label directly below the value
                        label_x = value_pos['bbox'][0]  # Align with start of value
                        label_y = value_pos['bbox'][3] + 2  # Just below value
                        
                        # Calculate label font size as 1/4 of the value's font size
                        value_font_size = value_pos['font_size']
                        label_font_size = value_font_size / 4
                        
                        # Add field label
                        page.insert_text(
                            (label_x, label_y),
                            field.key,
                            fontsize=label_font_size,
                            color=(0, 0, 1)  # Blue
                        )
                    
                except Exception as e:
                    logger.warning(f"Error annotating field {field.key}: {str(e)}")
                    continue
            
            doc.save(output_path)
            
        finally:
            doc.close()
