# pdf_extractor/cli.py
import sys
from pathlib import Path
from pdf_extractor.config.extraction_config import ExtractionConfig
from pdf_extractor.core.extractor import PDFExtractor
from pdf_extractor.utils.logging import get_logger

logger = get_logger(__name__)

def validate_paths(config_path: str, fields_template_path: str, input_folder: str, output_folder: str) -> None:
    """Validate all input and output paths."""
    # Check input files exist
    for path, desc in [
        (config_path, "Configuration file"),
        (fields_template_path, "Fields template file"),
        (input_folder, "Input folder")
    ]:
        if not Path(path).exists():
            raise FileNotFoundError(f"{desc} not found: {path}")
    
    # Ensure output folder exists or create it
    Path(output_folder).mkdir(parents=True, exist_ok=True)

def process_pdf_file(
    extractor: PDFExtractor,
    input_pdf_path: Path,
    output_folder: Path,
    fields_template_path: str,
    input_folder: Path  # Add input_folder as a parameter
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

    # Process the PDF
    try:
        logger.info(f"Processing {input_pdf_path}")
        extractor.process_pdf(
            input_pdf_path=str(input_pdf_path),
            template_path=fields_template_path,
            output_pdf_path=str(annotated_pdf_path),
            extracted_json_path=str(extracted_json_path)
        )
        logger.info(f"Completed processing {input_pdf_path}")
    except Exception as e:
        logger.error(f"Error processing {input_pdf_path}: {str(e)}")

def main():
    """
    New Usage:
      pdf-extractor <config.json> <model_name> <fields_template.json> <input_folder> <output_folder>
    - `config.json` is used ONLY for the API key (ml_engine.api_key).
    - `model_name` can be a base model or a fine-tuned model ID (e.g. ft:...).
    - `input_folder` is the directory containing PDF files to process.
    - `output_folder` is where the processed files will be saved.
    """
    try:
        if len(sys.argv) != 6:
            print("Usage: pdf-extractor <config.json> <model_name> <fields_template.json> <input_folder> <output_folder>")
            sys.exit(1)

        config_path = sys.argv[1]
        model_name = sys.argv[2]
        fields_template_path = sys.argv[3]
        input_folder = sys.argv[4]  # Assign input_folder here
        output_folder = sys.argv[5]

        # Validate paths
        validate_paths(config_path, fields_template_path, input_folder, output_folder)

        # Load only the API key from config
        config = ExtractionConfig.from_json(config_path)
        api_key = config.ml_engine.api_key  # We do NOT read "model" from the config
        logger.debug(f"Using user-provided model: {model_name}")

        # Create the PDFExtractor, passing in the API key and model name
        extractor = PDFExtractor(api_key=api_key, model_name=model_name)

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
                fields_template_path=fields_template_path,
                input_folder=input_folder_path  # Pass input_folder_path here
            )

        logger.info("All PDF processing completed successfully")
    except Exception as e:
        logger.error(f"Error during processing: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
