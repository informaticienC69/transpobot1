document.addEventListener('DOMContentLoaded', () => {
    // Coordonnées stratégiques de Dakar (Gare Routière / Centre)
    const dakarCenter = [14.6928, -17.4467];
    
    // 1. Initialisation de la carte Leaflet (exposée globalement pour invalidateSize)
    window.transpoBotMap = L.map('transportMap', {
        zoomControl: false // Déplacé manuellement plus tard
    }).setView(dakarCenter, 12);
    const map = window.transpoBotMap;

    // 2. Thème de la Carte : On utilise CartoDB "Dark Matter" pour matcher avec le Glassmorphism Noir
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
        subdomains: 'abcd',
        maxZoom: 19
    }).addTo(map);

    // Contrôles en bas à gauche pour ne pas gêner le Chatbot à droite
    L.control.zoom({ position: 'bottomleft' }).addTo(map);

    // ==========================================
    // 📍 IONES PERSONNALISÉS (Design UI/UX)
    // ==========================================
    
    // Icône Bus en mouvement (Néon Bleu)
    const busIcon = L.divIcon({
        className: 'custom-div-icon',
        html: "<div style='background-color:var(--primary); width:16px; height:16px; border-radius:50%; box-shadow: 0 0 12px var(--primary); border: 2px solid white; transition: all 0.3s;'></div>",
        iconSize: [16, 16],
        iconAnchor: [8, 8]
    });

    // Icône Arrêt Fixe (Gris Métallisé)
    const stopIcon = L.divIcon({
        className: 'custom-div-icon',
        html: "<div style='background-color:var(--text-muted); width:10px; height:10px; border-radius:50%; border: 1px solid rgba(255,255,255,0.5);'></div>",
        iconSize: [10, 10],
        iconAnchor: [5, 5]
    });

    // ==========================================
    // 🚏 SIMULATION DES DONNÉES GÉOGRAPHIQUES
    // (Issus de schema.sql L120 - Arrêts Dakar)
    // ==========================================
    const arretsData = [
        { nom: "Terminus Plateau", lat: 14.6654, lng: -17.4287 },
        { nom: "Gare de Rufisque", lat: 14.7135, lng: -17.2753 },
        { nom: "Keur Massar Croisement", lat: 14.7684, lng: -17.3197 },
        { nom: "UCAD (Université)", lat: 14.6853, lng: -17.4651 },
        { nom: "Maristes", lat: 14.7431, lng: -17.4244 }
    ];

    // Tracé des Arrêts
    arretsData.forEach(arret => {
        L.marker([arret.lat, arret.lng], { icon: stopIcon })
         .addTo(map)
         .bindPopup(`<div style="color:black; font-family:'Outfit';"><b>${arret.nom}</b><br>Arrêt du Réseau TranspoBot</div>`);
    });

    // 🌟 DESSIN DU RÉSEAU (Chemin Néon Cyan reliant les arrêts)
    const routeCoords = arretsData.map(a => [a.lat, a.lng]);
    L.polyline(routeCoords, {
        color: '#00D2FF',
        weight: 4,
        opacity: 0.6,
        dashArray: '10, 15'
    }).addTo(map);

    // ==========================================
    // 🚌 SIMULATION GPS TEMPS REEL (Animations)
    // ==========================================
    const vehiculesData = [
        { m: "DK-1234-A", lat: 14.6800, lng: -17.4500, stat: "En route", vitesse: "42" },
        { m: "DK-9876-B", lat: 14.7200, lng: -17.3000, stat: "Terminus", vitesse: "0" },
        { m: "DK-5555-C", lat: 14.7550, lng: -17.3300, stat: "En route", vitesse: "28" }
    ];

    // On stocke les marqueurs pour pouvoir les animer
    const liveMarkers = vehiculesData.map(v => {
        const marker = L.marker([v.lat, v.lng], { icon: busIcon }).addTo(map);
        
        let color = v.stat === "Terminus" ? "gray" : "#34C759";
        
        // Popup avec HTML unique pour pouvoir mettre à jour la vitesse
        const popupContent = `
            <div style="color:#0a0c10; font-family:'Inter'; text-align:center;">
                <h3 style="margin:0 0 5px 0; font-family:'Outfit';">Bus ${v.m}</h3>
                <span style="font-size:12px; font-weight:bold; color:${color}; background:rgba(0,0,0,0.05); padding:3px 8px; border-radius:10px;">${v.stat}</span>
                <p style="margin:5px 0 0 0; font-size:11px;">Vitesse: <b id="speed-${v.m}">${v.vitesse}</b> km/h</p>
            </div>
        `;
        marker.bindPopup(popupContent);
        
        // Return object for animation constraints
        return { marker, lat: v.lat, lng: v.lng, dirLat: 1, dirLng: 1, id: v.m, stat: v.stat };
    });

    // MOTEUR D'ANIMATION (Bouge les bus toutes les 1.5 secondes)
    setInterval(() => {
        liveMarkers.forEach(v => {
            if(v.stat === "Terminus") return; // Les bus au Terminus ne bougent pas

            // Petit déplacement aléatoire fluide (Simule la conduite GPS)
            v.lat += (Math.random() * 0.0005) * v.dirLat;
            v.lng += (Math.random() * 0.0005) * v.dirLng;

            // Aléatoirement, le bus tourne dans une rue
            if(Math.random() < 0.1) v.dirLat *= -1;
            if(Math.random() < 0.1) v.dirLng *= -1;

            // Mise à jour visuelle du marqueur sur la carte
            v.marker.setLatLng([v.lat, v.lng]);
            
            // Mise à jour de la vitesse dans la bulle si elle est ouverte
            const speedEl = document.getElementById(`speed-${v.id}`);
            if (speedEl) {
                speedEl.textContent = Math.floor(Math.random() * (50 - 20 + 1) + 20); // Entre 20 et 50 km/h
            }
        });
    }, 1500);

    // Optionnel : Forcer la map à se redessiner si on ouvre un menu modal
    setTimeout(() => map.invalidateSize(), 500);
});
