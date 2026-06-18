from fastapi import APIRouter
import config

router = APIRouter()


@router.get("/api/v1/debug/env")
def debug_env():
    """Return presence (True/False) of important environment variables.
    This endpoint intentionally does NOT return secret values.
    """
    keys = [
        "DATABASE_URL",
        "SECRET_KEY",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "STRIPE_PRICE_VIP",
        "STRIPE_PRICE_LIFETIME",
        "STRIPE_PRICE_5_CREDITS",
        "STRIPE_PRICE_15_CREDITS",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
    ]
    result = {k: bool(getattr(config, k, None)) for k in keys}
    return {"env_present": result}
