# pdf_extractor/services/gpt_implementations.py
from abc import ABC, abstractmethod
from typing import List, Dict
import openai
from pdf_extractor.utils.logging import get_logger

logger = get_logger(__name__)

class BaseGPT(ABC):
    """Base class for GPT implementations."""
    def __init__(self, api_key: str, model_name: str):
        self.api_key = api_key
        self.model_name = model_name

    @abstractmethod
    def generate_completion(self, messages: List[Dict]) -> str:
        """Generate completion from messages."""
        pass

class OpenAIGPT(BaseGPT):
    """OpenAI GPT implementation."""
    def __init__(self, api_key: str, model_name: str):
        super().__init__(api_key, model_name)
        openai.api_key = api_key

    def generate_completion(self, messages: List[Dict]) -> str:
        """Generate completion using OpenAI API."""
        response = openai.ChatCompletion.create(
            model=self.model_name,
            messages=messages,
            response_format={"type": "json_object"}
        )
        return response.choices[0]["message"]["content"]

def get_gpt_implementation(api_key: str, model_name: str) -> BaseGPT:
    """Factory function to get appropriate GPT implementation."""
    return OpenAIGPT(api_key, model_name)
