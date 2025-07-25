import os
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Determine environment: 'local' or 'production'
    ENVIRONMENT = os.getenv("FLASK_ENV", "local")

    if ENVIRONMENT == "production":
        # For Render/Supabase
        SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "")
        if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
            SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace("postgres://", "postgresql://")
    else:
        # Local development fallback
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'instance', 'local.db')

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Use secret key from environment or fallback for dev
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")

    # Google OAuth
    GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
    GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
    # For email confirmation
    SECURITY_PASSWORD_SALT = os.getenv('SECURITY_PASSWORD_SALT', 'dev-salt')
    
    # OpenWeather API
    OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY')

# postgresql://<db_user>:<db_password>@<db_host>:5432/<db_name>
# ueadox89Ex8hBOLz
# $env:SUPABASE_DB_URL = "postgresql://postgres:eadox89Ex8hBOLz@db.bjepgsacyvvdeoeqxufs.supabase.co:5432/postgres"