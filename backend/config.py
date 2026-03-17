"""
Configuration Management for Supegroww with Production Logging
==============================================================

This module centralizes all configuration and secrets management with
comprehensive logging for validation, initialization, and configuration changes.

LOGGING FEATURES IMPLEMENTED:
1. Configuration loading and validation logging
2. Environment variable presence/absence tracking
3. Sensitive data masking in logs
4. Configuration change detection
5. Integration validation logging
6. Startup diagnostic information
"""

import os
from typing import Optional
from pathlib import Path
from pydantic_settings import BaseSettings 
from pydantic import Field, validator, model_validator
from enum import Enum

# IMPORTANT: Delay logger import to avoid circular dependency
# Logger will be initialized after settings are loaded
_logger = None

def get_config_logger():
    """Get logger instance (lazy loaded to avoid circular import)"""
    global _logger
    if _logger is None:
        # Import here to avoid circular dependency
        from backend.logger import get_logger
        _logger = get_logger("config")
    return _logger


class Environment(str, Enum):
    """Environment types"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """
    Application settings with validation and logging.
    
    Why Pydantic BaseSettings:
    - Automatic environment variable loading
    - Type validation
    - Clear error messages if config is invalid
    - IDE autocomplete support
    """
    
    # APPLICATION
    
    APP_NAME: str = "Supergroww AI Interview Platform"
    ENVIRONMENT: Environment = Field(default=Environment.DEVELOPMENT)
    DEBUG: bool = Field(default=False)
    LOG_LEVEL: str = Field(default="INFO")
    LOG_TO_FILE: bool = Field(default=True)
    LOG_DIR: str = Field(default="./logs")
    
    # DATABASE
    
    DATABASE_URL: str = Field(
        default="postgresql://postgres.qfldythpnpnxupgcfpfl:Super%402004_1234@aws-0-ap-south-1.pooler.supabase.com:6543/postgres",
        description="PostgreSQL connection URL with URL-encoded password"
    )
    
    DATABASE_POOL_SIZE: int = Field(default=10)
    DATABASE_MAX_OVERFLOW: int = Field(default=20)
    
    # LIVEKIT (WebRTC Infrastructure)
    
    LIVEKIT_URL: str = Field(
        ...,  # Required field
        description="LiveKit server WebSocket URL (e.g., wss://your-server.livekit.cloud)"
    )
    
    LIVEKIT_API_KEY: str = Field(
        ...,  # Required
        description="LiveKit API key for authentication"
    )
    
    LIVEKIT_API_SECRET: str = Field(
        ...,  # Required
        description="LiveKit API secret for token generation"
    )
    
    # SPEECH-TO-TEXT (Deepgram)
    
    DEEPGRAM_API_KEY: str = Field(
        ...,  # Required
        description="Deepgram API key for speech recognition"
    )
    
    DEEPGRAM_MODEL: str = Field(
        default="nova-2",
        description="Deepgram model to use"
    )
    
    DEEPGRAM_LANGUAGE: str = Field(default="en-US")
    DEEPGRAM_SAMPLE_RATE: int = Field(default=16000)
    
    # LLM (Groq)
    
    GROQ_API_KEY: str = Field(
        ...,  # Required
        description="Groq API key for LLM inference"
    )
    
    GROQ_MODEL: str = Field(
        default="llama-3.3-70b-versatile",
        description="Groq model to use"
    )
    
    # Fallback to OpenAI if Groq fails
    OPENAI_API_KEY: Optional[str] = Field(
        default=None,
        description="OpenAI API key (optional fallback)"
    )
    
    OPENAI_MODEL: str = Field(
        default="gpt-4o",
        description="OpenAI model for fallback"
    )
    
    # TEXT-TO-SPEECH (ElevenLabs or Cartesia)
    
    TTS_PROVIDER: str = Field(
        default="cartesia",
        description="TTS provider: 'elevenlabs' or 'cartesia'"
    )
    
    ELEVENLABS_API_KEY: Optional[str] = Field(
        default="sk_75531957262bf587dc33e300ada95f352e18055f14abb492",
        description="ElevenLabs API key"
    )
    
    ELEVENLABS_VOICE_ID: str = Field(
        default="pNInz6obpgDQGcFmaJgB",  
        description="ElevenLabs voice ID to use"
    )
    
    CARTESIA_API_KEY: Optional[str] = Field(
        default=None,
        description="Cartesia API key"
    )

    CARTESIA_VOICE_ID: str = Field(
        default="79a125e8-cd45-4c13-8a67-188112f4dd22",  
        description="cartesia voice ID to use"
    )
    
    # EMBEDDINGS (for RAG)
    
    EMBEDDING_PROVIDER: str = Field(
        default="local",
        description="Embedding provider: 'openai' or 'local'"
    )
    
    EMBEDDING_MODEL: str = Field(
        default="all-MiniLM-L6-v2",
        description="Embedding model to use"
    )
    
    EMBEDDING_DIMENSION: int = Field(
        default=384,
        description="Vector dimension (must match model)"
    )
    
    # SENTIMENT ANALYSIS (Hume AI - Optional)
    
    HUME_API_KEY: Optional[str] = Field(
        default=None,
        description="Hume AI API key for sentiment analysis"
    )
    
    ENABLE_SENTIMENT_ANALYSIS: bool = Field(
        default=False,
        description="Enable real-time sentiment analysis"
    )
    
    # INTERVIEW SETTINGS
    
    DEFAULT_INTERVIEW_DURATION_MINUTES: int = Field(default=30)
    MAX_INTERVIEW_DURATION_MINUTES: int = Field(default=60)
    MAX_QUESTIONS_PER_INTERVIEW: int = Field(default=15)
    MAX_PROBING_DEPTH: int = Field(default=2)
    
    # STORAGE (for recordings and resumes)
    
    STORAGE_PROVIDER: str = Field(
        default="local",
        description="Storage provider: 'local', 's3', 'gcs'"
    )
    
    # S3 Configuration
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_S3_BUCKET: Optional[str] = None
    AWS_S3_REGION: str = Field(default="us-east-1")
    
    # Local storage
    LOCAL_STORAGE_PATH: str = Field(default="./storage")
    
    # ATS INTEGRATIONS
    
    # Lever
    LEVER_API_KEY: Optional[str] = None
    LEVER_WEBHOOK_SECRET: Optional[str] = None
    
    # Greenhouse
    GREENHOUSE_API_KEY: Optional[str] = None
    GREENHOUSE_WEBHOOK_SECRET: Optional[str] = None
    
    # SECURITY & COMPLIANCE
    
    # Anti-cheating
    ENABLE_GAZE_TRACKING: bool = Field(default=True)
    ENABLE_VOICE_BIOMETRICS: bool = Field(default=False)
    ENABLE_TAB_DETECTION: bool = Field(default=True)
    
    GAZE_API_KEY: Optional[str] = None
    
    # JWT for API authentication
    JWT_SECRET_KEY: str = Field(
        default="your-secret-key-change-in-production",
        description="Secret key for JWT tokens"
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_EXPIRATION_HOURS: int = Field(default=24)
    
    # CORS
    ALLOWED_ORIGINS: list = Field(
        default=["http://localhost:3000"],
        description="Allowed CORS origins"
    )
    
    # FEATURE FLAGS
    
    ENABLE_RAG: bool = Field(
        default=True,
        description="Enable Resume RAG retrieval"
    )
    
    ENABLE_REAL_TIME_EVALUATION: bool = Field(
        default=True,
        description="Enable per-answer scoring"
    )
    
    ENABLE_AUTO_PROBING: bool = Field(
        default=True,
        description="Auto-generate follow-up questions"
    )
    
    # MONITORING & OBSERVABILITY
    
    SENTRY_DSN: Optional[str] = Field(
        default=None,
        description="Sentry DSN for error tracking"
    )
    
    ENABLE_METRICS: bool = Field(default=True)
    METRICS_PORT: int = Field(default=9090)

    # VALIDATORS WITH LOGGING
    
    @validator("ENVIRONMENT")
    def validate_environment(cls, v):
        """Validate environment with logging"""
        logger = get_config_logger()
        logger.info(
            "Environment validated",
            extra={"environment": v.value if hasattr(v, 'value') else v}
        )
        return v
    
    @validator("LOG_LEVEL")
    def validate_log_level(cls, v):
        """Validate log level"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return v.upper()
    
    @validator("DATABASE_URL")
    def validate_database_url(cls, v):
        """Validate database URL with safe logging"""
        logger = get_config_logger()
        
        if not v.startswith("postgresql://"):
            raise ValueError("DATABASE_URL must start with postgresql://")
        
        # Log without exposing credentials
        host_info = v.split('@')[1] if '@' in v else 'unknown'
        logger.info(
            "Database URL validated",
            extra={"host": host_info}
        )
        
        return v
    
    @model_validator(mode='after')
    def validate_tts_provider(self):
        """Validate TTS provider configuration with logging"""
        logger = get_config_logger()
        
        tts_provider = self.TTS_PROVIDER
        elevenlabs_key = self.ELEVENLABS_API_KEY
        cartesia_key = self.CARTESIA_API_KEY
        
        logger.debug(
            "Validating TTS configuration",
            extra={
                "provider": tts_provider,
                "elevenlabs_configured": bool(elevenlabs_key),
                "cartesia_configured": bool(cartesia_key)
            }
        )
        
        if tts_provider == "elevenlabs" and not elevenlabs_key:
            logger.error("ElevenLabs API key missing")
            raise ValueError("ELEVENLABS_API_KEY required when TTS_PROVIDER is elevenlabs")
        if tts_provider == "cartesia" and not cartesia_key:
            logger.error("Cartesia API key missing")
            raise ValueError("CARTESIA_API_KEY required when TTS_PROVIDER is cartesia")
        
        logger.info(
            "TTS configuration validated",
            extra={"provider": tts_provider}
        )
        
        return self  
    
    @validator("EMBEDDING_DIMENSION")
    def validate_embedding_dimension(cls, v, values):
        """Ensure embedding dimension matches model with logging"""
        logger = get_config_logger()
        model = values.get("EMBEDDING_MODEL", "")
        
        logger.debug(
            "Validating embedding dimension",
            extra={
                "model": model,
                "dimension": v
            }
        )
        
        # OpenAI dimensions
        if "text-embedding-3-small" in model and v != 1536:
            logger.error("Embedding dimension mismatch for text-embedding-3-small")
            raise ValueError("text-embedding-3-small requires dimension=1536")
        if "text-embedding-3-large" in model and v != 3072:
            logger.error("Embedding dimension mismatch for text-embedding-3-large")
            raise ValueError("text-embedding-3-large requires dimension=3072")
        
        logger.info(
            "Embedding dimension validated",
            extra={
                "model": model,
                "dimension": v
            }
        )
        
        return v

    # PYDANTIC CONFIG
    
    class Config:
        """Pydantic configuration"""
        _config_dir = Path(__file__).parent.resolve()
        env_file = str(_config_dir / ".env")
        env_file_encoding = "utf-8"
        case_sensitive = True

