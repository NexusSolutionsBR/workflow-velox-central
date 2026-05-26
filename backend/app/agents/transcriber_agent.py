"""
Agente Especialista em Transcrição de Áudios.

Usa o SDK da OpenAI (Whisper) para transcrição, pois é a única API
com suporte nativo a speech-to-text de alta qualidade.
Quando outros providers lançarem STT, basta adicionar aqui.
"""

import openai
from app.core.config import settings


def transcribe_audio(file_path: str) -> str:
    """
    Transcreve um arquivo de áudio usando o Whisper da OpenAI.
    Se não houver chave configurada, retorna um mock simulado.
    """
    if not settings.OPENAI_API_KEY:
        filename = file_path.replace("\\", "/").split("/")[-1]
        return f"[Áudio Transcrito Simulado] Arquivo processado: {filename}"

    try:
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
        with open(file_path, "rb") as audio_file:
            response = client.audio.transcriptions.create(
                model=settings.AI_TRANSCRIPTION_MODEL or "whisper-1",
                file=audio_file
            )
            return response.text
    except Exception as e:
        print(f"[TranscriberAgent] Erro na transcrição: {e}")
        return f"[Erro na transcrição] Arquivo: {file_path}"
