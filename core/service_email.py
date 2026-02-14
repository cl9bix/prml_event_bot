import os
import ssl
import smtplib
import mimetypes
import logging
from pathlib import Path
from email.message import EmailMessage
from email.utils import formataddr
from email.headerregistry import Address
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)



def _safe_filename(name: str, default: str = "ticket") -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in name).strip("_")
    return slug or default

PRML_COLORS = {
    "bg": "#0F1216",
    "card": "#161B22",
    "text": "#E9EEF5",
    "muted": "#AAB4C3",
    "accent": "#FFC400",
    "border": "#242B36",
}


def _build_html(
    user_name: str,
    event_name: str,
    date: str,
    *,
    support_handle: str = "https://t.me/nina_matsyuk"
) -> str:
    c = PRML_COLORS

    return f"""\
<!doctype html>
<html lang="uk">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <meta name="x-apple-disable-message-reformatting" />
  <meta name="format-detection" content="telephone=no,address=no,email=no,date=no,url=no" />
  <meta name="color-scheme" content="dark" />
  <meta name="supported-color-schemes" content="dark" />
  <title>PRML | Квиток</title>

  <style>
    /* Force full-width container on mobile */
    @media (max-width: 620px) {{
      .container {{ width: 100% !important; max-width: 100% !important; }}
      .px {{ padding-left: 12px !important; padding-right: 12px !important; }}
      .cardpad {{ padding: 16px !important; }}
      .innerpad {{ padding: 14px !important; }}

      .h1 {{ font-size: 24px !important; line-height: 1.15 !important; }}
      .name {{
        font-size: 26px !important;
        line-height: 1.05 !important;
        letter-spacing: 0 !important;
        word-break: break-word !important;
        overflow-wrap: anywhere !important;
      }}

      .two-col td {{ display:block !important; width:100% !important; }}
      .statuscell {{ padding-top: 10px !important; text-align:left !important; }}
      .pill {{ display:inline-block !important; }}

      .sp18 {{ height: 12px !important; line-height: 12px !important; }}
    }}
  </style>
</head>

<body style="margin:0;padding:0;background:{c['bg']};font-family:Arial,Helvetica,sans-serif;color:{c['text']};">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
         style="background:{c['bg']};padding:22px 0;margin:0;">
    <tr>
      <td align="center">

        <!-- CONTAINER -->
        <table role="presentation" class="container" width="600" cellspacing="0" cellpadding="0" border="0"
               style="width:600px;max-width:600px;margin:0 auto;">
          <tr>
            <td class="px" style="padding:0 16px;">

              <!-- TOP STRIP -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom:12px;">
                <tr>
                  <td style="border:1px solid {c['border']};background:{c['card']};">
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td style="padding:12px 14px;">
                          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                            <tr>
                              <td style="font-size:12px;letter-spacing:2px;text-transform:uppercase;color:{c['muted']};">
                                PRML EVENTS
                              </td>
                              <td align="right" style="font-size:12px;letter-spacing:2px;text-transform:uppercase;color:{c['muted']};">
                                ОФІЦІЙНИЙ КВИТОК
                              </td>
                            </tr>
                          </table>
                        </td>
                      </tr>
                      <tr>
                        <td style="background:{c['accent']};height:3px;font-size:0;line-height:0;">&nbsp;</td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <!-- MAIN CARD -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                     style="background:{c['card']};border:1px solid {c['border']};">
                <tr>
                  <td class="cardpad" style="padding:18px;">

                    <!-- EVENT TITLE -->
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td class="h1" style="font-size:28px;line-height:1.12;font-weight:800;color:{c['text']};">
                          {event_name}
                        </td>
                      </tr>
                      <tr>
                        <td style="padding-top:10px;font-size:14px;line-height:1.7;color:{c['muted']};">
                          Привіт, <span style="color:{c['text']};font-weight:700;">{user_name}</span>!<br/>
                          Дякуємо за реєстрацію. Твій квиток уже сформовано та додано до цього листа.
                        </td>
                      </tr>
                    </table>

                    <!-- Spacer -->
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr><td class="sp18" height="14" style="height:14px;line-height:14px;font-size:0;">&nbsp;</td></tr>
                    </table>

                    <!-- INNER TICKET -->
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0"
                           style="background:#10151C;border:1px solid {c['border']};">
                      <tr>
                        <td class="innerpad" style="padding:16px;">

                          <!-- Label + Status (mobile-safe stacking) -->
                          <table role="presentation" class="two-col" width="100%" cellspacing="0" cellpadding="0" border="0">
                            <tr>
                              <td style="font-size:12px;letter-spacing:1.6px;text-transform:uppercase;color:{c['muted']};">
                                КВИТОК ДЛЯ:
                              </td>
                              <td class="statuscell" align="right" style="text-align:right;">
                                <span class="pill" style="display:inline-block;background:{c['accent']};color:#111111;font-weight:900;
                                  font-size:12px;letter-spacing:1px;text-transform:uppercase;padding:7px 10px;border:1px solid rgba(0,0,0,.25);">
                                  ПІДТВЕРДЖЕНО
                                </span>
                              </td>
                            </tr>
                          </table>

                          <!-- Big name (won't overflow) -->
                          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                            <tr>
                              <td class="name" style="padding-top:10px;font-size:32px;line-height:1.05;font-weight:900;color:{c['text']};
                                  text-transform:uppercase;word-break:break-word;overflow-wrap:anywhere;">
                                {user_name}
                              </td>
                            </tr>
                          </table>

                          <!-- Date -->
                          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                            <tr>
                              <td style="padding-top:12px;">
                                <div style="font-size:12px;color:{c['muted']};text-transform:uppercase;letter-spacing:1.6px;">
                                  Дата та час
                                </div>
                                <div style="padding-top:6px;font-size:18px;font-weight:900;color:{c['text']};letter-spacing:.2px;">
                                  {date}
                                </div>
                              </td>
                            </tr>
                          </table>

                          <!-- Perforation -->
                          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                            <tr>
                              <td style="padding-top:14px;border-top:1px dashed {c['border']};font-size:0;line-height:0;">
                                &nbsp;
                              </td>
                            </tr>
                          </table>

                        </td>
                      </tr>

                      <!-- Bottom accent strip -->
                      <tr>
                        <td style="background:{c['accent']};height:4px;font-size:0;line-height:0;">&nbsp;</td>
                      </tr>
                    </table>

                    <!-- WHAT NEXT -->
                    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                      <tr>
                        <td style="padding-top:16px;font-size:15px;line-height:1.8;color:{c['text']};">
                          <span style="font-weight:900;">Що далі?</span><br/>
                          • Збережи квиток на телефоні або роздрукуй.<br/>
                          • На вході покажи його організаторам.<br/>
                          • Питання? Напиши нам у Telegram:<br/>
                          <a href="{support_handle}" style="color:{c['accent']};font-weight:900;text-decoration:none;">
                            {support_handle}
                          </a>
                        </td>
                      </tr>
                      <tr>
                        <td style="padding-top:12px;font-size:12px;color:{c['muted']};line-height:1.6;">
                          Це автоматичний лист. Відповідати на нього не потрібно.
                        </td>
                      </tr>
                    </table>

                  </td>
                </tr>
              </table>

              <!-- FOOTER -->
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
                <tr>
                  <td style="padding:16px 0 0 0;text-align:center;font-size:12px;color:{c['muted']};line-height:1.7;">
                    PRML — місце, де навчання формує, спільнота збудовує, а знання застосовуються на практиці.<br/>
                    © PRML
                  </td>
                </tr>
              </table>

            </td>
          </tr>
        </table>

      </td>
    </tr>
  </table>
</body>
</html>
"""