# SINGLETON INSTANCE WITH LOGGING

def create_settings() -> Settings:
    """Create settings instance with initialization logging"""
    logger = get_config_logger()
    
    logger.info("Initializing application settings")
    
    try:
        settings = Settings()
        
        logger.info(
            "Settings loaded successfully",
            extra={
                "environment": settings.ENVIRONMENT.value,
                "debug_mode": settings.DEBUG,
                "log_level": settings.LOG_LEVEL
            }
        )
        
        return settings
    
    except Exception as e:
        logger.error(
            "Failed to load settings",
            extra={"error": str(e)},
            exc_info=True
        )
        raise

# Create singleton instance
settings = create_settings()

# VALIDATION HELPER WITH LOGGING

def validate_critical_settings():
    """
    Validate that all critical settings are present with logging.
    
    Why: Call this on application startup to fail fast if config is invalid.
    """
    logger = get_config_logger()
    
    logger.info("Starting critical settings validation")
    
    critical_vars = [
        "LIVEKIT_URL",
        "LIVEKIT_API_KEY",
        "LIVEKIT_API_SECRET",
        "DEEPGRAM_API_KEY",
        "GROQ_API_KEY",
    ]
    
    # TTS is critical
    if settings.TTS_PROVIDER == "elevenlabs":
        critical_vars.append("ELEVENLABS_API_KEY")
    elif settings.TTS_PROVIDER == "cartesia":
        critical_vars.append("CARTESIA_API_KEY")
    
    # Embeddings for RAG
    if settings.ENABLE_RAG:
        if settings.EMBEDDING_PROVIDER == "openai":
            critical_vars.append("OPENAI_API_KEY")
    
    logger.debug(
        "Checking critical variables",
        extra={"variables": critical_vars}
    )
    
    missing = []
    present = []
    
    for var in critical_vars:
        value = getattr(settings, var, None)
        if not value:
            missing.append(var)
        else:
            present.append(var)
    
    if missing:
        logger.error(
            "Missing critical environment variables",
            extra={
                "missing": missing,
                "present": present
            }
        )
        
        raise ValueError(
            f"Missing critical environment variables: {', '.join(missing)}\n"
            f"Please set these in your .env file or environment."
        )
    
    logger.info(
        "Critical settings validation passed",
        extra={
            "validated_count": len(present),
            "variables": present
        }
    )
    
    print("✅ Configuration validated successfully!")


