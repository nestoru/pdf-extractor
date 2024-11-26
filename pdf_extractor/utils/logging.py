import logging
import sys

def get_logger(name: str) -> logging.Logger:
    """
    Create and configure a logger instance.
    
    Args:
        name: The name for the logger
        
    Returns:
        A configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Only add handler if it hasn't been added before
    if not logger.handlers:
        # Set logging level to DEBUG to see all messages
        logger.setLevel(logging.DEBUG)
        
        # Create formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # Create console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.DEBUG)
        logger.addHandler(console_handler)
        
        # Prevent propagation to root logger
        logger.propagate = False
    
    return logger
