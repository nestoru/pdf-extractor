import os
import json
import requests
from pathlib import Path
import pandas as pd
import re

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
    response = requests.post(url, headers=headers, data=data)
    response.raise_for_status()
    return response.json().get("access_token")

def get_drive_info(access_token: str, user_email: str):
    """Get the drive ID for a user's OneDrive."""
    url = f"https://graph.microsoft.com/v1.0/users/{user_email}/drive"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def get_workbook_session(access_token: str, drive_id: str, file_id: str):
    """Create a workbook session."""
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/createSession"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    data = {"persistChanges": True}
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    return response.json().get("id")

def get_worksheet_data(access_token: str, drive_id: str, file_id: str, session_id: str):
    """Get worksheet data using Excel API."""
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets/Sheet1/usedRange"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "workbook-session-id": session_id
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def close_workbook_session(access_token: str, drive_id: str, file_id: str, session_id: str):
    """Close the workbook session."""
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/closeSession"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "workbook-session-id": session_id
    }
    response = requests.post(url, headers=headers)
    response.raise_for_status()

def add_worksheet_row(access_token: str, drive_id: str, file_id: str, session_id: str, values):
    """Add a row to the worksheet using the proper range format."""
    # First get the current used range to determine where to add the new row
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets/Sheet1/usedRange"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "workbook-session-id": session_id
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    # Get the current range address and row count
    range_data = response.json()
    last_row = len(range_data['values'])
    
    # Calculate the range for the new row
    new_row_range = f"A{last_row + 1}:{chr(65 + len(values) - 1)}{last_row + 1}"
    
    # Use update range instead of add rows
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets/Sheet1/range(address='{new_row_range}')"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "workbook-session-id": session_id,
        "Content-Type": "application/json"
    }
    
    data = {
        "values": [values]
    }
    
    response = requests.patch(url, headers=headers, json=data)
    response.raise_for_status()
    return response.json()

def process_json_files(input_folder: str, shared_link: str, access_token: str):
    """Process JSON files and update Excel."""
    drive_info = get_drive_info(access_token, "nurquiza@trustserve.net")
    drive_id = drive_info['id']
    print(f"Got drive ID: {drive_id}")

    file_id = shared_link.split('d=w')[1].split('&')[0]
    json_files = list(Path(input_folder).rglob("*.json"))
    print(f"\nFound {len(json_files)} JSON files to process")

    successful_syncs = 0
    session_id = None

    try:
        session_id = get_workbook_session(access_token, drive_id, file_id)
        print("Successfully created workbook session")

        worksheet_data = get_worksheet_data(access_token, drive_id, file_id, session_id)
        headers = worksheet_data['values'][0]

        for json_file in json_files:
            print(f"\nProcessing {json_file}")
            
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)

                if data.get("synced") == "true":
                    print(f"Skipping {json_file} - already synced")
                    continue

                row_values = [None] * len(headers)
                row_values[headers.index('FILE NAME')] = json_file.stem

                for field in data.get('fields', []):
                    key, value = field['key'], field['value']
                    if key in headers:
                        formatted_value = format_value(value)
                        row_values[headers.index(key)] = formatted_value
                        print(f"Formatted value for {key}: {value} -> {formatted_value}")

                # Replace None values with empty strings
                row_values = ['' if v is None else v for v in row_values]
                print("New row to be added:", dict(zip(headers, row_values)))

                add_worksheet_row(access_token, drive_id, file_id, session_id, row_values)
                print(f"Added row for {json_file.stem}")

                data["synced"] = "true"
                with open(json_file, 'w') as f:
                    json.dump(data, f, indent=2)
                print(f"Marked {json_file.stem} as synced")
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
        successful_syncs = process_json_files(input_folder, shared_link, access_token)
        
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
