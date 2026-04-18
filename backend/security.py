import jwt
from fastapi import HTTPException, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
from datetime import datetime, timedelta, timezone

SECRET_KEY = os.getenv("JWT_SECRET")
if not SECRET_KEY:
    raise RuntimeError("ERREUR CRITIQUE : La variable JWT_SECRET est absente du fichier .env. Le serveur ne peut pas démarrer sans une clé secrète sécurisée.")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 2  # 🔴 SECURITY UPGRADE: Le jeton meurt dans 2h au lieu de 12.

LOG_FILE = "security.log"

def get_ip_geo(ip: str) -> str:
    """Récupère la géolocalisation d'une IP via ip-api.com (gratuit, sans clé API)."""
    if not ip or ip in ("Unknown", "127.0.0.1", "::1", "localhost"):
        return "🏠 Réseau Local"
    try:
        import urllib.request
        import json
        url = f"http://ip-api.com/json/{ip}?fields=status,country,city,isp&lang=fr"
        req = urllib.request.Request(url, headers={"User-Agent": "TranspoBot-SOC/1.0"})
        with urllib.request.urlopen(req, timeout=2) as r:
            data = json.loads(r.read())
            if data.get("status") == "success":
                city = data.get("city", "?")
                country = data.get("country", "?")
                return f"📍 {city}, {country}"
    except Exception:
        pass
    return "🌐 Géo inconnue"

def log_security_event(event_type: str, details: str, ip: str = "Unknown"):
    """
    Enregistre les événements de sécurité.
    Priorité 1 : Base de données (logs_securite) pour persistance sur Render.
    Priorité 2 : Fichier log local en backup.
    """
    geo = get_ip_geo(ip)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Sauvegarde en Base de Données
    try:
        from .database import get_db_connection
        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO logs_securite (ip, geolocalisation, type_evenement, details) VALUES (%s, %s, %s, %s)",
                (ip, geo, event_type, details[:500])
            )
            conn.commit()
            cursor.close()
            conn.close()
    except Exception as e:
        print(f"Erreur d'écriture log en BDD : {e}")

    # 2. Sauvegarde dans Fichier local (backup pour le terminal)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] IP: {ip} | {geo} | {event_type} | {details}\n")
    except Exception:
        pass

security = HTTPBearer()

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Security(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        log_security_event("JWT_EXPIRED", "Token JWT expiré utilisé lors d'une requête.")
        raise HTTPException(status_code=401, detail="Token expiré. Veuillez vous reconnecter.")
    except jwt.InvalidTokenError:
        log_security_event("JWT_INVALID", "Token JWT invalide ou falsifié détecté.")
        raise HTTPException(status_code=401, detail="Token invalide. Accès refusé.")

