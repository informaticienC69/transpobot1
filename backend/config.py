import os
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env a la racine
load_dotenv()

class Settings:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", 3306))
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "transpobot")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

    # Identité d'envoi d'email
    SENDER_EMAIL = os.getenv("SENDER_EMAIL", "noreply@transpobot.app")

    # Brevo (Sendinblue) — API transactionnelle cloud (recommandée en production)
    BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")

    # URL publique du frontend (pour les liens d'activation)
    APP_URL = os.getenv("APP_URL", "https://transpobot-api.onrender.com")

settings = Settings()
