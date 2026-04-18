from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, Literal
from ..database import execute_write_query, execute_read_only_query
from ..security import verify_token
import re

router = APIRouter()

# ==========================================
# 🛡️ SCHÉMAS PYDANTIC (Validation des entrées UI)
# ==========================================
class ChauffeurCreate(BaseModel):
    numero_permis: str = Field(..., max_length=30)
    vehicule_immatriculation: Optional[str] = Field(None, max_length=20)
    nom: str = Field(..., min_length=2, max_length=100)
    prenom: str = Field(..., min_length=2, max_length=100)
    email: EmailStr                          # Validation format email strict
    telephone: str = Field(..., max_length=20)
    categorie_permis: str = Field(default="D", max_length=10)
    disponibilite: bool = True
    date_embauche: Optional[str] = None     # Format YYYY-MM-DD

class VehiculeCreate(BaseModel):
    immatriculation: str = Field(..., max_length=20)
    type: Literal['bus', 'minibus', 'taxi'] = 'bus'  # ✅ Bug #3 fix : conforme ENUM SQL
    marque: str = Field(..., max_length=80)
    modele: str = Field(..., max_length=80)
    capacite: int = Field(..., ge=1, le=300)  # Entre 1 et 300 passagers
    statut: Literal['actif', 'en_panne', 'maintenance', 'hors_service'] = 'actif'  # ✅ Bug #4 fix : conforme ENUM SQL
    kilometrage: int = Field(default=0, ge=0)
    kilometrage_seuil: int = Field(default=150000, ge=0)



# ==========================================
# 🧑‍✈️ GESTION DES CHAUFFEURS (C.R.U.D)
# ==========================================
@router.post("/chauffeurs")
def create_chauffeur(c: ChauffeurCreate):
    """Méthode POST : Permet à l'Administrateur d'embaucher un nouveau Chauffeur."""
    from datetime import date
    date_emb = c.date_embauche if c.date_embauche else str(date.today())
    
    # Validation Anti-Doublon
    check = execute_read_only_query("SELECT 1 FROM chauffeurs WHERE numero_permis = %s", (c.numero_permis,))
    if check.get('data'):
        raise HTTPException(status_code=400, detail=f"Le chauffeur avec le permis '{c.numero_permis}' existe déjà.")
    
    sql = """
        INSERT INTO chauffeurs 
            (numero_permis, vehicule_immatriculation, nom, prenom, email, telephone, 
             categorie_permis, disponibilite, date_embauche)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    params = (
        c.numero_permis,
        c.vehicule_immatriculation or None,
        c.nom,
        c.prenom,
        c.email,
        c.telephone,
        c.categorie_permis,
        c.disponibilite,
        date_emb
    )
    res = execute_write_query(sql, params)
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
    return res

@router.delete("/chauffeurs/{numero_permis}")
def delete_chauffeur(numero_permis: str):
    """Méthode DELETE : Supprime définitivement un chauffeur.
    Règle métier : interdit si le chauffeur a un trajet planifié ou en cours.
    """
    # ─── Fix #1 : Protection — vérif trajets actifs ───────────────────────────
    actifs = execute_read_only_query(
        "SELECT id_trajet, statut FROM trajets "
        "WHERE chauffeur_permis = %s AND statut IN ('planifie', 'en_cours')",
        (numero_permis,)
    )
    if actifs.get('data'):
        nb = len(actifs['data'])
        raise HTTPException(
            status_code=409,
            detail=f"Licenciement refusé : ce chauffeur a {nb} trajet(s) actif(s) "
                   f"(planifié ou en cours). Annulez-les d'abord."
        )
    # ─── Suppression autorisée ─────────────────────────────────────────────────
    sql = "DELETE FROM chauffeurs WHERE numero_permis = %s"
    res = execute_write_query(sql, (numero_permis,))
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
    return res


# ─── Fix #2 : PATCH profil chauffeur ──────────────────────────────────────────
class ChauffeurUpdate(BaseModel):
    """Tous les champs sont optionnels — seuls les champs fournis sont mis à jour."""
    telephone:               Optional[str] = None
    email:                   Optional[str] = None
    vehicule_immatriculation: Optional[str] = None  # None = désaffecter le bus

@router.patch("/chauffeurs/{numero_permis}/modifier")
def modifier_chauffeur(numero_permis: str, data: ChauffeurUpdate):
    """Modifie les coordonnées et/ou le bus assigné d'un chauffeur."""
    # Vérifier existence
    chk = execute_read_only_query(
        "SELECT 1 FROM chauffeurs WHERE numero_permis = %s", (numero_permis,)
    )
    if not chk.get('data'):
        raise HTTPException(status_code=404, detail="Chauffeur introuvable.")

    fields, params = [], []
    if data.telephone is not None:
        fields.append("telephone = %s");                params.append(data.telephone)
    if data.email is not None:
        fields.append("email = %s");                    params.append(data.email)
    if data.vehicule_immatriculation is not None:
        fields.append("vehicule_immatriculation = %s"); params.append(data.vehicule_immatriculation or None)

    if not fields:
        raise HTTPException(status_code=400, detail="Aucun champ à mettre à jour.")

    params.append(numero_permis)
    res = execute_write_query(
        f"UPDATE chauffeurs SET {', '.join(fields)} WHERE numero_permis = %s",
        tuple(params)
    )
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
    return {**res, "message": "Profil chauffeur mis à jour."}