def send_ticket_email(
    to_email: str,
    user_name: str,
    event_name: str,
    date: str,
    ticket_path: str,
    *,
    logo_path: str | None = None,   # опційно: інлайн-логотип, якщо хочеш
    support_handle: str = "https://t.me/nina_matsyuk"
) -> bool:
    logger.info("send_ticket_email: start | to=%s | event=%s", to_email, event_name)

    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    from_email = os.getenv("FROM_EMAIL") or smtp_user

    if not all([smtp_host, smtp_port, smtp_user, smtp_password, from_email]):
        logger.error("send_ticket_email: SMTP env is incomplete")
        return False

    ticket_file = Path(ticket_path)
    if not ticket_file.exists():
        logger.error("send_ticket_email: ticket file not found | path=%s", ticket_path)
        return False

    # MIME для вкладення
    mime_type, _ = mimetypes.guess_type(str(ticket_file))
    if mime_type is None:
        mime_type = "application/octet-stream"
    maintype, subtype = mime_type.split("/", 1)

    # Готуємо лист
    msg = EmailMessage()
    msg["Subject"] = f"PRML Events | Ваш квиток на подію «{event_name}»"
    # щоб виглядало “профі”: ім'я відправника
    msg["From"] = formataddr(("PRML Events", from_email))
    msg["To"] = to_email

    text_fallback = (
        f"Привіт, {user_name}!\n\n"
        f"Твій квиток на подію «{event_name}».\n"
        f"Дата/час: {date}\n\n"
        "Квиток у вкладенні до листа.\n"
        f"Питання? Напиши нам у Telegram: {support_handle}\n\n"
        "PRML"
    )

    msg.set_content(text_fallback)

    html = _build_html(user_name=user_name, event_name=event_name, date=date, support_handle=support_handle)
    msg.add_alternative(html, subtype="html")

    # (Опційно) інлайн логотип через CID — якщо передаси logo_path
    # В HTML я свідомо не вставляв <img>, бо багато клієнтів блокують картинки.
    # Але якщо хочеш — скажи, я вставлю блок з логотипом і CID.
    if logo_path:
        logo_file = Path(logo_path)
        if logo_file.exists():
            logo_mime, _ = mimetypes.guess_type(str(logo_file))
            if logo_mime:
                lm, ls = logo_mime.split("/", 1)
            else:
                lm, ls = "image", "png"
            with open(logo_file, "rb") as lf:
                msg.get_payload()[-1].add_related(  # HTML частина
                    lf.read(),
                    maintype=lm,
                    subtype=ls,
                    cid="prml_logo",
                )
            logger.info("send_ticket_email: attached inline logo | path=%s", logo_path)
        else:
            logger.warning("send_ticket_email: logo not found, skipping | path=%s", logo_path)

    # Вкладення квитка
    filename = f"{_safe_filename(user_name)}_ticket{ticket_file.suffix.lower()}"
    with open(ticket_file, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype=maintype,
            subtype=subtype,
            filename=filename,
        )
    logger.info("send_ticket_email: attached ticket | filename=%s | mime=%s", filename, mime_type)

    # SMTP send
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        logger.info("send_ticket_email: sent OK | to=%s", to_email)
        return True

    except smtplib.SMTPAuthenticationError:
        logger.exception("send_ticket_email: SMTP auth failed (check app password)")
        return False
    except smtplib.SMTPException:
        logger.exception("send_ticket_email: SMTP error")
        return False
    except Exception:
        logger.exception("send_ticket_email: unexpected error")
        return False


# приклад виклику:
# send_ticket_email(
#     "cl9bix.dev@gmail.com",
#     "cl9bix",
#     "Test Event Name",
#     "21.03 / 9:30",
#     "media/tickets/ticket_yuriy_scheffer_21_03_09_30.jpg"
# )
