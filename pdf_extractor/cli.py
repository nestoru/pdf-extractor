import sys
from pathlib import Path
from pdf_extractor.config.extraction_config import ExtractionConfig
from pdf_extractor.core.extractor import PDFExtractor
from pdf_extractor.utils.logging import get_logger

logger = get_logger(__name__)

def validate_paths(
    config_path: str,
    input_path: str,
    fields_template_path: str,
    output_pdf_path: str,
    output_json_path: str
) -> None:
    """Validate all input and output paths."""
    # Check input files exist
    for path, desc in [
        (config_path, "Configuration file"),
        (input_path, "Input PDF file"),
        (fields_template_path, "Fields template file")
    ]:
        if not Path(path).is_file():
            raise FileNotFoundError(f"{desc} not found: {path}")
        
    # Check output directories exist
    for path, desc in [
        (output_pdf_path, "Output PDF directory"),
        (output_json_path, "Output JSON directory")
    ]:
        output_dir = Path(path).parent
        if not output_dir.exists():
            raise ValueError(f"{desc} does not exist: {output_dir}")

def main():
    """Main entry point for the PDF extraction tool."""
    try:
        if len(sys.argv) != 6:
            print("Usage: pdf-extractor <config.json> <input.pdf> "
                  "<fields_template.json> <output.pdf> <extracted.json>")
            sys.exit(1)
            
        config_path = sys.argv[1]
        input_pdf_path = sys.argv[2]
        fields_template_path = sys.argv[3]
        output_pdf_path = sys.argv[4]
        extracted_json_path = sys.argv[5]
        
        # Validate paths
        validate_paths(
            config_path,
            input_pdf_path,
            fields_template_path,
            output_pdf_path,
            extracted_json_path
        )
        
        # Load configuration and validate selected model
        config = ExtractionConfig.from_json(config_path)
        # This will raise an error if the selected model is not in available_models
        config.get_model_config()
        
        logger.debug(f"Using model: {config.ml_engine.model}")
        
        extractor = PDFExtractor(config)
        extractor.process_pdf(
            input_pdf_path,
            fields_template_path,
            output_pdf_path,
            extracted_json_path
        )
        
        logger.info("PDF processing completed successfully")
        
    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
