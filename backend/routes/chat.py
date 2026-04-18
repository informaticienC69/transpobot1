from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from ..services.llm_service import generate_sql_query, generate_nl_response
from ..database import execute_read_only_query, execute_write_query
from ..security import verify_token, log_security_event
import re
import time

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    language: str = "fr"  # "fr" ou "en"

class ChatResponse(BaseModel):
    natural_response: str
    data_table: list
    columns: list
    executed_sql: str
    execution_time_ms: int
    error: str = None

@router.post("")
def handle_chat_message(request: ChatRequest, http_request: Request, user: dict = Depends(verify_token)):
    """
    Point d'entrée principal pour le Chatbot Text-to-SQL de TranspoBot.
    Gère le pipeline IA complet : Prompt -> SQL -> MySQL -> NLP -> Interface Web.
    Intègre une auto-correction silencieuse (Retry Loop) si le SQL généré est invalide.
    """
    client_ip = http_request.client.host if http_request.client else "Unknown"
    user_email = user.get("sub", "Anonyme")
    start_time = time.time()
    
    # ─── 1. Détection d'injection SQL directe ─────────────────────────────────
    sql_injection_pattern = r"\b(DROP|DELETE|INSERT|UPDATE|TRUNCATE|EXEC|EXECUTE|UNION|--|;\s*SELECT|xp_|0x[0-9a-fA-F]+)\b"
    if re.search(sql_injection_pattern, request.message, re.IGNORECASE):
        log_security_event(
            "SQL_INJECTION_ATTEMPT",
            f"Tentative d'injection SQL dans le chat. Email: {user_email}. Message: {request.message[:200]}",
            client_ip
        )

    # ─── 2. Détection d'intention de MODIFICATION via l'IA (FR + EN) ──────────
    # Mots-clés indiquant qu'un gestionnaire tente de faire écrire l'IA dans la BDD
    write_intent_fr = (
        r"\b(supprime[rz]?|efface[rz]?|modifi(?:er?|ez?|ons)?|chang(?:er?|ez?)|"
        r"met(?:s|tre|tons|tez)?\s+à\s+jour|mise?\s+à\s+jour|mets?\s+à\s+jour|"
        r"ajout(?:er?|ez?|e)?|crée[rz]?|cr[eé](?:er?|ez?)|insère[rz]?|insert(?:er?|ez?)?|"
        r"annul(?:er?|ez?|e)?|démarre[rz]?|termin(?:er?|ez?|e)?|arrêt(?:er?|ez?|e)?|"
        r"assign(?:er?|ez?|e)?|affect(?:er?|ez?|e)?|licenci(?:er?|ez?|e)?|embauche[rz]?|"
        r"vire[rz]?|renvoie[rz]?|désaffect(?:er?|ez?|e)?|planifi(?:er?|ez?|e)?|"
        r"enregistre[rz]?|sauvegardr?e[rz]?|met(?:s)?\s+en\s+maintenance|"
        r"repar(?:er?|ez?|e)?|r[eé]par(?:er?|ez?|e)?|résou(?:ds?|dre))\b"
    )
    write_intent_en = (
        r"\b(delete|remove|update|modify|change|add|create|insert|cancel|"
        r"start|terminate|end|assign|hire|fire|dismiss|edit|set|put|"
        r"register|save|schedule|plan|fix|repair|mark|flag|reset|deactivate|"
        r"activate|disable|enable|transfer|move|replace)\b"
    )

    msg_lower = request.message
    is_write_attempt_fr = re.search(write_intent_fr, msg_lower, re.IGNORECASE)
    is_write_attempt_en = re.search(write_intent_en, msg_lower, re.IGNORECASE)

    if is_write_attempt_fr or is_write_attempt_en:
        lang_detected = "FR" if is_write_attempt_fr else "EN"
        keyword_found = (is_write_attempt_fr or is_write_attempt_en).group(0)
        log_security_event(
            "AI_WRITE_ATTEMPT",
            f"Gestionnaire '{user_email}' tente une MODIFICATION via l'IA [{lang_detected}] "
            f"— Mot-clé: '{keyword_found}' — Message: {request.message[:250]}",
            client_ip
        )

    sql_query = ""
    db_result = {"success": False, "error": "Init", "data": [], "columns": []}
    
    max_retries = 3
    last_error = None
    
    # 1. & 2. Auto-Correction Loop (Générer -> Tester -> Corriger)
    for attempt in range(max_retries):
        try:
            sql_query = generate_sql_query(request.message, user_email=user_email, error_context=last_error)
            
            # Cas spécial : Demande hors lecture (ex: Bonjour, ou action d'écriture)
            if sql_query == "NON_SQL":
                db_result = {"success": True, "data": [], "columns": [], "is_non_sql": True}
                break
                
            db_result = execute_read_only_query(sql_query)
            
            if db_result.get("success"):
                break  # Requête valide, on sort de la boucle !
            else:
                last_error = db_result.get("error")
                if last_error and "Securite" in last_error:
                    break # Ne jamais retenter une requête qui viole la sécurité.
                
        except Exception as e:
            last_error = str(e)
            
    if not db_result.get("success"):
        # L'IA a généré une requête erronée 3 fois de suite
        # Utiliser l'IA pour générer une réponse naturelle expliquant l'échec total
        try:
            nl_reply = generate_nl_response(request.message, [], language=request.language, error=db_result.get("error"), sql_query=sql_query)
        except Exception as e:
            nl_reply = "Je dois formuler ma réponse sur des données, mais un problème technique critique m'empêche de lire la base." if request.language == "fr" else "Sorry, a critical technical issue prevents me from reading the database."
            
        return {
            "natural_response": nl_reply,
            "data_table": [],
            "columns": [],
            "executed_sql": sql_query,
            "execution_time_ms": int((time.time() - start_time) * 1000),
            "error": db_result.get("error")
        }
        
    data_rows = db_result.get("data", [])
    columns = db_result.get("columns", [])
    
    # 3. Ré-interroger l'IA pour générer le texte (Bilingue)
    try:
        nl_reply = generate_nl_response(request.message, data_rows, language=request.language, sql_query=sql_query)
    except Exception as e:
        nl_reply = "Erreur de formatage linguistique."
        
    exec_time_ms = int((time.time() - start_time) * 1000)
    
    # ─── 4. Enregistrement en base de données pour le SOC (logs_requetes) ───
    if user_email != "Anonyme":
        try:
            execute_write_query(
                "INSERT INTO logs_requetes (utilisateur_email, question, sql_genere, temps_reponse_ms) VALUES (%s, %s, %s, %s)",
                (user_email, request.message, sql_query, exec_time_ms)
            )
        except Exception as e:
            print(f"Erreur sauvegarde requete IA: {e}")

    # 5. Renvoyer le gros payload JSON formaté pour le Dashboard (Frontend)
    return {
        "natural_response": nl_reply,
        "data_table": data_rows,
        "columns": columns,
        "executed_sql": sql_query,
        "execution_time_ms": exec_time_ms,
        "error": None
    }
