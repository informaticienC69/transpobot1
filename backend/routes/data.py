from fastapi import APIRouter, HTTPException
import re
from ..database import execute_read_only_query

router = APIRouter()

@router.get("/vehicules")
def get_vehicules():
    """Récupère la liste de tous les véhicules."""
    result = execute_read_only_query("SELECT * FROM vehicules")
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result

@router.get("/chauffeurs")
def get_chauffeurs():
    """Récupère la liste simple de tous les chauffeurs (utilisé pour les selects/dropdowns)."""
    result = execute_read_only_query("SELECT * FROM chauffeurs")
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result

@router.get("/chauffeurs-stats")
def get_chauffeurs_stats():
    """Fix #4 : Récupère les chauffeurs avec statistiques agrégées complètes.
    Retourne : nb_trajets, recette_totale, retard_moyen, nb_incidents, note_moyenne.
    """
    query = """
    SELECT
        c.numero_permis,
        c.nom,
        c.prenom,
        c.email,
        c.telephone,
        c.disponibilite,
        c.note_moyenne,
        c.vehicule_immatriculation,
        c.date_embauche,
        COUNT(DISTINCT t.id_trajet)          AS nb_trajets,
        COALESCE(SUM(t.recette), 0)          AS recette_totale,
        COALESCE(AVG(t.retard_minutes), 0)   AS retard_moyen,
        COUNT(DISTINCT i.id_incident)        AS nb_incidents
    FROM chauffeurs c
    LEFT JOIN trajets t
        ON c.numero_permis = t.chauffeur_permis AND t.statut = 'termine'
    LEFT JOIN incidents i
        ON t.id_trajet = i.trajet_id
    GROUP BY
        c.numero_permis, c.nom, c.prenom, c.email,
        c.telephone, c.disponibilite, c.note_moyenne,
        c.vehicule_immatriculation, c.date_embauche
    ORDER BY nb_trajets DESC
    """
    result = execute_read_only_query(query)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result

@router.get("/trajets-recents")
def get_trajets_recents():
    """Récupère les trajets (semaine en cours) pour le dashboard."""
    query = """
    SELECT id_trajet, ligne_code, chauffeur_permis as chauffeur, vehicule_immatriculation as vehicule, statut 
    FROM trajets 
    WHERE YEARWEEK(date_heure_depart, 1) = YEARWEEK(CURDATE(), 1)
       OR YEARWEEK(created_at, 1) = YEARWEEK(CURDATE(), 1)
       OR YEARWEEK(date_heure_arrivee, 1) = YEARWEEK(CURDATE(), 1)
    ORDER BY id_trajet DESC
    LIMIT 20
    """
    result = execute_read_only_query(query)
    if not result.get("success"):
        return {"success": False, "error": "Requête DB échouée."}
    return result

@router.get("/lignes")
def get_lignes():
    """Fix #6 : Récupère toutes les lignes avec leur tarif normal pour le calcul financier auto."""
    query = """
    SELECT l.*, COALESCE(t.prix, 0) as tarif_normal
    FROM lignes l
    LEFT JOIN tarifs t ON l.code = t.ligne_code AND t.type_client = 'normal'
    ORDER BY l.code
    """
    result = execute_read_only_query(query)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result

@router.get("/incidents")
def get_incidents():
    """Récupère tous les incidents avec le contexte du trajet."""
    query = """
    SELECT i.id_incident, i.trajet_id, i.type, i.description, i.gravite,
           i.cout_reparation, i.date_incident, i.resolu,
           t.ligne_code, t.chauffeur_permis
    FROM incidents i
    JOIN trajets t ON i.trajet_id = t.id_trajet
    ORDER BY i.date_incident DESC
    """
    result = execute_read_only_query(query)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result

@router.get("/maintenances")
def get_maintenances():
    """Récupère toutes les interventions de maintenance."""
    query = """
    SELECT m.*, v.marque, v.modele
    FROM maintenances m
    JOIN vehicules v ON m.vehicule_immatriculation = v.immatriculation
    ORDER BY m.date_debut DESC
    """
    result = execute_read_only_query(query)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result

@router.get("/trajets-all")
def get_all_trajets():
    """Récupère les 30 derniers trajets avec les noms des chauffeurs."""
    query = """
    SELECT t.id_trajet, t.ligne_code, t.statut, t.date_heure_depart,
           t.nb_passagers, t.recette, t.retard_minutes,
           CONCAT(c.prenom, ' ', c.nom) AS chauffeur_nom,
           t.vehicule_immatriculation
    FROM trajets t
    JOIN chauffeurs c ON t.chauffeur_permis = c.numero_permis
    ORDER BY t.date_heure_depart DESC
    LIMIT 30
    """
    result = execute_read_only_query(query)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result