# ─── Fix #5 : PATCH toggle disponibilité (congé / reprise) ────────────────────
class DisponibiliteUpdate(BaseModel):
    disponible: bool

@router.patch("/chauffeurs/{numero_permis}/disponibilite")
def set_disponibilite(numero_permis: str, data: DisponibiliteUpdate):
    """Toggle manuel de la disponibilité (congé maladie, repos, etc.).
    Règle de cohérence : impossible de bloquer un chauffeur avec un trajet en_cours.
    """
    chk = execute_read_only_query(
        "SELECT disponibilite FROM chauffeurs WHERE numero_permis = %s", (numero_permis,)
    )
    if not chk.get('data'):
        raise HTTPException(status_code=404, detail="Chauffeur introuvable.")

    # Si on veut bloquer, vérifier qu'il n'est pas en cours de trajet
    if not data.disponible:
        trajet_actif = execute_read_only_query(
            "SELECT id_trajet FROM trajets WHERE chauffeur_permis = %s AND statut = 'en_cours'",
            (numero_permis,)
        )
        if trajet_actif.get('data'):
            raise HTTPException(
                status_code=409,
                detail="Impossible de mettre en congé : ce chauffeur est actuellement en trajet (en_cours)."
            )

    res = execute_write_query(
        "UPDATE chauffeurs SET disponibilite = %s WHERE numero_permis = %s",
        (data.disponible, numero_permis)
    )
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
    label = "Chauffeur disponible." if data.disponible else "Chauffeur mis en congé/indisponible."
    return {**res, "message": label}

# ==========================================
# 🚐 GESTION DE LA FLOTTE (C.R.U.D)
# ==========================================
@router.post("/vehicules")
def create_vehicule(v: VehiculeCreate):
    """Méthode POST : Ajoute un tout nouveau bus dans le parc automobile."""
    # Validation Anti-Doublon
    check = execute_read_only_query("SELECT 1 FROM vehicules WHERE immatriculation = %s", (v.immatriculation,))
    if check.get('data'):
        raise HTTPException(status_code=400, detail=f"Le véhicule '{v.immatriculation}' existe déjà.")
        
    sql = """
        INSERT INTO vehicules (immatriculation, type, marque, modele, capacite, statut, kilometrage, kilometrage_seuil)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    params = (v.immatriculation, v.type, v.marque, v.modele, v.capacite, v.statut, v.kilometrage, v.kilometrage_seuil)
    res = execute_write_query(sql, params)
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
    return res

@router.delete("/vehicules/{immatriculation}")
def delete_vehicule(immatriculation: str):
    """Méthode DELETE : Détruit un véhicule."""
    # ─── Fix Sécurité — vérif trajets actifs ───────────────────────────
    actifs = execute_read_only_query(
        "SELECT id_trajet FROM trajets "
        "WHERE vehicule_immatriculation = %s AND statut IN ('planifie', 'en_cours')",
        (immatriculation,)
    )
    if actifs.get('data'):
        nb = len(actifs['data'])
        raise HTTPException(
            status_code=409,
            detail=f"Opération refusée : ce véhicule est actuellement assigné à {nb} trajet(s) (planifié ou en cours)."
        )

    sql = "DELETE FROM vehicules WHERE immatriculation = %s"
    res = execute_write_query(sql, (immatriculation,))
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
    return res

# ==========================================
# 🛣️ GESTION DES LIGNES (C.R.U.D)
# ==========================================
class LigneCreate(BaseModel):
    code: str
    nom: str
    origine: str
    destination: str
    distance_km: Optional[float] = None
    duree_minutes: Optional[int] = None
    prix: Optional[float] = 0.0

@router.post("/lignes")
def create_ligne(l: LigneCreate):
    """Méthode POST : Crée une nouvelle ligne de transport et définit son tarif normal."""
    # Validation Anti-Doublon
    check = execute_read_only_query("SELECT 1 FROM lignes WHERE code = %s", (l.code,))
    if check.get('data'):
        raise HTTPException(status_code=400, detail=f"La ligne '{l.code}' existe déjà.")

    sql = """
        INSERT INTO lignes (code, nom, origine, destination, distance_km, duree_minutes)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    res = execute_write_query(sql, (l.code, l.nom, l.origine, l.destination, l.distance_km, l.duree_minutes))
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
        
    # Insertion du tarif
    if l.prix is not None and l.prix > 0:
        sql_tarif = "INSERT INTO tarifs (type_client, ligne_code, prix) VALUES ('normal', %s, %s)"
        execute_write_query(sql_tarif, (l.code, l.prix))
        
    return res

