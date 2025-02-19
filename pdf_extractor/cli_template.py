# pdf_extractor/cli_template.py

import sys
from pathlib import Path
from pdf_extractor.utils.logging import get_logger
from pdf_extractor.template.generator import create_template

logger = get_logger(__name__)

def print_usage():
    """Print usage information."""
    print("Usage:")
    print("  create-inference-template <config.json> <sharepoint_excel_shared_link> "
          "<document_type> <output_path>")
    print("\nExample:")
    print("  create-inference-template config.json "
          "'https://sharepoint.com/.../fields.xlsx' 'CAS' ./templates/cas_template.json")

def main():
    """Main entry point for creating inference templates."""
    try:
        if len(sys.argv) != 5:
            print_usage()
            sys.exit(1)

        config_path = sys.argv[1]
        sharepoint_link = sys.argv[2]
        document_type = sys.argv[3]
        output_path = sys.argv[4]

        print(f"\nCreating inference template for document type: {document_type}")
        create_template(
            config_path=config_path,
            sharepoint_link=sharepoint_link,
            document_type=document_type,
            output_path=output_path
        )
        print(f"\n✓ Template created successfully: {output_path}")

    except Exception as e:
        logger.error(f"Error creating template: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
