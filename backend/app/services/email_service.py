"""
Email delivery service.

Design decisions worth knowing:

1. **Sending never breaks the caller.** send_email() returns bool and swallows
   its own exceptions. A dead SMTP server should not turn a password-reset
   request into a 500 - the user would retry and get the same failure. The
   caller decides what to tell the user.

2. **It runs in a thread.** smtplib is blocking. Calling it directly from an
   async endpoint would stall the event loop for the duration of the SMTP
   handshake - on a slow relay that is seconds, during which the whole worker
   serves nothing. FastAPI's BackgroundTasks handles this.

3. **It fails loudly in production, quietly in dev.** If SMTP is unconfigured
   while ENVIRONMENT=production, that is a misconfiguration someone needs to
   see in the logs immediately - password reset is silently broken otherwise.
   In development it just logs at debug and moves on.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

_FROM_NAME = "ReturnIQ"


def is_configured() -> bool:
    """True if enough SMTP settings exist to attempt a send."""
    return bool(settings.SMTP_HOST and settings.SMTP_FROM)


def send_email(
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> bool:
    """
    Send an email. Returns True on success, False on any failure.

    Never raises. See module docstring for why.
    """
    if not is_configured():
        if settings.ENVIRONMENT == "production":
            logger.error(
                "SMTP is not configured but ENVIRONMENT=production. "
                "Email to %s was NOT sent. Password reset and invitations are "
                "silently broken until SMTP_HOST and SMTP_FROM are set.",
                to,
            )
        else:
            logger.info("SMTP not configured (dev) - would have emailed %s: %s", to, subject)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((_FROM_NAME, settings.SMTP_FROM))
    msg["To"] = to
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    try:
        context = ssl.create_default_context()

        if settings.SMTP_PORT == 465:
            # Implicit TLS
            with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT,
                                  context=context, timeout=15) as server:
                if settings.SMTP_USER:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)
        else:
            # STARTTLS (port 587, the common case for SES/SendGrid/Postmark)
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                if settings.SMTP_USER:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)

        logger.info("Email sent to %s: %s", to, subject)
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed - check SMTP_USER / SMTP_PASSWORD")
        return False
    except smtplib.SMTPException as exc:
        logger.error("SMTP error sending to %s: %s", to, exc)
        return False
    except OSError as exc:
        # Connection refused, DNS failure, timeout
        logger.error("Could not reach SMTP host %s: %s", settings.SMTP_HOST, exc)
        return False


# ── Templates ────────────────────────────────────────────────────────────────
# Plain, functional HTML. Deliberately no external images or CSS files: mail
# clients block remote content by default, and a broken layout in a security
# email erodes trust at exactly the wrong moment.

_WRAPPER = """\
<!DOCTYPE html>
<html><body style="margin:0;padding:24px;background:#f8fafc;
font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0f172a;">
  <div style="max-width:520px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;
  border-radius:12px;padding:32px;">
    <div style="font-size:18px;font-weight:600;color:#4f46e5;margin-bottom:24px;">ReturnIQ</div>
    {content}
    <hr style="border:none;border-top:1px solid #e2e8f0;margin:28px 0 16px;">
    <div style="font-size:12px;color:#94a3b8;line-height:1.5;">
      Kalman Consultancy Services<br>
      This is an automated message - please do not reply to it.
    </div>
  </div>
</body></html>"""


def send_password_reset(to: str, token: str, reset_base_url: str) -> bool:
    link = f"{reset_base_url.rstrip('/')}/reset-password?token={token}"

    text = (
        f"Someone requested a password reset for your ReturnIQ account.\n\n"
        f"Reset your password:\n{link}\n\n"
        f"This link expires in 1 hour and can only be used once.\n\n"
        f"If you didn't request this, you can ignore this email - your password "
        f"has not been changed."
    )

    html = _WRAPPER.format(content=f"""
      <div style="font-size:16px;font-weight:600;margin-bottom:12px;">Reset your password</div>
      <p style="font-size:14px;line-height:1.6;color:#475569;margin:0 0 24px;">
        Someone requested a password reset for your ReturnIQ account.
      </p>
      <a href="{link}" style="display:inline-block;background:#4f46e5;color:#ffffff;
      text-decoration:none;padding:11px 22px;border-radius:8px;font-size:14px;font-weight:600;">
        Reset password</a>
      <p style="font-size:13px;color:#94a3b8;margin:24px 0 0;line-height:1.6;">
        This link expires in <strong>1 hour</strong> and can only be used once.<br>
        If you didn't request this, you can ignore this email - your password has not been changed.
      </p>""")

    return send_email(to, "Reset your ReturnIQ password", text, html)


def send_team_invitation(to: str, full_name: str, org_name: str,
                         accept_url: str) -> bool:
    text = (
        f"Hi {full_name},\n\n"
        f"You've been invited to join {org_name} on ReturnIQ.\n\n"
        f"Email: {to}\n\n"
        f"Set your password here (this link works once and expires in 7 days):\n"
        f"{accept_url}\n\n"
        f"If you weren't expecting this invitation, you can ignore this email."
    )

    html = _WRAPPER.format(content=f"""
      <div style="font-size:16px;font-weight:600;margin-bottom:12px;">
        You've been invited to {org_name}</div>
      <p style="font-size:14px;line-height:1.6;color:#475569;margin:0 0 20px;">
        Hi {full_name}, an administrator has added you to {org_name} on ReturnIQ.
      </p>
      <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;
      padding:16px;margin-bottom:20px;font-size:13px;line-height:1.8;">
        <div><span style="color:#94a3b8;">Email</span><br><strong>{to}</strong></div>
        <div style="margin-top:10px;"><span style="color:#94a3b8;">Next step</span><br>
        Choose your own password using the button below.</div>
      </div>
      <a href="{accept_url}" style="display:inline-block;background:#4f46e5;color:#ffffff;
      text-decoration:none;padding:11px 22px;border-radius:8px;font-size:14px;font-weight:600;">
        Set your password</a>
      <p style="font-size:13px;color:#64748b;margin:20px 0 0;line-height:1.6;">
        This link works once and expires in 7 days. If you weren't expecting
        this invitation, you can safely ignore this email.
      </p>""")

    return send_email(to, f"You've been invited to {org_name} on ReturnIQ", text, html)
