document.addEventListener('DOMContentLoaded', () => {
    const toggleBtn = document.getElementById('chatbot-toggle-btn');
    const chatbotBody = document.getElementById('chat-messages');
    const chatbotFooter = document.querySelector('.chatbot-footer');
    const chatbotWrapper = document.querySelector('.chatbot-wrapper');
    const chatInput = document.getElementById('chat-input');
    const chatSendBtn = document.getElementById('chat-send-btn');

    const backdrop = document.getElementById('ai-backdrop');
    const headerBtn = document.getElementById('open-ai-spotlight');

    // ==========================================
    // 🧲 ANIMATION SPOTLIGHT (CMD+K)
    // ==========================================
    function toggleSpotlight() {
        const isActive = chatbotWrapper.classList.contains('active-spotlight');
        if (isActive) {
            chatbotWrapper.classList.remove('active-spotlight');
            backdrop.classList.remove('active');
        } else {
            chatbotWrapper.classList.add('active-spotlight');
            backdrop.classList.add('active');
            setTimeout(() => chatInput.focus(), 100);
        }
    }

    if (toggleBtn) {
        toggleBtn.addEventListener('click', toggleSpotlight);
    }
    if (backdrop) {
        backdrop.addEventListener('click', toggleSpotlight);
    }
    
    if (headerBtn) {
        headerBtn.addEventListener('click', toggleSpotlight);
    }

    // Keyboard Shortcuts (Cmd+K / Ctrl+K and Esc)
    document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            toggleSpotlight();
        }
        if (e.key === 'Escape' && chatbotWrapper.classList.contains('active-spotlight')) {
            toggleSpotlight();
        }
    });

    // ==========================================
    // 🧠 GESTION DES MESSAGES INTERACTIFS
    // ==========================================
    chatSendBtn.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    async function sendMessage() {
        const text = chatInput.value.trim();
        if (!text) return;

        // 1. Ajouter le message de l'utilisateur à l'écran
        appendMessage('user', text);
        chatInput.value = '';

        // 2. Afficher l'indicateur "L'IA écrit..."
        const typingId = showTypingIndicator();

        try {
            // 3. Appel de l'API /api/chat que nous avons construite en Semaine 2 !!
            const response = await fetch(`${API_BASE}/api/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                // On passe dynamiquement la langue ('fr' ou 'en')
                body: JSON.stringify({ message: text, language: UI_STATE.lang })
            });

            const result = await response.json();
            
            // 4. Supprimer l'indicateur "écrit..."
            removeElement(typingId);

            if (!response.ok) {
                appendMessage('bot', `⚠️ Erreur système : ${result.detail || 'Problème de connexion Backend.'}`);
                return;
            }

            // 5. Afficher la Réponse Native de l'IA (en Français ou Anglais selon le switch)
            appendBotResponse(result, text);

        } catch (error) {
            removeElement(typingId);
            appendMessage('bot', `⚠️ L'API FastAPI semble éteinte. Veuillez exécuter 'uvicorn backend.main:app' dans votre terminal.`);
            console.error(error);
        }
    }

    // ==========================================
    // 🎨 FONCTIONS DE DESSIN DU DOM (UI)
    // ==========================================
    function appendMessage(sender, text) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${sender}-message`;
        msgDiv.textContent = text;
        
        chatbotBody.appendChild(msgDiv);
        scrollToBottom();
    }

    function appendBotResponse(data, question = "Requête non spécifiée") {
        const msgContainer = document.createElement('div');
        msgContainer.className = 'message bot-message glass-message';
        
        // La phrase naturelle générée par Llama-3 (Groq)
        const p = document.createElement('p');
        p.textContent = data.natural_response;
        msgContainer.appendChild(p);

        // 📊 Afficher le Tableau JSON en HTML propre
        if (data.data_table && data.data_table.length > 0) {
            const table = document.createElement('table');
            table.className = "chat-table";
            
            // Création des en-têtes dynamiques basées sur le JSON !
            const thead = document.createElement('thead');
            const trHead = document.createElement('tr');
            data.columns.forEach(col => {
                const th = document.createElement('th');
                th.textContent = col.replace(/_/g, ' ').toUpperCase();
                trHead.appendChild(th);
            });
            thead.appendChild(trHead);
            table.appendChild(thead);

            // Création des lignes du tableau (Limité à 10 pour ne pas casser le design du widget)
            const tbody = document.createElement('tbody');
            const maxRows = Math.min(data.data_table.length, 10);
            
            for (let i = 0; i < maxRows; i++) {
                const rowObj = data.data_table[i];
                const tr = document.createElement('tr');
                
                data.columns.forEach(col => {
                    const td = document.createElement('td');
                    let cellVal = rowObj[col];
                    
                    if (cellVal === null) {
                        td.textContent = '-';
                    } else {
                        // Si la valeur est une Date ISO (ex: 2026-04-07T06:05:00) => on la formate
                        if (typeof cellVal === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/.test(cellVal)) {
                            const d = new Date(cellVal);
                            td.textContent = d.toLocaleDateString('fr-FR') + ' ' + d.toLocaleTimeString('fr-FR', {hour: '2-digit', minute:'2-digit'});
                        } else if (typeof cellVal === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(cellVal)) {
                             // Si juste une date YYYY-MM-DD
                            const d = new Date(cellVal);
                            td.textContent = d.toLocaleDateString('fr-FR');
                        } else {
                            td.textContent = cellVal;
                        }
                    }
                    tr.appendChild(td);
                });
                tbody.appendChild(tr);
            }
            table.appendChild(tbody);

            if (data.data_table.length > 10) {
                const info = document.createElement('div');
                info.style.fontSize = "10px";
                info.style.color = "var(--text-muted)";
                info.textContent = `+ ${data.data_table.length - 10} autres résultats masqués.`;
                table.appendChild(info);
            }

            msgContainer.appendChild(table);

            // Bouton Exporter PDF 
            const btnWrap = document.createElement('div');
            btnWrap.style.marginTop = "8px";
            btnWrap.style.textAlign = "right";

            const btnExport = document.createElement('button');
            btnExport.className = "btn-secondary";
            btnExport.innerHTML = '<i class="fa-solid fa-file-pdf" style="color:#ef4444;"></i> Exporter en PDF';
            btnExport.style.fontSize = "11px";
            btnExport.style.padding = "4px 10px";
            
            btnExport.onclick = () => {
                const win = window.open('', '_blank');
                win.document.write(`
                    <html>
                        <head>
                            <title>Rapport TranspoBot</title>
                            <style>
                                body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; padding: 20px; color: #1e293b; }
                                h2 { color: #0f172a; font-size:18px; border-bottom: 2px solid #e2e8f0; padding-bottom:10px; }
                                table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 12px; }
                                th, td { border: 1px solid #cbd5e1; padding: 8px; text-align: left; }
                                th { background-color: #f1f5f9; color: #334155; }
                            </style>
                        </head>
                        <body>
                            <h2>📊 Rapport I.A. TranspoBot</h2>
                            <p style="font-size:13px; color:#475569;"><strong>Question posée :</strong> ${question}</p>
                            ${table.outerHTML}
                            <p style="margin-top:20px; font-size:10px; color:#94a3b8;">Généré automatiquement par l'IA le ${new Date().toLocaleString('fr-FR')}</p>
                        </body>
                    </html>
                `);
                win.document.close();
                win.focus();
                setTimeout(() => { win.print(); win.close(); }, 350);
            };
            btnWrap.appendChild(btnExport);
            msgContainer.appendChild(btnWrap);
        }

        // Ajouter une note sur le temps d'exécution (Performance de l'agentique)
        const timeDiv = document.createElement('div');
        timeDiv.style.fontSize = "10px";
        timeDiv.style.color = "var(--success)";
        timeDiv.style.marginTop = "8px";
        timeDiv.innerHTML = `<i class="fa-solid fa-bolt"></i> Traité et analysé en ${data.execution_time_ms} ms`;
        msgContainer.appendChild(timeDiv);

        chatbotBody.appendChild(msgContainer);
        scrollToBottom();
    }

    function showTypingIndicator() {
        const id = 'typing-' + Date.now();
        const msgDiv = document.createElement('div');
        msgDiv.id = id;
        msgDiv.className = 'message bot-message typing-indicator';
        msgDiv.innerHTML = '<span></span><span></span><span></span>';
        chatbotBody.appendChild(msgDiv);
        scrollToBottom();
        return id;
    }

    function removeElement(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    function scrollToBottom() {
        chatbotBody.scrollTop = chatbotBody.scrollHeight;
    }
});
