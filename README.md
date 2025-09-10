# PDF Data Extraction System with GPT Fine-tuning

A professional PDF data extraction tool using GPT models with support for fine-tuning and validation. The system extracts structured data from PDFs using a SharePoint-based schema, supports human review, and continuously improves through automated model training.

![System Overview](production_pdf_data_extraction_system.png)

## Quick POC
Here is a quick POC that allows us to share this with business delivering a practical usable project.
```
+-------------------+       +-------------------+       +-------------------+
|   SharePoint      |       |   Network Location|       |   Scheduler       |
|-------------------|       |-------------------|       |-------------------|
| - Excel Schema    |<----->| - input_pdfs      |<----->| - OCR Job         |
| - Extracted Data  |       | - ocred_pdfs      |<----->| - Extraction      |
| - Approved Rows   |       | - output_pdfs     |<----->| - Sync Job        |
+-------------------+       | - input_jsons     |       +-------------------+
                            +-------------------+
                                    ^
                                    |
                                    v
                            +-------------------+
                            |   PDF Extractor   |
                            |-------------------|
                            | - OCR Tool        |
                            | - Extraction Tool |
                            | - Schema Builder  |
                            +-------------------+
                                    ^
                                    |
                                    v
                            +-------------------+
                            |   Training System |
                            |-------------------|
                            | - Model Training  |
                            +-------------------+
```

## Key Features

### Dynamic Schema from SharePoint
The system now reads extraction schemas directly from SharePoint Excel files. The Excel file structure includes:
- **Row 1**: Alternative Column Names (optional alternative names for each field)
- **Row 2**: Column Extraction Rules (optional tips/rules for extracting each field)
- **Row 3**: Column Headers (actual field names to extract)
- **Row 4+**: Extracted data

This eliminates the need for separate JSON template files - the SharePoint Excel file serves as both the schema definition and data storage.

### Special Field Handling
The system automatically handles certain special fields without requiring GPT analysis:
- **Filename Fields**: Any field with "filename", "file_name", "file name", "document_name", or "document name" in its name is automatically populated with the PDF filename (without path or extension)
- These special fields are excluded from GPT analysis, alternative names, and extraction rules to optimize performance and ensure accuracy

### Core Features
- PDF text and position extraction
- Field identification using GPT models with enhanced prompting
- Annotated PDF output with highlighted fields
- Field validation and correction
- Automated model fine-tuning pipeline
- Model quality validation
- Support for both OpenAI and custom fine-tuned models

Here's an example of annotated output:

![Annotated PDF](annotated_pdf.png)

## Prerequisites

- Python 3.8.1 or higher
- Poetry for dependency management
- OpenAI API key
- Microsoft Azure App registration (for SharePoint/OneDrive access)

## Installation

1. Install Poetry if you haven't already:
```bash
curl -sSL https://install.python-poetry.org | python3 -
```

2. Clone the repository:
```bash
git clone https://github.com/yourusername/pdf-extractor.git
cd pdf-extractor
```

3. Install dependencies:
```bash
poetry install
```

4. Activate the virtual environment:
```bash
poetry shell
```

## Configuration

Create a `.config.json` file with your settings:

```json
{
    "ml_engine": {
        "api_key": "your-openai-api-key"
    },
    "TENANT_ID": "your-azure-tenant-id",
    "CLIENT_ID": "your-azure-client-id",
    "CLIENT_SECRET": "your-azure-client-secret",
    "SHAREPOINT_DOMAIN": "your-domain.sharepoint.com",
    "USER_EMAIL": "your-email@your-domain.com"
}
```

## Basic Usage

### PDF Data Extraction

Run extraction using SharePoint Excel as schema source:
```bash
pdf-extractor <config.json> <model_name> <sharepoint_excel_url> <input_folder> <output_folder>
```

Example:
```bash
pdf-extractor config.json gpt-4o-mini "https://your-domain.sharepoint.com/:x:/r/sites/..." input_pdfs/ output_pdfs/
```

This will:
- Connect to SharePoint and read the schema from the Excel file (first 3 rows)
- For each PDF in input_folder:
  - Extract text
  - Automatically populate filename fields with the PDF filename
  - Use the specified GPT model to identify remaining fields
  - Apply alternative names and extraction rules from SharePoint for better accuracy
  - Create an annotated PDF with highlighted fields
  - Save extracted data to JSON
- Maintain input folder hierarchy in output_folder

### Syncing Extracted Data to Excel

After extraction, sync the extracted fields back to the SharePoint Excel:
```bash
sync-extracted-fields <config.json> <output_folder> <sharepoint_excel_url>
```

