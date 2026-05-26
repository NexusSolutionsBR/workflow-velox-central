import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    APP_PORT = os.getenv("APP_PORT", "3000")
    JWT_SECRET = os.getenv("JWT_SECRET", "")
    ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")]
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
    REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
    
    HELENA_API_URL = os.getenv("HELENA_API_URL", "https://api.helena.run/chat/v1/message")
    HELENA_API_KEY = os.getenv("HELENA_API_KEY")
    
    CENTER_API_URL = os.getenv("CENTER_API_URL", "https://api.center.example/v1/mgm")
    CENTER_API_KEY = os.getenv("CENTER_API_KEY")
    CENTER_CONSULTA_URL = os.getenv("CENTER_CONSULTA_URL", "https://gbr.center.emartim.com/Publico/Consulta")
    CENTER_IDENTIFICADOR = os.getenv("CENTER_IDENTIFICADOR", "")
    
    # AI Provider Configuration
    # Providers suportados: "openai", "google", "anthropic"
    AI_PROVIDER = os.getenv("AI_PROVIDER", "openai")
    
    # Modelos padrão por provider (sobrescritos via env)
    AI_CHAT_MODEL = os.getenv("AI_CHAT_MODEL", "gpt-4o")
    AI_TRANSCRIPTION_MODEL = os.getenv("AI_TRANSCRIPTION_MODEL", "whisper-1")
    
    # Chaves de API (uma chave por provider)
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    
    # Google Drive — OAuth user (preferido, funciona com conta pessoal)
    GOOGLE_DRIVE_CLIENT_ID = os.getenv("GOOGLE_DRIVE_CLIENT_ID")
    GOOGLE_DRIVE_CLIENT_SECRET = os.getenv("GOOGLE_DRIVE_CLIENT_SECRET")
    GOOGLE_DRIVE_REFRESH_TOKEN = os.getenv("GOOGLE_DRIVE_REFRESH_TOKEN")
    # Google Drive — Service Account (fallback, só com Workspace + Shared Drive)
    GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    GOOGLE_DRIVE_ROOT_FOLDER_ID = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "root")
    GDRIVE_IMAGE_INTERVAL_MINUTES = int(os.getenv("GDRIVE_IMAGE_INTERVAL_MINUTES", "5"))
    GDRIVE_IMAGE_MAX_PER_INTERVAL = int(os.getenv("GDRIVE_IMAGE_MAX_PER_INTERVAL", "1"))

    # Auto-sync delay após conclusão do pipeline (padrão: 3 horas)
    AUTO_SYNC_DELAY_SECONDS = int(os.getenv("AUTO_SYNC_DELAY_SECONDS", "10800"))

settings = Settings()
