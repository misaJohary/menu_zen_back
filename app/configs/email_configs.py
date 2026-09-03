import os
from pathlib import Path
from typing import Optional

from fastapi_mail import ConnectionConfig
from pydantic_settings import BaseSettings


TEMPLATE_FOLDER = Path(__file__).resolve().parent.parent / "email_templates"


class EmailSettings(BaseSettings):
    mail_username: Optional[str] = os.getenv("MAIL_USERNAME")
    mail_password: Optional[str] = os.getenv("MAIL_PASSWORD")
    mail_from: Optional[str] = os.getenv("MAIL_FROM")
    mail_from_name: Optional[str] = os.getenv("MAIL_FROM_NAME", "Menu Zen")
    mail_server: Optional[str] = os.getenv("MAIL_SERVER")
    mail_port: int = int(os.getenv("MAIL_PORT", "587"))
    mail_starttls: bool = os.getenv("MAIL_STARTTLS", "true").lower() == "true"
    mail_ssl_tls: bool = os.getenv("MAIL_SSL_TLS", "false").lower() == "true"
    mail_use_credentials: bool = os.getenv("MAIL_USE_CREDENTIALS", "true").lower() == "true"
    mail_validate_certs: bool = os.getenv("MAIL_VALIDATE_CERTS", "true").lower() == "true"

    class Config:
        env_file = ".env"


email_settings = EmailSettings()


def build_connection_config() -> Optional[ConnectionConfig]:
    """Return a `ConnectionConfig` when SMTP credentials are configured.

    Returns None when essential settings are missing — the email service
    treats that as a no-op send (logs only) so dev environments don't fail.
    """
    required = (
        email_settings.mail_username,
        email_settings.mail_password,
        email_settings.mail_from,
        email_settings.mail_server,
    )
    if any(v in (None, "") for v in required):
        return None
    return ConnectionConfig(
        MAIL_USERNAME=email_settings.mail_username,
        MAIL_PASSWORD=email_settings.mail_password,
        MAIL_FROM=email_settings.mail_from,
        MAIL_FROM_NAME=email_settings.mail_from_name,
        MAIL_SERVER=email_settings.mail_server,
        MAIL_PORT=email_settings.mail_port,
        MAIL_STARTTLS=email_settings.mail_starttls,
        MAIL_SSL_TLS=email_settings.mail_ssl_tls,
        USE_CREDENTIALS=email_settings.mail_use_credentials,
        VALIDATE_CERTS=email_settings.mail_validate_certs,
        TEMPLATE_FOLDER=TEMPLATE_FOLDER,
    )
