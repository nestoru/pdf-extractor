# pdf_extractor/finetune_commands/__init__.py
"""Command modules for the pdf-extractor fine-tuning tool."""

# Import excel2training unconditionally since it doesn't require openai
from .excel2training import excel2training_command

# Conditional imports for modules that require optional dependencies
def get_train_command():
    """Lazy import for train_command to avoid openai dependency issues."""
    try:
        from .train import train_command
        return train_command
    except ImportError as e:
        raise ImportError(f"Train command requires additional dependencies: {e}")

def get_validate_command():
    """Lazy import for validate_command to avoid dependency issues."""
    try:
        from .validate import validate_command
        return validate_command
    except ImportError as e:
        raise ImportError(f"Validate command requires additional dependencies: {e}")

__all__ = ['excel2training_command', 'get_train_command', 'get_validate_command']
