import os
import base64
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES: List[str] = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _get_credentials() -> Credentials:
    """
    Пріоритет:
    1) GOOGLE_CREDS_B64  (base64(JSON service account))
    2) GOOGLE_CREDS_PATH (шлях до json файлу)
    """
    b64 = (os.getenv("GOOGLE_CREDS_B64") or "").strip()
    if b64:
        try:
            info = json.loads(base64.b64decode(b64).decode("utf-8"))
            return Credentials.from_service_account_info(info, scopes=SCOPES)
        except Exception as e:
            logger.exception("Invalid GOOGLE_CREDS_B64 | %s", e)
            raise

    creds_path = (os.getenv("GOOGLE_CREDS_PATH") or "").strip()
    if creds_path:
        if not os.path.exists(creds_path):
            raise FileNotFoundError(f"GOOGLE_CREDS_PATH not found: {creds_path}")
        return Credentials.from_service_account_file(creds_path, scopes=SCOPES)

    raise RuntimeError("Google creds not configured. Set GOOGLE_CREDS_B64 or GOOGLE_CREDS_PATH")


def send_registration_to_google_sheets(data: Dict[str, Any]) -> None:
    """
    Додає рядок в Google Sheets.
    Очікує мінімум:
    {
      "tg_id": ...,
      "username": ...,
      "full_name": ...,
      "age": ...,
      "phone": ...,
      "email": ...
    }

    Також можна передати додаткові поля:
    event, payment_id, paid_at
    """
    sheet_id = (os.getenv("GOOGLE_SHEET_ID") or "").strip()
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID not set")

    credentials = _get_credentials()
    client = gspread.authorize(credentials)

    sheet = client.open_by_key(sheet_id).sheet1

    row = [
        str(data.get("tg_id", "")),
        str(data.get("username", "")),
        str(data.get("full_name", "")),
        str(data.get("age", "")),
        str(data.get("phone", "")),
        str(data.get("email", "")),
        str(data.get("event", "")),
        str(data.get("payment_id", "")),
        str(data.get("paid_at", "")),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    ]

    sheet.append_row(row, value_input_option="USER_ENTERED")

    logger.info("Google Sheets: saved | tg_id=%s | payment_id=%s", data.get("tg_id"), data.get("payment_id"))
