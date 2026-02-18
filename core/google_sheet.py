import os
import json
import base64
import logging
from datetime import datetime
from typing import Dict, Any

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

load_dotenv()
logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _get_credentials() -> Credentials:
    b64 = os.getenv("GOOGLE_CREDS_B64", "").strip()
    if not b64:
        raise RuntimeError("GOOGLE_CREDS_B64 not set")

    try:
        info = json.loads(base64.b64decode(b64).decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"GOOGLE_CREDS_B64 decode error: {e}")

    if "private_key" not in info or "client_email" not in info:
        raise RuntimeError("Bad creds JSON: missing private_key/client_email")

    return Credentials.from_service_account_info(info, scopes=SCOPES)


def send_registration_to_google_sheets(data: Dict[str, Any]) -> None:
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID not set")

    credentials = _get_credentials()
    client = gspread.authorize(credentials)
    sheet = client.open_by_key(sheet_id).sheet1

    row = [
        str(data.get("tg_id", "")),
        data.get("username", "") or "",
        data.get("full_name", "") or "",
        str(data.get("age", "") or ""),
        data.get("phone", "") or "",
        data.get("email", "") or "",
        data.get("event", "") or "",
        str(data.get("payment_id", "") or ""),
        data.get("paid_at", "") or "",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ]

    sheet.append_row(row, value_input_option="USER_ENTERED")
    logger.info("Google Sheets: saved | tg_id=%s", data.get("tg_id"))
