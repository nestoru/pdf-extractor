# pdf_extractor/finetune_commands/excel2training.py

import sys
from pathlib import Path
import pandas as pd
import json
import urllib.parse
import requests
from pdf_extractor.utils.logging import get_logger
from pdf_extractor.sync_to_onedrive import (
    format_value, load_config, get_access_token,
    get_drive_info, get_workbook_session,
    get_worksheet_data, close_workbook_session
)
from pdf_extractor.fine_tuning.data_processor import FineTuningDataProcessor

logger = get_logger(__name__)

def extract_file_id_from_url(shared_link):
    """Extract file ID from SharePoint URL, handling different URL formats"""
    if 'd=w' in shared_link:
        # Handle URLs with d=w parameter (both personal and site)
        return shared_link.split('d=w')[1].split('&')[0]
    elif 'sourcedoc=' in shared_link:
        # Handle site URLs with sourcedoc parameter
        parsed_url = urllib.parse.urlparse(shared_link)
        params = urllib.parse.parse_qs(parsed_url.query)
        if 'sourcedoc' in params:
            # Get the sourcedoc parameter and URL decode it
            sourcedoc = urllib.parse.unquote(params['sourcedoc'][0])
            # Remove curly braces if present
            if sourcedoc.startswith('{') and sourcedoc.endswith('}'):
                sourcedoc = sourcedoc[1:-1]
            return sourcedoc

    raise ValueError(f"Unable to extract file ID from URL: {shared_link}")

def determine_drive_type(shared_link):
    """Determine if the link is for personal OneDrive or SharePoint site."""
    if '/sites/' in shared_link:
        # Extract site name from SharePoint site URL
        # Format: https://company.sharepoint.com/:x:/r/sites/SiteName/...
        parts = shared_link.split('/sites/')
        if len(parts) > 1:
            site_name = parts[1].split('/')[0]  # Get the site name
            return 'site', site_name
    elif '-my.sharepoint.com' in shared_link:
        return 'personal', None

    raise ValueError(f"Unable to determine drive type from URL: {shared_link}")

