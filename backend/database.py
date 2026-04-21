import mysql.connector
from mysql.connector import pooling
from .config import settings
from .security import log_security_event
import re

# ══════════════════════════════════════════════════════════════
# 🚀 POOL DE CONNEXIONS MySQL
# Au lieu d'ouvrir/fermer une connexion à chaque requête (lent),
# le pool maintient 5 connexions persistantes prêtes à l'emploi.
# Résultat : latence DB divisée par ~10 sur les requêtes répétées.
# ══════════════════════════════════════════════════════════════
_pool = None

def get_pool():
    global _pool
    if _pool is None:
        try:
            _pool = pooling.MySQLConnectionPool(
                pool_name="transpobot_pool",
                pool_size=5,           # 5 connexions simultanées max (Render free = 1 instance)
                pool_reset_session=True,
                host=settings.DB_HOST,
                port=settings.DB_PORT,
                user=settings.DB_USER,
                password=settings.DB_PASSWORD,
                database=settings.DB_NAME,
                connect_timeout=10,    # Timeout connexion : 10s max
                autocommit=False,
            )
            print("✅ Pool de connexions MySQL initialisé (5 connexions).")
        except mysql.connector.Error as err:
            print(f"❌ Erreur initialisation pool MySQL : {err}")
            _pool = None
    return _pool

def get_db_connection():
    """Retourne une connexion depuis le pool (ne pas oublier de la fermer après)."""
    pool = get_pool()
    if pool:
        try:
            return pool.get_connection()
        except mysql.connector.Error as err:
            print(f"⚠️ Pool épuisé ou erreur, tentative connexion directe : {err}")
    # Fallback : connexion directe si le pool est indisponible
    try:
        return mysql.connector.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
            connect_timeout=10,
        )
    except mysql.connector.Error as err:
        print(f"❌ Erreur de connexion MySQL (fallback) : {err}")
        return None

def execute_read_only_query(query: str, params: tuple = None):
    """
    Execute une requete SQL en LECTURE SEULE.
    Securite absolue : bloque tout trafic non-SELECT.
    Accepte un parametre `params` pour les requetes parametrees (anti-injection).
    """
    query_clean = query.strip()

    # Filtre de securite severe (Blocage des commandes destructives)
    forbidden_keywords = r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|GRANT|REVOKE|COMMIT|ROLLBACK|CREATE|REPLACE)\b"
    if re.search(forbidden_keywords, query_clean, re.IGNORECASE):
        log_security_event("BLOCKED_QUERY", f"Tentative d'écriture SQL bloquée : {query_clean}")
        return {
            "success": False,
            "error": "Erreur de Securite : La requete contient une commande destructive non autorisee."
        }

    # Bloquer explicitement les fuites de mots de passe (PII/Secret)
    forbidden_columns = r"\b(mot_de_passe_hash)\b"
    if re.search(forbidden_columns, query_clean, re.IGNORECASE):
        log_security_event("DATA_LEAK_PREVENTED", f"Tentative d'accès au PII (mot de passe) via SQL : {query_clean}")
        return {
            "success": False,
            "error": "Erreur de Securite : Il est strictement interdit d'interroger la colonne 'mot_de_passe_hash'."
        }

    if not query_clean.upper().startswith("SELECT") and not query_clean.upper().startswith("WITH"):
        return {
            "success": False,
            "error": "Erreur : La requete doit etre une structure de selection (SELECT / WITH)."
        }

    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Impossible de se connecter a la base de donnees."}

    try:
        cursor = conn.cursor(dictionary=True)  # dictionary=True => {'colonne': 'valeur'}
        if params:
            cursor.execute(query_clean, params)
        else:
            cursor.execute(query_clean)
        results = cursor.fetchall()

        column_names = [i[0] for i in cursor.description] if cursor.description else []

        cursor.close()
        conn.close()  # Retourne la connexion au pool (ne la détruit pas)

        return {
            "success": True,
            "columns": column_names,
            "data": results,
            "count": len(results)
        }
    except Exception as e:
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass
        log_security_event("DB_ERROR", f"Erreur MySQL (lecture) : {str(e)}")
        return {
            "success": False,
            "error": "Une erreur technique est survenue lors de la lecture des données."
        }

def execute_write_query(query: str, params: tuple = None):
    """
    Execute une requete d'ecriture (INSERT, UPDATE, DELETE) pour les operations Administrateur.
    Strictement reservee a l'API CRUD (Interface Web), interdite au Chatbot IA.
    """
    conn = get_db_connection()
    if not conn:
        return {"success": False, "error": "Impossible de se connecter a la base de donnees."}

    try:
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        conn.commit()  # Valider formellement la transaction MySQL
        last_id = cursor.lastrowid

        cursor.close()
        conn.close()  # Retourne la connexion au pool

        return {"success": True, "last_id": last_id, "message": "Opération effectuée avec succès."}
    except Exception as e:
        try:
            conn.rollback()
            cursor.close()
            conn.close()
        except Exception:
            pass
        log_security_event("DB_ERROR", f"Erreur MySQL (écriture) : {str(e)}")
        return {"success": False, "error": "Une erreur technique est survenue lors de l'écriture des données."}
