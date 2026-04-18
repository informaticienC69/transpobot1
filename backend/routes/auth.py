from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
import hashlib
import bcrypt
import time
from ..database import get_db_connection, execute_write_query
from ..security import create_access_token, log_security_event

router = APIRouter()

class LoginRequest(BaseModel):
    email: str
    password: str

def hash_password_bcrypt(password: str) -> str:
    """Hash un mot de passe avec bcrypt (standard industrie, résistant aux rainbow tables)."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password: str, stored_hash: str) -> bool:
    """
    Vérifie un mot de passe avec migration transparente SHA-256 → bcrypt.
    Si l'ancien hash SHA-256 correspond, le mot de passe est re-hashé en bcrypt automatiquement.
    """
    # Cas 1 : Hash bcrypt (commence par $2b$ ou $2a$)
    if stored_hash.startswith("$2b$") or stored_hash.startswith("$2a$"):
        return bcrypt.checkpw(plain_password.encode('utf-8'), stored_hash.encode('utf-8'))
    # Cas 2 : Ancien hash SHA-256 (migration transparente)
    sha256_hash = hashlib.sha256(plain_password.encode('utf-8')).hexdigest()
    return sha256_hash == stored_hash

# Stockage temporaire en mémoire des tentatives échouées : { "ip_address": {"count": X, "lockout_until": TIMESTAMP} }
login_attempts = {}
MAX_ATTEMPTS = 5
LOCKOUT_TIME_SECONDS = 900  # 15 minutes

@router.post("/login")
def login(request_data: LoginRequest, http_request: Request):
    client_ip = http_request.client.host if http_request.client else "Unknown"
    current_time = time.time()
    
    # Vérification Brute-Force
    if client_ip in login_attempts:
        attempt_info = login_attempts[client_ip]
        if attempt_info["count"] >= MAX_ATTEMPTS:
            if current_time < attempt_info["lockout_until"]:
                log_security_event("BRUTE_FORCE_BLOCKED", f"IP bloquée après {MAX_ATTEMPTS} échecs.", client_ip)
                raise HTTPException(status_code=429, detail="Trop de tentatives échouées. Compte temporairement bloqué pendant 15 minutes.")
            else:
                # Le lockout est terminé, on réinitialise
                del login_attempts[client_ip]

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Database connection failed")

    cursor = None
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT email, nom, mot_de_passe_hash, role, statut FROM utilisateurs WHERE email = %s", (request_data.email,))
        user = cursor.fetchone()

        # Mauvais identifiants
        if not user or not verify_password(request_data.password, user['mot_de_passe_hash']):
            # Incrémenter le compteur d'échecs
            if client_ip not in login_attempts:
                login_attempts[client_ip] = {"count": 1, "lockout_until": current_time + LOCKOUT_TIME_SECONDS}
            else:
                login_attempts[client_ip]["count"] += 1

            log_security_event("FAILED_LOGIN", f"Echec de connexion pour email: {request_data.email}", client_ip)
            raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

        # Vérification du statut du compte
        statut = user.get('statut', 'actif')  # 'actif' par défaut pour rétrocompatibilité
        if statut == 'en_attente':
            log_security_event("BLOCKED_LOGIN", f"Tentative de connexion sur un compte en attente d'activation: {request_data.email}", client_ip)
            raise HTTPException(status_code=403, detail="Votre compte est en attente d'activation. Vérifiez votre boîte email.")
        if statut == 'revoque':
            log_security_event("BLOCKED_LOGIN", f"Tentative de connexion sur un compte révoqué: {request_data.email}", client_ip)
            raise HTTPException(status_code=403, detail="Votre accès a été révoqué. Contactez l'administrateur.")

        # Connexion réussie : on efface l'ardoise des tentatives
        if client_ip in login_attempts:
            del login_attempts[client_ip]

        # Migration transparente SHA-256 → bcrypt à la première connexion
        if not (user['mot_de_passe_hash'].startswith("$2b$") or user['mot_de_passe_hash'].startswith("$2a$")):
            new_hash = hash_password_bcrypt(request_data.password)
            execute_write_query(
                "UPDATE utilisateurs SET mot_de_passe_hash = %s WHERE email = %s",
                (new_hash, user['email'])
            )

        access_token = create_access_token(data={"sub": user["email"], "role": user["role"]})

        # ✅ Log de connexion réussie — visible dans le SOC Super Admin
        log_security_event(
            "USER_LOGIN",
            f"Connexion réussie. Email: {user['email']} | Rôle: {user['role']} | Nom: {user['nom']}",
            client_ip
        )

        return {
            "success": True,
            "message": "Connexion réussie",
            "token": access_token,
            "user": {
                "email": user["email"],
                "nom": user["nom"],
                "role": user["role"]
            }
        }

    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


# ===========================================================
# ACTIVATION DE COMPTE (via le lien email)
# ===========================================================

class ActivateRequest(BaseModel):
    token: str
    password: str

@router.post("/activate")
def activate_account(request_data: ActivateRequest, http_request: Request):
    """Active un compte gestionnaire : vérifie le token et définit le mot de passe."""
    import hashlib
    import re

    client_ip = http_request.client.host if http_request.client else "Unknown"
    raw_token = request_data.token.strip()
    password = request_data.password

    # Validation de la complexité du mot de passe
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins 8 caractères.")
    if not re.search(r'[A-Z]', password):
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins une majuscule.")
    if not re.search(r'[0-9]', password):
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins un chiffre.")
    if not re.search(r'[!@#$%^&*(),.?\":{}|<>]', password):
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins un caractère spécial.")

    # Hacher le token pour comparaison en base
    hashed_token = hashlib.sha256(raw_token.encode()).hexdigest()

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Erreur de connexion à la base de données.")

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT email, nom, statut, token_expiration
            FROM utilisateurs
            WHERE token_activation = %s AND statut = 'en_attente'
        """, (hashed_token,))
        user = cursor.fetchone()

        if not user:
            log_security_event("INVALID_TOKEN", f"Tentative d'activation avec un token invalide ou expiré.", client_ip)
            raise HTTPException(status_code=400, detail="Lien d'activation invalide ou déjà utilisé.")

        # Vérifier l'expiration
        from datetime import datetime
        if user["token_expiration"] and datetime.now() > user["token_expiration"]:
            log_security_event("EXPIRED_TOKEN", f"Token expiré pour {user['email']}", client_ip)
            raise HTTPException(status_code=400, detail="Ce lien d'activation a expiré. Contactez votre administrateur pour en recevoir un nouveau.")

        # Hacher le mot de passe et activer le compte
        hashed_password = hash_password_bcrypt(password)
        cursor.execute("""
            UPDATE utilisateurs
            SET mot_de_passe_hash = %s, statut = 'actif', token_activation = NULL, token_expiration = NULL
            WHERE email = %s
        """, (hashed_password, user["email"]))
        conn.commit()
        cursor.close()
        conn.close()

        log_security_event(
            "ACCOUNT_ACTIVATED",
            f"Compte activé avec succès. Email: {user['email']} | Nom: {user['nom']}",
            client_ip
        )

        return {"success": True, "message": f"Compte activé avec succès ! Vous pouvez maintenant vous connecter."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'activation: {str(e)}")
