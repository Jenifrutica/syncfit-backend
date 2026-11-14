"""Transactional email over SMTP (AWS SES in production)."""

from __future__ import annotations

import html
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from ..config import settings


class MailNotConfigured(RuntimeError):
    """SMTP is missing: the caller must surface it instead of losing the mail."""


def is_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from)


_SUBJECT = {
    "ES": "Recupera tu contraseña de SyncFit",
    "EN": "Reset your SyncFit password",
    "ZH": "重置你的 SyncFit 密码",
}

_INTRO = {
    "ES": "Hola {name}, recibimos una solicitud para cambiar tu contraseña.",
    "EN": "Hi {name}, we received a request to change your password.",
    "ZH": "{name}，你好：我们收到了修改密码的请求。",
}

_ACTION = {
    "ES": "Crea una contraseña nueva",
    "EN": "Choose a new password",
    "ZH": "设置新密码",
}

_EXPIRY = {
    "ES": "El enlace caduca en {minutes} minutos y solo se puede usar una vez.",
    "EN": "The link expires in {minutes} minutes and can only be used once.",
    "ZH": "链接将在 {minutes} 分钟后失效，且只能使用一次。",
}

_IGNORE = {
    "ES": "Si no fuiste tú, ignora este correo: tu contraseña sigue igual.",
    "EN": "If this wasn't you, ignore this email: your password stays the same.",
    "ZH": "如果不是你本人操作，请忽略此邮件：密码不会改变。",
}


def _copy(language: str, name: str, link: str, minutes: int) -> tuple[str, str, str]:
    code = language.upper() if language.upper() in _SUBJECT else "EN"
    subject = _SUBJECT[code]
    intro = _INTRO[code].format(name=name)
    action = _ACTION[code]
    expiry = _EXPIRY[code].format(minutes=minutes)
    ignore = _IGNORE[code]
    text = f"{intro}\n\n{action}: {link}\n\n{expiry}\n{ignore}\n"
    body = f"""\
<!doctype html>
<html lang="{code.lower()}">
  <body style="margin:0;background:#f6f1e8;padding:32px 16px;font-family:Arial,Helvetica,sans-serif;color:#1f2430;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;margin:0 auto;background:#ffffff;border-radius:16px;padding:32px;">
      <tr><td>
        <p style="margin:0 0 8px;font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#7a6f5f;">SyncFit Edge</p>
        <h1 style="margin:0 0 16px;font-size:24px;line-height:1.25;">{html.escape(subject)}</h1>
        <p style="margin:0 0 16px;font-size:16px;line-height:1.5;">{html.escape(intro)}</p>
        <p style="margin:0 0 24px;">
          <a href="{html.escape(link, quote=True)}" style="display:inline-block;background:#1f6f4a;color:#ffffff;text-decoration:none;font-weight:bold;padding:14px 22px;border-radius:999px;">{html.escape(action)}</a>
        </p>
        <p style="margin:0 0 8px;font-size:14px;line-height:1.5;color:#5c5548;">{html.escape(expiry)}</p>
        <p style="margin:0;font-size:14px;line-height:1.5;color:#5c5548;">{html.escape(ignore)}</p>
      </td></tr>
    </table>
  </body>
</html>
"""
    return subject, text, body


def send_password_reset(*, to: str, name: str, link: str, language: str = "ES") -> None:
    """Send the reset link; raises MailNotConfigured if SMTP is absent."""
    if not is_configured():
        raise MailNotConfigured("SMTP_HOST and SMTP_FROM are required")
    subject, text, body = _copy(language, name, link, settings.password_reset_minutes)
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr(("SyncFit Edge", settings.smtp_from))
    message["To"] = to
    message.set_content(text)
    message.add_alternative(body, subtype="html")

    if settings.smtp_port == 465:
        server: smtplib.SMTP = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15)
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
    with server:
        if settings.smtp_port != 465:
            server.starttls()
        if settings.smtp_user and settings.smtp_password:
            server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(message)


__all__ = ["MailNotConfigured", "is_configured", "send_password_reset"]