def get_site_drive_info(access_token: str, site_name: str, config: dict):
    """Get the drive ID for a SharePoint site."""
    # First get the site ID
    sharepoint_domain = config.get('SHAREPOINT_DOMAIN', 'sharepoint.com')
    url = f"https://graph.microsoft.com/v1.0/sites/{sharepoint_domain}:/sites/{site_name}"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    site_info = response.json()

    # Then get the drive for that site
    site_id = site_info['id']
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def process_sharepoint_excel(config_path: str, sharepoint_link: str) -> pd.DataFrame:
    """
    Download and process Excel file from SharePoint shared link using authentication.
    Now handles the 3-row schema structure.
    """
    try:
        # Load SharePoint config
        config = load_config(config_path)
        access_token = get_access_token(config)

        # Determine drive type and get appropriate drive info
        drive_type, site_name = determine_drive_type(sharepoint_link)

        if drive_type == 'personal':
            user_email = config.get('USER_EMAIL', 'user@example.com')
            drive_info = get_drive_info(access_token, user_email)
            logger.info(f"Using personal OneDrive for {user_email}")
        elif drive_type == 'site':
            drive_info = get_site_drive_info(access_token, site_name, config)
            logger.info(f"Using SharePoint site: {site_name}")
        else:
            raise ValueError(f"Unsupported drive type: {drive_type}")

        drive_id = drive_info['id']
        logger.info("Successfully obtained drive info")

        # Extract file ID from shared link using improved parsing
        file_id = extract_file_id_from_url(sharepoint_link)
        logger.info(f"Extracted file ID: {file_id}")

        # Create workbook session
        session_id = get_workbook_session(access_token, drive_id, file_id)
        logger.info("Successfully created workbook session")

        try:
            # Get worksheet data
            worksheet_data = get_worksheet_data(access_token, drive_id, file_id, session_id)

            # NEW: Handle 3-row schema structure
            # Check if we have at least 3 rows for schema + 1 row for data
            if len(worksheet_data['values']) < 4:
                raise ValueError("Excel file does not have the expected structure (need at least 3 schema rows + 1 data row)")

            # Row 3 (index 2) contains the actual headers
            headers = worksheet_data['values'][2]
            
            # Data starts from row 4 (index 3)
            data = worksheet_data['values'][3:]
            
            # Convert to DataFrame
            df = pd.DataFrame(data, columns=headers)
            
            logger.info(f"Loaded Excel with {len(df)} data rows (starting from row 4)")

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
            # Handle NaN values in APPROVED column
            df['APPROVED'] = df['APPROVED'].fillna('')
            df = df[df['APPROVED'].astype(str).str.upper() == 'Y']
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
    Updated to handle 3-row schema structure.
    """
    try:
        # Create folder paths
        json_folder_path = Path(json_folder)
        pdf_folder_path = Path(pdf_folder)

        logger.info("Starting Excel to training data conversion...")
        print("\nProcessing SharePoint Excel file with 3-row schema structure...")

        # Initialize the data processor for extracting text from PDFs
        data_processor = FineTuningDataProcessor()

        # Process Excel file (now handles 3-row schema)
        excel_data = process_sharepoint_excel(config_path, sharepoint_link)
        print(f"Found {len(excel_data)} approved records (from row 4 onwards)")

        successful_conversions = 0
        skipped_files = 0
        existing_files = 0
        
        # Track skipped files with reasons
        skipped_files_list = []

        # Process each approved row
        for idx, row in excel_data.iterrows():
            if 'FILE NAME' not in row or pd.isna(row['FILE NAME']) or row['FILE NAME'] == '':
                reason = "Row missing FILE NAME column or empty filename"
                logger.warning(reason)
                skipped_files_list.append({
                    'file': 'N/A (missing filename)',
                    'reason': reason
                })
                skipped_files += 1
                continue

            # Get the file name and ensure it has the .pdf extension
            file_name = str(row['FILE NAME']).strip()
            if not file_name.lower().endswith('.pdf'):
                file_name += '.pdf'

            # Search for PDF file - case insensitive search for both filename and extension
            pdf_files = []
            for pdf_file in pdf_folder_path.rglob('*'):
                # Check if it's a PDF file (case insensitive extension check)
                if pdf_file.suffix.lower() == '.pdf' and pdf_file.name.lower() == file_name.lower():
                    pdf_files.append(pdf_file)

            if not pdf_files:
                reason = f"PDF file not found in folder: {pdf_folder}"
                logger.warning(f"PDF file not found: {file_name}")
                skipped_files_list.append({
                    'file': file_name,
                    'reason': reason
                })
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
                    reason = "PDF file is empty or text extraction failed"
                    logger.warning(f"PDF file is empty or text extraction failed: {pdf_path}")
                    skipped_files_list.append({
                        'file': file_name,
                        'reason': reason
                    })
                    skipped_files += 1
                    continue
            except Exception as e:
                reason = f"Error extracting text from PDF: {str(e)}"
                logger.error(f"Error extracting text from PDF {pdf_path}: {str(e)}")
                skipped_files_list.append({
                    'file': file_name,
                    'reason': reason
                })
                skipped_files += 1
                continue

            # Create JSON content with fields structure and PDF content
            # IMPORTANT: Use exact column names as they appear in Excel (with type annotations if present)
            row_dict = row.to_dict()
            fields = []
            for key, value in row_dict.items():
                if key != 'FILE NAME' and key != 'APPROVED':  # Skip filename and approved flag
                    formatted_value = format_value(str(value) if pd.notnull(value) else '')
                    if formatted_value.strip():  # Only include non-empty fields
                        fields.append({
                            "key": key,  # Use the exact column name from Excel
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

        # Display skipped files details
        if skipped_files_list:
            print("\nSkipped Files Details:")
            print("-" * 30)
            for i, skip_info in enumerate(skipped_files_list, 1):
                print(f"{i}. File: {skip_info['file']}")
                print(f"   Reason: {skip_info['reason']}")
                print()

        if successful_conversions > 0 or existing_files > 0:
            print("✓ Conversion completed successfully")
            print(f"✓ Training data files available in: {json_folder}")
            if successful_conversions > 0:
                print("  Note: New JSON files include PDF text content for proper training.")
                print("  Note: Field keys preserve Excel column names exactly (including type annotations)")
        else:
            print("\n⚠ No files were converted")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Error in excel2training command: {str(e)}")
        sys.exit(1)
