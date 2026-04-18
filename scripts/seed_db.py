import mysql.connector
from datetime import datetime, timedelta
import random

db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'transpobot'
}

def seed():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    
    # 1. CLEAN DB
    print("Nettoyage de la base de donnees...")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
    for table in ['incidents', 'maintenances', 'trajets', 'tarifs', 'chauffeurs', 'vehicules', 'lignes']:
        cursor.execute(f"TRUNCATE TABLE {table};")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
    
    # 2. INSERT 10 LIGNES
    print("Insertion de 10 Lignes...")
    lignes_data = [
        ("L1", "Centre - Pikine", "Dakar", "Pikine", 15.5, 45, 500),
        ("L2", "Plateau - Parcelles", "Plateau", "Parcelles", 18.0, 50, 400),
        ("L3", "Yoff - Thies", "Yoff", "Thies", 60.5, 90, 1500),
        ("L4", "Guediawaye - Centre", "Guediawaye", "Centre", 20.0, 55, 600),
        ("L5", "Rufisque - Dakar", "Rufisque", "Dakar", 30.0, 70, 800),
        ("L6", "Mbour - Thies", "Mbour", "Thies", 45.0, 80, 1000),
        ("L7", "Ouakam - Ngor", "Ouakam", "Ngor", 8.0, 20, 300),
        ("L8", "AIBD - Centre", "AIBD", "Centre", 50.0, 60, 2000),
        ("L9", "Keur Massar - Dakar", "Keur", "Dakar", 25.0, 65, 700),
        ("L10", "Point E - Almadies", "Point E", "Almadies", 12.0, 30, 400)
    ]
    for l in lignes_data:
        cursor.execute("INSERT INTO lignes (code, nom, origine, destination, distance_km, duree_minutes) VALUES (%s, %s, %s, %s, %s, %s)", l[:6])
        cursor.execute("INSERT INTO tarifs (type_client, ligne_code, prix) VALUES ('normal', %s, %s)", (l[0], l[6]))

    # 3. INSERT 15 VEhICULES
    print("Insertion de 15 Vehicules...")
    vehicules = []
    for i in range(1, 16):
        immatriculation = f"DK-{1000+i}-A"
        vehicules.append(immatriculation)
        cursor.execute("INSERT INTO vehicules (immatriculation, type, marque, modele, capacite, statut, kilometrage, kilometrage_seuil) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", 
            (immatriculation, "Bus Standard", "SenBus", f"Indus {i}", random.randint(40, 65), "En_route", random.randint(10000, 120000), 150000))

    # 4. INSERT 15 CHAUFFEURS
    print("Insertion de 15 Chauffeurs...")
    chauffeurs = []
    for i in range(1, 16):
        permis = f"SN-{20000+i}"
        chauffeurs.append(permis)
        # Random assignment of ~10 buses to drivers
        bus_assigne = vehicules[i-1] if i <= 10 else None
        cursor.execute("INSERT INTO chauffeurs (numero_permis, vehicule_immatriculation, nom, prenom, email, telephone, categorie_permis, disponibilite, date_embauche) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (permis, bus_assigne, f"Nom-{i}", f"Prenom-{i}", f"chauffeur{i}@transpo.sn", f"77444{i:03d}", random.choice(["D", "C"]), True, "2024-01-01"))

    # 5. INSERT 40 TRAJETS
    print("Insertion de 40 Trajets...")
    trajets = []
    now = datetime.now()
    for i in range(1, 41):
        ligne = random.choice(lignes_data)
        chauffeur = random.choice(chauffeurs)
        bus = random.choice(vehicules)
        
        # Generation de stats decalees sur 2 semaines (passées et futures)
        offset = random.randint(-14, 5) # Jours
        depart = now + timedelta(days=offset, hours=random.randint(-5, 5))
        arrivee = None
        statut = "termine"
        
        if offset > 0:
            statut = "planifie"
        elif offset == 0 and depart > now:
            statut = "planifie"
        elif offset == 0 and depart <= now:
            statut = "en_cours"
        
        if statut == "termine":
            arrivee = depart + timedelta(minutes=ligne[5])
        
        nb_p = random.randint(15, 60) if statut == "termine" else 0
        recette = nb_p * ligne[6] if statut == "termine" else 0
        
        sql_tr = ("INSERT INTO trajets (ligne_code, chauffeur_permis, vehicule_immatriculation, date_heure_depart, date_heure_arrivee, statut, nb_passagers, recette) "
                  "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)")
        cursor.execute(sql_tr, (ligne[0], chauffeur, bus, depart.strftime('%Y-%m-%d %H:%M:%S'), 
                                arrivee.strftime('%Y-%m-%d %H:%M:%S') if arrivee else None, 
                                statut, nb_p, recette))
        if statut == "termine":
            trajets.append(cursor.lastrowid)

    # 6. INSERT 9 INCIDENTS
    print("Insertion de 9 Incidents...")
    for i in range(9):
        t_id = random.choice(trajets) if trajets else 1
        gravite = random.choice(["Faible", "Moyenne", "Grave"])
        resolu = True if gravite != "Grave" else random.choice([True, False])
        cursor.execute("INSERT INTO incidents (trajet_id, type, description, gravite, cout_reparation, date_incident, resolu) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (t_id, random.choice(["panne", "accident", "retard"]), "Probleme aleatoire sur le troncon", gravite, random.randint(10000, 50000), (now - timedelta(days=random.randint(1,10))).strftime('%Y-%m-%d'), resolu))

    # 7. INSERT 9 MAINTENANCES
    print("Insertion de 9 Maintenances...")
    for i in range(9):
        bus = random.choice(vehicules)
        dt_debut = (now - timedelta(days=random.randint(3,10)))
        dt_fin = dt_debut + timedelta(days=random.randint(1,4))
        statut_m = random.choice(["en_cours", "terminee"])
        cursor.execute("INSERT INTO maintenances (vehicule_immatriculation, type_intervention, date_debut, date_fin, cout, technicien, statut) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (bus, random.choice(["vidange", "revision", "reparation"]), dt_debut.strftime('%Y-%m-%d'), dt_fin.strftime('%Y-%m-%d') if statut_m == "terminee" else None, random.randint(20000, 150000), "Garage Automoto", statut_m))

    conn.commit()
    cursor.close()
    conn.close()
    print("Super !! Base de donnees peuplee avec un total de 98 lignes representatives de data !!!")

if __name__ == '__main__':
    seed()
