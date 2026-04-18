"""
TranspoBot — Service d'envoi d'emails
Utilisé pour l'activation de compte et la réinitialisation de mot de passe.
Infrastructure : Brevo (Sendinblue) API HTTP — 100% compatible cloud (Render, Railway, etc.)
"""
import json
import urllib.request
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger("uvicorn.error")
from ..config import settings


def _build_html(recipient_name: str, heading: str, message_body: str, activation_url: str) -> str:
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #0a0f1c; color: #e0e6ed; padding: 40px 20px; }}
            .container {{ max-width: 520px; margin: 0 auto; background: #111827; border-radius: 16px; padding: 40px; border: 1px solid #1e293b; }}
            .logo {{ text-align: center; font-size: 24px; font-weight: 700; color: #00ffc8; letter-spacing: 2px; margin-bottom: 24px; }}
            h1 {{ font-size: 20px; color: #ffffff; margin-bottom: 16px; }}
            p {{ font-size: 15px; line-height: 1.7; color: #94a3b8; }}
            .btn {{ display: inline-block; background: linear-gradient(135deg, #00ffc8, #00b894); color: #0a0f1c; padding: 14px 32px; border-radius: 8px; text-decoration: none; font-weight: 700; font-size: 15px; margin: 24px 0; }}
            .footer {{ font-size: 12px; color: #475569; margin-top: 32px; text-align: center; }}
            .warning {{ font-size: 13px; color: #f59e0b; margin-top: 16px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">🚌 TRANSPOBOT</div>
            <h1>{heading}</h1>
            <p>Bonjour <strong>{recipient_name}</strong>,</p>
            <p>{message_body}</p>
            <p style="text-align: center;">
                <a href="{activation_url}" class="btn">Activer mon compte</a>
            </p>
            <p class="warning">⏳ Ce lien est valable <strong>48 heures</strong>. Passé ce délai, demandez à votre administrateur de renvoyer une invitation.</p>
            <p class="footer">
                Si vous n'avez pas demandé ce compte, ignorez cet email.<br>
                — TranspoBot Security Operations Center
            </p>
        </div>
    </body>
    </html>
    """


def send_activation_email(recipient_email: str, recipient_name: str, token: str, is_reset: bool = False) -> bool:
    """
    Envoie un email d'activation ou de réinitialisation de mot de passe.
    Priorité 1 : Brevo API (HTTP, compatible tous les hébergeurs cloud)
    Priorité 2 : SMTP (fallback si pas de clé Brevo)
    """
    activation_url = f"{settings.APP_URL}/activation.html?token={token}"

    if is_reset:
        subject = "TranspoBot — Réinitialisation de votre mot de passe"
        heading = "Réinitialisation de mot de passe"
        message_body = (
            "L'administrateur a réinitialisé votre mot de passe. "
            "Cliquez sur le bouton ci-dessous pour en définir un nouveau."
        )
    else:
        subject = "TranspoBot — Activation de votre compte"
        heading = "Bienvenue sur TranspoBot !"
        message_body = (
            "Votre compte gestionnaire a été créé par l'administrateur. "
            "Cliquez sur le bouton ci-dessous pour vérifier votre email et définir votre mot de passe personnel."
        )

    html_content = _build_html(recipient_name, heading, message_body, activation_url)

    # === Brevo API ===
    brevo_key = settings.BREVO_API_KEY
    if brevo_key:
        return _send_via_brevo(brevo_key, recipient_email, recipient_name, subject, html_content)

    logger.warning(f"[EMAIL] ⚠️ Aucune clé Brevo (BREVO_API_KEY) configurée. Token pour {recipient_email}: {token}")
    return False


def _send_via_brevo(api_key: str, to_email: str, to_name: str, subject: str, html: str) -> bool:
    """Envoie l'email via l'API HTTP Brevo (Sendinblue). Compatible avec tous les hébergeurs cloud."""
    payload = json.dumps({
        "sender": {"name": "TranspoBot SOC", "email": settings.SENDER_EMAIL or "noreply@transpobot.app"},
        "to": [{"email": to_email, "name": to_name}],
        "subject": subject,
        "htmlContent": html
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=payload,
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status in (200, 201):
                logger.info(f"[EMAIL] ✅ Brevo : email envoyé à {to_email}")
                return True
            logger.error(f"[EMAIL] ❌ Brevo : réponse inattendue {response.status}")
            return False
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        logger.error(f"[EMAIL] ❌ Brevo HTTP {e.code}: {body} (SENDER: {settings.SENDER_EMAIL})")
        return False
    except Exception as e:
        logger.error(f"[EMAIL] ❌ Brevo exception: {type(e).__name__}: {e}")
        return False
