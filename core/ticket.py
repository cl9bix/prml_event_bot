import uuid
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFont

from core.models import Ticket, Event, TgUser, Payment

DEFAULT_TEMPLATE_REL = "templates/ex.png"  # file must exist: MEDIA_ROOT/templates/ex.png


def _load_font(size: int) -> ImageFont.ImageFont:
    try:
        import PIL
        pil_fonts = Path(PIL.__file__).resolve().parent / "fonts"
        return ImageFont.truetype(str(pil_fonts / "DejaVuSans.ttf"), size)
    except Exception:
        return ImageFont.load_default()


def _safe_open_template(event: Event) -> Image.Image:
    """
    Priority:
    1) event.ticket_template if реально існує
    2) MEDIA_ROOT/templates/ex.png
    3) fallback: пустий біленький
    """
    # 1) event template
    try:
        if event.ticket_template and getattr(event.ticket_template, "path", None):
            p = Path(event.ticket_template.path)
            if p.exists():
                return Image.open(p).convert("RGBA")
    except Exception:
        pass

    # 2) default ex.png
    try:
        media_root = Path(getattr(settings, "MEDIA_ROOT", ""))  # може бути ''
        default_path = media_root / DEFAULT_TEMPLATE_REL
        if default_path.exists():
            return Image.open(default_path).convert("RGBA")
    except Exception:
        pass

    # 3) fallback
    return Image.new("RGBA", (1600, 900), (20, 10, 40, 255))


def generate_ticket(event: Event, user: TgUser, payment: Payment) -> Ticket:
    base = _safe_open_template(event)
    draw = ImageDraw.Draw(base)
    W, H = base.size

    font_title = _load_font(max(34, int(H * 0.075)))
    font_name = _load_font(max(26, int(H * 0.055)))
    font_small = _load_font(max(20, int(H * 0.040)))

    title = (event.title or "").strip()
    name = (user.full_name or "").strip()
    date_str = event.start_at.strftime("%d.%m.%Y %H:%M") if event.start_at else ""
    code = f"ID: {payment.id}"

    def xy(xp: float, yp: float) -> tuple[int, int]:
        return int(W * xp), int(H * yp)

    def text_shadow(pos, text, font, fill=(255, 255, 255, 255)):
        if not text:
            return
        x, y = pos
        draw.text((x + 3, y + 3), text, font=font, fill=(0, 0, 0, 160))
        draw.text((x, y), text, font=font, fill=fill)

    text_shadow(xy(0.08, 0.18), title, font_title)
    text_shadow(xy(0.08, 0.30), name, font_name)
    text_shadow(xy(0.08, 0.40), date_str, font_small)
    text_shadow(xy(0.08, 0.50), code, font_small, fill=(230, 230, 230, 255))

    token = uuid.uuid4().hex

    buf = BytesIO()
    base.save(buf, format="PNG", optimize=True)
    buf.seek(0)

    ticket = Ticket(user=user, event=event, payment=payment, token=token)
    ticket.image.save(f"ticket_{token}.png", ContentFile(buf.read()), save=True)
    return ticket
