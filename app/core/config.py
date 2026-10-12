from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Read values from environment variables (and from a .env file if one exists)
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str
    TEST_DATABASE_URL: str

    # Auth (tokens are signed with HS256)
    JWT_SECRET: str = ""
    JWT_EXPIRE_MINUTES: int = 60

    # Stripe (empty until M7)
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_CURRENCY: str = "inr"

    # Where the browser reaches the app
    FRONTEND_BASE_URL: str = "http://localhost:8000"


# One settings object shared by the whole app
settings = Settings()

# Refuse to start without a JWT secret, because an empty secret would let anyone forge tokens
if settings.JWT_SECRET == "":
    raise RuntimeError("JWT_SECRET is empty. Generate one with: openssl rand -hex 32")
