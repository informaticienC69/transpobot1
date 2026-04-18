from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import jwt
import os
import time
import json
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from ..database import get_db_connection
from ..security import SECRET_KEY, ALGORITHM, log_security_event

load_dotenv()

router = APIRouter()
security = HTTPBearer()

# ===========================================================
# SUPER ADMIN CREDENTIALS (Chargés depuis les variables d'environnement)
# ===========================================================
SUPERADMIN_USERNAME = os.getenv("SUPERADMIN_USERNAME")
SUPERADMIN_PASSWORD = os.getenv("SUPERADMIN_PASSWORD")
SUPERADMIN_TOKEN_EXPIRE = 3600  # 1h seulement

# Sécurité : le backend refuse de démarrer si les credentials ne sont pas définis
if not SUPERADMIN_USERNAME or not SUPERADMIN_PASSWORD:
    raise RuntimeError(
        "ERREUR CRITIQUE : Les variables SUPERADMIN_USERNAME et SUPERADMIN_PASSWORD "
        "sont manquantes dans le fichier .env ou les variables d'environnement Render."
    )

# Brute force protection pour SuperAdmin
super_attempts: dict = {}
MAX_SUPER_ATTEMPTS = 3  # Plus strict que le login normal
SUPER_LOCKOUT_SECONDS = 1800  # 30 minutes

class SuperLoginRequest(BaseModel):
    username: str
    password: str


def create_superadmin_token() -> str:
    payload = {
        "sub": SUPERADMIN_USERNAME,
        "role": "superadmin",
        "exp": int(time.time()) + SUPERADMIN_TOKEN_EXPIRE
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_superadmin_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("role") != "superadmin":
            raise HTTPException(status_code=403, detail="Accès réservé au Super Administrateur.")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session Super Admin expirée.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token Super Admin invalide.")


@router.post("/login")
def superadmin_login(request_data: SuperLoginRequest, http_request: Request):
    client_ip = http_request.client.host if http_request.client else "Unknown"
    current_time = time.time()

    # Vérification lockout
    if client_ip in super_attempts:
        info = super_attempts[client_ip]
        if info["count"] >= MAX_SUPER_ATTEMPTS:
            if current_time < info["lockout_until"]:
                log_security_event("SUPERADMIN_BRUTE_FORCE", f"IP bloquée sur le portail Super Admin.", client_ip)
                raise HTTPException(status_code=429, detail="Trop de tentatives. Accès Super Admin verrouillé pendant 30 minutes.")
            else:
                del super_attempts[client_ip]

    if request_data.username != SUPERADMIN_USERNAME or request_data.password != SUPERADMIN_PASSWORD:
        if client_ip not in super_attempts:
            super_attempts[client_ip] = {"count": 1, "lockout_until": current_time + SUPER_LOCKOUT_SECONDS}
        else:
            super_attempts[client_ip]["count"] += 1
        log_security_event("SUPERADMIN_FAILED_LOGIN", f"Echec tentative Super Admin. Username: {request_data.username}", client_ip)
        raise HTTPException(status_code=401, detail="Identifiants Super Admin incorrects.")

    if client_ip in super_attempts:
        del super_attempts[client_ip]

    log_security_event("SUPERADMIN_LOGIN", f"Connexion Super Admin réussie.", client_ip)
    token = create_superadmin_token()
    return {"success": True, "token": token}


@router.get("/stats")
def get_system_stats(_: dict = Depends(verify_superadmin_token)):
    """Statistiques globales du système pour le dashboard Super Admin."""
    conn = get_db_connection()
    stats = {}
    try:
        cursor = conn.cursor(dictionary=True)
        # Stats utilisateurs
        cursor.execute("SELECT COUNT(*) as total FROM utilisateurs")
        stats["total_users"] = cursor.fetchone()["total"]
        cursor.execute("SELECT role, COUNT(*) as count FROM utilisateurs GROUP BY role")
        stats["users_by_role"] = cursor.fetchall()
        # Stats trajets
        cursor.execute("SELECT statut, COUNT(*) as count FROM trajets GROUP BY statut")
        stats["trajets_by_statut"] = cursor.fetchall()
        cursor.execute("SELECT COUNT(*) as total FROM trajets WHERE DATE(created_at) = CURDATE()")
        stats["trajets_today"] = cursor.fetchone()["total"]
        # Stats incidents
        cursor.execute("SELECT COUNT(*) as total FROM incidents")
        stats["total_incidents"] = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) as total FROM incidents WHERE resolu = 0")
        stats["incidents_ouverts"] = cursor.fetchone()["total"]
        # Stats véhicules
        cursor.execute("SELECT statut, COUNT(*) as count FROM vehicules GROUP BY statut")
        stats["vehicules_by_statut"] = cursor.fetchall()
        # Stats logs IA
        cursor.execute("SELECT COUNT(*) as total FROM logs_requetes")
        stats["total_ai_queries"] = cursor.fetchone()["total"]
        cursor.execute("SELECT COUNT(*) as total FROM logs_requetes WHERE DATE(date_requete) = CURDATE()")
        stats["ai_queries_today"] = cursor.fetchone()["total"]
        cursor.execute("SELECT AVG(temps_reponse_ms) as avg FROM logs_requetes WHERE DATE(date_requete) = CURDATE()")
        row = cursor.fetchone()
        stats["avg_ai_response_ms"] = round(row["avg"]) if row["avg"] else 0
        cursor.close()
        conn.close()
    except Exception as e:
        stats["error"] = str(e)
    return stats


