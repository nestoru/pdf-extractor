# pdf_extractor/cli_finetune.py
import sys
from pathlib import Path
from typing import Optional
import json
from pdf_extractor.utils.logging import get_logger
from pdf_extractor.finetune_commands.train import train_command
from pdf_extractor.finetune_commands.validate import validate_command
from pdf_extractor.finetune_commands.excel2training import excel2training_command
from pdf_extractor.finetune_commands.list_models import list_models_command
from pdf_extractor.finetune_commands.list_jobs import list_jobs_command
from pdf_extractor.finetune_commands.status import get_job_status_command

logger = get_logger(__name__)

def print_usage():
    """Print usage information."""
    print("Usage:")
    print("  pdf-extractor-finetune list-models <config.json>")
    print("  pdf-extractor-finetune list-jobs <config.json> [limit]")
    print("  pdf-extractor-finetune status <config.json> <job_id>")
    print("  pdf-extractor-finetune train <config.json> "
          "<openai_model_name> <json_files_folder> <custom_model_name> [--dry-run]")
    print("  pdf-extractor-finetune validate <config.json> "
          "<json_files_folder> <pdf_files_folder> <model_name> <template_path> [error_limit]")
    print("  pdf-extractor-finetune excel2training <config.json> "
          "<json_files_folder> <pdf_files_folder> <sharepoint_excel_shared_link>")

def main():
    """Main entry point for the PDF extraction fine-tuning tool."""
    try:
        if len(sys.argv) < 2:
            print_usage()
            sys.exit(1)

        command = sys.argv[1]
        args = sys.argv[2:]

        if command == "list-models":
            if len(args) != 1:
                print("Usage: pdf-extractor-finetune list-models <config.json>")
                sys.exit(1)
            list_models_command(args[0])

        elif command == "list-jobs":
            if len(args) not in [1, 2]:
                print("Usage: pdf-extractor-finetune list-jobs <config.json> [limit]")
                sys.exit(1)
            limit = int(args[1]) if len(args) == 2 else None
            list_jobs_command(args[0], limit)

        elif command == "status":
            if len(args) != 2:
                print("Usage: pdf-extractor-finetune status <config.json> <job_id>")
                sys.exit(1)
            get_job_status_command(args[0], args[1])

        elif command == "train":
            # Updated to remove pdf_files_folder parameter
            if len(args) not in [4, 5] or (len(args) == 5 and args[4] != '--dry-run'):
                print("Usage: pdf-extractor-finetune train <config.json> "
                      "<openai_model_name> <json_files_folder> <custom_model_name> [--dry-run]")
                sys.exit(1)
            dry_run = len(args) == 5 and args[4] == '--dry-run'
            train_command(
                config_path=args[0],
                base_model_name=args[1],
                json_folder=args[2],
                custom_model_name=args[3],
                dry_run=dry_run
            )

        elif command == "validate":
            if len(args) not in [5, 6, 7] or (len(args) == 7 and args[6] != '--dry-run'):
                print("Usage: pdf-extractor-finetune validate <config.json> "
                      "<openai_model_name> <json_files_folder> <pdf_files_folder> "
                      "<template_path> [error_limit] [--dry-run]")
                sys.exit(1)

            # Check if error_limit or dry_run are provided
            dry_run = args[-1] == '--dry-run' if len(args) == 7 else False
            if dry_run:
                error_limit = int(args[5]) if len(args) == 7 else 5
            else:
                error_limit = int(args[5]) if len(args) == 6 else 5

            validate_command(
                config_path=args[0],
                model_name=args[1],
                json_folder=args[2],
                pdf_folder=args[3],
                template_path=args[4],
                error_limit=error_limit,
                dry_run=dry_run
            )

        elif command == "excel2training":
            if len(args) != 4:
                print("Usage: pdf-extractor-finetune excel2training <config.json> "
                      "<json_files_folder> <pdf_files_folder> <sharepoint_excel_shared_link>")
                sys.exit(1)
            excel2training_command(
                config_path=args[0],
                json_folder=args[1],
                pdf_folder=args[2],
                sharepoint_link=args[3]
            )

        else:
            print(f"Unknown command: {command}")
            print("Available commands: list-models, list-jobs, status, train, validate, excel2training")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
