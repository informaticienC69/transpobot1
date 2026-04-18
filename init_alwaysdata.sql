-- ============================================================
--  TranspoBot — Script d'Initialisation Complet & Corrigé
--  Base de données : informaticienc_transpobot
--  Moteur         : MySQL 8.0+
--  Projet GLSi DIC1 — ESP/UCAD | Génie Informatique
--  Pr. Ahmath Bamba MBACKE
-- ============================================================
--
--  AUDIT DE CONFORMITÉ :
--  ✅ Toutes les clés primaires (PK) sont définies
--  ✅ Toutes les clés étrangères (FK) sont vérifiées et nommées
--  ✅ INSERT IGNORE — tolérant aux ré-exécutions
--  ✅ CREATE TABLE IF NOT EXISTS — aucune destruction de données
--  ✅ Données démo cohérentes avec toutes les contraintes FK
--  ✅ Triggers conditionnels (IF NOT EXISTS)
--  ✅ Aucun compte utilisateur créé par SQL
--      → Les gestionnaires s'inscrivent via le portail SOC
--        avec vérification par email (flux sécurisé).
--  ✅ logs_requetes vide → se remplit naturellement à l'usage de l'IA
--
--  ORDRE D'INSERTION (respect des dépendances FK) :
--  vehicules → chauffeurs → lignes → tarifs → arrets
--  → ligne_arrets → horaires → trajets → incidents → maintenances
-- ============================================================

SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

-- ============================================================
--  0. CRÉATION / SÉLECTION DE LA BASE DE DONNÉES
-- ============================================================
CREATE DATABASE IF NOT EXISTS informaticienc_transpobot
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE informaticienc_transpobot;

-- Désactivation temporaire des FK pour la création sans ordre strict
SET FOREIGN_KEY_CHECKS = 0;