@router.get("/security-log")
def get_security_log(limit: int = 100, _: dict = Depends(verify_superadmin_token)):
    """Lecture des événements de sécurité depuis la base de données (persistance)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT date_evenement, ip, geolocalisation, type_evenement, details
            FROM logs_securite
            ORDER BY date_evenement DESC
            LIMIT %s
        """, (limit,))
        rows = cursor.fetchall()
        cursor.close()
        
        events = []
        for r in rows:
            events.append({
                "timestamp": str(r["date_evenement"]),
                "ip": r["ip"],
                "geo": r["geolocalisation"],
                "type": r["type_evenement"],
                "details": r["details"]
            })
            
        # Obtenir le total
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM logs_securite")
        total = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        
        return {"events": events, "total": total}
    except Exception as e:
        return {"events": [], "total": 0, "error": str(e)}



@router.get("/ai-logs")
def get_ai_logs(limit: int = 50, _: dict = Depends(verify_superadmin_token)):
    """Dernières requêtes IA (logs_requetes)."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT lr.utilisateur_email, u.nom, lr.question, lr.sql_genere,
                   lr.temps_reponse_ms, lr.date_requete
            FROM logs_requetes lr
            LEFT JOIN utilisateurs u ON lr.utilisateur_email = u.email
            ORDER BY lr.date_requete DESC
            LIMIT %s
        """, (limit,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"logs": rows, "total": len(rows)}
    except Exception as e:
        return {"logs": [], "error": str(e)}


