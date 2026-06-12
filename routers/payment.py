from fastapi import APIRouter, Depends, HTTPException, Request, Body
import stripe

from config import (
    STRIPE_SECRET_KEY,
    STRIPE_PRICE_VIP,
    STRIPE_PRICE_LIFETIME,
    STRIPE_PRICE_5_CREDITS,
    STRIPE_PRICE_15_CREDITS,
    STRIPE_WEBHOOK_SECRET,
)
from models.db import get_db, User
from routers.auth import get_current_user

router = APIRouter()
stripe.api_key = STRIPE_SECRET_KEY

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
if not STRIPE_PRICE_PLAN_MAP:
    raise RuntimeError("Stripe price IDs are not configured in the environment.")


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


@router.post("/api/v1/payment/create-checkout-session")
async def create_checkout_session(
    plan: str = Body(...),
    request: Request,
    user: User = Depends(get_current_user),
):
    price_id = PLAN_CODE_TO_PRICE_ID.get(plan)
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
            success_url=f"{base_url}?payment=success",
            cancel_url=f"{base_url}?payment=cancel",
            client_reference_id=user.id,
            metadata={"price_id": price_id},
        )
        return {"url": session.url}
    except stripe.error.StripeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


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

    db = next(get_db())
    if event.type == "checkout.session.completed":
        session = event.data.object
        user = db.query(User).filter(User.id == session.client_reference_id).first()
        if not user:
            return {"status": "user_not_found"}

        if session.mode == "subscription":
            user.stripe_customer_id = session.customer
            user.stripe_subscription_id = session.subscription
            user.subscription_status = "active"
            user.membership_type = "monthly"
        else:
            price_id = session.metadata.get("price_id") if session.metadata else None
            plan = _get_plan(price_id)
            if not plan:
                return {"status": "ignored"}

            if plan.get("membership_type"):
                membership_type = plan["membership_type"]
                user.membership_type = membership_type
                user.subscription_status = (
                    "lifetime" if membership_type == "lifetime" else membership_type
                )

            if plan.get("credits"):
                user.credits = (user.credits or 0) + plan["credits"]
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