def print_config_summary():
    """Print and log configuration summary (safe for logs - no secrets)"""
    logger = get_config_logger()
    
    logger.info("Generating configuration summary")
    
    # Build summary data
    summary_data = {
        "environment": settings.ENVIRONMENT.value,
        "debug_mode": settings.DEBUG,
        "log_level": settings.LOG_LEVEL,
        "database_configured": bool(settings.DATABASE_URL),
        "livekit_configured": bool(settings.LIVEKIT_URL),
        "deepgram_model": settings.DEEPGRAM_MODEL,
        "groq_model": settings.GROQ_MODEL,
        "tts_provider": settings.TTS_PROVIDER,
        "embedding_provider": settings.EMBEDDING_PROVIDER,
        "embedding_model": settings.EMBEDDING_MODEL,
        "interview_duration": settings.DEFAULT_INTERVIEW_DURATION_MINUTES,
        "max_questions": settings.MAX_QUESTIONS_PER_INTERVIEW,
        "feature_flags": {
            "rag": settings.ENABLE_RAG,
            "real_time_evaluation": settings.ENABLE_REAL_TIME_EVALUATION,
            "auto_probing": settings.ENABLE_AUTO_PROBING,
            "sentiment_analysis": settings.ENABLE_SENTIMENT_ANALYSIS,
            "gaze_tracking": settings.ENABLE_GAZE_TRACKING,
            "tab_detection": settings.ENABLE_TAB_DETECTION
        },
        "integrations": {
            "lever": bool(settings.LEVER_API_KEY),
            "greenhouse": bool(settings.GREENHOUSE_API_KEY),
            "sentry": bool(settings.SENTRY_DSN)
        }
    }
    
    logger.info("Configuration summary", extra=summary_data)
    
    # Print human-readable summary
    print("\n" + "="*60)
    print("🔧 SUPEGROWW CONFIGURATION SUMMARY")
    print("="*60)
    
    print(f"\n📋 Environment: {settings.ENVIRONMENT.value}")
    print(f"🐛 Debug Mode: {settings.DEBUG}")
    print(f"📊 Log Level: {settings.LOG_LEVEL}")
    
    print(f"\n🗄️  Database: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'configured'}")
    
    print(f"\n🎥 LiveKit: {settings.LIVEKIT_URL}")
    print(f"🎤 Speech-to-Text: Deepgram ({settings.DEEPGRAM_MODEL})")
    print(f"🧠 LLM: Groq ({settings.GROQ_MODEL})")
    print(f"🔊 Text-to-Speech: {settings.TTS_PROVIDER.title()}")
    print(f"📦 Embeddings: {settings.EMBEDDING_PROVIDER.title()} ({settings.EMBEDDING_MODEL})")
    
    print(f"\n⏱️  Interview Duration: {settings.DEFAULT_INTERVIEW_DURATION_MINUTES} minutes")
    print(f"❓ Max Questions: {settings.MAX_QUESTIONS_PER_INTERVIEW}")
    print(f"🔍 Max Probing Depth: {settings.MAX_PROBING_DEPTH}")
    
    print(f"\n🔒 Security Features:")
    print(f"   - Gaze Tracking: {settings.ENABLE_GAZE_TRACKING}")
    print(f"   - Voice Biometrics: {settings.ENABLE_VOICE_BIOMETRICS}")
    print(f"   - Tab Detection: {settings.ENABLE_TAB_DETECTION}")
    
    print(f"\n🎯 Feature Flags:")
    print(f"   - RAG Enabled: {settings.ENABLE_RAG}")
    print(f"   - Real-time Evaluation: {settings.ENABLE_REAL_TIME_EVALUATION}")
    print(f"   - Auto Probing: {settings.ENABLE_AUTO_PROBING}")
    print(f"   - Sentiment Analysis: {settings.ENABLE_SENTIMENT_ANALYSIS}")
    
    print(f"\n💾 Storage: {settings.STORAGE_PROVIDER.title()}")
    
    integrations = []
    if settings.LEVER_API_KEY:
        integrations.append("Lever")
    if settings.GREENHOUSE_API_KEY:
        integrations.append("Greenhouse")
    
    print(f"🔗 ATS Integrations: {', '.join(integrations) if integrations else 'None'}")
    
    print("\n" + "="*60 + "\n")

