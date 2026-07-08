from fastapi import APIRouter, Depends, HTTPException
import config
import os
from routers.auth import get_current_user

router = APIRouter()


REQUIRED_ENVIRONMENT = {
    "DATABASE_URL": ["DATABASE_URL"],
    "STRIPE_SECRET_KEY": ["STRIPE_SECRET_KEY"],
    "STRIPE_WEBHOOK_SECRET": ["STRIPE_WEBHOOK_SECRET"],
    "SECRET_KEY": ["SECRET_KEY", "JWT_SECRET_KEY"],
}

OPTIONAL_ENVIRONMENT = [
    "STRIPE_PRICE_VIP",
    "STRIPE_PRICE_LIFETIME",
    "STRIPE_PRICE_5_CREDITS",
    "STRIPE_PRICE_15_CREDITS",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "DEEPSEEK_API_KEY",
]


@router.get("/api/v1/debug/env")
def debug_env():
    """Return presence (True/False) of important environment variables.
    This endpoint intentionally does NOT return secret values.
    """
    required_status = {}
    missing_required = []
    for key, aliases in REQUIRED_ENVIRONMENT.items():
        present = any(os.environ.get(alias) for alias in aliases)
        required_status[key] = present
        if not present:
            missing_required.append(key)

    optional_status = {k: bool(os.environ.get(k)) for k in OPTIONAL_ENVIRONMENT}
    combined = {**required_status, **optional_status}
    return {
        "env_present": combined,
        "required_ok": len(missing_required) == 0,
        "missing_required": missing_required,
    }


@router.get("/api/v1/debug/whoami")
def debug_whoami(user=Depends(get_current_user)):
    """Return information about the injected `user` object for debugging.

    - `type`: class name of the object returned by `get_current_user`
    - `attrs`: selective attributes (id, username, email, credits, membership_type)
    """
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    info = {"type": type(user).__name__}
    attrs = {}
    for a in ("id", "username", "email", "credits", "membership_type"):
        try:
            attrs[a] = getattr(user, a)
        except Exception:
            try:
                attrs[a] = user.get(a)
            except Exception:
                attrs[a] = None
    info["attrs"] = attrs
    return info
