import mysql.connector
from .config import settings
from .security import log_security_event
import re

def get_db_connection():
    """Cree et retourne une connexion a la base de donnees locale via mysql-connector."""
    try:
        return mysql.connector.connect(
            host=settings.DB_HOST,
            port=settings.DB_PORT,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME
        )
    except mysql.connector.Error as err:
        print(f"Erreur de connexion MySQL : {err}")
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
        return {"success": False, "error": "Impossible de se connecter a la base de donnees locale."}

    try:
        cursor = conn.cursor(dictionary=True)  # dictionary=True => {'colonne': 'valeur'}
        if params:
            cursor.execute(query_clean, params)
        else:
            cursor.execute(query_clean)
        results = cursor.fetchall()

        column_names = [i[0] for i in cursor.description] if cursor.description else []

        cursor.close()
        conn.close()

        return {
            "success": True,
            "columns": column_names,
            "data": results,
            "count": len(results)
        }
    except Exception as e:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()
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
        return {"success": False, "error": "Impossible de se connecter a la base de donnees locale."}

    try:
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        conn.commit()  # Valider formellement la transaction MySQL
        last_id = cursor.lastrowid

        cursor.close()
        conn.close()

        return {"success": True, "last_id": last_id, "message": "Opération effectuée avec succès."}
    except Exception as e:
        if conn and conn.is_connected():
            conn.rollback()
            cursor.close()
            conn.close()
        log_security_event("DB_ERROR", f"Erreur MySQL (écriture) : {str(e)}")
        return {"success": False, "error": "Une erreur technique est survenue lors de l'écriture des données."}
