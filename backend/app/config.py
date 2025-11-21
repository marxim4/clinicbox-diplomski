import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the backend root (backend/.env) if present
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    ENV = os.getenv("FLASK_ENV", "development")

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://clinicbox:clinicbox@localhost:5432/clinicbox",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173")

    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret-change-me")


class DevConfig(Config):
    DEBUG = True


class ProdConfig(Config):
    DEBUG = False
