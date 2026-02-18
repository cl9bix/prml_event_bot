# core/google_sheet.py
import os
import json
import base64
import logging
from datetime import datetime
from typing import Dict, Any, Optional

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def _load_service_account_info() -> dict:
    """
    1) GOOGLE_CREDS_B64 (base64 of json)
    2) GOOGLE_CREDS_PATH (path to json file)
    """
    b64 = (os.getenv("GOOGLE_CREDS_B64") or "").strip()
    if b64:
        try:
            raw = base64.b64decode(b64).decode("utf-8")
            info = json.loads(raw)
            return info
        except Exception as e:
            raise RuntimeError(f"GOOGLE_CREDS_B64 decode failed: {e}")

    path = (os.getenv("GOOGLE_CREDS_PATH") or "").strip()
    if path:
        if not os.path.exists(path):
            raise RuntimeError(f"GOOGLE_CREDS_PATH not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    raise RuntimeError("Set GOOGLE_CREDS_B64 or GOOGLE_CREDS_PATH")


def _get_gspread_client() -> gspread.Client:
    info = _load_service_account_info()

    # важливо: private_key має бути з \n, не з реальними переносами
    pk = info.get("private_key", "")
    if "BEGIN PRIVATE KEY" not in pk or "END PRIVATE KEY" not in pk:
        raise RuntimeError("private_key missing/invalid in creds json")

    credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(credentials)


def send_registration_to_google_sheets(data: Dict[str, Any]) -> None:
    sheet_id = (os.getenv("GOOGLE_SHEET_ID") or "").strip()
    if not sheet_id:
        raise RuntimeError("GOOGLE_SHEET_ID not set")

    client = _get_gspread_client()
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
        data.get("paid_at", "") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ]

    sheet.append_row(row, value_input_option="USER_ENTERED")
    logger.info("Google Sheets: saved | tg_id=%s payment_id=%s", data.get("tg_id"), data.get("payment_id"))