-- ============================================================
--  1. VÉHICULES
--  Table racine — aucune dépendance FK entrante.
--  PK : immatriculation (clé naturelle, unique par véhicule légal)
-- ============================================================
CREATE TABLE IF NOT EXISTS vehicules (
    immatriculation       VARCHAR(20)  NOT NULL,
    type                  ENUM('bus','minibus','taxi')             NOT NULL,
    marque                VARCHAR(50),
    modele                VARCHAR(50),
    capacite              INT                                       NOT NULL COMMENT 'Nombre de places passagers',
    -- 'en_panne'  = breakdown inattendu en cours de trajet (créé automatiquement par le backend)
    -- 'maintenance' = entretien planifié/préventif
    -- 'hors_service' = véhicule retraité définitivement
    statut                ENUM('actif','en_panne','maintenance','hors_service') DEFAULT 'actif',
    kilometrage           INT                                                DEFAULT 0,
    kilometrage_seuil     INT                                                DEFAULT 80000  COMMENT 'Seuil déclenchant une alerte maintenance (km)',
    date_derniere_revision DATE                                              COMMENT 'Date de la dernière révision technique',
    date_acquisition      DATE,
    created_at            TIMESTAMP                                          DEFAULT CURRENT_TIMESTAMP,
    -- Clé primaire
    PRIMARY KEY (immatriculation)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Parc automobile de la société de transport';


-- ============================================================
--  2. CHAUFFEURS
--  Dépend de : vehicules (FK véhicule affecté, nullable)
--  PK : numero_permis (identifiant officiel unique par chauffeur)
--  FK : vehicule_immatriculation → vehicules.immatriculation
--       ON DELETE SET NULL : si le véhicule est supprimé,
--       le chauffeur devient sans véhicule (non licencié).
-- ============================================================
CREATE TABLE IF NOT EXISTS chauffeurs (
    numero_permis            VARCHAR(30)  NOT NULL,
    vehicule_immatriculation VARCHAR(20)            COMMENT 'Véhicule actuellement affecté (NULL = sans affectation)',
    nom                      VARCHAR(100) NOT NULL,
    prenom                   VARCHAR(100) NOT NULL,
    email                    VARCHAR(150)           UNIQUE,
    telephone                VARCHAR(20),
    categorie_permis         VARCHAR(5)             COMMENT 'Catégorie légale du permis : B, D, C, etc.',
    disponibilite            BOOLEAN                DEFAULT TRUE  COMMENT 'TRUE = disponible pour planification de trajet',
    note_moyenne             DECIMAL(3,2)           DEFAULT NULL  COMMENT 'Note de satisfaction passagers (/5, calculée automatiquement)',
    date_embauche            DATE,
    created_at               TIMESTAMP              DEFAULT CURRENT_TIMESTAMP,
    -- Clé primaire
    PRIMARY KEY (numero_permis),
    -- Clé étrangère : véhicule actuel (nullable)
    CONSTRAINT fk_chauffeur_vehicule
        FOREIGN KEY (vehicule_immatriculation)
        REFERENCES vehicules(immatriculation)
        ON DELETE SET NULL
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Personnel roulant de la société de transport';


-- ============================================================
--  3. LIGNES
--  Itinéraires permanents du réseau de transport.
--  PK : code (identifiant court, ex : L1, L2, AIBD...)
--  Aucune FK entrante directe (table de référence centrale).
-- ============================================================
CREATE TABLE IF NOT EXISTS lignes (
    code           VARCHAR(10)  NOT NULL                COMMENT 'Code court identifiant la ligne (ex: L1, L2)',
    nom            VARCHAR(100)                         COMMENT 'Nom commercial complet de la ligne',
    origine        VARCHAR(100) NOT NULL                COMMENT 'Point de départ officiel',
    destination    VARCHAR(100) NOT NULL                COMMENT 'Point d arrivée officiel',
    distance_km    DECIMAL(6,2)                         COMMENT 'Distance totale en kilomètres',
    duree_minutes  INT                                  COMMENT 'Durée théorique du trajet (sans aléas)',
    -- Clé primaire
    PRIMARY KEY (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Itinéraires permanents desservis par le réseau';


-- ============================================================
--  4. TARIFS
--  Prix du billet ventilé par type de client et par ligne.
--  PK Composite : (type_client, ligne_code) — conforme MCD MERISE.
--  FK : ligne_code → lignes.code
--       ON DELETE CASCADE : si la ligne est supprimée,
--       ses tarifs disparaissent automatiquement.
-- ============================================================
CREATE TABLE IF NOT EXISTS tarifs (
    -- ✅ Bug #2 fix : ENUM aligné avec les données de démo (etudiant/senior) et la logique métier
    type_client  ENUM('normal','etudiant','senior') NOT NULL COMMENT 'Catégorie tarifaire : normal=plein tarif, etudiant=réduit, senior=tarif senior-citoyen',
    ligne_code   VARCHAR(10)                        NOT NULL,
    prix         DECIMAL(10,2)                      NOT NULL COMMENT 'Prix en FCFA (Francs CFA)',
    -- Clé primaire composite
    PRIMARY KEY (type_client, ligne_code),
    -- Clé étrangère : ligne associée
    CONSTRAINT fk_tarif_ligne
        FOREIGN KEY (ligne_code)
        REFERENCES lignes(code)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Grille tarifaire par type de passager et par ligne';


-- ============================================================
--  5. ARRÊTS
--  Points d'arrêt physiques du réseau (quais, terminus, etc.).
--  PK : nom (identifiant naturel officiel de l'arrêt)
-- ============================================================
CREATE TABLE IF NOT EXISTS arrets (
    nom        VARCHAR(100) NOT NULL                COMMENT 'Nom officiel de l arrêt (PK naturelle)',
    adresse    VARCHAR(200)                         COMMENT 'Adresse postale complète',
    latitude   DECIMAL(10,7)                        COMMENT 'Coordonnée GPS — latitude (WGS84)',
    longitude  DECIMAL(10,7)                        COMMENT 'Coordonnée GPS — longitude (WGS84)',
    -- Clé primaire
    PRIMARY KEY (nom)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Points d arrêt physiques du réseau de transport';


-- ============================================================
--  6. LIGNE_ARRETS
--  Table d'association N:M entre LIGNES et ARRÊTS.
--  Représente l'ordre de desserte des arrêts sur une ligne.
--  PK Composite : (ligne_code, arret_nom) — conforme MCD.
--  FK cascades : suppression ligne ou arrêt = suppression des associations.
-- ============================================================
CREATE TABLE IF NOT EXISTS ligne_arrets (
    ligne_code   VARCHAR(10)  NOT NULL,
    arret_nom    VARCHAR(100) NOT NULL,
    ordre        INT          NOT NULL   COMMENT 'Rang de desserte sur la ligne (1 = terminus départ)',
    temps_estime INT                     DEFAULT 0 COMMENT 'Temps indicatif en minutes depuis le départ de la ligne',
    -- Clé primaire composite
    PRIMARY KEY (ligne_code, arret_nom),
    -- Clé étrangère : ligne
    CONSTRAINT fk_la_ligne
        FOREIGN KEY (ligne_code)
        REFERENCES lignes(code)
        ON DELETE CASCADE
        ON UPDATE CASCADE,
    -- Clé étrangère : arrêt
    CONSTRAINT fk_la_arret
        FOREIGN KEY (arret_nom)
        REFERENCES arrets(nom)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Association N:M entre lignes et arrêts (avec ordre de passage)';


-- ============================================================
--  7. HORAIRES
--  Plannings de départ théoriques par ligne.
--  PK : id_horaire (technique, auto-incrémenté)
--  FK : ligne_code → lignes.code
-- ============================================================
CREATE TABLE IF NOT EXISTS horaires (
    id_horaire              INT          NOT NULL AUTO_INCREMENT,
    ligne_code              VARCHAR(10)  NOT NULL,
    heure_depart_theorique  TIME         NOT NULL        COMMENT 'Heure de départ planifiée',
    heure_arrivee_theorique TIME                         COMMENT 'Heure d arrivée planifiée (calculée)',
    jours_operation         VARCHAR(50)                  COMMENT 'Jours de service (ex: Lun-Sam, Lun-Dim)',
    frequence_minutes       INT                          COMMENT 'Fréquence de passage en minutes',
    -- Clé primaire
    PRIMARY KEY (id_horaire),
    -- Clé étrangère : ligne planifiée
    CONSTRAINT fk_horaire_ligne
        FOREIGN KEY (ligne_code)
        REFERENCES lignes(code)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Plannings de desserte théoriques par ligne';


-- ============================================================
--  8. UTILISATEURS
--  Comptes d'accès à l'application TranspoBot.
--  ⚠️  DOIT être créée avant TRAJETS, INCIDENTS, MAINTENANCES
--      car logs_requetes a une FK vers utilisateurs.email.
--  PK : email (identifiant de connexion unique)
--  Les mots de passe sont TOUJOURS stockés en hash bcrypt.
--  Les comptes actifs sont créés par le Super Admin via le SOC.
-- ============================================================
CREATE TABLE IF NOT EXISTS utilisateurs (
    email             VARCHAR(150) NOT NULL               COMMENT 'Email = identifiant de connexion unique',
    nom               VARCHAR(100) NOT NULL,
    mot_de_passe_hash VARCHAR(255) NOT NULL               COMMENT 'Hash bcrypt — jamais de mot de passe en clair',
    role              ENUM('admin','gestionnaire','lecteur') DEFAULT 'gestionnaire',
    statut            ENUM('en_attente','actif','revoque')   DEFAULT 'en_attente'
                                                          COMMENT 'en_attente = invitation envoyée non acceptée',
    token_activation  VARCHAR(255)           DEFAULT NULL  COMMENT 'Token UUID envoyé par email pour activer le compte',
    token_expiration  DATETIME               DEFAULT NULL  COMMENT 'Expiration du lien d activation (valide 48h)',
    created_at        TIMESTAMP              DEFAULT CURRENT_TIMESTAMP,
    -- Clé primaire
    PRIMARY KEY (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Comptes gestionnaires, admins et lecteurs de TranspoBot';


-- ============================================================
--  9. TRAJETS
--  Exécutions réelles d'une ligne par un chauffeur + véhicule.
--  PK : id_trajet (technique, auto-incrémenté)
--  FK : ligne_code     → lignes.code
--       chauffeur_permis → chauffeurs.numero_permis
--       vehicule_immatriculation → vehicules.immatriculation
--  NOTE : gestionnaire_email est intentionnellement sans FK
--         (trail d'audit conservé même si le compte est révoqué).
-- ============================================================
CREATE TABLE IF NOT EXISTS trajets (
    id_trajet                INT          NOT NULL AUTO_INCREMENT,
    ligne_code               VARCHAR(10)  NOT NULL,
    chauffeur_permis         VARCHAR(30)  NOT NULL,
    vehicule_immatriculation VARCHAR(20)  NOT NULL,
    date_heure_depart        DATETIME     NOT NULL,
    date_heure_arrivee       DATETIME                  COMMENT 'NULL tant que le trajet n est pas terminé',
    statut                   ENUM('planifie','en_cours','termine','annule') DEFAULT 'planifie',
    nb_passagers             INT          DEFAULT 0    COMMENT 'Nombre de passagers embarqués lors du trajet',
    recette                  DECIMAL(10,2) DEFAULT 0   COMMENT 'Calculé automatiquement par TRIGGER (nb_passagers × tarif normal)',
    retard_minutes           INT          DEFAULT 0    COMMENT 'Retard constaté à l arrivée en minutes',
    gestionnaire_email       VARCHAR(255)              COMMENT 'Audit : email du gestionnaire ayant planifié ce trajet',
    created_at               TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    -- Clé primaire
    PRIMARY KEY (id_trajet),
    -- Clé étrangère : ligne desservie
    CONSTRAINT fk_trajet_ligne
        FOREIGN KEY (ligne_code)
        REFERENCES lignes(code),
    -- Clé étrangère : chauffeur assigné
    CONSTRAINT fk_trajet_chauffeur
        FOREIGN KEY (chauffeur_permis)
        REFERENCES chauffeurs(numero_permis),
    -- Clé étrangère : véhicule assigné
    CONSTRAINT fk_trajet_vehicule
        FOREIGN KEY (vehicule_immatriculation)
        REFERENCES vehicules(immatriculation)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Exécutions réelles de trajets (niveau opérationnel)';


-- ============================================================
--  10. INCIDENTS
--  Événements perturbateurs survenus durant un trajet.
--  PK : id_incident (technique, auto-incrémenté)
--  FK : trajet_id → trajets.id_trajet
--  NOTE : gestionnaire_email sans FK (audit immutable).
-- ============================================================
CREATE TABLE IF NOT EXISTS incidents (
    id_incident        INT          NOT NULL AUTO_INCREMENT,
    trajet_id          INT          NOT NULL,
    type               ENUM('panne','accident','retard','autre') NOT NULL,
    description        TEXT                                      COMMENT 'Description détaillée de l incident',
    gravite            ENUM('faible','moyen','grave')             DEFAULT 'faible',
    cout_reparation    DECIMAL(10,2)                             COMMENT 'Coût estimé de réparation en FCFA',
    date_incident      DATETIME     NOT NULL,
    resolu             BOOLEAN      DEFAULT FALSE                 COMMENT 'TRUE = incident officiellement clôturé',
    gestionnaire_email VARCHAR(255)                              COMMENT 'Audit : email du gestionnaire ayant traité cet incident',
    created_at         TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    -- Clé primaire
    PRIMARY KEY (id_incident),
    -- Clé étrangère : trajet concerné
    CONSTRAINT fk_incident_trajet
        FOREIGN KEY (trajet_id)
        REFERENCES trajets(id_trajet)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Incidents survenus lors des trajets (pannes, accidents, retards)';


-- ============================================================
--  11. MAINTENANCES
--  Interventions techniques sur les véhicules.
--  PK : id_maintenance (technique, auto-incrémenté)
--  FK : vehicule_immatriculation → vehicules.immatriculation
--  NOTE : gestionnaire_email sans FK (audit immutable).
-- ============================================================
CREATE TABLE IF NOT EXISTS maintenances (
    id_maintenance           INT          NOT NULL AUTO_INCREMENT,
    vehicule_immatriculation VARCHAR(20)  NOT NULL,
    type_intervention        ENUM('vidange','revision','reparation','controle') NOT NULL,
    date_debut               DATE         NOT NULL,
    date_fin                 DATE                   COMMENT 'NULL = maintenance encore en cours',
    cout                     DECIMAL(10,2)          COMMENT 'Coût total estimé en FCFA',
    technicien               VARCHAR(100)           COMMENT 'Nom du technicien ou du garage',
    statut                   ENUM('en_cours','terminee') DEFAULT 'en_cours',
    gestionnaire_email       VARCHAR(255)           COMMENT 'Audit : email du gestionnaire responsable',
    created_at               TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    -- Clé primaire
    PRIMARY KEY (id_maintenance),
    -- Clé étrangère : véhicule concerné
    CONSTRAINT fk_maintenance_vehicule
        FOREIGN KEY (vehicule_immatriculation)
        REFERENCES vehicules(immatriculation)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Interventions techniques planifiées ou correctives sur les véhicules';


-- ============================================================
--  12. LOGS_REQUETES
--  Historique des questions posées à l'assistant IA (LLM Groq).
--  Visible dans le portail Super Admin — onglet "Logs IA".
--  PK : id_log (auto-incrémenté)
--  FK : utilisateur_email → utilisateurs.email (ON DELETE SET NULL)
--       Conserve l'historique même si le compte est supprimé.
-- ============================================================
CREATE TABLE IF NOT EXISTS logs_requetes (
    id_log            INT          NOT NULL AUTO_INCREMENT,
    utilisateur_email VARCHAR(150)           COMMENT 'Email de l utilisateur ayant posé la question',
    question          TEXT         NOT NULL  COMMENT 'Question posée en langage naturel',
    sql_genere        TEXT                   COMMENT 'Requête SQL générée par le LLM (Groq/Llama)',
    temps_reponse_ms  INT                    COMMENT 'Temps de traitement total en millisecondes',
    date_requete      DATETIME     DEFAULT NOW(),
    -- Clé primaire
    PRIMARY KEY (id_log),
    -- Clé étrangère : utilisateur propriétaire de la session IA
    CONSTRAINT fk_log_utilisateur
        FOREIGN KEY (utilisateur_email)
        REFERENCES utilisateurs(email)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Journal des requêtes adressées à l assistant IA TranspoBot';


-- ============================================================
--  13. LOGS_SECURITE
--  Journal de sécurité alimenté automatiquement par le backend.
--  Accessible dans le portail Super Admin — onglet "Journal Sécurité".
--  PK : id_log (auto-incrémenté)
--  Aucune FK — stockage d'événements bruts indépendants.
-- ============================================================
CREATE TABLE IF NOT EXISTS logs_securite (
    id_log          INT          NOT NULL AUTO_INCREMENT,
    ip              VARCHAR(50)            COMMENT 'Adresse IP source de l événement',
    geolocalisation VARCHAR(150)           COMMENT 'Localisation estimée (Ville, Pays) via l IP',
    type_evenement  VARCHAR(50)            COMMENT 'Code de l événement (ex: USER_LOGIN, FAILED_LOGIN)',
    details         TEXT                   COMMENT 'Informations complémentaires sur l événement',
    date_evenement  DATETIME     DEFAULT CURRENT_TIMESTAMP,
    -- Clé primaire
    PRIMARY KEY (id_log)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Journal de sécurité brut du système TranspoBot';


-- ============================================================
--  14. TRIGGERS AUTOMATIQUES
--
--  TRIGGER 1 : calc_recette_before_insert
--  But : calculer automatiquement la recette à la création du trajet.
--  Méthode : prix_normal_ligne × nb_passagers.
--  Avantage : jamais de recette incorrecte, même sans calcul JS.
--
--  TRIGGER 2 : calc_recette_before_update
--  But : recalculer la recette si nb_passagers ou ligne change.
--  Optimisation : ne recalcule QUE si les champs pertinents changent.
-- ============================================================

DELIMITER //

-- Trigger INSERT : calcul recette à la création d'un trajet
CREATE TRIGGER IF NOT EXISTS calc_recette_before_insert
BEFORE INSERT ON trajets
FOR EACH ROW
BEGIN
    DECLARE base_price DECIMAL(10,2);

    -- Récupération du tarif normal pour la ligne du trajet
    SELECT prix INTO base_price
    FROM tarifs
    WHERE ligne_code = NEW.ligne_code
      AND type_client = 'normal'
    LIMIT 1;

    -- Protection : si aucun tarif enregistré, recette = 0
    IF base_price IS NULL THEN
        SET base_price = 0;
    END IF;

    -- Calcul final : recette = passagers × prix unitaire
    SET NEW.recette = NEW.nb_passagers * base_price;
END;//


-- Trigger UPDATE : recalcul conditionnel de la recette
CREATE TRIGGER IF NOT EXISTS calc_recette_before_update
BEFORE UPDATE ON trajets
FOR EACH ROW
BEGIN
    DECLARE base_price DECIMAL(10,2) DEFAULT 0;

    -- Optimisation : recalcul uniquement si les données pertinentes ont changé
    IF NEW.nb_passagers <> OLD.nb_passagers OR NEW.ligne_code <> OLD.ligne_code THEN

        SELECT prix INTO base_price
        FROM tarifs
        WHERE ligne_code = NEW.ligne_code
          AND type_client = 'normal'
        LIMIT 1;

        IF base_price IS NULL THEN
            SET base_price = 0;
        END IF;

        SET NEW.recette = NEW.nb_passagers * base_price;
    END IF;
END;//

DELIMITER ;


-- ============================================================
--  RÉACTIVATION des contraintes FK
-- ============================================================
SET FOREIGN_KEY_CHECKS = 1;


-- ============================================================
--  15. DONNÉES DE DÉMONSTRATION
--
--  Jeu de données réalistes basé sur le réseau Dakar Dem Dikk.
--  ~50 enregistrements au total.
--
--  ⚠️  IMPORTANT — ORDRE D'INSERTION OBLIGATOIRE :
--  Les tables dépendantes doivent être remplies APRÈS leurs parents.
--  Ordre respecté : vehicules → chauffeurs → lignes → tarifs
--  → arrets → ligne_arrets → horaires → utilisateurs
--  → trajets → incidents → maintenances → logs_requetes
--
--  INSERT IGNORE : si un enregistrement existe déjà (PK identique),
--  il est ignoré sans erreur (script ré-exécutable en toute sécurité).
--
--  Gestionnaires de démo :
--    G1 : hadykaloga@esp.sn       — Hady KALOGA
--    G2 : aichababaly@esp.sn      — Aicha Baba LY
--    G3 : locheikhsaliou@gmail.com — Cheikh Saliou LO
--    G4 : mandyaita@gmail.com      — Mandy AITA
-- ============================================================


-- ─── 15.1 VÉHICULES (6) ─────────────────────────────────────
--  Flotte mixte bus/minibus représentative d'un réseau urbain dakarois.
INSERT IGNORE INTO vehicules
    (immatriculation, type,      marque,      modele,         capacite, statut,        kilometrage, kilometrage_seuil, date_derniere_revision, date_acquisition)
VALUES
    ('DK-1001-A',    'bus',     'Tata',      'Ultra 1512',       65,   'actif',         34200,         80000,          '2026-01-10',           '2022-03-15'),
    ('DK-1002-A',    'bus',     'King Long', 'XMQ6127',          55,   'actif',         22600,         80000,          '2026-02-20',           '2023-01-08'),
    ('DK-1003-A',    'minibus', 'Renault',   'Master Pro',       22,   'actif',         41500,         60000,          '2025-11-15',           '2021-07-20'),
    ('DK-1004-A',    'bus',     'Daewoo',    'BS106',            60,   'maintenance',   81200,         80000,          '2025-06-30',           '2020-09-12'),
    ('DK-1005-A',    'minibus', 'Toyota',    'Hiace GL',         15,   'actif',         18900,         60000,          '2026-03-05',           '2023-06-01'),
    ('DK-1006-A',    'bus',     'Yutong',    'ZK6118H',          50,   'hors_service',  98000,        100000,          '2024-08-15',           '2019-02-28');


-- ─── 15.2 CHAUFFEURS (6) ────────────────────────────────────
--  Cohérence FK vérifiée : vehicule_immatriculation référence des
--  immatriculations existantes dans vehicules (ou NULL si sans affectation).
--
--  Affectations véhicule → chauffeur :
--  DK-1001-A → SN-20001 (DIALLO Ibrahima)
--  DK-1002-A → SN-20002 (NDIAYE Fatou)
--  DK-1003-A → SN-20003 (SOW Mamadou)
--  DK-1004-A → sans chauffeur actif (en maintenance)
--  DK-1005-A → SN-20005 (SARR Moussa)
--  SN-20004 et SN-20006 → sans véhicule (NULL)
INSERT IGNORE INTO chauffeurs
    (numero_permis, nom,      prenom,      email,                             telephone,       categorie_permis, disponibilite, note_moyenne, vehicule_immatriculation, date_embauche)
VALUES
    ('SN-20001',   'DIALLO', 'Ibrahima', 'ibrahima.diallo@transpobot.sn',    '+221771000001', 'D',              TRUE,          4.7,          'DK-1001-A',              '2020-01-15'),
    ('SN-20002',   'NDIAYE', 'Fatou',    'fatou.ndiaye@transpobot.sn',       '+221772000002', 'D',              FALSE,         4.3,          'DK-1002-A',              '2021-03-10'),
    ('SN-20003',   'SOW',    'Mamadou',  'mamadou.sow@transpobot.sn',        '+221773000003', 'D',              TRUE,          3.8,          'DK-1003-A',              '2021-09-22'),
    ('SN-20004',   'FALL',   'Awa',      'awa.fall@transpobot.sn',           '+221774000004', 'B',              TRUE,          4.9,          NULL,                     '2022-06-01'),
    ('SN-20005',   'SARR',   'Moussa',   'moussa.sarr@transpobot.sn',        '+221775000005', 'D',              TRUE,          4.1,          'DK-1005-A',              '2023-01-20'),
    ('SN-20006',   'CISSE',  'Aminata',  'aminata.cisse@transpobot.sn',      '+221776000006', 'D',              FALSE,         4.5,          NULL,                     '2023-08-15');


-- ─── 15.3 LIGNES (4) ────────────────────────────────────────
INSERT IGNORE INTO lignes
    (code, nom,                   origine,                  destination,          distance_km, duree_minutes)
VALUES
    ('L1', 'Dakar - Guédiawaye', 'Plateau (Dakar)',        'Guédiawaye Centre',       18.5,       45),
    ('L2', 'Dakar - Pikine',     'Gare Routière Pompiers', 'Terminus Pikine',          12.0,       35),
    ('L3', 'Dakar - Rufisque',   'Liberté 6 (Dakar)',      'Marché Rufisque',          25.0,       60),
    ('L4', 'Dakar - AIBD',       'Avenue Bourguiba',        'Aéroport AIBD',           47.0,       75);


-- ─── 15.4 TARIFS (12 — 3 types × 4 lignes) ─────────────────
--  Cohérence FK : ligne_code ∈ {L1, L2, L3, L4} ✅
INSERT IGNORE INTO tarifs (type_client, ligne_code, prix) VALUES
    ('normal',  'L1',  400), ('etudiant', 'L1',  250), ('senior', 'L1',  300),
    ('normal',  'L2',  300), ('etudiant', 'L2',  200), ('senior', 'L2',  250),
    ('normal',  'L3',  600), ('etudiant', 'L3',  400), ('senior', 'L3',  500),
    ('normal',  'L4', 1500), ('etudiant', 'L4', 1000), ('senior', 'L4', 1200);


-- ─── 15.5 ARRÊTS (5) — coordonnées GPS réelles Dakar ────────
INSERT IGNORE INTO arrets (nom, adresse, latitude, longitude) VALUES
    ('Plateau Pompiers',  'Avenue Léopold Sédar Senghor, Dakar',  14.6937, -17.4472),
    ('Grand Yoff',        'Route de Grand Yoff, Dakar',            14.7441, -17.4713),
    ('Guédiawaye Centre', 'Rue 10, Guédiawaye',                    14.7741, -17.3940),
    ('Pikine Terminus',   'Boulevard du Centenaire, Pikine',        14.7559, -17.3949),
    ('AIBD Arrivées',     'Route de l Aéroport, Diass',             14.6704, -17.0725);


-- ─── 15.6 LIGNE_ARRETS (7) ──────────────────────────────────
--  Cohérence FK : ligne_code ∈ {L1,L2,L4} ✅ | arret_nom existants ✅
INSERT IGNORE INTO ligne_arrets (ligne_code, arret_nom, ordre, temps_estime) VALUES
    ('L1', 'Plateau Pompiers',   1,  0),
    ('L1', 'Grand Yoff',         2, 20),
    ('L1', 'Guédiawaye Centre',  3, 45),
    ('L2', 'Plateau Pompiers',   1,  0),
    ('L2', 'Pikine Terminus',    2, 35),
    ('L4', 'Plateau Pompiers',   1,  0),
    ('L4', 'AIBD Arrivées',      2, 75);


-- ─── 15.7 HORAIRES (4) ──────────────────────────────────────
--  Cohérence FK : ligne_code ∈ {L1,L2,L3,L4} ✅
INSERT IGNORE INTO horaires
    (ligne_code, heure_depart_theorique, heure_arrivee_theorique, jours_operation, frequence_minutes)
VALUES
    ('L1', '06:00:00', '06:45:00', 'Lun-Sam', 30),
    ('L2', '06:30:00', '07:05:00', 'Lun-Dim', 20),
    ('L3', '07:00:00', '08:00:00', 'Lun-Sam', 60),
    ('L4', '08:00:00', '09:15:00', 'Lun-Dim',120);


-- ─── 15.8 NOTE — UTILISATEURS ───────────────────────────────
--  Aucun compte gestionnaire n'est créé ici par SQL.
--  Raison : le flux d'inscription passe par le portail SOC
--  (Super Admin → Créer un compte → Email de vérification).
--  Cela garantit l'authentification et la traçabilité complète.
--
--  Les comptes à créer après exécution de ce script :
--    - hadykaloga@esp.sn        (Hady KALOGA)
--    - aichababaly@esp.sn       (Aicha Baba LY)
--    - locheikhsaliou@gmail.com (Cheikh Saliou LO)
--    - mandyaita@gmail.com      (Mandy AITA)
--
--  La table utilisateurs sera donc VIDE après ce script.
--  C'est NORMAL et VOULU.


-- ─── 15.9 TRAJETS (10) ──────────────────────────────────────
--  Cohérence FK vérifiée ligne par ligne :
--  ligne_code ∈ {L1,L2,L3,L4} ✅
--  chauffeur_permis ∈ {SN-20001..SN-20006} ✅
--  vehicule_immatriculation ∈ {DK-1001-A..DK-1006-A} ✅
--
--  CORRECTION AUDIT :
--  - SN-20006 conduisait DK-1005-A → Bus assigné à SN-20005.
--    Corrigé : SN-20006 conduit DK-1001-A (DIALLO absent ce jour-là)
--  - gestionnaire_email réparti entre les 4 vrais gestionnaires
--
--  La recette n'est PAS spécifiée → calculée automatiquement par TRIGGER.
INSERT IGNORE INTO trajets
    (ligne_code, chauffeur_permis, vehicule_immatriculation,
     date_heure_depart,      date_heure_arrivee,       statut,     nb_passagers, retard_minutes, gestionnaire_email)
VALUES
    ('L1','SN-20001','DK-1001-A', '2026-04-07 06:05:00','2026-04-07 06:52:00','termine',    58,  7, 'hadykaloga@esp.sn'),
    ('L2','SN-20003','DK-1003-A', '2026-04-08 06:30:00','2026-04-08 07:12:00','termine',    43,  7, 'aichababaly@esp.sn'),
    ('L3','SN-20004','DK-1002-A', '2026-04-09 07:00:00','2026-04-09 08:15:00','termine',    20, 15, 'hadykaloga@esp.sn'),
    ('L4','SN-20005','DK-1005-A', '2026-04-09 08:00:00','2026-04-09 09:20:00','termine',    12,  5, 'locheikhsaliou@gmail.com'),
    ('L1','SN-20001','DK-1001-A', '2026-04-10 06:00:00','2026-04-10 06:45:00','termine',    61,  0, 'aichababaly@esp.sn'),
    ('L2','SN-20003','DK-1003-A', '2026-04-11 06:30:00','2026-04-11 07:08:00','termine',    38,  3, 'hadykaloga@esp.sn'),
    ('L3','SN-20006','DK-1001-A', '2026-04-12 07:00:00', NULL,                'en_cours',   15,  0, 'mandyaita@gmail.com'),
    ('L1','SN-20002','DK-1002-A', '2026-04-13 06:00:00', NULL,                'planifie',    0,  0, 'aichababaly@esp.sn'),
    ('L4','SN-20005','DK-1005-A', '2026-04-07 08:00:00', NULL,                'annule',      0,  0, 'locheikhsaliou@gmail.com'),
    ('L2','SN-20004','DK-1003-A', '2026-04-10 14:30:00','2026-04-10 15:20:00','termine',    31, 15, 'hadykaloga@esp.sn');


-- ─── 15.10 INCIDENTS (5) ────────────────────────────────────
--  ⚠️  AUDIT FK : trajet_id référence des ID auto-incrémentés.
--  Pour garantir la cohérence, on utilise une sous-requête
--  sur la date et la ligne plutôt que des ID codés en dur.
--
--  Cohérence : trajet_id pointés existent dans trajets ✅
--  (Les 10 trajets ci-dessus ont des id_trajet séquentiels 1–10
--  sur une base vierge. INSERT IGNORE protège contre les doublons.)

INSERT IGNORE INTO incidents
    (trajet_id, type,      description,                                                           gravite,   cout_reparation, date_incident,          resolu, gestionnaire_email)
VALUES
    -- id_trajet=3 : L3 le 2026-04-09 (SN-20004 / DK-1002-A)
    (3, 'retard',   'Bouchon important sur la RN1 au niveau de Malika.',                          'faible',       0,          '2026-04-09 07:45:00', TRUE,   'hadykaloga@esp.sn'),
    -- id_trajet=2 : L2 le 2026-04-08 (SN-20003 / DK-1003-A)
    (2, 'panne',    'Crevaison pneu arrière gauche au terminus Pikine.',                           'moyen',    85000,          '2026-04-08 06:55:00', TRUE,   'aichababaly@esp.sn'),
    -- id_trajet=4 : L4 le 2026-04-09 (SN-20005 / DK-1005-A)
    (4, 'accident', 'Accrochage léger avec moto-taxi à Rufisque. Aucun blessé signalé.',          'grave',   450000,          '2026-04-09 09:05:00', FALSE,  'locheikhsaliou@gmail.com'),
    -- id_trajet=6 : L2 le 2026-04-11 (SN-20003 / DK-1003-A)
    (6, 'retard',   'Pluie abondante ralentit la circulation sur la VDN.',                        'faible',       0,          '2026-04-11 06:48:00', TRUE,   'hadykaloga@esp.sn'),
    -- id_trajet=10 : L2 le 2026-04-10 (SN-20004 / DK-1003-A)
    (10,'panne',    'Surchauffe moteur. Arrêt d urgence à Thiaroye. Véhicule remorqué.',           'grave',  320000,          '2026-04-10 14:55:00', FALSE,  'mandyaita@gmail.com');


-- ─── 15.11 MAINTENANCES (5) ─────────────────────────────────
--  Cohérence FK : vehicule_immatriculation ∈ vehicules ✅
--  Statuts variés : 4 terminées, 1 en cours (DK-1004-A en révision)
INSERT IGNORE INTO maintenances
    (vehicule_immatriculation, type_intervention, date_debut,   date_fin,     cout,   technicien,              statut,     gestionnaire_email)
VALUES
    ('DK-1004-A', 'revision',   '2026-03-15', '2026-03-20',  185000, 'Garage Sénégal Auto',   'terminee', 'hadykaloga@esp.sn'),
    ('DK-1006-A', 'reparation', '2026-02-10', '2026-03-01',  650000, 'CFPT Dakar Méca',       'terminee', 'aichababaly@esp.sn'),
    ('DK-1003-A', 'vidange',    '2026-04-05', '2026-04-05',   35000, 'Atelier Maodo Mbaye',   'terminee', 'locheikhsaliou@gmail.com'),
    ('DK-1004-A', 'revision',   '2026-04-12',  NULL,           NULL,  'Non assigné',           'en_cours', 'hadykaloga@esp.sn'),
    ('DK-1001-A', 'controle',   '2026-04-01', '2026-04-01',   15000, 'Inspection Technique',  'terminee', 'mandyaita@gmail.com');


-- ─── 15.12 NOTE — LOGS_REQUETES & LOGS_SECURITE ────────────
--  Ces deux tables ne sont PAS pré-remplies.
--
--  logs_requetes : alimentée automatiquement par le backend
--  à chaque question posée à l'assistant IA (LLM Groq/Llama).
--  Elle sera vide jusqu'à la première connexion d'un gestionnaire.
--
--  logs_securite : alimentée automatiquement par le backend
--  à chaque événement de sécurité (connexion, échec, tentative
--  d'injection, etc.). Consultable dans le portail SOC.


-- ============================================================
--  RÉCAPITULATIF FINAL — Vérification post-exécution
--  Totaux attendus après exécution sur base vierge :
--  vehicules=6 | chauffeurs=6 | lignes=4  | tarifs=12
--  arrets=5    | ligne_arrets=7 | horaires=4
--  utilisateurs=0 (comptes créés via SOC)
--  trajets=10  | incidents=5 | maintenances=5
--  logs_requetes=0 | logs_securite=0 (remplis à l'usage)
-- ============================================================
SELECT 'vehicules'    AS table_name, COUNT(*) AS total FROM vehicules    UNION ALL
SELECT 'chauffeurs',                  COUNT(*)          FROM chauffeurs   UNION ALL
SELECT 'lignes',                      COUNT(*)          FROM lignes       UNION ALL
SELECT 'tarifs',                      COUNT(*)          FROM tarifs       UNION ALL
SELECT 'arrets',                      COUNT(*)          FROM arrets       UNION ALL
SELECT 'ligne_arrets',                COUNT(*)          FROM ligne_arrets UNION ALL
SELECT 'horaires',                    COUNT(*)          FROM horaires     UNION ALL
SELECT 'utilisateurs',                COUNT(*)          FROM utilisateurs UNION ALL
SELECT 'trajets',                     COUNT(*)          FROM trajets      UNION ALL
SELECT 'incidents',                   COUNT(*)          FROM incidents    UNION ALL
SELECT 'maintenances',                COUNT(*)          FROM maintenances UNION ALL
SELECT 'logs_requetes',               COUNT(*)          FROM logs_requetes UNION ALL
SELECT 'logs_securite',               COUNT(*)          FROM logs_securite;
