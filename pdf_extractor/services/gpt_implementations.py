from abc import ABC, abstractmethod
from typing import List, Dict, Optional
import openai
import requests
from pdf_extractor.config.extraction_config import ModelConfig
from pdf_extractor.utils.logging import get_logger

logger = get_logger(__name__)

class BaseGPT(ABC):
    """Base class for GPT implementations."""
    
    def __init__(self, api_key: str, model_config: ModelConfig):
        self.api_key = api_key
        self.model_config = model_config
    
    @abstractmethod
    def generate_completion(self, messages: List[Dict]) -> str:
        """Generate completion from messages."""
        pass

class OpenAIGPT(BaseGPT):
    """OpenAI GPT implementation."""
    
    def __init__(self, api_key: str, model_config: ModelConfig):
        super().__init__(api_key, model_config)
        openai.api_key = api_key
    
    def generate_completion(self, messages: List[Dict]) -> str:
        """Generate completion using OpenAI API."""
        response = openai.chat.completions.create(
            model=self.model_config.name,
            messages=messages,
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content

class CustomOpenAIGPT(BaseGPT):
    """Custom OpenAI-compatible GPT implementation."""
    
    def generate_completion(self, messages: List[Dict]) -> str:
        """Generate completion using custom OpenAI-compatible API."""
        if not self.model_config.endpoint:
            raise ValueError(f"Endpoint not specified for model {self.model_config.name}")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model_config.name,
            "messages": messages,
            "response_format": {"type": "json_object"}
        }
        
        response = requests.post(
            self.model_config.endpoint,
            headers=headers,
            json=payload
        )
        
        if response.status_code != 200:
            raise ValueError(f"API error: {response.text}")
            
        return response.json()['choices'][0]['message']['content']

def get_gpt_implementation(api_key: str, model_config: ModelConfig) -> BaseGPT:
    """Factory function to get appropriate GPT implementation."""
    if model_config.endpoint:
        return CustomOpenAIGPT(api_key, model_config)
    else:
        return OpenAIGPT(api_key, model_config)
