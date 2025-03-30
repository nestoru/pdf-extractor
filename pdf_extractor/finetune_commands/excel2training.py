# pdf_extractor/finetune_commands/excel2training.py

import sys
from pathlib import Path
import pandas as pd
import json
from pdf_extractor.utils.logging import get_logger
from pdf_extractor.sync_to_onedrive import (
    format_value, load_config, get_access_token,
    get_drive_info, get_workbook_session,
    get_worksheet_data, close_workbook_session
)
from pdf_extractor.fine_tuning.data_processor import FineTuningDataProcessor

logger = get_logger(__name__)

def process_sharepoint_excel(config_path: str, sharepoint_link: str) -> pd.DataFrame:
    """
    Download and process Excel file from SharePoint shared link using authentication.
    """
    try:
        # Load SharePoint config
        config = load_config(config_path)
        access_token = get_access_token(config)

        # Get drive info
        drive_info = get_drive_info(access_token, config.get('USER_EMAIL', 'nurquiza@trustserve.net'))
        drive_id = drive_info['id']
        logger.info("Successfully obtained drive info")

        # Extract file ID from shared link
        file_id = sharepoint_link.split('d=w')[1].split('&')[0]

        # Create workbook session
        session_id = get_workbook_session(access_token, drive_id, file_id)
        logger.info("Successfully created workbook session")

        try:
            # Get worksheet data
            worksheet_data = get_worksheet_data(access_token, drive_id, file_id, session_id)

            # Convert to DataFrame
            headers = worksheet_data['values'][0]
            data = worksheet_data['values'][1:]  # Skip header row
            df = pd.DataFrame(data, columns=headers)

            # Check if APPROVED column exists
            if 'APPROVED' not in df.columns:
                error_msg = (
                    "Excel file is missing the 'APPROVED' column. "
                    "Please ensure the Excel file has an 'APPROVED' column with 'Y' values "
                    "for records that should be processed."
                )
                logger.error(error_msg)
                raise ValueError(error_msg)

            # Filter for approved records (case insensitive 'Y' in APPROVED column)
            df = df[df['APPROVED'].str.upper() == 'Y']
            logger.info(f"Found {len(df)} approved records")

            return df

        finally:
            # Always close the session
            if session_id:
                close_workbook_session(access_token, drive_id, file_id, session_id)
                logger.info("Successfully closed workbook session")

    except ValueError as e:
        # Re-raise ValueError with descriptive messages
        raise
    except Exception as e:
        logger.error(f"Error processing SharePoint Excel file: {str(e)}")
        raise ValueError(f"Failed to process SharePoint Excel file: {str(e)}")

def excel2training_command(
    config_path: str,
    json_folder: str,
    pdf_folder: str,
    sharepoint_link: str
) -> None:
    """
    Process SharePoint Excel file and create JSON files.
    """
    try:
        # Create folder paths
        json_folder_path = Path(json_folder)
        pdf_folder_path = Path(pdf_folder)

        logger.info("Starting Excel to training data conversion...")
        print("\nProcessing SharePoint Excel file...")

        # Initialize the data processor for extracting text from PDFs
        data_processor = FineTuningDataProcessor()

        # Process Excel file
        excel_data = process_sharepoint_excel(config_path, sharepoint_link)
        print(f"Found {len(excel_data)} approved records")

        successful_conversions = 0
        skipped_files = 0
        existing_files = 0

        # Process each approved row
        for idx, row in excel_data.iterrows():
            if 'FILE NAME' not in row or pd.isna(row['FILE NAME']) or row['FILE NAME'] == '':
                logger.warning("Row missing FILE NAME column or empty filename, skipping")
                skipped_files += 1
                continue

            # Get the file name and ensure it has the .pdf extension
            file_name = str(row['FILE NAME']).strip()
            if not file_name.lower().endswith('.pdf'):
                file_name += '.pdf'

            # Search for PDF file - case insensitive search
            pdf_files = []
            for pdf_file in pdf_folder_path.rglob('*.pdf'):
                if pdf_file.name.lower() == file_name.lower():
                    pdf_files.append(pdf_file)

            if not pdf_files:
                logger.warning(f"PDF file not found: {file_name}")
                skipped_files += 1
                continue

            if len(pdf_files) > 1:
                logger.warning(f"Multiple matches found for {file_name}, using first match")

            pdf_path = pdf_files[0]
            
            # Create corresponding JSON path
            rel_path = pdf_path.relative_to(pdf_folder_path)
            json_path = json_folder_path / rel_path.with_suffix('.json')
            
            # Skip if JSON file already exists
            if json_path.exists():
                logger.info(f"JSON file already exists: {json_path}, skipping creation")
                existing_files += 1
                continue
            
            # Extract text from PDF
            try:
                pdf_text = data_processor.extract_pdf_text(pdf_path)
                if not pdf_text or pdf_text.strip() == '':
                    logger.warning(f"PDF file is empty or text extraction failed: {pdf_path}")
                    skipped_files += 1
                    continue
            except Exception as e:
                logger.error(f"Error extracting text from PDF {pdf_path}: {str(e)}")
                skipped_files += 1
                continue

            # Create JSON content with fields structure and PDF content
            row_dict = row.to_dict()
            fields = []
            for key, value in row_dict.items():
                if key != 'FILE NAME' and key != 'APPROVED':  # Skip filename and approved flag
                    formatted_value = format_value(str(value) if pd.notnull(value) else '')
                    if formatted_value.strip():  # Only include non-empty fields
                        fields.append({
                            "key": key,
                            "value": formatted_value
                        })

            # Create full JSON structure with PDF content
            json_content = {
                "pdf_content": pdf_text,
                "fields": fields
            }

            # Create directory if needed
            json_path.parent.mkdir(parents=True, exist_ok=True)

            # Write JSON file
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(json_content, f, indent=2, ensure_ascii=False)

            logger.info(f"Created JSON file: {json_path}")
            successful_conversions += 1

            # Print progress
            if successful_conversions % 10 == 0:
                print(f"Processed {successful_conversions} files...")

        # Print summary
        print("\nConversion Summary:")
        print("-" * 20)
        print(f"Total approved records: {len(excel_data)}")
        print(f"Successfully converted: {successful_conversions}")
        print(f"Existing JSON files (skipped): {existing_files}")
        print(f"Skipped files (errors/not found): {skipped_files}")

        if successful_conversions > 0 or existing_files > 0:
            print("\n✓ Conversion completed successfully")
            print(f"✓ Training data files available in: {json_folder}")
            if successful_conversions > 0:
                print("  Note: New JSON files include PDF text content for proper training.")
        else:
            print("\n⚠ No files were converted")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Error in excel2training command: {str(e)}")
        sys.exit(1)
