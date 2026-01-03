import os
import requests
from django.conf import settings
import base64
import hashlib
import requests
import ecdsa

MONO_PUBKEY_URL = "https://api.monobank.ua/api/merchant/pubkey"
MONO_MERCHANT_TOKEN = os.getenv("MONO_MERCHANT_TOKEN",'mqw1iDQUsAlw9EVUrP6aJJg')
MONO_CREATE_INVOICE_URL = "https://api.monobank.ua/api/merchant/invoice/create"

_cached_pubkey_pem: str | None = None

def mono_create_invoice(*, amount_uah: float, reference: str, webhook_url: str,
                        redirect_url: str | None = None) -> dict:
    amount = int(round(float(amount_uah) * 100))

    payload = {
        "amount": amount,
        "ccy": 980,
        "merchantPaymInfo": {
            "reference": reference,
            "destination": "Оплата івенту",
            "comment": reference,
        },
        "webHookUrl": webhook_url,
        "redirectUrl": f"https://t.me/{settings.BOT_USERNAME}",
    }
    if redirect_url:
        payload["redirectUrl"] = redirect_url

    headers = {"X-Token": MONO_MERCHANT_TOKEN}
    r = requests.post(MONO_CREATE_INVOICE_URL, json=payload, headers=headers, timeout=15)
    return {'ok':True,"invoiceData":r.json()}



def _get_pubkey_pem() -> str:
    global _cached_pubkey_pem
    if _cached_pubkey_pem:
        return _cached_pubkey_pem

    headers = {"X-Token": MONO_MERCHANT_TOKEN}
    r = requests.get(MONO_PUBKEY_URL, headers=headers, timeout=15)
    r.raise_for_status()
    _cached_pubkey_pem = r.text  # PEM
    return _cached_pubkey_pem


def verify_mono_webhook_signature(*, body_bytes: bytes, x_sign_b64: str) -> bool:
    pub_pem = _get_pubkey_pem()
    vk = ecdsa.VerifyingKey.from_pem(pub_pem)
    sig = base64.b64decode(x_sign_b64)

    digest = hashlib.sha256(body_bytes).digest()
    try:
        return vk.verify(sig, digest, hashfunc=hashlib.sha256, sigdecode=ecdsa.util.sigdecode_der)
    except Exception:
        return False