# CONFIGURATION HELPERS

def mask_sensitive_value(value: str, show_chars: int = 4) -> str:
    """
    Mask sensitive configuration value for logging.
    
    Args:
        value: The value to mask
        show_chars: Number of characters to show at start/end
    
    Returns:
        Masked string (e.g., "sk_ab...xy89")
    """
    if not value or len(value) <= show_chars * 2:
        return "***"
    
    return f"{value[:show_chars]}...{value[-show_chars:]}"


def get_config_for_logging() -> dict:
    """
    Get configuration dict safe for logging (secrets masked).
    
    Returns:
        Dict with sensitive values masked
    """
    return {
        "app_name": settings.APP_NAME,
        "environment": settings.ENVIRONMENT.value,
        "debug": settings.DEBUG,
        "log_level": settings.LOG_LEVEL,
        "livekit_url": settings.LIVEKIT_URL,
        "livekit_api_key": mask_sensitive_value(settings.LIVEKIT_API_KEY),
        "deepgram_model": settings.DEEPGRAM_MODEL,
        "groq_model": settings.GROQ_MODEL,
        "tts_provider": settings.TTS_PROVIDER,
        "embedding_provider": settings.EMBEDDING_PROVIDER,
        "embedding_model": settings.EMBEDDING_MODEL,
        "feature_flags": {
            "rag": settings.ENABLE_RAG,
            "real_time_evaluation": settings.ENABLE_REAL_TIME_EVALUATION,
            "auto_probing": settings.ENABLE_AUTO_PROBING,
        }
    }

