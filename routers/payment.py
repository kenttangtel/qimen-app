from fastapi import APIRouter, HTTPException, Request, Query, Header
from pydantic import BaseModel
import stripe
from jose import jwt, JWTError
import logging
import hmac
from sqlalchemy import text
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
from models.db import SessionLocal, User, CheckoutSessionRecord, RevenueCatEvent

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


def _extract_subscription_id(obj):
    """Resolve a subscription id from either an Invoice or a Subscription object.

    Stripe's newer API versions removed `Invoice.subscription`; the id now lives
    under `invoice.parent.subscription_details.subscription`. A
    `customer.subscription.*` event's data object IS the Subscription itself, so
    its own `id` is the subscription id.
    """
    direct = _safe_stripe_attr(obj, "subscription", None)
    if isinstance(direct, str):
        return direct

    parent = _safe_stripe_attr(obj, "parent", None)
    details = _safe_stripe_attr(parent, "subscription_details", None)
    nested = _safe_stripe_attr(details, "subscription", None)
    if isinstance(nested, str):
        return nested

    # Fallback: the object may itself be a Subscription (customer.subscription.*)
    if _safe_stripe_attr(obj, "object", None) == "subscription":
        return _safe_stripe_attr(obj, "id", None)

    return None


def _apply_supabase_patch(user_id, update_payload):
    """Best-effort mirror of the update into Supabase (the app's source of truth)."""
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return
    try:
        supabase_admin = get_supabase_admin()
        update_resp = supabase_admin.from_("users").update(update_payload).eq("id", user_id).execute()
        logger.info("Supabase admin update response: %s", update_resp)
    except Exception as e:
        logger.error("Supabase admin update failed: %s", e)


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


def _add_credits_atomic(db, user_id: str, amount: int) -> int:
    """Increment credits with a single UPDATE ... SET credits = credits + :n.

    A read-modify-write (user.credits = user.credits + n) loses credits when two
    webhooks land concurrently. Returning the new value keeps the ORM object and
    Supabase in sync without a second query.
    """
    result = db.execute(
        text(
            "UPDATE users SET credits = COALESCE(credits, 0) + :amount "
            "WHERE id = :uid RETURNING credits"
        ),
        {"amount": amount, "uid": user_id},
    )
    row = result.first()
    return int(row[0]) if row else 0


