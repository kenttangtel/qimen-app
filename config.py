import os

from dotenv import load_dotenv

load_dotenv()


DATABASE_URL = os.environ.get("DATABASE_URL")
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY")
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")
STRIPE_PRICE_VIP = os.environ.get("STRIPE_PRICE_VIP")
STRIPE_PRICE_LIFETIME = os.environ.get("STRIPE_PRICE_LIFETIME")
STRIPE_PRICE_5_CREDITS = os.environ.get("STRIPE_PRICE_5_CREDITS")
STRIPE_PRICE_15_CREDITS = os.environ.get("STRIPE_PRICE_15_CREDITS")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
SECRET_KEY = os.environ.get("SECRET_KEY") or os.environ.get("JWT_SECRET_KEY") or "dev-secret-key"
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "kenttangtel@gmail.com"