@router.get("/dashboard-stats")
def get_dashboard_stats(period: str = 'tout', debut: str = None, fin: str = None):
    """Récupère les KPIs et données de graphes (Filtré dynamiquement par période)."""
    
    # 1. Définition du filtre temporel SQL
    where_clause_t = ""
    where_clause_i = ""
    where_clause_m = ""
    
    # Sécurisation des dates (Regex stricte YYYY-MM-DD) pour prévenir les injections SQL "B608"
    valid_date_regex = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    if period == 'custom' and debut and fin:
        if not valid_date_regex.match(debut) or not valid_date_regex.match(fin):
            raise HTTPException(status_code=400, detail="Format de date invalide. Attendu YYYY-MM-DD.")
        where_clause_t = f"DATE(date_heure_depart) >= '{debut}' AND DATE(date_heure_depart) <= '{fin}'"
        where_clause_i = f"DATE(date_incident) >= '{debut}' AND DATE(date_incident) <= '{fin}'"
        where_clause_m = f"DATE(date_debut) >= '{debut}' AND DATE(date_debut) <= '{fin}'"
    elif period == 'semaine_cours':
        where_clause_t = "YEARWEEK(date_heure_depart, 1) = YEARWEEK(CURDATE(), 1)"
        where_clause_i = "YEARWEEK(date_incident, 1) = YEARWEEK(CURDATE(), 1)"
        where_clause_m = "YEARWEEK(date_debut, 1) = YEARWEEK(CURDATE(), 1)"
    elif period == 'semaine_passe':
        where_clause_t = "YEARWEEK(date_heure_depart, 1) = YEARWEEK(CURDATE() - INTERVAL 1 WEEK, 1)"
        where_clause_i = "YEARWEEK(date_incident, 1) = YEARWEEK(CURDATE() - INTERVAL 1 WEEK, 1)"
        where_clause_m = "YEARWEEK(date_debut, 1) = YEARWEEK(CURDATE() - INTERVAL 1 WEEK, 1)"
    elif period == 'mois_cours':
        where_clause_t = "MONTH(date_heure_depart) = MONTH(CURDATE()) AND YEAR(date_heure_depart) = YEAR(CURDATE())"
        where_clause_i = "MONTH(date_incident) = MONTH(CURDATE()) AND YEAR(date_incident) = YEAR(CURDATE())"
        where_clause_m = "MONTH(date_debut) = MONTH(CURDATE()) AND YEAR(date_debut) = YEAR(CURDATE())"
    elif period == 'mois_passe':
        where_clause_t = "MONTH(date_heure_depart) = MONTH(CURDATE() - INTERVAL 1 MONTH) AND YEAR(date_heure_depart) = YEAR(CURDATE() - INTERVAL 1 MONTH)"
        where_clause_i = "MONTH(date_incident) = MONTH(CURDATE() - INTERVAL 1 MONTH) AND YEAR(date_incident) = YEAR(CURDATE() - INTERVAL 1 MONTH)"
        where_clause_m = "MONTH(date_debut) = MONTH(CURDATE() - INTERVAL 1 MONTH) AND YEAR(date_debut) = YEAR(CURDATE() - INTERVAL 1 MONTH)"
    elif period == 'annee_cours':
        where_clause_t = "YEAR(date_heure_depart) = YEAR(CURDATE())"
        where_clause_i = "YEAR(date_incident) = YEAR(CURDATE())"
        where_clause_m = "YEAR(date_debut) = YEAR(CURDATE())"
    elif period == 'annee_passe':
        where_clause_t = "YEAR(date_heure_depart) = YEAR(CURDATE() - INTERVAL 1 YEAR)"
        where_clause_i = "YEAR(date_incident) = YEAR(CURDATE() - INTERVAL 1 YEAR)"
        where_clause_m = "YEAR(date_debut) = YEAR(CURDATE() - INTERVAL 1 YEAR)"
    else: # 'tout' ou fallback
        where_clause_t = "1=1"
        where_clause_i = "1=1"
        where_clause_m = "1=1"

    # Line Chart revenue
    query_revenues = f"""
        SELECT DATE(date_heure_depart) as date_jour, SUM(recette) as total_recette
        FROM trajets
        WHERE {where_clause_t} AND statut = 'termine'
        GROUP BY DATE(date_heure_depart)
        ORDER BY date_jour ASC
    """
    revenues = execute_read_only_query(query_revenues).get('data', [])
    
    # 2. Répartition de la Flotte
    if period == 'tout':
        query_fleet = """
            SELECT statut, COUNT(*) as count 
            FROM vehicules 
            GROUP BY statut
        """
        fleet = execute_read_only_query(query_fleet).get('data', [])
    else:
        # Quand une date est sélectionnée, on affiche les "Évènements" pour les véhicules
        try:
            c_trajets = execute_read_only_query(f"SELECT COUNT(DISTINCT vehicule_immatriculation) as c FROM trajets WHERE {where_clause_t}").get('data', [{}])[0].get('c', 0)
            c_pannes = execute_read_only_query(f"SELECT COUNT(*) as c FROM incidents WHERE {where_clause_i} AND type IN ('panne', 'accident')").get('data', [{}])[0].get('c', 0)
            c_maint = execute_read_only_query(f"SELECT COUNT(*) as c FROM maintenances WHERE {where_clause_m}").get('data', [{}])[0].get('c', 0)
            fleet = [
                {"statut": "actif", "count": c_trajets},
                {"statut": "panne", "count": c_pannes},
                {"statut": "maintenance", "count": c_maint}
            ]
        except:
            fleet = []
    
    # 3. Macro KPIs paramétrés
    query_kpi = f"""
        SELECT 
            (SELECT COUNT(*) FROM trajets WHERE {where_clause_t}) as trajets_mois,
            (SELECT COALESCE(SUM(recette), 0) FROM trajets WHERE {where_clause_t} AND statut = 'termine') as recettes_mois,
            (SELECT COUNT(*) FROM incidents WHERE {where_clause_i}) as incidents_mois
    """
    try:
        kpis = execute_read_only_query(query_kpi).get('data', [{}])[0]
    except Exception:
        kpis = {"trajets_mois":0, "recettes_mois":0, "incidents_mois":0}
    
    return {
        "success": True,
        "revenues_7d": revenues,
        "fleet_status": fleet,
        "kpis": kpis
    }
