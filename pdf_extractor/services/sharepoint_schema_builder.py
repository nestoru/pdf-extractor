# pdf_extractor/services/sharepoint_schema_builder.py
import json
import requests
import time
from typing import Dict, List, Tuple, Optional
from functools import wraps
import urllib.parse
from pdf_extractor.utils.logging import get_logger
from pdf_extractor.core.models import ExtractionTemplate, FieldTemplate

logger = get_logger(__name__)

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
                        logger.info(f"Attempt {attempt + 1} failed with {e.response.status_code}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise
                except requests.exceptions.Timeout as e:
                    if attempt < max_retries:
                        wait_time = backoff_factor ** attempt
                        logger.info(f"Timeout on attempt {attempt + 1}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise
            return None
        return wrapper
    return decorator

class SharePointSchemaBuilder:
    """Service for building extraction schema from SharePoint Excel data file."""
    
    def __init__(self, config_path: str):
        """Initialize with configuration for SharePoint access."""
        self.config = self._load_config(config_path)
        self.access_token = self._get_access_token()
    
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from config.json - reusing existing pattern from sync_to_onedrive.py."""
        with open(config_path, 'r') as f:
            return json.load(f)
    
    def _get_access_token(self) -> str:
        """Get access token using client credentials flow - exact same as sync_to_onedrive.py."""
        url = f"https://login.microsoftonline.com/{self.config['TENANT_ID']}/oauth2/v2.0/token"
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "grant_type": "client_credentials",
            "client_id": self.config['CLIENT_ID'],
            "client_secret": self.config['CLIENT_SECRET'],
            "scope": "https://graph.microsoft.com/.default"
        }
        response = requests.post(url, headers=headers, data=data, timeout=30)
        response.raise_for_status()
        return response.json().get("access_token")
    
    def _extract_file_id_from_url(self, shared_link: str) -> str:
        """Extract file ID from SharePoint URL - exact same logic as sync_to_onedrive.py."""
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
    
    def _determine_drive_type(self, shared_link: str) -> Tuple[str, Optional[str]]:
        """Determine if the link is for personal OneDrive or SharePoint site - from sync_to_onedrive.py."""
        if '/sites/' in shared_link:
            # Extract site name from SharePoint site URL
            parts = shared_link.split('/sites/')
            if len(parts) > 1:
                site_name = parts[1].split('/')[0]
                return 'site', site_name
        elif '-my.sharepoint.com' in shared_link:
            return 'personal', None
        raise ValueError(f"Unable to determine drive type from URL: {shared_link}")
    
    def _get_drive_info(self, user_email: str) -> Dict:
        """Get the drive ID for a user's OneDrive - from sync_to_onedrive.py."""
        url = f"https://graph.microsoft.com/v1.0/users/{user_email}/drive"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    
    def _get_site_drive_info(self, site_name: str) -> Dict:
        """Get the drive ID for a SharePoint site - from sync_to_onedrive.py."""
        # First get the site ID
        sharepoint_domain = self.config.get('SHAREPOINT_DOMAIN', 'sharepoint.com')
        url = f"https://graph.microsoft.com/v1.0/sites/{sharepoint_domain}:/sites/{site_name}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
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
    def _get_worksheet_data(self, drive_id: str, file_id: str) -> Dict:
        """Get worksheet data directly without session."""
        url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{file_id}/workbook/worksheets/Sheet1/usedRange"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    
    def build_extraction_schema(self, sharepoint_url: str) -> Tuple[ExtractionTemplate, Dict[str, str], Dict[str, str]]:
        """
        Build extraction schema from SharePoint Excel data file.
        
        The Excel file contains both the schema (first 3 rows) and the actual extracted data.
        This method reads the schema information from the first 3 rows to understand:
        - What fields to extract
        - Alternative names for those fields
        - Extraction rules/tips for each field
        
        Returns:
            - ExtractionTemplate: The schema with fields to extract
            - Dict[str, str]: Alternative names for each field
            - Dict[str, str]: Extraction rules for each field
        """
        logger.info(f"Building extraction schema from SharePoint data file: {sharepoint_url}")
        
        # Determine drive type and get appropriate drive info (using exact logic from sync_to_onedrive.py)
        drive_type, site_name = self._determine_drive_type(sharepoint_url)
        
        if drive_type == 'personal':
            user_email = self.config.get('USER_EMAIL', 'user@example.com')
            drive_info = self._get_drive_info(user_email)
            logger.info(f"Using personal OneDrive for {user_email}")
        elif drive_type == 'site':
            drive_info = self._get_site_drive_info(site_name)
            logger.info(f"Using SharePoint site: {site_name}")
        else:
            raise ValueError(f"Unsupported drive type: {drive_type}")
        
        drive_id = drive_info['id']
        logger.info(f"Got drive ID: {drive_id}")
        
        # Extract file ID from URL
        file_id = self._extract_file_id_from_url(sharepoint_url)
        logger.info(f"Extracted file ID: {file_id}")
        
        # Get worksheet data
        worksheet_data = self._get_worksheet_data(drive_id, file_id)
        
        if not worksheet_data or 'values' not in worksheet_data or len(worksheet_data['values']) < 3:
            raise ValueError("Excel file does not have the expected structure (need at least 3 rows for schema)")
        
        values = worksheet_data['values']
        
        # Parse the schema from the first three rows
        alternative_names_row = values[0]
        extraction_rules_row = values[1]
        headers_row = values[2]
        
        # Find where "Alternative Column Names" and "Column Extraction Rules" labels are
        alt_names_col = None
        rules_col = None
        
        for i, cell in enumerate(alternative_names_row):
            if cell == "Alternative Column Names":
                alt_names_col = i
                break
        
        for i, cell in enumerate(extraction_rules_row):
            if cell == "Column Extraction Rules":
                rules_col = i
                break
        
        logger.info(f"Found {len(headers_row)} columns in schema")
        
        # Build the extraction schema and metadata
        fields = []
        alternative_names = {}
        extraction_rules = {}
        
        for i, header in enumerate(headers_row):
            if header and header.strip():  # Skip empty headers
                # Use the header exactly as it appears in Excel
                header_key = header.strip()
                
                fields.append(FieldTemplate(key=header_key, value=""))
                
                # Get alternative name if exists (skip the label column itself)
                if i < len(alternative_names_row) and alternative_names_row[i] and i != alt_names_col:
                    alternative_names[header_key] = alternative_names_row[i]
                
                # Get extraction rule if exists (skip the label column itself)
                if i < len(extraction_rules_row) and extraction_rules_row[i] and i != rules_col:
                    extraction_rules[header_key] = extraction_rules_row[i]
        
        logger.info(f"Built schema with {len(fields)} fields from SharePoint data file")
        logger.info(f"Found {len(alternative_names)} alternative names")
        logger.info(f"Found {len(extraction_rules)} extraction rules")
        
        # Create the extraction template/schema
        template = ExtractionTemplate(
            document_type="Financial Statement",  # Could be made configurable if needed
            fields=fields
        )
        
        return template, alternative_names, extraction_rules
