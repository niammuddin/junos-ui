import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
    ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY', 'dev-encryption-key-change-me')
    PORT = int(os.environ.get('PORT', 5000))
    
    # Security configurations
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = False
    REMEMBER_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = 3600
    
    # Database
    DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'users.db')
    
    # Rate limiting
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL', 'memory://')
    RATELIMIT_STRATEGY = os.environ.get('RATELIMIT_STRATEGY', 'fixed-window')
    SUPPRESS_TLS_WARNINGS = os.environ.get('SUPPRESS_TLS_WARNINGS', 'true').lower() in {'1', 'true', 'yes', 'on'}

    # REST API defaults
    API_DEFAULT_PORT = int(os.environ.get('API_DEFAULT_PORT', 3000))
    API_DEFAULT_USE_SSL = os.environ.get('API_USE_SSL', 'false').lower() in {'1', 'true', 'yes'}
    API_DEFAULT_VERIFY_SSL = os.environ.get('API_VERIFY_SSL', 'false').lower() in {'1', 'true', 'yes'}

    # gNMI / Telemetry
    GNMI_DEFAULT_PORT = int(os.environ.get('GNMI_DEFAULT_PORT', 9339))
    GNMI_DEFAULT_USE_SSL = os.environ.get('GNMI_USE_SSL', 'false').lower() in {'1', 'true', 'yes'}
    GNMI_DEFAULT_VERIFY_SSL = os.environ.get('GNMI_VERIFY_SSL', 'false').lower() in {'1', 'true', 'yes'}
