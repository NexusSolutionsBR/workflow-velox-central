"""
Fábrica de Modelos de IA via Agno — Troca de Provider centralizada.

Suporte atual: OpenAI, Google Gemini, Anthropic Claude.
Para trocar, altere AI_PROVIDER e AI_CHAT_MODEL no .env.

Este módulo centraliza a criação dos modelos para os agentes do Agno,
removendo a dependência do LangChain.
"""

from app.core.config import settings

def get_model():
    """
    Retorna uma instância de modelo do Agno configurada
    baseada nas variáveis AI_PROVIDER e AI_CHAT_MODEL do .env.
    """
    provider = settings.AI_PROVIDER.lower()
    model_id = settings.AI_CHAT_MODEL

    if provider == "google":
        from agno.models.google import Gemini
        return Gemini(
            id=model_id or "gemini-2.0-flash",
            api_key=settings.GOOGLE_API_KEY,
        )

    if provider == "anthropic":
        from agno.models.anthropic import Anthropic
        return Anthropic(
            id=model_id or "claude-3-5-sonnet-20240620",
            api_key=settings.ANTHROPIC_API_KEY,
        )

    from agno.models.openai import OpenAIChat
    return OpenAIChat(
        id=model_id or "gpt-5-mini",
        api_key=settings.OPENAI_API_KEY,
    )


def is_ai_configured() -> bool:
    """Verifica se existe pelo menos uma chave de API de IA configurada."""
    return bool(
        settings.OPENAI_API_KEY
        or settings.GOOGLE_API_KEY
        or settings.ANTHROPIC_API_KEY
    )
