import os
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Determine environment: 'local' or 'production'
    ENVIRONMENT = os.getenv("FLASK_ENV", "production")

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

    # WeatherAPI.com API
    WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')

    # Production optimizations
    if ENVIRONMENT == "production":
        # Security headers
        SESSION_COOKIE_SECURE = True
        SESSION_COOKIE_HTTPONLY = True
        SESSION_COOKIE_SAMESITE = 'Lax'
        
        # Database connection pooling for better performance
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_size': 10,
            'pool_timeout': 30,
            'pool_recycle': 3600,
            'max_overflow': 20
        }
        
        # Cache configuration for visitor stats
        VISITOR_CACHE_TIMEOUT = 300  # 5 minutes cache for visitor stats

    # Production environment validation
    @classmethod
    def validate_production_config(cls):
        """Validate that all required environment variables are set for production"""
        if cls.ENVIRONMENT == "production":
            required_vars = [
                'DATABASE_URL',
                'SECRET_KEY',
                'SECURITY_PASSWORD_SALT'
            ]
            
            missing_vars = []
            for var in required_vars:
                if not os.getenv(var):
                    missing_vars.append(var)
            
            if missing_vars:
                raise ValueError(f"Missing required environment variables for production: {', '.join(missing_vars)}")
            
            # Validate database URL format
            db_url = os.getenv('DATABASE_URL', '')
            if not (db_url.startswith('postgresql://') or db_url.startswith('postgres://')):
                raise ValueError("DATABASE_URL must be a valid PostgreSQL connection string")
            
            print("✅ Production environment validation passed")
            return True
        return True