def process_checkout_session(session, db):
    if not session or not _safe_stripe_attr(session, "id", None):
        return {"status": "error", "message": "invalid_session"}
    if is_checkout_session_processed(db, _safe_stripe_attr(session, "id", "")):
        return {"status": "success", "message": "already_processed"}

    client_ref = _safe_stripe_attr(session, "client_reference_id", None)
    user = db.query(User).filter(User.id == str(client_ref)).first()
    if not user:
        return {"status": "error", "message": "user_not_found"}

    update_payload = {}
    credits_to_add = 0

    session_mode = _safe_stripe_attr(session, "mode", "")
    if session_mode == "subscription":
        stripe_customer = _safe_stripe_attr(session, "customer", None)
        stripe_subscription = _safe_stripe_attr(session, "subscription", None)
        update_payload = {
            **(dict(stripe_customer_id=stripe_customer) if stripe_customer else {}),
            **(dict(stripe_subscription_id=stripe_subscription) if stripe_subscription else {}),
            "subscription_status": "active",
            "membership_type": "monthly",
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

            # 永久會員大禮包：自動加碼送 10 點
            if membership_type == "lifetime":
                credits_to_add += 10

        if plan.get("credits"):
            credits_to_add += plan["credits"]

    # NOTE: `users.is_vip` exists in the database (and is maintained by Supabase),
    # but it is NOT a mapped column on the SQLAlchemy `User` model. Setting
    # `user.is_vip` therefore silently does nothing. `is_vip` is derived from
    # `membership_type` everywhere in the API, so we only mirror it to Supabase.
    if update_payload.get("membership_type") in ("monthly", "lifetime"):
        update_payload["is_vip"] = True

    _apply_supabase_patch(user.id, update_payload)

    for field in ("stripe_customer_id", "stripe_subscription_id", "subscription_status", "membership_type"):
        if field in update_payload:
            setattr(user, field, update_payload[field])

    if credits_to_add:
        user.credits = _add_credits_atomic(db, user.id, credits_to_add)

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
                # Returning 200 here would tell Stripe the event was handled and
                # suppress its retry. Surface a real error so the event is retried.
                db.rollback()
                raise HTTPException(status_code=500, detail=f"checkout session failed: {result.get('message')}")

        elif event.type in ("invoice.payment_succeeded", "invoice.paid"):
            obj = event.data.object
            subscription_id = _extract_subscription_id(obj)
            user = None
            if subscription_id:
                user = db.query(User).filter(User.stripe_subscription_id == subscription_id).first()
            if not user:
                customer_id = _safe_stripe_attr(obj, "customer", None)
                if customer_id:
                    user = db.query(User).filter(User.stripe_customer_id == customer_id).first()
            if user:
                user.subscription_status = "active"
                user.membership_type = "monthly"
                _apply_supabase_patch(user.id, {"subscription_status": "active", "membership_type": "monthly", "is_vip": True})
            else:
                logger.warning("invoice.payment_succeeded: no user matched (subscription=%s)", subscription_id)

        elif event.type in ("customer.subscription.deleted", "customer.subscription.updated", "invoice.payment_failed"):
            obj = event.data.object
            subscription_id = _extract_subscription_id(obj)
            user = None
            if subscription_id:
                user = db.query(User).filter(User.stripe_subscription_id == subscription_id).first()
            if not user:
                customer_id = _safe_stripe_attr(obj, "customer", None)
                if customer_id:
                    user = db.query(User).filter(User.stripe_customer_id == customer_id).first()

            if user:
                if event.type == "invoice.payment_failed":
                    status = "past_due"
                elif event.type == "customer.subscription.updated":
                    # Only downgrade when the subscription actually left a live state.
                    stripe_status = _safe_stripe_attr(obj, "status", "")
                    status = "active" if stripe_status in ("active", "trialing") else "inactive"
                else:
                    status = "inactive"

                user.subscription_status = status
                if status == "active":
                    user.membership_type = "monthly"
                else:
                    user.membership_type = "free"
                _apply_supabase_patch(
                    user.id,
                    {
                        "subscription_status": status,
                        "membership_type": user.membership_type,
                        "is_vip": status == "active",
                    },
                )
            else:
                logger.warning("%s: no user matched (subscription=%s)", event.type, subscription_id)

        db.commit()
        return {"status": "success"}
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Stripe webhook handling failed for event %s", getattr(event, "type", "?"))
        raise HTTPException(status_code=500, detail=f"webhook processing failed: {exc}")
    finally:
        db.close()


# ==========================================
# RevenueCat (App 雙平台 IAP) 金流 Webhook
# ==========================================
def _credit_amount_for_product(product_id: str) -> int:
    """Map a RevenueCat product id to the number of credits it grants."""
    mapping = {
        "topup_5": 5,
        "topup_15": 15,
    }
    return mapping.get(product_id, 0)


@router.post("/api/v1/payment/webhook/revenuecat")
async def revenuecat_webhook(request: Request, authorization: str = Header(None)):
    """接收來自 RevenueCat 的伺服器對伺服器 (S2S) 付款成功通知"""
    # 1. 取得系統環境變數中的 Webhook 密碼
    WEBHOOK_TOKEN = config.REVENUECAT_WEBHOOK_TOKEN
    if not WEBHOOK_TOKEN:
        # Fail closed. A default token would let anyone grant themselves credits.
        logger.error("REVENUECAT_WEBHOOK_TOKEN 未設定，拒絕處理 RevenueCat webhook")
        raise HTTPException(status_code=503, detail="RevenueCat webhook not configured")

    # 2. 安全驗證（constant-time 比對，避免時序側信道）
    expected_auth = f"Bearer {WEBHOOK_TOKEN}"
    if not authorization or not hmac.compare_digest(authorization, expected_auth):
        logger.error("Webhook 安全驗證失敗")
        raise HTTPException(status_code=401, detail="Unauthorized webhook call")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = payload.get("event", {}) or {}
    event_type = event.get("type")
    event_id = event.get("id")
    app_user_id = event.get("app_user_id")
    product_id = event.get("product_id")

    logger.info("收到 App 金流事件: %s | id: %s | 用戶: %s | 購買商品: %s", event_type, event_id, app_user_id, product_id)

    db = SessionLocal()
    try:
        # 3. 冪等性：RevenueCat 會重試投遞，同一 event id 只能處理一次
        if event_id:
            already = db.query(RevenueCatEvent).filter(RevenueCatEvent.id == str(event_id)).first()
            if already:
                logger.info("RevenueCat 事件 %s 已處理過，略過重複投遞", event_id)
                return {"status": "success", "message": "already_processed"}

        if event_type in ("INITIAL_PURCHASE", "NON_RENEWING_PURCHASE"):
            user = db.query(User).filter(User.id == app_user_id).first()
            if user:
                added_credits = _credit_amount_for_product(product_id)
                if added_credits <= 0:
                    logger.warning("未知的商品 ID '%s'，未加點 (用戶 %s)", product_id, app_user_id)
                else:
                    user.credits = _add_credits_atomic(db, user.id, added_credits)
                    logger.info("App 儲值成功！已為用戶 %s 增加 %s 點", app_user_id, added_credits)
            else:
                logger.error("找不到對應的用戶 ID: %s", app_user_id)

        if event_id:
            db.add(
                RevenueCatEvent(
                    id=str(event_id),
                    user_id=app_user_id,
                    event_type=event_type,
                    product_id=product_id,
                )
            )

        db.commit()
        return {"status": "success"}

    except HTTPException:
        db.rollback()
        raise
    except Exception as db_exc:
        db.rollback()
        logger.exception("處理 RevenueCat Webhook 時發生錯誤: %s", db_exc)
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        db.close()