@router.get("/active-sessions")
def get_active_sessions(_: dict = Depends(verify_superadmin_token)):
    """
    Retourne tous les gestionnaires avec statut en temps réel.
    Source 1 : logs_securite → USER_LOGIN (dernière connexion toutes périodes)
    Source 2 : logs_requetes → dernière utilisation de l'IA
    Actif = connecté dans les dernières 8 heures
    """
    import re as _re

    # ── Source 1 : Toutes les connexions depuis logs_securite ──────────────
    last_logins: dict = {}   # email → dernière date de connexion
    active_users: set = set()  # email → connecté dans les 8 dernières heures
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor(dictionary=True)
            # Toutes les connexions réussies, on garde la plus récente par email
            cursor.execute("""
                SELECT details, date_evenement
                FROM logs_securite
                WHERE type_evenement = 'USER_LOGIN'
                ORDER BY date_evenement DESC
            """)
            logs = cursor.fetchall()
            cursor.close()
            conn.close()
            for row in logs:
                m = _re.search(r"Email:\s*([\w.+\-]+@[\w.\-]+)", row["details"])
                if m:
                    email = m.group(1).strip()
                    date_evt = row["date_evenement"]
                    # On garde seulement la connexion la plus récente
                    if email not in last_logins:
                        last_logins[email] = str(date_evt)
                    # Actif = connecté dans les 8 dernières heures
                    from datetime import datetime, timedelta
                    if isinstance(date_evt, str):
                        date_evt = datetime.fromisoformat(date_evt)
                    if datetime.now() - date_evt <= timedelta(hours=8):
                        active_users.add(email)
        except Exception as e:
            print(f"Erreur sessions: {e}")

    # ── Source 2 : Utilisateurs + activité IA ────────────────────────
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.email, u.nom, u.role, u.statut,
                   MAX(lr.date_requete) as derniere_activite_ia
            FROM utilisateurs u
            LEFT JOIN logs_requetes lr ON u.email = lr.utilisateur_email
            GROUP BY u.email, u.nom, u.role
            ORDER BY u.nom ASC
        """)
        users = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        return {"sessions": [], "error": str(e)}

    # ── Fusion ──────────────────────────────────────────
    sessions = []
    for u in users:
        email = u["email"]
        derniere_connexion = last_logins.get(email)
        ia_activity = u.get("derniere_activite_ia")
        is_active = email in active_users
        sessions.append({
            "email": email,
            "nom": u["nom"],
            "role": u["role"],
            "statut": u.get("statut", "actif"),
            "derniere_connexion": derniere_connexion,
            "derniere_activite": str(ia_activity) if ia_activity else None,
            "connecte": is_active
        })

    # Connectés en premier, puis ordre alphabétique
    sessions.sort(key=lambda x: (not x["connecte"], x["nom"] or ""))
    return {"sessions": sessions}


# ===========================================================
# GESTION DES COMPTES GESTIONNAIRES
# ===========================================================

class CreateUserRequest(BaseModel):
    nom: str
    email: str
    role: str = "gestionnaire"

class UpdateUserRequest(BaseModel):
    nom: str = None
    role: str = None


@router.post("/users")
def create_user(request_data: CreateUserRequest, http_request: Request, _: dict = Depends(verify_superadmin_token)):
    """Crée un nouveau compte gestionnaire avec envoi d'email d'activation."""
    import secrets
    import hashlib
    import re as _re
    from ..services.email_service import send_activation_email

    client_ip = http_request.client.host if http_request.client else "Unknown"
    email = request_data.email.strip().lower()
    nom = request_data.nom.strip()
    role = request_data.role.strip().lower()

    # Validation du format email
    if not _re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        raise HTTPException(status_code=400, detail="Format d'email invalide.")

    # Validation du rôle
    if role not in ("gestionnaire", "lecteur"):
        raise HTTPException(status_code=400, detail="Le rôle doit être 'gestionnaire' ou 'lecteur'.")

    if not nom or len(nom) < 2:
        raise HTTPException(status_code=400, detail="Le nom doit contenir au moins 2 caractères.")

    # Vérifier que l'email n'existe pas déjà
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données.")

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT email, statut FROM utilisateurs WHERE email = %s", (email,))
        existing = cursor.fetchone()

        if existing:
            if existing["statut"] == "revoque":
                raise HTTPException(status_code=409, detail="Ce compte existe déjà (révoqué). Utilisez la réactivation.")
            raise HTTPException(status_code=409, detail="Un compte avec cet email existe déjà.")

        # Générer le token d'activation
        raw_token = secrets.token_urlsafe(32)
        hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()

        # Insérer le compte en attente
        cursor.execute("""
            INSERT INTO utilisateurs (email, nom, mot_de_passe_hash, role, statut, token_activation, token_expiration)
            VALUES (%s, %s, 'PENDING', %s, 'en_attente', %s, DATE_ADD(NOW(), INTERVAL 48 HOUR))
        """, (email, nom, role, hashed_token))
        conn.commit()
        cursor.close()
        conn.close()

        # Envoyer l'email d'activation
        email_sent = send_activation_email(email, nom, raw_token, is_reset=False)

        log_security_event(
            "ACCOUNT_CREATED",
            f"Super Admin a créé le compte '{nom}' ({email}) — Rôle: {role} — Email envoyé: {email_sent}",
            client_ip
        )

        return {
            "success": True,
            "message": f"Compte créé pour {nom}. Email d'activation envoyé à {email}.",
            "email_sent": email_sent
        }
    except HTTPException:
        raise
    except Exception as e:
        log_security_event("ACCOUNT_ERROR", f"Erreur création compte {email}: {str(e)}", client_ip)
        raise HTTPException(status_code=500, detail=f"Erreur lors de la création du compte: {str(e)}")


@router.put("/users/{email}")
def update_user(email: str, request_data: UpdateUserRequest, http_request: Request, _: dict = Depends(verify_superadmin_token)):
    """Modifie le nom ou le rôle d'un compte gestionnaire."""
    client_ip = http_request.client.host if http_request.client else "Unknown"

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données.")

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT email, nom, role FROM utilisateurs WHERE email = %s", (email,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Compte introuvable.")

        updates = []
        params = []
        if request_data.nom and request_data.nom.strip():
            updates.append("nom = %s")
            params.append(request_data.nom.strip())
        if request_data.role and request_data.role in ("gestionnaire", "lecteur", "admin"):
            updates.append("role = %s")
            params.append(request_data.role)

        if not updates:
            raise HTTPException(status_code=400, detail="Aucune modification fournie.")

        params.append(email)
        cursor.execute(f"UPDATE utilisateurs SET {', '.join(updates)} WHERE email = %s", tuple(params))
        conn.commit()
        cursor.close()
        conn.close()

        log_security_event(
            "ACCOUNT_MODIFIED",
            f"Super Admin a modifié le compte {email}: {', '.join(updates)}",
            client_ip
        )

        return {"success": True, "message": f"Compte {email} modifié avec succès."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{email}/reset-password")
def reset_user_password(email: str, http_request: Request, _: dict = Depends(verify_superadmin_token)):
    """Réinitialise le mot de passe d'un gestionnaire (remet en attente + envoie un email)."""
    import secrets
    import hashlib
    from ..services.email_service import send_activation_email

    client_ip = http_request.client.host if http_request.client else "Unknown"

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données.")

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT email, nom, statut FROM utilisateurs WHERE email = %s", (email,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Compte introuvable.")

        # Générer un nouveau token
        raw_token = secrets.token_urlsafe(32)
        hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()

        # Remettre en attente et invalider l'ancien mot de passe
        cursor.execute("""
            UPDATE utilisateurs
            SET statut = 'en_attente', mot_de_passe_hash = 'PENDING',
                token_activation = %s, token_expiration = DATE_ADD(NOW(), INTERVAL 48 HOUR)
            WHERE email = %s
        """, (hashed_token, email))
        conn.commit()
        cursor.close()
        conn.close()

        email_sent = send_activation_email(email, user["nom"], raw_token, is_reset=True)

        log_security_event(
            "PASSWORD_RESET",
            f"Super Admin a réinitialisé le mot de passe de {email} — Email envoyé: {email_sent}",
            client_ip
        )

        return {"success": True, "message": f"Mot de passe réinitialisé. Email envoyé à {email}.", "email_sent": email_sent}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/users/{email}/revoke")
