from groq import Groq
from ..config import settings
import json
import re

client = Groq(api_key=settings.GROQ_API_KEY)

SCHEMA_BDD = """
Schéma EXACT et VÉRIFIÉ de la base MySQL TranspoBot (colonnes réelles) :

1. vehicules(immatriculation PK VARCHAR, type ENUM('bus','minibus','taxi'), marque VARCHAR, modele VARCHAR, capacite INT, statut ENUM('actif','en_panne','maintenance','hors_service'), kilometrage INT, kilometrage_seuil INT, date_derniere_revision DATE, date_acquisition DATE, created_at TIMESTAMP)
   -- ✅ Bug #7 fix : 'en_panne' est le statut exact pour un véhicule en panne (JAMAIS 'panne' seul)

2. chauffeurs(numero_permis PK VARCHAR, vehicule_immatriculation FK VARCHAR, nom VARCHAR, prenom VARCHAR, email VARCHAR, telephone VARCHAR, categorie_permis VARCHAR, disponibilite TINYINT(1), note_moyenne DECIMAL, date_embauche DATE, created_at TIMESTAMP)
   -- ⚠️ COLONNES EXACTES : s'appellent 'nom' et 'prenom'. JAMAIS 'chauffeur_nom' ou 'chauffeur_prenom' — ces colonnes n'existent pas !
   -- disponibilite=1 → libre. disponibilite=0 → en voyage ou en congé.
   -- JOIN chauffeurs : trajets.chauffeur_permis = chauffeurs.numero_permis

3. lignes(code PK VARCHAR, nom VARCHAR, origine VARCHAR, destination VARCHAR, distance_km DECIMAL, duree_minutes INT)

4. trajets(id_trajet PK INT, ligne_code FK VARCHAR, chauffeur_permis FK VARCHAR, vehicule_immatriculation FK VARCHAR, date_heure_depart DATETIME, date_heure_arrivee DATETIME, statut ENUM('planifie','en_cours','termine','annule'), nb_passagers INT, recette DECIMAL, retard_minutes INT, gestionnaire_email FK VARCHAR, created_at TIMESTAMP)
   -- ⚠️ TRACABILITÉ : gestionnaire_email indique qui a planifié/terminé. JOIN utilisateurs ON trajets.gestionnaire_email = utilisateurs.email (puis u.nom) pour identifier ce gestionnaire.
   -- ⚠️ COMPTABLE : Sommer recette et nb_passagers SEULEMENT si statut = 'termine'.
   -- Pour accéder au nom du chauffeur : JOIN chauffeurs ON trajets.chauffeur_permis = chauffeurs.numero_permis → utiliser chauffeurs.nom, chauffeurs.prenom

5. incidents(id_incident PK INT, trajet_id FK INT, type ENUM('panne','accident','retard','autre'), description TEXT, gravite ENUM('faible','moyen','grave'), cout_reparation DECIMAL, date_incident DATETIME, resolu TINYINT(1), gestionnaire_email FK VARCHAR, created_at TIMESTAMP)
   -- ⚠️ DANGER : incidents n'a PAS de colonne chauffeur_permis. Toujours JOIN trajets ON incidents.trajet_id = trajets.id_trajet

6. maintenances(id_maintenance PK INT, vehicule_immatriculation FK VARCHAR, type_intervention ENUM('vidange','revision','reparation','controle'), date_debut DATE, date_fin DATE, cout DECIMAL, technicien VARCHAR, statut ENUM('en_cours','terminee'), gestionnaire_email FK VARCHAR, created_at TIMESTAMP)

7. arrets(nom PK VARCHAR, adresse VARCHAR, latitude DECIMAL, longitude DECIMAL)

8. ligne_arrets(ligne_code FK VARCHAR, arret_nom FK VARCHAR, ordre INT, temps_estime INT)

9. horaires(id_horaire PK INT, ligne_code FK VARCHAR, heure_depart_theorique TIME, heure_arrivee_theorique TIME, jours_operation VARCHAR, frequence_minutes INT)

10. tarifs(type_client ENUM('normal','etudiant','senior'), ligne_code FK VARCHAR, prix DECIMAL)
    -- ✅ Bug #2 fix : ENUM aligné avec la DB réelle. 'normal'=plein tarif, 'etudiant'=réduit, 'senior'=senior-citoyen

11. utilisateurs(email PK VARCHAR, nom VARCHAR, mot_de_passe_hash VARCHAR, role ENUM('admin','gestionnaire','lecteur'), statut ENUM('en_attente','actif','revoque'), token_activation VARCHAR, token_expiration DATETIME, created_at TIMESTAMP)
    -- Comptes des gestionnaires ERP. Chaque gestionnaire a un email unique.
    -- ✅ Bug #8 fix : colonnes statut, token_activation, token_expiration ajoutées.
    -- ⚠️ ATTENTION : La table utilisateurs NE CONTIENT PAS de colonne 'prenom'. Il n'y a que la colonne 'nom'.
    -- Pour filtrer les comptes actifs : WHERE statut = 'actif'

12. logs_requetes(id_log PK INT, utilisateur_email VARCHAR, question TEXT, sql_genere TEXT, temps_reponse_ms INT, date_requete DATETIME)
    -- ✅ TRAÇABILITÉ GESTIONNAIRES : Chaque requête IA est enregistrée avec l'email du gestionnaire qui l'a posée.
    -- Pour trouver l'identité complète d'un gestionnaire depuis les logs : JOIN utilisateurs ON logs_requetes.utilisateur_email = utilisateurs.email
    -- Exemple de question : "Quel gestionnaire a posé le plus de questions ?" → GROUP BY utilisateur_email, ORDER BY COUNT DESC
    -- Colonne date_requete de type DATETIME pour filtrer par période.


**RÈGLES ABSOLUES ET INFLEXIBLES** :
- Devise = TOUJOURS FCFA, jamais Euros ni Dollars.
- "cette semaine" → YEARWEEK(colonne_date, 1) = YEARWEEK(CURDATE(), 1). Interdit d'utiliser INTERVAL 7 DAY.
- "ce mois" → MONTH(colonne) = MONTH(CURDATE()) AND YEAR(colonne) = YEAR(CURDATE()).
- Colonnes nom/prénom des chauffeurs : chauffeurs.nom et chauffeurs.prenom (sans aucun préfixe).
- Pour avoir le nom complet d'un chauffeur depuis un trajet : toujours JOIN chauffeurs ON trajets.chauffeur_permis = chauffeurs.numero_permis, puis utiliser chauffeurs.nom et chauffeurs.prenom.
- incidents.chauffeur_permis N'EXISTE PAS → toujours passer par trajets.
- logs_requetes.utilisateur_email est l'identifiant du gestionnaire, jointure avec utilisateurs.email. Pour retrouver l'identité du gestionnaire, utiliser UNIQUEMENT la colonne utilisateurs.nom (la colonne prenom n'existe pas pour les utilisateurs!).

Voici des exemples représentatifs du niveau de précision attendu pour l'assistant IA :
- Utilisateur : "Combien de trajets ont été effectués cette semaine ?"
  -> SQL généré : SELECT COUNT(*) FROM trajets WHERE date_heure_depart >= DATE_SUB(NOW(), INTERVAL 7 DAY) AND statut='termine'

- Utilisateur : "Quel chauffeur a le plus d'incidents ce mois-ci ?"
  -> SQL généré : SELECT c.nom, c.prenom, COUNT(i.id_incident) as nb FROM incidents i JOIN trajets t ON i.trajet_id=t.id_trajet JOIN chauffeurs c ON t.chauffeur_permis=c.numero_permis WHERE MONTH(i.date_incident)=MONTH(NOW()) GROUP BY c.numero_permis, c.nom, c.prenom ORDER BY nb DESC LIMIT 1

- Utilisateur : "Mes trajets de la semaine" (si le demandeur est jean@test.com)
  -> SQL généré : SELECT * FROM trajets WHERE gestionnaire_email='jean@test.com' AND date_heure_depart >= DATE_SUB(NOW(), INTERVAL 7 DAY)
"""


