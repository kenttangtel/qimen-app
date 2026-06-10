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

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "kenttangtel@gmail.com"