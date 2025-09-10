# pdf_extractor/cli.py
import sys
from pathlib import Path
from pdf_extractor.config.extraction_config import ExtractionConfig
from pdf_extractor.core.extractor import PDFExtractor
from pdf_extractor.utils.logging import get_logger

logger = get_logger(__name__)

def validate_paths(config_path: str, sharepoint_url: str, input_folder: str, output_folder: str) -> None:
    """Validate all input and output paths."""
    # Check config file exists
    if not Path(config_path).exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    # Validate SharePoint URL format
    if not (sharepoint_url.startswith('http') and 'sharepoint.com' in sharepoint_url):
        raise ValueError(f"Invalid SharePoint URL format: {sharepoint_url}")
    
    logger.info(f"Extraction schema will be built from SharePoint: {sharepoint_url}")
    
    # Check input folder exists
    if not Path(input_folder).exists():
        raise FileNotFoundError(f"Input folder not found: {input_folder}")
    
    # Ensure output folder exists or create it
    Path(output_folder).mkdir(parents=True, exist_ok=True)

def process_pdf_file(
    extractor: PDFExtractor,
    input_pdf_path: Path,
    output_folder: Path,
    sharepoint_url: str,
    input_folder: Path
) -> None:
    """Process a single PDF file."""
    # Define output paths
    relative_path = input_pdf_path.relative_to(input_folder)
    output_dir = output_folder / relative_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    annotated_pdf_path = output_dir / f"{input_pdf_path.stem}_annotated.pdf"
    extracted_json_path = output_dir / f"{input_pdf_path.stem}.json"

    # Check if both output files exist and are non-empty
    if (
        annotated_pdf_path.exists() and extracted_json_path.exists() and
        annotated_pdf_path.stat().st_size > 0 and extracted_json_path.stat().st_size > 0
    ):
        logger.info(f"Skipping {input_pdf_path} as both output files already exist.")
        return

    # Process the PDF - let exceptions propagate up
    logger.info(f"Processing {input_pdf_path}")
    extractor.process_pdf(
        input_pdf_path=str(input_pdf_path),
        sharepoint_url=sharepoint_url,
        output_pdf_path=str(annotated_pdf_path),
        extracted_json_path=str(extracted_json_path)
    )
    logger.info(f"Completed processing {input_pdf_path}")

def main():
    """
    Usage:
      pdf-extractor <config.json> <model_name> <sharepoint_url> <input_folder> <output_folder>
    
    - `config.json`: Configuration file with API keys and SharePoint credentials
    - `model_name`: Base model or fine-tuned model ID (e.g. ft:...)
    - `sharepoint_url`: SharePoint Excel URL containing extraction schema and data
    - `input_folder`: Directory containing PDF files to process
    - `output_folder`: Where the processed files will be saved
    
    Example:
      pdf-extractor config.json ft:gpt-4o-mini "https://company.sharepoint.com/:x:/r/sites/..." input/ output/
    """
    try:
        if len(sys.argv) != 6:
            print("Usage: pdf-extractor <config.json> <model_name> <sharepoint_url> <input_folder> <output_folder>")
            print("  sharepoint_url: SharePoint Excel URL containing extraction schema and data")
            sys.exit(1)

        config_path = sys.argv[1]
        model_name = sys.argv[2]
        sharepoint_url = sys.argv[3]
        input_folder = sys.argv[4]
        output_folder = sys.argv[5]

        # Validate paths
        validate_paths(config_path, sharepoint_url, input_folder, output_folder)

        # Load config
        config = ExtractionConfig.from_json(config_path)
        api_key = config.ml_engine.api_key
        logger.debug(f"Using user-provided model: {model_name}")

        # Create the PDFExtractor with config path for SharePoint access
        extractor = PDFExtractor(api_key=api_key, model_name=model_name, config_path=config_path)

        # Convert input_folder and output_folder to Path objects
        input_folder_path = Path(input_folder)
        output_folder_path = Path(output_folder)

        # Find all PDF files in the input folder recursively
        pdf_files = list(input_folder_path.rglob("*.pdf"))

        if not pdf_files:
            logger.warning(f"No PDF files found in {input_folder}")
            sys.exit(0)

        # Process each PDF file
        for pdf_file in pdf_files:
            process_pdf_file(
                extractor=extractor,
                input_pdf_path=pdf_file,
                output_folder=output_folder_path,
                sharepoint_url=sharepoint_url,
                input_folder=input_folder_path
            )

        logger.info("All PDF processing completed successfully")
    except Exception as e:
        logger.error(f"Error during processing: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
