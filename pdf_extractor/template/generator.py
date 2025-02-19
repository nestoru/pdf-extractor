# pdf_extractor/template/generator.py

import json
from pathlib import Path
import pandas as pd
from pdf_extractor.utils.logging import get_logger
from pdf_extractor.sync_to_onedrive import (
    load_config, get_access_token, get_drive_info,
    get_workbook_session, get_worksheet_data, close_workbook_session
)

logger = get_logger(__name__)

def get_valid_headers(headers):
    """
    Get valid headers from Excel fieldnames, excluding special columns.
    """
    return [
        header for header in headers
        if header and header.strip() 
        and not header.startswith('Unnamed:')
        and header not in ['FILE NAME', 'APPROVED', 'synced']
    ]

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

            # Get headers
            headers = worksheet_data['values'][0]
            logger.info(f"Found {len(headers)} columns in Excel")

            return headers

        finally:
            # Always close the session
            if session_id:
                close_workbook_session(access_token, drive_id, file_id, session_id)
                logger.info("Successfully closed workbook session")

    except Exception as e:
        logger.error(f"Error processing SharePoint Excel file: {str(e)}")
        raise

def create_template(
    config_path: str,
    sharepoint_link: str,
    document_type: str,
    output_path: str
) -> None:
    """
    Create an inference template from SharePoint Excel headers.
    """
    try:
        # Process Excel headers
        headers = process_sharepoint_excel(config_path, sharepoint_link)
        
        # Get valid field names
        valid_fields = get_valid_headers(headers)
        
        if not valid_fields:
            raise ValueError("No valid fields found in Excel file")
            
        logger.info(f"Found {len(valid_fields)} valid fields")
        
        # Create template structure
        template = {
            "document_type": document_type,
            "fields": [
                {"key": field, "value": ""}
                for field in valid_fields
            ]
        }
        
        # Create output directory if needed
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write template file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(template, f, indent=2)
            
        logger.info(f"Created template with {len(valid_fields)} fields")
        
    except Exception as e:
        logger.error(f"Error creating template: {str(e)}")
        raise
