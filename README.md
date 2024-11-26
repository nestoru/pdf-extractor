# PDF Data Extraction System with GPT Fine-tuning

A professional PDF data extraction tool using GPT models with support for fine-tuning and validation. The system extracts structured data from PDFs, supports human review, and continuously improves through automated model training.

![System Overview](production_pdf_data_extraction_system.png)

## Project structure
```
.
├── README.md
├── annotated_pdf.png
├── pdf_extractor
│   ├── __init__.py
│   ├── cli.py
│   ├── cli_finetune.py
│   ├── config
│   │   ├── __init__.py
│   │   └── extraction_config.py
│   ├── core
│   │   ├── __init__.py
│   │   ├── extractor.py
│   │   └── models.py
│   ├── fine_tuning
│   │   ├── data_processor.py
│   │   └── trainer.py
│   ├── services
│   │   ├── __init__.py
│   │   ├── gpt_implementations.py
│   │   ├── gpt_service.py
│   │   └── pdf_service.py
│   ├── utils
│   │   ├── __init__.py
│   │   └── logging.py
│   └── validation
│       └── model_validator.py
├── poetry.lock
├── production_pdf_data_extraction_system.png
├── pyproject.toml
└── workflow.mmd
```

## Features

- PDF text and position extraction
- Field identification using GPT models
- Annotated PDF output with highlighted fields
- Field validation and correction UI
- Automated model fine-tuning pipeline
- Model quality validation
- Support for both OpenAI and custom endpoint models

Here's an example of annotated output:

![Annotated PDF](annotated_pdf.png)

## Prerequisites

- Python 3.8.1 or higher
- Poetry for dependency management
- Node.js (for diagram generation)
- OpenAI API key

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
        "model": "gpt-4-1106-preview",
        "api_key": "your-api-key-here",
        "available_models": [
            {
                "name": "gpt-4-1106-preview"
            },
            {
                "name": "gpt-4"
            },
            {
                "name": "gpt-3.5-turbo"
            }
        ]
    }
}
```

## Basic Usage

### PDF Data Extraction

1. Prepare your field template (e.g., `invoice_fields_template.json`):
```json
{
    "document_type": "invoice",
    "fields": [
        {"key": "invoice_number", "value": ""},
        {"key": "date", "value": ""},
        {"key": "total_amount", "value": ""}
    ]
}
```

2. Run extraction:
```bash
pdf-extractor config.json input.pdf fields_template.json output.pdf extracted.json
```

This will:
- Extract text from the input PDF
- Use GPT to identify fields
- Create an annotated PDF with highlighted fields
- Save extracted data to JSON

## Fine-tuning Pipeline

The system includes a complete fine-tuning pipeline for improving model performance.

### Commands

1. List available models:
```bash
pdf-extractor-finetune list-models config.json
```

2. List fine-tuning jobs:
```bash
pdf-extractor-finetune list-jobs config.json
# Optional: Limit number of jobs shown
pdf-extractor-finetune list-jobs config.json 10
```

3. Check job status:
```bash
pdf-extractor-finetune status config.json job-123
```

4. Start model training:
```bash
pdf-extractor-finetune train config.json gpt-3.5-turbo ./training_dir my-custom-1.0.0
```

5. Validate model performance:
```bash
pdf-extractor-finetune validate config.json ./training_dir
# Optional: Set error example limit
pdf-extractor-finetune validate config.json ./training_dir 10
```

### Training Data Structure

Your training directory should contain:
```
training_dir/
├── doc1.pdf
├── doc1.json              # Extraction results
├── doc1.template.json     # Field template
├── doc2.pdf
├── doc2.json
└── doc2.template.json
```

## Automated Workflow

The system supports an automated workflow where:
1. PDFs are processed using current best model
2. Users review and correct extractions
3. Corrected data is saved for training
4. When >100 new corrections accumulate, fine-tuning triggers
5. New model is validated against previous model
6. Better models are automatically deployed

## Development

### Project Structure
```
.
├── pdf_extractor/
│   ├── cli.py              # Main CLI
│   ├── cli_finetune.py     # Fine-tuning CLI
│   ├── config/             # Configuration handling
│   ├── core/               # Core extraction logic
│   ├── fine_tuning/        # Fine-tuning pipeline
│   ├── services/           # GPT and PDF services
│   ├── utils/              # Utilities
│   └── validation/         # Model validation
```

### Generate Documentation Diagrams

1. Install Mermaid CLI:
```bash
npm install @mermaid-js/mermaid-cli
```

2. Generate workflow diagram:
```bash
npx @mermaid-js/mermaid-cli -i workflow.mmd -o workflow.svg
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT

