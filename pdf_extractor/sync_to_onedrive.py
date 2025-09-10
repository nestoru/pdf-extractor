# pdf_extractor/sync_to_onedrive.py
import os
import json
import requests
import time
from pathlib import Path
import pandas as pd
import re
import urllib.parse
from functools import wraps

def retry_on_timeout(max_retries=3, backoff_factor=2, timeout_codes=[504, 502, 503]):
    """Decorator to retry function calls on timeout or server errors."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code in timeout_codes and attempt < max_retries:
                        wait_time = backoff_factor ** attempt
                        print(f"Attempt {attempt + 1} failed with {e.response.status_code}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise
                except requests.exceptions.Timeout as e:
                    if attempt < max_retries:
                        wait_time = backoff_factor ** attempt
                        print(f"Timeout on attempt {attempt + 1}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise
            return None
        return wrapper
    return decorator

def format_value(value):
    """Format value by removing dollar signs, commas and converting parentheses to negative numbers."""
    if not isinstance(value, str):
        return value

    # Remove dollar signs and commas
    value = value.replace('$', '').replace(',', '').strip()

    # Check if the number is in parentheses
    parentheses_pattern = r'\(([\d.]+)\)'
    match = re.match(parentheses_pattern, value)
    if match:
        # Convert (number) to -number
        return f"-{match.group(1)}"

    return value

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

def load_config(config_path: str):
    """Load configuration from config.json."""
    with open(config_path, 'r') as f:
        return json.load(f)

def get_access_token(config: dict):
    """Get access token using client credentials flow."""
    url = f"https://login.microsoftonline.com/{config['TENANT_ID']}/oauth2/v2.0/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "client_credentials",
        "client_id": config['CLIENT_ID'],
        "client_secret": config['CLIENT_SECRET'],
        "scope": "https://graph.microsoft.com/.default"
    }
    response = requests.post(url, headers=headers, data=data, timeout=30)
    response.raise_for_status()
    return response.json().get("access_token")

def get_drive_info(access_token: str, user_email: str):
    """Get the drive ID for a user's OneDrive."""
    url = f"https://graph.microsoft.com/v1.0/users/{user_email}/drive"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()

def get_site_drive_info(access_token: str, site_name: str, config: dict):
    """Get the drive ID for a SharePoint site."""
    # First get the site ID
    sharepoint_domain = config.get('SHAREPOINT_DOMAIN', 'sharepoint.com')
    url = f"https://graph.microsoft.com/v1.0/sites/{sharepoint_domain}:/sites/{site_name}"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    site_info = response.json()

    # Then get the drive for that site
    site_id = site_info['id']
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive"
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()

@retry_on_timeout(max_retries=3, backoff_factor=2)
def get_workbook_session(access_token: str, drive_id: str, file_id: str):
    """Create a workbook session with retry logic."""
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/createSession"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    data = {"persistChanges": True}
    response = requests.post(url, headers=headers, json=data, timeout=30)
    response.raise_for_status()
    return response.json().get("id")

@retry_on_timeout(max_retries=3, backoff_factor=2)
def get_worksheet_data(access_token: str, drive_id: str, file_id: str, session_id: str):
    """Get worksheet data using Excel API with retry logic."""
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets/Sheet1/usedRange"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "workbook-session-id": session_id
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()

def close_workbook_session(access_token: str, drive_id: str, file_id: str, session_id: str):
    """Close the workbook session."""
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/closeSession"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "workbook-session-id": session_id
    }
    response = requests.post(url, headers=headers, timeout=30)
    response.raise_for_status()

def column_number_to_letter(column_number):
    """Convert column number to Excel column letter(s)."""
    result = ""
    while column_number > 0:
        column_number -= 1
        result = chr(65 + column_number % 26) + result
        column_number //= 26
    return result

@retry_on_timeout(max_retries=3, backoff_factor=1)
def add_worksheet_row(access_token: str, drive_id: str, file_id: str, session_id: str, values, row_number: int):
    """Add a row to the worksheet at a specific row number."""
    # Calculate the range for the new row
    end_column = column_number_to_letter(len(values))
    new_row_range = f"A{row_number}:{end_column}{row_number}"

    # Use update range to add the row
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets/Sheet1/range(address='{new_row_range}')"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "workbook-session-id": session_id,
        "Content-Type": "application/json"
    }

    data = {
        "values": [values]
    }

    response = requests.patch(url, headers=headers, json=data, timeout=30)
    response.raise_for_status()
    return response.json()

def process_json_files(input_folder: str, shared_link: str, access_token: str, config: dict):
    """Process JSON files and update Excel with new 3-row schema structure."""

    # Determine drive type and get appropriate drive info
    drive_type, site_name = determine_drive_type(shared_link)

    if drive_type == 'personal':
        user_email = config.get('USER_EMAIL', 'user@example.com')
        drive_info = get_drive_info(access_token, user_email)
        print(f"Using personal OneDrive for {user_email}")
    elif drive_type == 'site':
        drive_info = get_site_drive_info(access_token, site_name, config)
        print(f"Using SharePoint site: {site_name}")
    else:
        raise ValueError(f"Unsupported drive type: {drive_type}")

    drive_id = drive_info['id']
    print(f"Got drive ID: {drive_id}")

    # Extract file ID from URL
    file_id = extract_file_id_from_url(shared_link)
    print(f"Extracted file ID: {file_id}")

    json_files = list(Path(input_folder).rglob("*.json"))
    print(f"\nFound {len(json_files)} JSON files to process")

    successful_syncs = 0
    session_id = None

    try:
        session_id = get_workbook_session(access_token, drive_id, file_id)
        print("Successfully created workbook session")

        # Get Excel data
        worksheet_data = get_worksheet_data(access_token, drive_id, file_id, session_id)
        
        # NEW: Handle the 3-row schema structure
        # Row 0: Alternative Column Names
        # Row 1: Column Extraction Rules
        # Row 2: Headers (actual column names)
        # Row 3+: Data
        
        if len(worksheet_data['values']) < 3:
            raise ValueError("Excel file does not have the expected 3-row schema structure")
        
        # Headers are now in row 3 (index 2)
        headers = worksheet_data['values'][2]
        
        # Use headers exactly as they are - no cleaning
        existing_file_names = []

        # Data starts from row 4 (index 3)
        if len(worksheet_data['values']) > 3:
            file_name_index = headers.index('FILE NAME')
            for row in worksheet_data['values'][3:]:  # Skip the 3 schema rows
                if len(row) > file_name_index and row[file_name_index]:
                    file_name = row[file_name_index]
                    # Store both with and without .pdf extension for robust checking
                    existing_file_names.append(file_name)
                    if file_name.endswith('.pdf'):
                        existing_file_names.append(file_name[:-4])
                    else:
                        existing_file_names.append(f"{file_name}.pdf")

        print(f"Found {len(existing_file_names) // 2} existing entries in Excel (starting from row 4)")
        
        # Calculate the next row number for new data (accounting for 3 schema rows)
        next_row_number = max(4, len(worksheet_data['values']) + 1)  # Start at row 4 minimum

        for json_file in json_files:
            print(f"\nProcessing {json_file}")

            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)

                # Check if file is already in Excel by name
                file_already_in_excel = json_file.stem in existing_file_names or f"{json_file.stem}.pdf" in existing_file_names

                if file_already_in_excel:
                    print(f"Skipping {json_file} - already exists in Excel")
                    continue

                # Create row for Excel using headers exactly as they are
                row_values = [None] * len(headers)
                row_values[headers.index('FILE NAME')] = json_file.stem

                for field in data.get('fields', []):
                    key, value = field['key'], field['value']
                    
                    # Try to find the key directly in headers (exact match)
                    if key in headers:
                        formatted_value = format_value(value)
                        row_values[headers.index(key)] = formatted_value
                        print(f"Formatted value for {key}: {value} -> {formatted_value}")
                    else:
                        print(f"Warning: Field '{key}' not found in headers")

                # Replace None values with empty strings
                row_values = ['' if v is None else v for v in row_values]
                print("New row to be added at row", next_row_number, ":", dict(zip(headers, row_values)))

                add_worksheet_row(access_token, drive_id, file_id, session_id, row_values, next_row_number)
                print(f"Added row for {json_file.stem} at row {next_row_number}")
                next_row_number += 1
                successful_syncs += 1

            except Exception as e:
                print(f"Error processing {json_file}: {str(e)}")
                continue

    finally:
        if session_id:
            try:
                print("\nClosing workbook session...")
                close_workbook_session(access_token, drive_id, file_id, session_id)
                print("Successfully closed workbook session")
            except Exception as e:
                print(f"Error closing session: {str(e)}")

    return successful_syncs

def main():
    """Main function to sync JSON data to Excel."""
    import sys
    if len(sys.argv) != 4:
        print("Usage: sync-extracted-fields <config.json> <input_folder> <sharepoint_excel_shared_link>")
        sys.exit(1)

    config_path = sys.argv[1]
    input_folder = sys.argv[2]
    shared_link = sys.argv[3]

    try:
        config = load_config(config_path)
        access_token = get_access_token(config)
        # Pass config to process_json_files
        successful_syncs = process_json_files(input_folder, shared_link, access_token, config)

        if successful_syncs > 0:
            print(f"Sync completed successfully - {successful_syncs} files processed")
        else:
            print("Sync completed with no files successfully processed")
            sys.exit(1)
    except Exception as e:
        print(f"Error during sync: {str(e)}")
        import traceback
        print(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()
