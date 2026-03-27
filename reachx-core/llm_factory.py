from typing import List, Dict, Any, Optional
from openai import OpenAI
from loguru import logger
import json

from config import settings

class LLMProvider:
    """Unified interface for multiple LLM providers"""
    
    def __init__(self, provider: str = "kimi"):
        self.provider = provider.lower()
        if self.provider == "kimi":
            self.client = OpenAI(api_key=settings.kimi_api_key, base_url=settings.kimi_base_url)
            self.model = settings.kimi_model
        elif self.provider == "deepseek":
            self.client = OpenAI(api_key=settings.deepseek_api_key, base_url=settings.deepseek_base_url)
            self.model = settings.deepseek_model
        elif self.provider == "openai":
            self.client = OpenAI(api_key=settings.openai_api_key)
            self.model = "gpt-4o"
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4000
    ) -> Dict[str, Any]:
        """Generic completion method"""
        
        # Mock check
        api_key = getattr(settings, f"{self.provider}_api_key", None) or settings.kimi_api_key
        if not api_key or "test-key" in api_key:
            return {"content": "MOCKED CONTENT FROM " + self.provider.upper()}

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return {
                "content": response.choices[0].message.content,
                "usage": response.usage.model_dump() if response.usage else None
            }
        except Exception as e:
            logger.error(f"LLM Provider ({self.provider}) error: {e}")
            raise

class LLMFactory:
    """Factory for creating LLM providers"""
    
    @staticmethod
    def get_provider(provider: Optional[str] = None) -> LLMProvider:
        if not provider:
            # Automatic selection logic
            if settings.deepseek_api_key:
                return LLMProvider("deepseek")
            return LLMProvider("kimi")
        return LLMProvider(provider)