@router.delete("/lignes/{code}")
def delete_ligne(code: str):
    """Méthode DELETE : Supprime une ligne du réseau."""
    # ─── Fix Sécurité — vérif trajets actifs ou historiques ────────────────────
    check = execute_read_only_query("SELECT 1 FROM trajets WHERE ligne_code = %s", (code,))
    if check.get('data'):
        raise HTTPException(
            status_code=409, 
            detail="Opération refusée : cette ligne possède un historique de trajets. Elle ne peut être supprimée."
        )

    res = execute_write_query("DELETE FROM lignes WHERE code = %s", (code,))
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
    return res

# ==========================================
# 🚌 GESTION DES TRAJETS (C.R.U.D)
# ==========================================
class TrajetCreate(BaseModel):
    ligne_code: str
    chauffeur_permis: str
    vehicule_immatriculation: str
    date_heure_depart: str  # Format 'YYYY-MM-DD HH:MM'
    nb_passagers: int = 0

@router.post("/trajets")
def create_trajet(t: TrajetCreate, user: dict = Depends(verify_token)):
    """Méthode POST : Planifie un nouveau trajet."""
    # 0. Règle Métier : Anti-Fatigue Chauffeur (Max 8h/24h)
    check_fatigue = execute_read_only_query("""
        SELECT COALESCE(SUM(l.duree_minutes), 0) as duree_24h
        FROM trajets tr
        JOIN lignes l ON tr.ligne_code = l.code
        WHERE tr.chauffeur_permis = %s AND tr.date_heure_depart >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
    """, (t.chauffeur_permis,))
    duree_cumulative = int(check_fatigue.get('data', [{'duree_24h': 0}])[0].get('duree_24h') or 0)
    
    ligne = execute_read_only_query("SELECT duree_minutes FROM lignes WHERE code = %s", (t.ligne_code,))
    duree_nouveau = int(ligne.get('data', [{'duree_minutes': 0}])[0].get('duree_minutes') or 0)
    
    if (duree_cumulative + duree_nouveau) > 480:
        raise HTTPException(
            status_code=409, 
            detail=f"Sécurité : Ce chauffeur a déjà {duree_cumulative}min de route sur 24h. L'ajout de ce trajet dépasse la limite de 8h (480min)."
        )

    # 1. Règle Métier : Anti-Collision Spatio-Temporelle (Double-Booking)
    query_collision = """
        SELECT tr.id_trajet, tr.vehicule_immatriculation, tr.chauffeur_permis, tr.statut 
        FROM trajets tr
        JOIN lignes l ON tr.ligne_code = l.code
        WHERE tr.statut IN ('planifie', 'en_cours')
        AND (tr.chauffeur_permis = %s OR tr.vehicule_immatriculation = %s)
        AND %s < DATE_ADD(tr.date_heure_depart, INTERVAL l.duree_minutes MINUTE)
        AND DATE_ADD(%s, INTERVAL %s MINUTE) > tr.date_heure_depart
    """
    collisions = execute_read_only_query(
        query_collision, 
        (t.chauffeur_permis, t.vehicule_immatriculation, 
         t.date_heure_depart, t.date_heure_depart, duree_nouveau)
    )
    if collisions.get('data'):
        conflict = collisions['data'][0]
        conflit_msg = f"Double-booking détecté ! Ce créneau chevauche le trajet #{conflict['id_trajet']} ({conflict['statut']}). "
        if conflict['chauffeur_permis'] == t.chauffeur_permis:
            conflit_msg += "Le chauffeur sera sur la route durant cette tranche horaire."
        else:
            conflit_msg += "Le véhicule est déjà réquisitionné pour cette plage horaire."
        raise HTTPException(status_code=409, detail=conflit_msg)

    # 2. Vérification Chauffeur Disponible (Global)
    check_c = execute_read_only_query(
        "SELECT disponibilite FROM chauffeurs WHERE numero_permis = %s", 
        (t.chauffeur_permis,)
    )
    if not check_c.get('data'):
        raise HTTPException(status_code=400, detail="Action refusée : Le chauffeur sélectionné n'existe pas.")
    if not check_c['data'][0]['disponibilite']:
        raise HTTPException(status_code=400, detail="Action refusée : Ce chauffeur est actuellement indisponible.")

    # 2.5 Vérification Véhicule Disponible (Statut technique)
    check_v = execute_read_only_query(
        "SELECT statut FROM vehicules WHERE immatriculation = %s", 
        (t.vehicule_immatriculation,)
    )
    if not check_v.get('data'):
        raise HTTPException(status_code=400, detail="Action refusée : Le véhicule sélectionné n'existe pas.")
    statut_v = check_v['data'][0]['statut'].lower()
    if 'panne' in statut_v or 'maintenance' in statut_v or 'hors' in statut_v:
        raise HTTPException(status_code=400, detail=f"Saisie impossible : Le bus {t.vehicule_immatriculation} ne peut pas rouler (Statut technique : {statut_v}).")


    # 2. Création du Trajet
    sql = """
        INSERT INTO trajets (ligne_code, chauffeur_permis, vehicule_immatriculation, date_heure_depart, nb_passagers, gestionnaire_email)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    res = execute_write_query(sql, (t.ligne_code, t.chauffeur_permis, t.vehicule_immatriculation, t.date_heure_depart, t.nb_passagers, user.get('sub')))
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
        
    # 3. Règle Métier : Bloquer le chauffeur (Indisponible)
    execute_write_query("UPDATE chauffeurs SET disponibilite = FALSE WHERE numero_permis = %s", (t.chauffeur_permis,))
    return res

@router.patch("/trajets/{id_trajet}/statut")
def update_trajet_statut(id_trajet: int, statut: str, user: dict = Depends(verify_token)):
    """
    ⚠️  Bug #9 fix : Endpoint restreint — transitions autorisées UNIQUEMENT.
    Pour démarrer/terminer/annuler, utiliser les endpoints spécialisés.
    Seule transition permise ici : planifie → annule (cas d'urgence admin).
    """
    from ..database import execute_read_only_query
    
    check = execute_read_only_query("SELECT statut, chauffeur_permis FROM trajets WHERE id_trajet = %s", (id_trajet,))
    if not check.get('data'):
        raise HTTPException(status_code=404, detail="Trajet introuvable.")
    
    statut_actuel = check['data'][0]['statut']
    chauffeur_permis = check['data'][0]['chauffeur_permis']
    
    if statut_actuel in ('termine', 'annule'):
        raise HTTPException(
            status_code=403,
            detail=f"Règle métier : le trajet est '{statut_actuel}'. Il ne peut plus être modifié (document comptable protégé)."
        )
    
    # ✅ Transitions strictes : les régressions (termine→planifie) sont interdites
    transitions_valides = {
        'planifie':  ['annule'],
        'en_cours':  ['annule'],
    }
    if statut not in transitions_valides.get(statut_actuel, []):
        raise HTTPException(
            status_code=422,
            detail=f"Transition interdite : '{statut_actuel}' → '{statut}'. "
                   f"Utilisez les endpoints /demarrer, /terminer ou /annuler."
        )
    
    sql = "UPDATE trajets SET statut = %s, gestionnaire_email = %s WHERE id_trajet = %s"
    res = execute_write_query(sql, (statut, user.get('sub'), id_trajet))
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
    # Libérer le chauffeur si annulé
    execute_write_query("UPDATE chauffeurs SET disponibilite = TRUE WHERE numero_permis = %s", (chauffeur_permis,))
    return res

@router.delete("/trajets/{id_trajet}")
def delete_trajet(id_trajet: int):
    """Méthode DELETE. Règle métier : seul un trajet 'planifie' peut être supprimé."""
    from ..database import execute_read_only_query
    
    # Vérifier le statut actuel pour libérer le chauffeur
    check = execute_read_only_query("SELECT statut, chauffeur_permis FROM trajets WHERE id_trajet = %s", (id_trajet,))
    if not check.get('data'):
        raise HTTPException(status_code=404, detail="Trajet introuvable.")
    
    statut_actuel = check['data'][0]['statut']
    chauffeur_permis = check['data'][0]['chauffeur_permis']
    
    # Règle Métier : seul un trajet planifié peut être annulé/supprimé
    if statut_actuel != 'planifie':
        raise HTTPException(
            status_code=403,
            detail=f"Règle métier : impossible de supprimer un trajet '{statut_actuel}'. Seul un trajet 'planifie' peut l'être."
        )
    
    res = execute_write_query("DELETE FROM trajets WHERE id_trajet = %s", (id_trajet,))
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
        
    # Règle Métier : Libérer le profil du chauffeur suite à la suppression du trajet planifié
    execute_write_query("UPDATE chauffeurs SET disponibilite = TRUE WHERE numero_permis = %s", (chauffeur_permis,))
    
    return res

# ==========================================
# 🚦 MACHINE À ÉTATS TRAJETS (Transitions strictes)
# ==========================================

class TrajetModifier(BaseModel):
    """Payload de réassignation — trajet PLANIFIÉ uniquement."""
    ligne_code: Optional[str] = None
    chauffeur_permis: Optional[str] = None
    vehicule_immatriculation: Optional[str] = None
    date_heure_depart: Optional[str] = None

class TrajetCloturer(BaseModel):
    """Payload de clôture — données opérationnelles uniquement, recette calculée par DB."""
    date_heure_arrivee: str
    retard_minutes: int = 0

@router.patch("/trajets/{id_trajet}/demarrer")
def demarrer_trajet(id_trajet: int, user: dict = Depends(verify_token)):
    """planifie → en_cours. Enregistre heure de départ réelle et le gestionnaire."""
    from datetime import datetime
    check = execute_read_only_query(
        "SELECT statut, chauffeur_permis, date_heure_depart FROM trajets WHERE id_trajet = %s", (id_trajet,)
    )
    if not check.get('data'):
        raise HTTPException(status_code=404, detail="Trajet introuvable.")
    row = check['data'][0]
    if row['statut'] != 'planifie':
        raise HTTPException(status_code=422,
            detail=f"Impossible de démarrer : statut actuel '{row['statut']}'. Seul 'planifie' peut démarrer.")
            
    # Vérification stricte Heure
    maintenant = datetime.now()
    if isinstance(row['date_heure_depart'], str):
        date_depart = datetime.strptime(row['date_heure_depart'], '%Y-%m-%d %H:%M:%S')
    else:
        date_depart = row['date_heure_depart']
        
    if maintenant < date_depart:
        raise HTTPException(status_code=403,
            detail=f"Action refusée : le trajet est prévu pour le {date_depart.strftime('%d/%m/%Y %H:%M')}. Il ne peut pas démarrer en avance.")

    now_str = maintenant.strftime('%Y-%m-%d %H:%M:%S')
    res = execute_write_query(
        "UPDATE trajets SET statut='en_cours', date_heure_depart=%s, gestionnaire_email=%s WHERE id_trajet=%s",
        (now_str, user.get('sub'), id_trajet)
    )
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
    return {**res, "message": "Trajet démarré. Chauffeur en route."}

@router.patch("/trajets/{id_trajet}/terminer")
def terminer_trajet(id_trajet: int, data: TrajetCloturer, user: dict = Depends(verify_token)):
    """en_cours → termine. Collecte financière avec anti-fraude, met à jour km bus et maintenance préventive auto."""
    check = execute_read_only_query(
        "SELECT statut, chauffeur_permis, vehicule_immatriculation, ligne_code FROM trajets WHERE id_trajet = %s", (id_trajet,)
    )
    if not check.get('data'):
        raise HTTPException(status_code=404, detail="Trajet introuvable.")
    row = check['data'][0]
    if row['statut'] != 'en_cours':
        raise HTTPException(status_code=422,
            detail=f"Clôture impossible : statut actuel '{row['statut']}'. Seul 'en_cours' peut être terminé.")
            
    # Plus de contrôle anti-fraude sur recette car la BD gère la recette via trigger.

    res = execute_write_query(
        """UPDATE trajets SET statut='termine', date_heure_arrivee=%s,
           retard_minutes=%s, gestionnaire_email=%s WHERE id_trajet=%s""",
        (data.date_heure_arrivee, data.retard_minutes, user.get('sub'), id_trajet)
    )
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
        
    # Libérer le chauffeur
    execute_write_query("UPDATE chauffeurs SET disponibilite=TRUE WHERE numero_permis=%s", (row['chauffeur_permis'],))
    
    # Incrémenter kilométrage bus (distance de la ligne) ET maintenance préventive auto
    km_info = execute_read_only_query(
        """SELECT v.kilometrage, v.kilometrage_seuil, l.distance_km 
           FROM vehicules v 
           JOIN lignes l ON l.code = %s 
           WHERE v.immatriculation = %s""", (row['ligne_code'], row['vehicule_immatriculation'])
    )
    if km_info.get('data'):
        v = km_info['data'][0]
        dist = int(v.get('distance_km') or 0)
        nouveau_km = int(v.get('kilometrage') or 0) + dist
        seuil = int(v.get('kilometrage_seuil') or 0)
        
        if nouveau_km >= seuil and seuil > 0:
            # Passe en maintenance et créer ticket
            execute_write_query("UPDATE vehicules SET kilometrage = %s, statut = 'maintenance' WHERE immatriculation = %s", (nouveau_km, row['vehicule_immatriculation']))
            execute_write_query("""
                INSERT INTO maintenances (vehicule_immatriculation, type_intervention, date_debut, cout, technicien, statut)
                VALUES (%s, 'revision', CURDATE(), NULL, 'Non assigné auto', 'en_cours')
            """, (row['vehicule_immatriculation'],))
        else:
            execute_write_query("UPDATE vehicules SET kilometrage = %s WHERE immatriculation = %s", (nouveau_km, row['vehicule_immatriculation']))
    # Fix #3 : Recalculer note_moyenne (5 etoiles si 0 retard, -1 par 10min, plancher 1)
    execute_write_query(
        """
        UPDATE chauffeurs
        SET note_moyenne = (
            SELECT ROUND(GREATEST(1.0, 5.0 - AVG(retard_minutes) / 10.0), 1)
            FROM trajets
            WHERE chauffeur_permis = %s AND statut = 'termine'
        )
        WHERE numero_permis = %s
        """,
        (row['chauffeur_permis'], row['chauffeur_permis'])
    )
    return {**res, "message": "Trajet cloture. Chauffeur libere. Note recalculee. Kilometrage mis a jour."}

@router.patch("/trajets/{id_trajet}/annuler")
def annuler_trajet(id_trajet: int, user: dict = Depends(verify_token)):
    """Annule depuis planifie OU en_cours. Libère toujours chauffeur."""
    check = execute_read_only_query(
        "SELECT statut, chauffeur_permis FROM trajets WHERE id_trajet = %s", (id_trajet,)
    )
    if not check.get('data'):
        raise HTTPException(status_code=404, detail="Trajet introuvable.")
    row = check['data'][0]
    if row['statut'] in ('termine', 'annule'):
        raise HTTPException(status_code=422,
            detail=f"Annulation impossible : trajet '{row['statut']}' (document comptable protégé).")
    res = execute_write_query(
        "UPDATE trajets SET statut='annule', gestionnaire_email=%s WHERE id_trajet=%s",
        (user.get('sub'), id_trajet)
    )
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
    execute_write_query("UPDATE chauffeurs SET disponibilite=TRUE WHERE numero_permis=%s", (row['chauffeur_permis'],))
    return {**res, "message": "Trajet annulé. Chauffeur libéré."}

@router.patch("/trajets/{id_trajet}/modifier")
def modifier_trajet(id_trajet: int, data: TrajetModifier, user: dict = Depends(verify_token)):
    """Modifie un trajet PLANIFIÉ : swap chauffeur/bus, horaire, ligne."""
    check = execute_read_only_query(
        "SELECT statut, chauffeur_permis FROM trajets WHERE id_trajet = %s", (id_trajet,)
    )
    if not check.get('data'):
        raise HTTPException(status_code=404, detail="Trajet introuvable.")
    row = check['data'][0]
    if row['statut'] != 'planifie':
        raise HTTPException(status_code=422,
            detail=f"Modification impossible : statut '{row['statut']}'. Seul 'planifie' est modifiable.")
    if data.chauffeur_permis and data.chauffeur_permis != row['chauffeur_permis']:
        chk = execute_read_only_query(
            "SELECT disponibilite FROM chauffeurs WHERE numero_permis = %s", (data.chauffeur_permis,)
        )
        if not chk.get('data'):
            raise HTTPException(status_code=400, detail="Nouveau chauffeur introuvable en base.")
        if not chk['data'][0]['disponibilite']:
            raise HTTPException(status_code=400, detail="Nouveau chauffeur indisponible (déjà sur un trajet).")
        execute_write_query("UPDATE chauffeurs SET disponibilite=TRUE  WHERE numero_permis=%s", (row['chauffeur_permis'],))
        execute_write_query("UPDATE chauffeurs SET disponibilite=FALSE WHERE numero_permis=%s", (data.chauffeur_permis,))
    fields, params = ["gestionnaire_email=%s"], [user.get('sub')]
    if data.ligne_code:               fields.append("ligne_code=%s");                  params.append(data.ligne_code)
    if data.chauffeur_permis:         fields.append("chauffeur_permis=%s");             params.append(data.chauffeur_permis)
    if data.vehicule_immatriculation: fields.append("vehicule_immatriculation=%s");     params.append(data.vehicule_immatriculation)
    if data.date_heure_depart:        fields.append("date_heure_depart=%s");            params.append(data.date_heure_depart)
    params.append(id_trajet)
    res = execute_write_query(f"UPDATE trajets SET {', '.join(fields)} WHERE id_trajet=%s", tuple(params))
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
    return {**res, "message": "Trajet réassigné avec succès."}

# ==========================================
# ⚠️ GESTION DES INCIDENTS (C.R.U.D)
# ==========================================
class IncidentCreate(BaseModel):
    trajet_id: int
    type: Literal['panne', 'accident', 'retard', 'autre']  # ✅ Bug #5 fix : conforme ENUM SQL
    description: str
    gravite: Literal['faible', 'moyen', 'grave'] = 'faible'  # ✅ Bug #5 fix : conforme ENUM SQL
    cout_reparation: Optional[float] = 0
    date_incident: Optional[str] = None  # Auto = now si vide

@router.post("/incidents")
def create_incident(inc: IncidentCreate, user: dict = Depends(verify_token)):
    """Méthode POST : Signale un incident sur un trajet avec Logique Métier."""
    from datetime import datetime
    date_inc = inc.date_incident if inc.date_incident else datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 1. Insertion classique de l'incident
    sql = """
        INSERT INTO incidents (trajet_id, type, description, gravite, cout_reparation, date_incident, gestionnaire_email)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    res = execute_write_query(sql, (inc.trajet_id, inc.type, inc.description, inc.gravite, inc.cout_reparation or 0, date_inc, user.get('sub')))
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
        
    # 2. Logique Métier : Répercussion sur le véhicule si grave
    if inc.gravite == 'grave' or inc.type in ('panne', 'accident'):
        from ..database import execute_read_only_query
        bus_check = execute_read_only_query(
            "SELECT vehicule_immatriculation FROM trajets WHERE id_trajet = %s", 
            (inc.trajet_id,)
        )
        if bus_check.get('data') and bus_check['data'][0].get('vehicule_immatriculation'):
            immat = bus_check['data'][0]['vehicule_immatriculation']
            
            # Bloquer le véhicule — ✅ Bug #1 fix : 'en_panne' conforme ENUM SQL
            execute_write_query("UPDATE vehicules SET statut='en_panne' WHERE immatriculation = %s", (immat,))
            
            # Créer un ticket de maintenance auto
            execute_write_query("""
                INSERT INTO maintenances (vehicule_immatriculation, type_intervention, date_debut, cout, technicien, statut)
                VALUES (%s, %s, %s, NULL, 'Non assigné', 'en_cours')
            """, (immat, 'reparation', date_inc.split(' ')[0]))
            
    return res

class IncidentResoudre(BaseModel):
    cout_reparation: float

@router.patch("/incidents/{id_incident}/resoudre")
def resoudre_incident(id_incident: int, data: IncidentResoudre, user: dict = Depends(verify_token)):
    """Méthode PATCH : Marque un incident comme résolu avec affectation du coût final."""
    res = execute_write_query(
        "UPDATE incidents SET resolu = TRUE, cout_reparation = %s, gestionnaire_email = %s WHERE id_incident = %s", 
        (data.cout_reparation, user.get('sub'), id_incident)
    )
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
    return res

@router.delete("/incidents/{id_incident}")
def delete_incident(id_incident: int):
    """Méthode DELETE : Supprime un incident."""
    check = execute_read_only_query("SELECT resolu FROM incidents WHERE id_incident = %s", (id_incident,))
    if check.get('data') and check['data'][0].get('resolu'):
        raise HTTPException(
            status_code=409,
            detail="Opération refusée : cet incident est déjà résolu. Impossible de supprimer une archive."
        )

    res = execute_write_query("DELETE FROM incidents WHERE id_incident = %s", (id_incident,))
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
    return res

# ==========================================
# 🔧 GESTION DES MAINTENANCES (C.R.U.D)
# ==========================================
class MaintenanceCreate(BaseModel):
    vehicule_immatriculation: str
    type_intervention: Literal['vidange', 'revision', 'reparation', 'controle']  # ✅ Bug #6 fix : conforme ENUM SQL
    date_debut: str
    date_fin: Optional[str] = None
    cout: Optional[float] = None
    technicien: Optional[str] = None

@router.post("/maintenances")
def create_maintenance(m: MaintenanceCreate, user: dict = Depends(verify_token)):
    """Méthode POST : Enregistre une nouvelle intervention de maintenance."""
    from ..database import execute_read_only_query
    
    # Règle Métier : Interdire si le bus est actuellement en trajet
    check = execute_read_only_query(
        "SELECT 1 FROM trajets WHERE vehicule_immatriculation = %s AND statut = 'en_cours'",
        (m.vehicule_immatriculation,)
    )
    if check.get('data'):
        raise HTTPException(
            status_code=409, 
            detail="Maintenance bloquée : Ce véhicule est actuellement en cours de trajet."
        )

    sql = """
        INSERT INTO maintenances (vehicule_immatriculation, type_intervention, date_debut, date_fin, cout, technicien, gestionnaire_email)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    res = execute_write_query(sql, (m.vehicule_immatriculation, m.type_intervention, m.date_debut, m.date_fin, m.cout, m.technicien, user.get('sub')))
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
    # Passer le véhicule en statut 'maintenance'
    execute_write_query("UPDATE vehicules SET statut='maintenance' WHERE immatriculation = %s", (m.vehicule_immatriculation,))
    return res

class MaintenanceCloturer(BaseModel):
    cout: float
    technicien: str

@router.patch("/maintenances/{id_maintenance}/terminer")
def terminer_maintenance(id_maintenance: int, data: MaintenanceCloturer, user: dict = Depends(verify_token)):
    """Méthode PATCH : Clôture une maintenance et remet le véhicule en service."""
    from datetime import date
    from ..database import execute_read_only_query
    
    # ✅ Bug #10 fix : vérification 404 avant toute opération
    veh = execute_read_only_query(
        "SELECT vehicule_immatriculation, statut FROM maintenances WHERE id_maintenance = %s", 
        (id_maintenance,)
    )
    if not veh.get('data'):
        raise HTTPException(status_code=404, detail="Maintenance introuvable.")
    if veh['data'][0].get('statut') == 'terminee':
        raise HTTPException(status_code=409, detail="Cette maintenance est déjà clôturée.")

    res = execute_write_query(
        "UPDATE maintenances SET statut='terminee', date_fin=%s, cout=%s, technicien=%s, gestionnaire_email=%s WHERE id_maintenance=%s",
        (str(date.today()), data.cout, data.technicien, user.get('sub'), id_maintenance)
    )
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
    immat = veh['data'][0]['vehicule_immatriculation']
    execute_write_query(
        "UPDATE vehicules SET statut='actif', date_derniere_revision=%s WHERE immatriculation=%s",
        (str(date.today()), immat)
    )
    return res

@router.delete("/maintenances/{id_maintenance}")
def delete_maintenance(id_maintenance: int):
    """Méthode DELETE : Supprime une fiche de maintenance."""
    check = execute_read_only_query("SELECT statut FROM maintenances WHERE id_maintenance = %s", (id_maintenance,))
    if check.get('data') and check['data'][0].get('statut') == 'terminee':
        raise HTTPException(
            status_code=409,
            detail="Opération refusée : cette maintenance est déjà terminée. L'historique des coûts doit être conservé."
        )

    res = execute_write_query("DELETE FROM maintenances WHERE id_maintenance = %s", (id_maintenance,))
    if not res.get('success'):
        raise HTTPException(status_code=400, detail=res.get('error'))
    return res

