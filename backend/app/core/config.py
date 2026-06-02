import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    APP_PORT = os.getenv("APP_PORT", "3000")
    JWT_SECRET = os.getenv("JWT_SECRET", "")
    ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")]
    COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    # Documentação interativa (Swagger/ReDoc/OpenAPI). Desabilitada por padrão —
    # expor o schema revela todos os endpoints a quem não tem token. Habilitar só em dev.
    ENABLE_DOCS = os.getenv("ENABLE_DOCS", "false").lower() == "true"
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
    REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
    
    HELENA_API_URL = os.getenv("HELENA_API_URL", "https://api.helena.run/chat/v1/message")
    HELENA_API_KEY = os.getenv("HELENA_API_KEY")
    
    # URL base — igual para todas as operações
    CENTER_CONSULTA_URL = os.getenv("CENTER_CONSULTA_URL", "https://gbr.center.emartim.com/Publico/Consulta")
    # Identificadores por operação (cada API do Center tem o seu)
    CENTER_IDENTIFICADOR_FICHA      = os.getenv("CENTER_IDENTIFICADOR_FICHA", "")       # consulta dados da ficha (relatório)
    CENTER_IDENTIFICADOR_OCORRENCIAS = os.getenv("CENTER_IDENTIFICADOR_OCORRENCIAS", "")  # busca ocorrências existentes
    CENTER_IDENTIFICADOR_INSERCAO   = os.getenv("CENTER_IDENTIFICADOR_INSERCAO", "")    # inserção de ocorrências
    CENTER_USUARIO_PARAMETRO = os.getenv("CENTER_USUARIO_PARAMETRO", "")
    
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
