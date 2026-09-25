import asyncio
import smtplib
from email.message import EmailMessage

import httpx

from app.core.config import settings


def notification_status() -> dict[str, bool]:
    return {
        "telegram": bool(settings.telegram_bot_token and settings.telegram_chat_id),
        "webhook": bool(settings.alert_webhook_url),
        "email": bool(
            settings.smtp_host
            and settings.smtp_username
            and settings.smtp_password
            and settings.alert_email_from
            and settings.alert_email_to
        ),
    }


async def _telegram(message: str) -> None:
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            url, json={"chat_id": settings.telegram_chat_id, "text": message}
        )
        response.raise_for_status()


async def _webhook(event: str, payload: dict[str, object]) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            settings.alert_webhook_url, json={"event": event, **payload}
        )
        response.raise_for_status()


def _email(subject: str, message: str) -> None:
    email = EmailMessage()
    email["Subject"] = subject
    email["From"] = settings.alert_email_from
    email["To"] = settings.alert_email_to
    email.set_content(message)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(email)


async def send_alert(event: str, endpoint_name: str, detail: str) -> list[str]:
    """Deliver alerts independently so one failed channel cannot block the others."""
    message = f"PulseWatch {event.upper()}\n{endpoint_name}\n{detail}"
    tasks: list[tuple[str, object]] = []
    status = notification_status()
    if status["telegram"]:
        tasks.append(("telegram", _telegram(message)))
    if status["webhook"]:
        tasks.append(
            ("webhook", _webhook(event, {"service": endpoint_name, "detail": detail}))
        )
    if status["email"]:
        tasks.append(
            (
                "email",
                asyncio.to_thread(
                    _email, f"PulseWatch: {event} — {endpoint_name}", message
                ),
            )
        )
    if not tasks:
        return []
    results = await asyncio.gather(*(task for _, task in tasks), return_exceptions=True)
    return [
        name
        for (name, _), result in zip(tasks, results, strict=True)
        if isinstance(result, Exception)
    ]
