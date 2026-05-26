"""
Registro centralizado de todos os agentes do sistema.

Facilita a importação e orquestração de agentes em qualquer
parte do backend.
"""

from app.agents.transcriber_agent import transcribe_audio
from app.agents.summarizer_agent import generate_summary
from app.agents.llm_factory import get_model, is_ai_configured

__all__ = [
    "transcribe_audio",
    "generate_summary",
    "get_model",
    "is_ai_configured",
]
