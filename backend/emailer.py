import os
import re
import smtplib
from email.message import EmailMessage

# Отправка писем через Gmail SMTP.
# В backend/.env нужны две строки:
#   SMTP_EMAIL=твой_адрес@gmail.com
#   SMTP_PASSWORD=пароль приложения (16 символов, НЕ обычный пароль от почты)
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(address: str) -> bool:
    return bool(EMAIL_PATTERN.match(address or ""))


def send_email(to: str, subject: str, body: str):
    """Отправляет письмо. Возвращает (True, None) или (False, текст ошибки)"""
    sender = os.getenv("SMTP_EMAIL")
    password = os.getenv("SMTP_PASSWORD")
    if not sender or not password:
        return False, "Почта не настроена: в .env нет SMTP_EMAIL или SMTP_PASSWORD"

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls()  # шифруем соединение
            server.login(sender, password)
            server.send_message(msg)
        return True, None
    except smtplib.SMTPAuthenticationError:
        return False, "Gmail не принял логин или пароль приложения"
    except (smtplib.SMTPException, OSError) as e:
        print("Ошибка отправки письма:", e)
        return False, "Не удалось отправить письмо"