This will:
- Process all JSON files in the output folder
- Add new rows to the Excel file (starting from row 4)
- Skip files already in Excel to avoid duplication
- Handle the 3-row schema structure correctly

## Fine-tuning Pipeline

### Commands

1. **List available models**:
```bash
pdf-extractor-finetune list-models config.json
```

2. **List fine-tuning jobs**:
```bash
pdf-extractor-finetune list-jobs config.json [limit]
```

3. **Check job status**:
```bash
pdf-extractor-finetune status config.json job-123
```

4. **Prepare training data from SharePoint Excel**:
```bash
pdf-extractor-finetune excel2training <config.json> <json_folder> <pdf_folder> <sharepoint_excel_url>
```
This reads approved records (APPROVED = 'Y') from the Excel file and creates training JSON files.

5. **Start model training**:
```bash
pdf-extractor-finetune train <config.json> <base_model> <json_folder> <custom_model_name> [--dry-run]
```

6. **Validate model performance**:
```bash
pdf-extractor-finetune validate <config.json> <model_name> <json_folder> <pdf_folder> <sharepoint_excel_url> [error_limit]
```

### Training Data Structure

The excel2training command creates JSON files with this structure:
```json
{
    "pdf_content": "extracted text from PDF...",
    "fields": [
        {"key": "INVOICE NUMBER", "value": "INV-2024-001"},
        {"key": "DATE", "value": "2024-01-14"},
        {"key": "TOTAL AMOUNT ($)", "value": "1234.56"}
    ]
}
```

Note: Field keys preserve the exact column names from Excel, including any type annotations.

## SharePoint Excel Structure

Your SharePoint Excel file must have this structure:

| Row | Content | Description |
|-----|---------|-------------|
| 1 | Alternative Column Names | Optional alternative names for fields |
| 2 | Column Extraction Rules | Optional extraction tips/rules |
| 3 | Column Headers | Actual field names (can include type annotations) |
| 4+ | Data | Extracted or manually entered data |

Example:
- Row 1, Column B: "Account Name, Series Name"
- Row 2, Column B: "Look for partner or investor name"
- Row 3, Column B: "CLIENT INVESTOR NAME (TEXT)"
- Row 4+, Column B: Actual extracted values

For filename fields, you can simply use column names like "FILENAME", "FILE_NAME", or "DOCUMENT_NAME" without needing alternative names or extraction rules.

## Automated Workflow

The system supports an automated workflow:
1. PDFs are processed using SharePoint schema
2. Extracted data is synced to SharePoint Excel
3. Users review and mark records as APPROVED = 'Y'
4. Approved data is converted to training format
5. Models are fine-tuned on approved data
6. New models are validated and deployed

## Project Structure
```
.
├── pdf_extractor/
│   ├── cli.py                          # Main CLI
│   ├── cli_finetune.py                 # Fine-tuning CLI
│   ├── sync_to_onedrive.py            # SharePoint sync functionality
│   ├── config/                         # Configuration handling
│   ├── core/                           # Core extraction logic
│   │   ├── extractor.py               # Main extractor
│   │   └── models.py                   # Data models
│   ├── services/                       # External services
│   │   ├── gpt_service.py             # GPT integration
│   │   ├── pdf_service.py             # PDF processing
│   │   └── sharepoint_schema_builder.py # SharePoint schema reader
│   ├── fine_tuning/                    # Training pipeline
│   │   └── data_processor.py          # Training data preparation
│   ├── finetune_commands/              # Fine-tuning commands
│   │   ├── excel2training.py          # Excel to training conversion
│   │   ├── train.py                   # Model training
│   │   └── validate.py                # Model validation
│   └── utils/                          # Utilities
```

## Key Improvements in This Version

1. **No JSON Templates**: Schema is read directly from SharePoint Excel
2. **Enhanced Prompting**: Uses alternative names and extraction rules for better accuracy
3. **Dynamic Fields**: Add/remove fields in SharePoint without code changes
4. **Unified Data Source**: SharePoint Excel serves as both schema and data storage
5. **Better Error Handling**: Improved tracking of successes and failures
6. **3-Row Schema Structure**: Supports metadata for each field
7. **Special Field Handling**: Automatic filename extraction without GPT analysis

## Migration from Previous Version

If you're migrating from the JSON template version:
1. Ensure your SharePoint Excel has the 3-row schema structure
2. Remove any JSON template files (no longer needed)
3. Update your extraction commands to use SharePoint URLs instead of template paths
4. The `create-inference-template` command has been deprecated

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT
