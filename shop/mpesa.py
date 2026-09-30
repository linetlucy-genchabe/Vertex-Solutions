"""
M-Pesa Daraja STK push ("Lipa na M-Pesa Online").
Get keys at https://developer.safaricom.co.ke — sandbox first, then "Go Live" for production.
"""
import base64
from datetime import datetime

import requests
from django.conf import settings


class MpesaError(Exception):
    pass


def is_configured():
    s = settings
    return bool(s.MPESA_CONSUMER_KEY and s.MPESA_CONSUMER_SECRET and s.MPESA_PASSKEY and s.MPESA_CALLBACK_URL)


def _base_url():
    return "https://api.safaricom.co.ke" if settings.MPESA_ENV == "production" else "https://sandbox.safaricom.co.ke"


def normalize_phone(phone):
    """0712345678 / +254712345678 / 712345678 → 254712345678"""
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if digits.startswith("0"):
        digits = "254" + digits[1:]
    elif len(digits) == 9 and digits[0] in "17":
        digits = "254" + digits
    if not (digits.startswith("254") and len(digits) == 12):
        raise MpesaError("Enter a valid Safaricom number, e.g. 0712 345 678")
    return digits


def _token():
    r = requests.get(
        f"{_base_url()}/oauth/v1/generate?grant_type=client_credentials",
        auth=(settings.MPESA_CONSUMER_KEY, settings.MPESA_CONSUMER_SECRET),
        timeout=20,
    )
    if r.status_code != 200:
        raise MpesaError("Could not connect to M-Pesa. Please try again.")
    return r.json()["access_token"]


def _password(timestamp):
    raw = f"{settings.MPESA_SHORTCODE}{settings.MPESA_PASSKEY}{timestamp}"
    return base64.b64encode(raw.encode()).decode()


def stk_push(phone, amount, account_ref, description="Vertex Solutions order"):
    """Send the payment prompt to the customer's phone. Returns CheckoutRequestID."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    till = settings.MPESA_TILL_NUMBER
    payload = {
        "BusinessShortCode": settings.MPESA_SHORTCODE,
        "Password": _password(timestamp),
        "Timestamp": timestamp,
        "TransactionType": "CustomerBuyGoodsOnline" if till else "CustomerPayBillOnline",
        "Amount": int(amount),
        "PartyA": phone,
        "PartyB": till or settings.MPESA_SHORTCODE,
        "PhoneNumber": phone,
        "CallBackURL": settings.MPESA_CALLBACK_URL,
        "AccountReference": account_ref[:12],
        "TransactionDesc": description[:13],
    }
    r = requests.post(
        f"{_base_url()}/mpesa/stkpush/v1/processrequest",
        json=payload,
        headers={"Authorization": f"Bearer {_token()}"},
        timeout=30,
    )
    data = r.json() if r.content else {}
    if r.status_code != 200 or data.get("ResponseCode") != "0":
        raise MpesaError(data.get("errorMessage") or data.get("CustomerMessage") or "M-Pesa request failed.")
    return data["CheckoutRequestID"]


def stk_query(checkout_request_id):
    """Ask Safaricom for the result (used if the callback is slow). Returns (result_code, description)."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    r = requests.post(
        f"{_base_url()}/mpesa/stkpushquery/v1/query",
        json={
            "BusinessShortCode": settings.MPESA_SHORTCODE,
            "Password": _password(timestamp),
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        },
        headers={"Authorization": f"Bearer {_token()}"},
        timeout=20,
    )
    data = r.json() if r.content else {}
    code = data.get("ResultCode")
    return (str(code) if code is not None else None), data.get("ResultDesc", "")


def parse_callback(body):
    """Pull the useful bits out of Safaricom's callback JSON."""
    cb = body.get("Body", {}).get("stkCallback", {})
    items = {i.get("Name"): i.get("Value") for i in cb.get("CallbackMetadata", {}).get("Item", [])}
    return {
        "checkout_request_id": cb.get("CheckoutRequestID", ""),
        "result_code": str(cb.get("ResultCode", "")),
        "result_desc": cb.get("ResultDesc", ""),
        "receipt": str(items.get("MpesaReceiptNumber", "") or ""),
        "amount": items.get("Amount"),
    }