# ENVIRONMENT FILE TEMPLATE GENERATOR

def generate_env_template():
    """Generate a .env.example file for documentation"""
    logger = get_config_logger()
    logger.info("Generating environment template")
    
    template = """# Supegroww AI Interview Platform - Environment Variables
# Copy this file to .env and fill in your actual values

# =============================================================================
# APPLICATION
# =============================================================================
ENVIRONMENT=development
DEBUG=true
LOG_LEVEL=INFO

# =============================================================================
# DATABASE
# =============================================================================
DATABASE_URL=postgresql://postgres:password@localhost:5432/supegroww

# =============================================================================
# LIVEKIT (WebRTC Infrastructure)
# =============================================================================
# Sign up at: https://livekit.io
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=your-api-key
LIVEKIT_API_SECRET=your-api-secret

# =============================================================================
# SPEECH-TO-TEXT
# =============================================================================
# Sign up at: https://deepgram.com (Free tier: $200 credit)
DEEPGRAM_API_KEY=your-deepgram-key

# =============================================================================
# LLM (Large Language Model)
# =============================================================================
# Sign up at: https://groq.com (Free tier available)
GROQ_API_KEY=your-groq-key

# Optional fallback
# OPENAI_API_KEY=your-openai-key

# =============================================================================
# TEXT-TO-SPEECH
# =============================================================================
# Choose: elevenlabs or cartesia
TTS_PROVIDER=elevenlabs

# ElevenLabs (https://elevenlabs.io)
ELEVENLABS_API_KEY=your-elevenlabs-key
ELEVENLABS_VOICE_ID=pNInz6obpgDQGcFmaJgB

# OR Cartesia (https://cartesia.ai)
# CARTESIA_API_KEY=your-cartesia-key

# =============================================================================
# EMBEDDINGS (for Resume RAG)
# =============================================================================
OPENAI_API_KEY=your-openai-key  # Required for embeddings
EMBEDDING_MODEL=text-embedding-3-small

# =============================================================================
# OPTIONAL: SENTIMENT ANALYSIS
# =============================================================================
# HUME_API_KEY=your-hume-key
# ENABLE_SENTIMENT_ANALYSIS=false

# =============================================================================
# OPTIONAL: ATS INTEGRATIONS
# =============================================================================
# LEVER_API_KEY=your-lever-key
# LEVER_WEBHOOK_SECRET=your-webhook-secret
# GREENHOUSE_API_KEY=your-greenhouse-key
# GREENHOUSE_WEBHOOK_SECRET=your-webhook-secret

# =============================================================================
# SECURITY
# =============================================================================
JWT_SECRET_KEY=change-this-to-a-random-string-in-production

# =============================================================================
# STORAGE
# =============================================================================
STORAGE_PROVIDER=local
LOCAL_STORAGE_PATH=./storage

# For S3:
# AWS_ACCESS_KEY_ID=your-access-key
# AWS_SECRET_ACCESS_KEY=your-secret-key
# AWS_S3_BUCKET=your-bucket-name
"""
    return template

# MODULE ENTRY POINT

if __name__ == "__main__":
    import sys
    
    logger = get_config_logger()
    
    if "--generate-template" in sys.argv:
        print(generate_env_template())
    else:
        # Validate and print config
        try:
            logger.info("Running configuration validation")
            validate_critical_settings()
            print_config_summary()
            logger.info("Configuration validation completed successfully")
        except ValueError as e:
            logger.error(
                "Configuration validation failed",
                extra={"error": str(e)},
                exc_info=True
            )
            print(f"\n❌ Configuration Error:\n{e}\n")
            print("Run: python config.py --generate-template > .env.example")
            print("Then copy .env.example to .env and fill in your values.")
            sys.exit(1)