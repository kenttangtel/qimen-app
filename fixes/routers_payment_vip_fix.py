from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel
import stripe
from jose import jwt, JWTError
from datetime import datetime
import logging
import os
from supabase import create_client

from config import (
    STRIPE_SECRET_KEY,
    STRIPE_PRICE_VIP,
    STRIPE_PRICE_LIFETIME,
    STRIPE_PRICE_5_CREDITS,
    STRIPE_PRICE_15_CREDITS,
    STRIPE_WEBHOOK_SECRET,
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
)
import config
from models.db import SessionLocal, User, CheckoutSessionRecord

router = APIRouter()
stripe.api_key = STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


def get_supabase_admin():
    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set for admin webhook operations")
    if config.SUPABASE_URL.strip().startswith("https://your-project-ref.supabase.co"):
        raise RuntimeError("SUPABASE_URL is not configured correctly; replace the placeholder URL with your real Supabase project URL")
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)

STRIPE_PRICE_PLAN_MAP = {
    STRIPE_PRICE_VIP: {
        "mode": "subscription",
        "membership_type": "monthly",
    },
    STRIPE_PRICE_LIFETIME: {
        "mode": "payment",
        "membership_type": "lifetime",
    },
    STRIPE_PRICE_5_CREDITS: {
        "mode": "payment",
        "credits": 5,
    },
    STRIPE_PRICE_15_CREDITS: {
        "mode": "payment",
        "credits": 15,
    },
}
STRIPE_PRICE_PLAN_MAP = {
    price_id: plan for price_id, plan in STRIPE_PRICE_PLAN_MAP.items() if price_id
}


PLAN_CODE_TO_PRICE_ID = {
    "vip_monthly": STRIPE_PRICE_VIP,
    "vip_lifetime": STRIPE_PRICE_LIFETIME,
    "topup_15": STRIPE_PRICE_15_CREDITS,
    "topup_5": STRIPE_PRICE_5_CREDITS,
}
PLAN_CODE_TO_PRICE_ID = {
    plan_code: price_id
    for plan_code, price_id in PLAN_CODE_TO_PRICE_ID.items()
    if price_id
}


def _get_plan(price_id: str):
    return STRIPE_PRICE_PLAN_MAP.get(price_id)