def generate_sql_query(question: str, user_email: str = None, error_context: str = None) -> str:
    """Demande à Groq de générer une requête SQL à partir du Schéma."""
    
    system_prompt = f"""Tu es TranspoBot, un ingénieur de données MySQL expert.
Voici le schéma EXACT de la base de données :
{SCHEMA_BDD}

Ton SEUL objectif : Générer la requête SQL demandée par l'utilisateur.
L'utilisateur qui te parle actuellement est le gestionnaire avec l'email : '{user_email}'. S'il demande 'mes trajets', filtre avec ce gestionnaire_email !
8. Règles strictes et Inflexibles :
1. Si l'utilisateur demande de MODIFIER, SUPPRIMER ou AJOUTER des données, OU si sa demande ne concerne absolument PAS l'analyse de données (bonjour, conseils...), réponds EXACTEMENT par le mot-clé : NON_SQL
2. Sinon, réponds UNIQUEMENT par la requête SQL valide (SELECT). AUCUN autre texte, ZERO explication.
3. Ne mets PAS de bloc markdown ```sql ou ```. La sortie doit commencer par SELECT.
4. Seules les requêtes SELECT sont possibles.
5. Tolérance pour les recherches textes avec LOWER(colonne) LIKE '%texte%'.
6. Les colonnes nom et prenom dans la table chauffeurs s'appellent strictement 'nom' et 'prenom'.
7. La table utilisateurs possède UNIQUEMENT 'nom', NE demande jamais u.prenom !
8. 🛑 SÉCURITÉ ABSOLUE : Tu ne dois JAMAIS inclure la colonne `mot_de_passe_hash` dans ta clause SELECT, sous aucun prétexte. Si l'utilisateur demande des infos sur son profil, sélectionne explicitement `SELECT email, nom, role, created_at` pour ignorer le mot de passe.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Question du gestionnaire : {question}"}
    ]
    
    if error_context:
        messages.append({"role": "user", "content": f"Ta précédente requête a échoué.\nErreur MySQL :\n{error_context}\n\nCorrige ton erreur et renvoie UNIQUEMENT la requête SQL corrigée sans aucun markdown."})

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.0
    )
    
    sql_raw = response.choices[0].message.content.strip()
    
    # Sécurité anti-hallucination (supprimer les backticks markdown et la réflexion DeepSeek)
    import re
    sql_raw = re.sub(r'<think>.*?</think>', '', sql_raw, flags=re.DOTALL)
    sql_raw = re.sub(r'(?i)```sql', '', sql_raw)
    sql_raw = re.sub(r'```', '', sql_raw)
    return sql_raw.strip()


def generate_nl_response(question: str, data: list, language: str = "fr", error: str = None, sql_query: str = None) -> str:
    """Génère la réponse narrative bilingue basée sur le JSON et le Schéma de la Base de Données."""
    
    instructions_langue = (
        "Consigne stricte : Tu dois formuler ta réponse finale en FRANÇAIS exclusivement." 
        if language == "fr" else 
        "CRITICAL RULE: YOU MUST GENERATE YOUR ENTIRE RESPONSE AND ANALYSIS IN ENGLISH."
    )
    
    if sql_query == "NON_SQL":
        system_prompt = f"""Tu es 'TranspoBot', l'assistant IA expert de l'application de transport.
{instructions_langue}

