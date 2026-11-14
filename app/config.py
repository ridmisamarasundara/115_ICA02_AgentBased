import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./eventsphere.db")
# Render/Heroku give "postgres://..." but SQLAlchemy needs "postgresql://..."
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-secret")
APP_ENV = os.getenv("APP_ENV", "development")
# Event times are entered and shown in local venue time. Sri Lanka = UTC+5:30 = 330 minutes.
TZ_OFFSET_MINUTES = int(os.getenv("TZ_OFFSET_MINUTES", "330"))
# Set SEED_DEMO=true to create demo accounts and sample events on startup (useful on Render's free tier)
SEED_DEMO = os.getenv("SEED_DEMO", "false").lower() == "true"

if APP_ENV == "production" and SECRET_KEY == "dev-only-secret":
    raise RuntimeError("Set a real SECRET_KEY environment variable in production")
