# # import logging
# # import os
# # import asyncio
# # import time
# # from typing import Dict, Any, Optional
# # from urllib.parse import quote
# #
# # import requests
# # from telegram import (
# #     Update,
# #     InlineKeyboardMarkup,
# #     InlineKeyboardButton,
# # )
# # from telegram.ext import (
# #     Application,
# #     CommandHandler,
# #     MessageHandler,
# #     CallbackQueryHandler,
# #     ConversationHandler,
# #     ContextTypes,
# #     filters,
# # )
# # from telegram.constants import ChatAction
# #
# #
# # # ================== НАЛАШТУВАННЯ ===================
# #
# # TELEGRAM_TOKEN = os.getenv("BOT_TOKEN",'8299398757:AAHvOZBKNbsVogB7X3jILQqXGUur89rT4rI')
# # DJANGO_BASE_URL = os.getenv("DJANGO_BASE_URL", "http://localhost:8000")
# #
# # API_CHECK_USER = f"{DJANGO_BASE_URL}/api/tg/check_user/"
# # API_EVENTS_LIST = f"{DJANGO_BASE_URL}/api/events/"
# # API_CREATE_PAYMENT = f"{DJANGO_BASE_URL}/api/payments/create/"
# # API_CREATE_PAYMENT_LINK = f"{DJANGO_BASE_URL}/api/payments/create/payment/link"
# # API_CHECK_PAYMENT = f"{DJANGO_BASE_URL}/api/payments/check/"
# # API_CHECK_MONOBANK_PAYMENT = f"{DJANGO_BASE_URL}/api/payments/monobank/check"
# # API_GET_TICKET = f"{DJANGO_BASE_URL}/api/tickets/get/"
# # API_GET_PROMO_VALUE = f"{DJANGO_BASE_URL}/api/promocode/data/get/"
# # API_USER_TICKETS = f"{DJANGO_BASE_URL}/api/tickets/my/"
# # API_CONFIRM_MONO = f"{DJANGO_BASE_URL}/api/payments/confirm_monobank/"
# # API_PAYMENTS_CONFIG = f'{DJANGO_BASE_URL}/api/payments/config/'
# # API_PAYMENTS_HISTORY = f'{DJANGO_BASE_URL}/api/payments/history/'
# #
# # # Monobank
# # MONO_TOKEN = os.getenv("MONO_TOKEN", "")
# # MONO_CARD = os.getenv("MONOBANK_CARD", "0000 0000 0000 0000")
# # MONO_CLIENT_INFO_URL = "https://api.monobank.ua/personal/client-info"
# # MONO_STATEMENT_URL = "https://api.monobank.ua/personal/statement/{account}/{from_date}/{to_date}"
# # MONO_DAYS_LOOKBACK = int(os.getenv("MONOBANK_DAYS_LOOKBACK", "3"))
# #
# # # Conversation states
# # CHOOSING_EVENT, REG_NAME, REG_AGE, REG_PHONE, REG_EMAIL, ASK_PROMO, ENTER_PROMO, WAITING_PAYMENT, WAITING_GROUP = range(9)
# #
# #
# # logging.basicConfig(
# #     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
# #     level=logging.INFO,
# # )
# # logger = logging.getLogger(__name__)
# #
# #
# #
# # API_CHECK_MONOBANK_PAYMENT = f"{DJANGO_BASE_URL}/api/payments/monobank/check"
# #
# # def api_get_json(method: str, url: str, **kwargs) -> Dict[str, Any]:
# #     try:
# #         resp = requests.request(method, url, timeout=10, **kwargs)
# #
# #         # якщо бек повернув json навіть на 400 — віддай його в лог і в відповідь
# #         content_type = resp.headers.get("Content-Type", "")
# #         if resp.status_code >= 400:
# #             try:
# #                 data = resp.json()
# #             except Exception:
# #                 data = {"detail": resp.text[:2000]}
# #             logger.error("API %s %s -> %s | %s", method, url, resp.status_code, data)
# #             return {"ok": False, "status_code": resp.status_code, "error": data}
# #
# #         return resp.json()
# #
# #     except Exception as e:
# #         logger.exception("API error: %s", e)
# #         return {"ok": False, "error": str(e)}
# #
# #
# # def check_payment_monobank(payment_id: int) -> Dict[str, Any]:
# #     return api_get_json(
# #         "GET",
# #         API_CHECK_MONOBANK_PAYMENT,
# #         params={"payment_id": payment_id}
# #     )
# #
# #
# #
# #
# # check_payment_monobank = check_payment_monobank(payment_id=71)
# # print(check_payment_monobank)
#
#
#
# from __future__ import annotations
#
# from pathlib import Path
# from PIL import Image, ImageDraw, ImageFont
#
#
# # Підправ за потреби (шляхи/координати/шрифти)
# TEMPLATE_PATH = Path("media/templates/ticket_template.png")
# OUT_PATH = Path("ticket_out.png")
#
# FONT_BOLD = "static/Unbounded-Bold.ttf"  # Linux
# # Для Windows можна так:
# # FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"
#
# # Центри (під твій template 1638x2048)
# NAME_CENTER_Y = 2000
# DATE_CENTER_Y = 2400
#
#
# def _fit_font(draw: ImageDraw.ImageDraw, text: str, font_path: str, target_width: int,
#               max_size: int = 240, min_size: int = 10) -> ImageFont.FreeTypeFont:
#     """Підбирає найбільший розмір шрифту, щоб текст вліз у target_width."""
#     lo, hi = min_size, max_size
#     best = min_size
#
#     while lo <= hi:
#         mid = (lo + hi) // 2
#         font = ImageFont.truetype(font_path, mid)
#         x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
#         w = x1 - x0
#
#         if w <= target_width:
#             best = mid
#             lo = mid + 1
#         else:
#             hi = mid - 1
#
#     return ImageFont.truetype(font_path, best)
#
#
# def generate_ticket(full_name: str, date_text: str,
#                     template_path: Path = TEMPLATE_PATH)
#
#     """
#     full_name: "Ніна Мацюк"
#     date_text: "21.03 / 9:30" (або будь-який формат, який хочеш показати)
#     """
#     img = Image.open(template_path).convert("RGBA")
#     draw = ImageDraw.Draw(img)
#
#     w, h = img.size
#     cx = w // 2
#
#     # 1) Готуємо рядки імені (1-й рядок — ім’я, 2-й — решта)
#     parts = full_name.strip().split()
#     if len(parts) <= 1:
#         name_lines = [full_name.strip().upper()]
#     else:
#         name_lines = [parts[0].upper(), " ".join(parts[1:]).upper()]
#
#     # 2) Підбираємо шрифт під ширину (щоб довгі прізвища не вилазили)
#     max_name_width = int(w * 0.75)
#     name_fonts = [
#         _fit_font(draw, line, FONT_BOLD, max_name_width)
#         for line in name_lines
#     ]
#
#     # 3) Рахуємо висоту блоку і центруємо його по вертикалі
#     name_bboxes = [draw.textbbox((0, 0), line, font=f) for line, f in zip(name_lines, name_fonts)]
#     name_heights = [(b[3] - b[1]) for b in name_bboxes]
#     gap = int(0.15 * max(name_heights)) if name_heights else 0  # відступ між рядками
#
#     total_name_h = sum(name_heights) + gap * (len(name_lines) - 1)
#     y = NAME_CENTER_Y - total_name_h / 2
#
#     for line, font, line_h in zip(name_lines, name_fonts, name_heights):
#         # anchor="mm" = по центру (middle-middle)
#         draw.text((cx, y + line_h / 2), line, font=font, fill=(255, 255, 255, 255), anchor="mm")
#         y += line_h + gap
#
#     # 4) Дата
#     max_date_width = int(w * 0.60)
#     date_font = _fit_font(draw, date_text, FONT_BOLD, max_date_width, max_size=140)
#     draw.text((cx, DATE_CENTER_Y), date_text, font=date_font, fill=(255, 255, 255, 255), anchor="mm")
#     out_path = f'ticket_{full_name.lower().replace(" ","_")}.png'
#     return out_path
#
#
# if __name__ == "__main__":
#     # приклад
#     result = generate_ticket("Georg Scheffer", "11.03 / 12:30")
#     print(f"Saved: {result}")
