"""SMTP submission for transcript emails. Credentials are read only by this module."""
from dataclasses import dataclass
from email.message import EmailMessage
import os
import re
import smtplib
import ssl


class EmailNotConfigured(Exception):
    pass


@dataclass(frozen=True)
class SMTPSettings:
    host: str
    port: int
    username: str
    password: str
    from_address: str
    security: str

    @classmethod
    def from_env(cls):
        host = os.getenv('SMTP_HOST', '').strip()
        from_address = os.getenv('SMTP_FROM_ADDRESS', '').strip()
        security = os.getenv('SMTP_SECURITY', 'starttls').strip().lower()
        if not host or not from_address or any(ord(char) < 33 for char in host + from_address) or not _valid_address(from_address):
            raise EmailNotConfigured()
        try:
            port = int(os.getenv('SMTP_PORT', '587'))
        except ValueError:
            raise EmailNotConfigured() from None
        if not (1 <= port <= 65535) or security not in {'ssl', 'starttls'}:
            raise EmailNotConfigured()
        return cls(host, port, os.getenv('SMTP_USERNAME', ''), os.getenv('SMTP_PASSWORD', ''), from_address, security)


def _valid_address(value):
    return bool(re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", value)) and '..' not in value


class SMTPEmailSender:
    def __init__(self, settings=None, timeout=15):
        self.settings = settings or SMTPSettings.from_env()
        self.timeout = timeout

    def send(self, *, recipient, subject, body, attachment=None, filename=None):
        message = EmailMessage()
        message['To'] = recipient
        message['From'] = self.settings.from_address
        message['Subject'] = subject
        message.set_content(body)
        if attachment is not None:
            message.add_attachment(attachment.encode('utf-8'), maintype='text', subtype='plain', filename=filename)
        context = ssl.create_default_context()
        smtp_class = smtplib.SMTP_SSL if self.settings.security == 'ssl' else smtplib.SMTP
        with smtp_class(self.settings.host, self.settings.port, timeout=self.timeout, **({'context': context} if self.settings.security == 'ssl' else {})) as smtp:
            if self.settings.security == 'starttls':
                smtp.starttls(context=context)
            if self.settings.username or self.settings.password:
                smtp.login(self.settings.username, self.settings.password)
            smtp.send_message(message)
