import os
from dotenv import load_dotenv
load_dotenv()
from routers.payment import process_checkout_session
from models.db import SessionLocal

class FakeSession(dict):
    def __getattr__(self, item):
        return self.get(item)

# Simulate Stripe checkout.session.completed for VIP monthly subscription
subscription_session = FakeSession({
    'id': 'cs_test_sub_001',
    'object': 'checkout.session',
    'mode': 'subscription',
    'payment_status': 'paid',
    'status': 'complete',
    'customer': 'cus_test',
    'subscription': 'sub_test_001',
    'client_reference_id': '8bf0b507b6bbd570',
    'metadata': {'price_id': os.environ.get('STRIPE_PRICE_VIP')}
})

# Simulate Stripe checkout.session.completed for lifetime payment
payment_session = FakeSession({
    'id': 'cs_test_pay_001',
    'object': 'checkout.session',
    'mode': 'payment',
    'payment_status': 'paid',
    'status': 'complete',
    'customer': 'cus_test',
    'subscription': None,
    'client_reference_id': '8bf0b507b6bbd570',
    'metadata': {'price_id': os.environ.get('STRIPE_PRICE_LIFETIME')}
})

db = SessionLocal()
try:
    for s in [subscription_session, payment_session]:
        try:
            print('testing', s['id'])
            result = process_checkout_session(s, db)
            print(result)
        except Exception as e:
            print('error', type(e).__name__, e)
finally:
    db.close()
