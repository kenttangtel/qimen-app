import time
import hmac
import hashlib
import json
import urllib.request

secret = 'whsec_mwuyN8jioxBNXFPZlVC5HmoUFHhkgoFj'
payload = {
    'id': 'evt_test_webhook',
    'object': 'event',
    'type': 'checkout.session.completed',
    'data': {
        'object': {
            'id': 'cs_test_webhook_001',
            'object': 'checkout.session',
            'mode': 'payment',
            'payment_status': 'paid',
            'status': 'complete',
            'customer': 'cus_test',
            'client_reference_id': 'd67cf5184f42f0e3',
            'subscription': None,
            'metadata': {'price_id': 'price_1TeoyS4ky7SVhT8tlCg26lhp'}
        }
    }
}
payload_json = json.dumps(payload)
timestamp = str(int(time.time()))
signed_payload = f'{timestamp}.{payload_json}'
sig = hmac.new(secret.encode('utf-8'), signed_payload.encode('utf-8'), hashlib.sha256).hexdigest()
header = f't={timestamp},v1={sig}'
req = urllib.request.Request(
    'http://127.0.0.1:8000/api/v1/payment/webhook',
    data=payload_json.encode('utf-8'),
    method='POST'
)
req.add_header('Content-Type', 'application/json')
req.add_header('Stripe-Signature', header)
with urllib.request.urlopen(req) as resp:
    print(resp.status)
    print(resp.read().decode('utf-8'))
