from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Підправ за потреби (шляхи/координати/шрифти)
TEMPLATE_PATH = Path("media/templates/ticket_template.png")

FONT_BOLD = "static/Unbounded-Bold.ttf"  # Linux
# Для Windows можна так:
# FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"

# Центри (під твій template 1638x2048)
NAME_CENTER_Y = 2000
DATE_CENTER_Y = 2400


def _fit_font(draw: ImageDraw.ImageDraw, text: str, font_path: str, target_width: int,
              max_size: int = 240, min_size: int = 10) -> ImageFont.FreeTypeFont:
    """Підбирає найбільший розмір шрифту, щоб текст вліз у target_width."""
    lo, hi = min_size, max_size
    best = min_size

    while lo <= hi:
        mid = (lo + hi) // 2
        font = ImageFont.truetype(font_path, mid)
        x0, y0, x1, y1 = draw.textbbox((0, 0), text, font=font)
        w = x1 - x0

        if w <= target_width:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1

    return ImageFont.truetype(font_path, best)


def generate_ticket(full_name: str, date_text: str,
                    template_path: Path = TEMPLATE_PATH):
    """
    full_name: "Ніна Мацюк"
    date_text: "21.03 / 9:30" (або будь-який формат, який хочеш показати)
    """
    img = Image.open(template_path).convert("RGBA")
    draw = ImageDraw.Draw(img)

    w, h = img.size
    cx = w // 2

    # 1) Готуємо рядки імені (1-й рядок — ім’я, 2-й — решта)
    parts = full_name.strip().split()
    if len(parts) <= 1:
        name_lines = [full_name.strip().upper()]
    else:
        name_lines = [parts[0].upper(), " ".join(parts[1:]).upper()]

    # 2) Підбираємо шрифт під ширину (щоб довгі прізвища не вилазили)
    max_name_width = int(w * 0.75)
    name_fonts = [
        _fit_font(draw, line, FONT_BOLD, max_name_width)
        for line in name_lines
    ]

    # 3) Рахуємо висоту блоку і центруємо його по вертикалі
    name_bboxes = [draw.textbbox((0, 0), line, font=f) for line, f in zip(name_lines, name_fonts)]
    name_heights = [(b[3] - b[1]) for b in name_bboxes]
    gap = int(0.15 * max(name_heights)) if name_heights else 0  # відступ між рядками

    total_name_h = sum(name_heights) + gap * (len(name_lines) - 1)
    y = NAME_CENTER_Y - total_name_h / 2

    for line, font, line_h in zip(name_lines, name_fonts, name_heights):
        # anchor="mm" = по центру (middle-middle)
        draw.text((cx, y + line_h / 2), line, font=font, fill=(255, 255, 255, 255), anchor="mm")
        y += line_h + gap

    # 4) Дата
    max_date_width = int(w * 0.60)
    date_font = _fit_font(draw, date_text, FONT_BOLD, max_date_width, max_size=140)
    draw.text((cx, DATE_CENTER_Y), date_text, font=date_font, fill=(255, 255, 255, 255), anchor="mm")
    if not full_name:
        raise ValueError("full_name is empty")
    import re
    safe_name = re.sub(r'[^a-zA-Z0-9_]+', '_', f"{full_name}_{date_text}".lower())
    tickets_dir = Path("media/tickets")
    tickets_dir.mkdir(parents=True, exist_ok=True)
    out_path = f"ticket_{safe_name}.png"
    img = img.convert("RGB")
    img.save(tickets_dir / out_path.replace(".png", ".jpg"), format="JPEG", quality=82, optimize=True)
    return out_path.replace(".png", ".jpg")