def _safe_stripe_attr(obj, attr, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(attr, default)
    try:
        return getattr(obj, attr, default)
    except Exception:
        pass
    try:
        return obj[attr]
    except Exception:
        return default


def _safe_session_metadata_value(session, key):
    metadata = _safe_stripe_attr(session, "metadata", None)
    if metadata is None:
        return None
    if isinstance(metadata, dict):
        return metadata.get(key)
    if hasattr(metadata, "get"):
        try:
            return metadata.get(key)
        except Exception:
            pass
    try:
        return metadata[key]
    except Exception:
        return _safe_stripe_attr(metadata, key, None)


class CheckoutRequest(BaseModel):
    plan: str
    token: str | None = None


def get_user_from_token(token: str | None) -> User | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
    except JWTError:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    db = SessionLocal()
    try:
        return db.query(User).filter(User.id == user_id).first()
    finally:
        db.close()


def is_checkout_session_processed(db, session_id: str) -> bool:
    return db.query(CheckoutSessionRecord).filter(CheckoutSessionRecord.id == session_id).first() is not None


def process_checkout_session(session, db):
    if not session or not _safe_stripe_attr(session, "id", None):
        return {"status": "error", "message": "invalid_session"}
    if is_checkout_session_processed(db, _safe_stripe_attr(session, "id", "")):
        return {"status": "success", "message": "already_processed"}

    client_ref = _safe_stripe_attr(session, "client_reference_id", None)
    user = db.query(User).filter(User.id == str(client_ref)).first()
    if not user:
        return {"status": "error", "message": "user_not_found"}

    use_supabase_admin = SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
    update_payload = {}

    session_mode = _safe_stripe_attr(session, "mode", "")
    if session_mode == "subscription":
        stripe_customer = _safe_stripe_attr(session, "customer", None)
        stripe_subscription = _safe_stripe_attr(session, "subscription", None)
        update_payload = {
            **({"stripe_customer_id": stripe_customer} if stripe_customer else {}),
            **({"stripe_subscription_id": stripe_subscription} if stripe_subscription else {}),
            "subscription_status": "active",
            "membership_type": "monthly",
            "is_vip": True,
        }
    else:
        price_id = _safe_session_metadata_value(session, "price_id")
        plan = _get_plan(price_id)
        if not plan:
            return {"status": "error", "message": "Unknown plan"}

        if plan.get("membership_type"):
            membership_type = plan["membership_type"]
            update_payload["membership_type"] = membership_type
            update_payload["subscription_status"] = "lifetime" if membership_type == "lifetime" else membership_type
            if membership_type in ("monthly", "lifetime"):
                update_payload["is_vip"] = True

        if plan.get("credits"):
            update_payload["credits"] = (user.credits or 0) + plan["credits"]

    if update_payload:
        if use_supabase_admin:
            supabase_admin = get_supabase_admin()
            update_resp = supabase_admin.from_("users").update(update_payload).eq("id", user.id).execute()
            logger.info("Supabase admin update response: %s", update_resp)
            if update_resp.error:
                logger.error("Supabase admin update error detail: %s", update_resp.error)
                # 紀錄錯誤但仍同步本地資料，避免前端讀不到已付款的能量
        if "stripe_customer_id" in update_payload:
            user.stripe_customer_id = update_payload["stripe_customer_id"]
        if "stripe_subscription_id" in update_payload:
            user.stripe_subscription_id = update_payload["stripe_subscription_id"]
        if "subscription_status" in update_payload:
            user.subscription_status = update_payload["subscription_status"]
        if "membership_type" in update_payload:
            user.membership_type = update_payload["membership_type"]
        if "credits" in update_payload:
            user.credits = update_payload["credits"]
        if "is_vip" in update_payload:
            user.is_vip = update_payload["is_vip"]

    record = CheckoutSessionRecord(
        id=_safe_stripe_attr(session, "id", None),
        user_id=user.id,
        price_id=_safe_session_metadata_value(session, "price_id"),
    )
    db.add(record)
    db.commit()
    return {"status": "success", "message": "processed"}


@router.post("/api/v1/payment/create-checkout-session")
async def create_checkout_session(
    request_data: CheckoutRequest,
    request: Request,
):
    auth_header = request.headers.get("Authorization", "")
    token = request_data.token or (auth_header.split("Bearer ")[-1] if auth_header.startswith("Bearer ") else None)
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user = get_user_from_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    plan_code = request_data.plan
    price_id = PLAN_CODE_TO_PRICE_ID.get(plan_code)
    if not price_id:
        raise HTTPException(status_code=400, detail="無效的付費方案代號")

    plan_info = _get_plan(price_id)
    if not plan_info:
        raise HTTPException(status_code=400, detail="Invalid price_id")

    try:
        base_url = str(request.base_url)
        session = stripe.checkout.Session.create(
            mode=plan_info["mode"],
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=f"{base_url}?payment=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}?payment=cancel",
            client_reference_id=str(user.id),
            metadata={"price_id": price_id},
        )
        return {"status": "success", "url": session.url, "id": session.id}
    except stripe.error.StripeError as exc:
        return {"status": "error", "message": str(exc)}


@router.get("/api/v1/payment/confirm-checkout-session")
async def confirm_checkout_session(session_id: str = Query(...), request: Request = None):
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.split("Bearer ")[-1] if auth_header.startswith("Bearer ") else None
    user = get_user_from_token(token)

    try:
        stripe_session = stripe.checkout.Session.retrieve(session_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid session: {str(exc)}")

    if not (getattr(stripe_session, "payment_status", "") == "paid" or getattr(stripe_session, "status", "") == "complete"):
        raise HTTPException(status_code=400, detail="Payment not completed")

    db = SessionLocal()
    try:
        if not user:
            client_ref = getattr(stripe_session, "client_reference_id", None)
            if client_ref:
                user = db.query(User).filter(User.id == str(client_ref)).first()
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")

        result = process_checkout_session(stripe_session, db)
        return result
    finally:
        db.close()


@router.post("/api/v1/payment/webhook")
async def webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    db = SessionLocal()
    try:
        if event.type == "checkout.session.completed":
            session = event.data.object
            result = process_checkout_session(session, db)
            if result.get("status") != "success":
                return result
        elif event.type == "invoice.payment_succeeded":
            subscription = event.data.object.subscription
            user = db.query(User).filter(User.stripe_subscription_id == subscription).first()
            if user:
                user.subscription_status = "active"
                user.membership_type = "monthly"
        elif event.type in ("customer.subscription.deleted", "invoice.payment_failed"):
            subscription = event.data.object.subscription
            user = db.query(User).filter(User.stripe_subscription_id == subscription).first()
            if user:
                user.subscription_status = "past_due" if event.type == "invoice.payment_failed" else "inactive"
                user.membership_type = "free"
        db.commit()
        return {"status": "success"}
    except Exception as exc:
        db.rollback()
        return {"status": "error", "message": str(exc)}
    finally:
        db.close()
