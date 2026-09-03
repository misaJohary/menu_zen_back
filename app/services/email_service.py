import logging
from datetime import datetime
from typing import Optional, Sequence, TypedDict

from fastapi_mail import FastMail, MessageSchema, MessageType

from app.configs.email_configs import build_connection_config

logger = logging.getLogger(__name__)


def _get_fastmail() -> Optional[FastMail]:
    conf = build_connection_config()
    if conf is None:
        return None
    return FastMail(conf)


def _format_reserved_at(value: datetime) -> str:
    """Human-friendly rendering for the template.

    Falls back to ISO if `strftime` fails for any reason — we never want a
    rendering quirk to block notification delivery.
    """
    try:
        return value.strftime("%A %d %B %Y · %H:%M")
    except Exception:
        return value.isoformat()


async def send_reservation_request_email(
    *,
    restaurant_email: str,
    restaurant_name: str,
    customer_name: str,
    customer_phone: str,
    reserved_at: datetime,
    party_size: int,
    note: Optional[str] = None,
) -> None:
    """Email the restaurant owner about a new reservation request.

    Silently logs (no raise) when SMTP isn't configured — the reservation has
    already been persisted, so a failed notification shouldn't break the
    customer-facing flow.
    """
    fast_mail = _get_fastmail()
    subject = f"New reservation request — {restaurant_name}"

    if fast_mail is None:
        logger.info(
            "Email skipped (SMTP not configured). To=%s subject=%s",
            restaurant_email,
            subject,
        )
        return

    message = MessageSchema(
        subject=subject,
        recipients=[restaurant_email],
        template_body={
            "restaurant_name": restaurant_name,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "reserved_at_display": _format_reserved_at(reserved_at),
            "party_size": party_size,
            "note": note,
        },
        subtype=MessageType.html,
    )
    try:
        await fast_mail.send_message(message, template_name="reservation_request.html")
    except Exception:
        logger.exception(
            "Failed to send reservation request email to %s", restaurant_email
        )


class DeliveryEmailItem(TypedDict):
    name: str
    quantity: int
    unit_price: Optional[float]
    note: Optional[str]


def _format_scheduled_for(value: Optional[datetime]) -> str:
    if value is None:
        return "As soon as possible"
    try:
        return value.strftime("%A %d %B %Y · %H:%M")
    except Exception:
        return value.isoformat()


async def send_delivery_request_email(
    *,
    restaurant_email: str,
    restaurant_name: str,
    order_id: int,
    customer_name: str,
    customer_phone: str,
    delivery_address: str,
    delivery_notes: Optional[str],
    scheduled_for: Optional[datetime],
    total_amount: Optional[float],
    items: Sequence[DeliveryEmailItem],
) -> None:
    """Email the restaurant owner about a new delivery order from a customer.

    Same fail-soft behavior as the reservation email: missing SMTP config
    becomes a logged no-op, and SMTP failures don't bubble up to the request.
    """
    fast_mail = _get_fastmail()
    subject = f"New delivery order #{order_id} — {restaurant_name}"

    if fast_mail is None:
        logger.info(
            "Email skipped (SMTP not configured). To=%s subject=%s",
            restaurant_email,
            subject,
        )
        return

    message = MessageSchema(
        subject=subject,
        recipients=[restaurant_email],
        template_body={
            "restaurant_name": restaurant_name,
            "order_id": order_id,
            "customer_name": customer_name,
            "customer_phone": customer_phone,
            "delivery_address": delivery_address,
            "delivery_notes": delivery_notes,
            "scheduled_for_display": _format_scheduled_for(scheduled_for),
            "total_amount": total_amount,
            "items": list(items),
        },
        subtype=MessageType.html,
    )
    try:
        await fast_mail.send_message(message, template_name="delivery_request.html")
    except Exception:
        logger.exception(
            "Failed to send delivery request email to %s", restaurant_email
        )