def revoke_user(email: str, http_request: Request, _: dict = Depends(verify_superadmin_token)):
    """Révoque l'accès d'un gestionnaire (le compte reste pour l'historique)."""
    client_ip = http_request.client.host if http_request.client else "Unknown"

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données.")

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT email, nom, role FROM utilisateurs WHERE email = %s", (email,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Compte introuvable.")

        if user["role"] == "admin":
            raise HTTPException(status_code=403, detail="Impossible de révoquer un compte administrateur.")

        cursor.execute("""
            UPDATE utilisateurs SET statut = 'revoque', token_activation = NULL, token_expiration = NULL
            WHERE email = %s
        """, (email,))
        conn.commit()
        cursor.close()
        conn.close()

        log_security_event(
            "ACCOUNT_REVOKED",
            f"Super Admin a révoqué l'accès de {user['nom']} ({email})",
            client_ip
        )

        return {"success": True, "message": f"Accès révoqué pour {user['nom']}."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/users/{email}/reactivate")
def reactivate_user(email: str, http_request: Request, _: dict = Depends(verify_superadmin_token)):
    """Réactive un compte révoqué (remet en attente + envoie un email d'activation)."""
    import secrets
    import hashlib
    from ..services.email_service import send_activation_email

    client_ip = http_request.client.host if http_request.client else "Unknown"

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données.")

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT email, nom, statut FROM utilisateurs WHERE email = %s", (email,))
        user = cursor.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Compte introuvable.")
        if user["statut"] != "revoque":
            raise HTTPException(status_code=400, detail="Ce compte n'est pas révoqué.")

        raw_token = secrets.token_urlsafe(32)
        hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()

        cursor.execute("""
            UPDATE utilisateurs
            SET statut = 'en_attente', mot_de_passe_hash = 'PENDING',
                token_activation = %s, token_expiration = DATE_ADD(NOW(), INTERVAL 48 HOUR)
            WHERE email = %s
        """, (hashed_token, email))
        conn.commit()
        cursor.close()
        conn.close()

        email_sent = send_activation_email(email, user["nom"], raw_token, is_reset=False)

        log_security_event(
            "ACCOUNT_REACTIVATED",
            f"Super Admin a réactivé le compte de {user['nom']} ({email})",
            client_ip
        )

        return {"success": True, "message": f"Compte réactivé. Email d'activation envoyé à {email}.", "email_sent": email_sent}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
