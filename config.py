import os

from dotenv import load_dotenv

load_dotenv()


def require_env(name: str, alt: str | None = None) -> str:
    value = os.environ.get(name) or (os.environ.get(alt) if alt else None)
    if not value:
        if alt:
            raise RuntimeError(f"Environment variable {name} or {alt} must be set")
        raise RuntimeError(f"Environment variable {name} must be set")
    return value


def optional_env(name: str) -> str | None:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None


# --- Required ---
DATABASE_URL = require_env("DATABASE_URL")
STRIPE_SECRET_KEY = require_env("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = require_env("STRIPE_WEBHOOK_SECRET")
SECRET_KEY = require_env("SECRET_KEY", "JWT_SECRET_KEY")

# --- Stripe prices (optional; unset prices are simply unavailable for purchase) ---
STRIPE_API_KEY = optional_env("STRIPE_API_KEY")
STRIPE_PRICE_VIP = optional_env("STRIPE_PRICE_VIP")
STRIPE_PRICE_LIFETIME = optional_env("STRIPE_PRICE_LIFETIME")
STRIPE_PRICE_5_CREDITS = optional_env("STRIPE_PRICE_5_CREDITS")
STRIPE_PRICE_15_CREDITS = optional_env("STRIPE_PRICE_15_CREDITS")

# --- AI ---
DEEPSEEK_API_KEY = optional_env("DEEPSEEK_API_KEY")

# --- Password-reset email (Resend HTTP API). Required by /auth/forgot-password. ---
RESEND_API_KEY = optional_env("RESEND_API_KEY")
RESEND_FROM_EMAIL = optional_env("RESEND_FROM_EMAIL") or "onboarding@resend.dev"

# --- RevenueCat mobile IAP webhook. Required for /payment/webhook/revenuecat. ---
REVENUECAT_WEBHOOK_TOKEN = optional_env("REVENUECAT_WEBHOOK_TOKEN")

# --- Supabase admin (optional) ---
SUPABASE_URL = optional_env("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = optional_env("SUPABASE_SERVICE_ROLE_KEY")

# --- JWT ---
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# --- Legacy SMTP (kept for reference; password reset now uses Resend) ---
GMAIL_APP_PASSWORD = optional_env("GMAIL_APP_PASSWORD")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "kenttangtel@gmail.com")
