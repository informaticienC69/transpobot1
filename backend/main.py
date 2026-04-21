from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from contextlib import asynccontextmanager
import asyncio
import os
from .database import execute_write_query, get_pool
from .routes import data, chat, crud, auth, superadmin

async def auto_start_trajets():
    """Tâche de fond : passe automatiquement les trajets 'planifie' en 'en_cours' à l'heure H."""
    while True:
        try:
            execute_write_query(
                "UPDATE trajets SET statut = 'en_cours' WHERE statut = 'planifie' AND date_heure_depart <= NOW()"
            )
        except Exception as e:
            print(f"[TACHE FOND] Erreur auto-start trajets : {e}")
        await asyncio.sleep(60)  # Vérifie toutes les 60 secondes

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 🚀 Préchauffage du pool de connexions MySQL au démarrage
    # Évite la latence sur la 1ère requête après cold start
    try:
        pool = get_pool()
        if pool:
            print("✅ Pool MySQL préchauffé et prêt.")
    except Exception as e:
        print(f"⚠️ Avertissement pool MySQL : {e}")
    
    task = asyncio.create_task(auto_start_trajets())
    yield
    task.cancel()

# Détection environnement (local vs production Render)
IS_PRODUCTION = os.getenv("RENDER", False)

# Origines autorisées : env var explicite OU URL Render par défaut OU tout en local
_raw_origins = os.getenv("FRONTEND_ORIGIN", "")
if _raw_origins:
    ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]
else:
    ALLOWED_ORIGINS = ["https://transpobot-api.onrender.com", "http://localhost:8000", "http://127.0.0.1:8000"]

app = FastAPI(
    title="TranspoBot API",
    description="Backend - IA Text-to-SQL (Bilingue) sur MySQL",
    version="1.0.0",
    lifespan=lifespan,
    # En production, masquer la doc publique
    docs_url="/docs" if not IS_PRODUCTION else None,
    redoc_url=None,
)

# CORS : ouvert en local, restreint en production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not IS_PRODUCTION else ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🗜️ Compression GZip : réduit la taille des réponses JSON de ~70%
# (accélère le chargement du dashboard et des tables de données)
app.add_middleware(GZipMiddleware, minimum_size=1000)

from .security import verify_token, log_security_event
from fastapi import Depends, HTTPException, Request

def require_role(*roles):
    """Fabrique une dépendance FastAPI qui exige un rôle spécifique dans le token JWT."""
    def role_checker(user: dict = Depends(verify_token)):
        if user.get("role") not in roles:
            log_security_event(
                "RBAC_DENIED",
                f"Accès refusé : email='{user.get('sub')}' rôle='{user.get('role')}' tentait d'accéder à une zone réservée aux : {', '.join(roles)}."
            )
            raise HTTPException(
                status_code=403,
                detail=f"Accès refusé : rôle '{user.get('role')}' insuffisant. Action réservée aux : {', '.join(roles)}."
            )
        return user
    return role_checker

# Injection des routes (endpoints)
app.include_router(data.router, prefix="/api/data", tags=["Données Dashboard"], dependencies=[Depends(verify_token)])
app.include_router(chat.router, prefix="/api/chat", tags=["Assistant IA Bilingue"], dependencies=[Depends(verify_token)])
app.include_router(crud.router, prefix="/api/crud", tags=["Administration CRUD"],
    dependencies=[Depends(require_role("admin", "gestionnaire"))])
app.include_router(auth.router, prefix="/api/auth", tags=["Authentification"])
app.include_router(superadmin.router, prefix="/api/superadmin", tags=["Super Admin"])

# ─── Servir le Frontend (index.html + assets) ─────────────────────────────────
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")

    @app.get("/", response_class=HTMLResponse)
    def serve_index():
        """Sert le dashboard principal."""
        with open(os.path.join(FRONTEND_DIR, "index.html"), "r", encoding="utf-8") as f:
            return f.read()

    @app.get("/superadmin.html", response_class=HTMLResponse)
    def serve_superadmin():
        """Sert le portail Super Admin SOC."""
        with open(os.path.join(FRONTEND_DIR, "superadmin.html"), "r", encoding="utf-8") as f:
            return f.read()

    @app.get("/activation.html", response_class=HTMLResponse)
    def serve_activation():
        """Sert la page d'activation de compte gestionnaire."""
        with open(os.path.join(FRONTEND_DIR, "activation.html"), "r", encoding="utf-8") as f:
            return f.read()

else:
    @app.get("/")
    def res_home():
        return {"status": "TranspoBot API opérationnelle", "version": "1.0.0"}

