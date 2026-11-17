"""Send one real password-reset email through the configured SMTP (SES).

Run it once SMTP_USER/SMTP_PASS exist, before the redeploy:

    set -a && . ~/.config/syncfit/local.env && set +a
    PYTHONPATH=".:../syncfit-contracts/python:../syncfit-core:../syncfit-simulator/py:../syncfit-database:../syncfit-ai-reasoning" \
        python3 scripts/check_smtp.py [destino]

Default destination is the SES mailbox simulator, which accepts mail even while
the account is in the sandbox and creates no data in the app.
"""

from __future__ import annotations

import sys

from app.config import settings
from app.services import mailer

SIMULATOR = "success@simulator.amazonses.com"


def main() -> int:
    to = sys.argv[1] if len(sys.argv) > 1 else SIMULATOR
    missing = [name for name, value in (
        ("SMTP_HOST", settings.smtp_host),
        ("SMTP_FROM", settings.smtp_from),
        ("SMTP_USER", settings.smtp_user),
        ("SMTP_PASS", settings.smtp_password),
    ) if not value]
    if missing:
        print("Faltan variables:", ", ".join(missing))
        return 2
    mailer.send_password_reset(to=to, name="Prueba SMTP", link=f"{settings.app_base_url}/recuperar/?token=prueba", language="ES")
    print(f"OK: correo aceptado por {settings.smtp_host}:{settings.smtp_port} para {to}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
