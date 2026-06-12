from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from app.config import Settings


def get_chat_model(settings: Settings) -> BaseChatModel:
    provider = settings.provider.lower()
    
    if provider == "gemini":
        from provider.gemini import build_gemini_model
        return build_gemini_model(settings)
        
    elif provider == "openai":
        from provider.openai import build_openai_model
        return build_openai_model(settings)
        
    elif provider == "openrouter":
        from provider.openrouter import build_openrouter_model
        return build_openrouter_model(settings)
        
    elif provider == "ollama":
        from provider.ollama import build_ollama_model
        return build_ollama_model(settings)
        
    elif provider == "custom":
        from provider.custom import build_custom_model
        return build_custom_model(settings)
        
    else:
        raise ValueError(f"Unsupported provider: {settings.provider}")
