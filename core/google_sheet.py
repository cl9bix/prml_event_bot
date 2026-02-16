import os
import logging
from typing import Dict
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials


logger = logging.getLogger(__name__)


SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def send_registration_to_google_sheets(data: Dict) -> None:
    """
    Зберігає реєстрацію в Google Sheets
    Очікує data:
    {
        "tg_id": ...,
        "username": ...,
        "full_name": ...,
        "age": ...,
        "phone": ...,
        "email": ...
    }
    """

    try:
        creds_path = 'creds/prml-event-bot-ebdc66bc35f3.json'
        sheet_id = os.getenv("GOOGLE_SHEET_ID") or '19l9P2AvR_T5Erui1yYqL483xSTfdnvUIVgwAGvCgSp8'

        if not creds_path or not sheet_id:
            logger.error("Google Sheets env variables not configured")
            return

        credentials = Credentials.from_service_account_file(
            creds_path,
            scopes=SCOPES,
        )

        client = gspread.authorize(credentials)

        sheet = client.open_by_key(sheet_id).sheet1

        row = [
            str(data.get("tg_id", "")),
            data.get("username", ""),
            data.get("full_name", ""),
            str(data.get("age", "")),
            data.get("phone", ""),
            data.get("email", ""),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ]

        sheet.append_row(row, value_input_option="USER_ENTERED")

        logger.info(
            "Google Sheets: registration saved | tg_id=%s",
            data.get("tg_id"),
        )

    except Exception as e:
        logger.exception("Google Sheets error | %s", e)