RÈGLE ABSOLUE ET CRITIQUE : Tu es un assistant d'ANALYSE (Consultation et Lecture seule). Tu n'as STRICTEMENT AUCUN droit de modifier, créer, ou supprimer des données dans le système.
SI l'utilisateur te demande de créer un trajet, modifier un bus, ou changer une information de la base de données : 
TU DOIS REFUSER IMMEDIATEMENT en 2 ou 3 lignes grand maximum, très poliment, en lui indiquant qu'il doit utiliser les boutons et formulaires de l'interface graphique (ex: bouton "Planifier un Trajet", vue "Flotte" ou "Chauffeurs"). N'invente JAMAIS d'étapes ni de pseudo-réponse détaillée pour une modification.

Sinon, s'il s'agit d'une question/interaction normale :
- De la courtoisie (bonjour, merci).
- Des conseils génériques.
Ton rôle : Réponds brièvement et précisément."""
        context = f"Message de l'utilisateur : {question}"
    else:
        system_prompt = f"""Tu es 'TranspoBot', un analyste de données pertinent.
Un gestionnaire t'a posé une question. Le système a exécuté une requête SQL sur notre base et te fournit les résultats.

Pour t'aider à comprendre le sens des données voici le dictionnaire de données EXACT (MLD) de notre application :
{SCHEMA_BDD}

Ton rôle : Résumer le résultat de façon naturelle et directe en t'appuyant intelligemment sur notre schéma.
{instructions_langue}

Consignes :
1. Sois ultra-concis. Parle comme un vrai analyste au bureau.
2. Ne cite JAMAIS de détails techniques (pas de "Selon le JSON" ni de "D'après la requête SQL").
3. Si la donnée est vide ('[]'), dis simplement qu'il n'y a aucun résultat correspondant.
4. Intègre la donnée trouvée naturellement dans ta réponse (même si les noms de chauffeurs ou matériels semblent factices).
5. Notre domaine est le transport (selon le dictionnaire de données), utilise le vocabulaire approprié. L'argent est en "FCFA".
"""
        if error:
            context = f"Question : {question}\nRequête SQL (échouée) : {sql_query}\nErreur technique :\n{error}\n\nExplique gentiment à l'utilisateur pourquoi la requête a échoué (traduis l'erreur en mots simples) :"
        else:
            context = f"Question : {question}\nRequête exécutée : {sql_query}\nRésultat extrait (JSON) :\n{json.dumps(data, default=str)}\n\nÉcris le compte-rendu :"

    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context}
        ],
        temperature=0.4
    )
    
    nl_raw = response.choices[0].message.content.strip()
    import re
    nl_raw = re.sub(r'<think>.*?</think>', '', nl_raw, flags=re.DOTALL)
    return nl_raw.strip()
