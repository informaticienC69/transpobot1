const UI_STATE = { lang: 'fr' };
const API_BASE = (window.location.hostname === '' || window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') ? 'http://127.0.0.1:8000' : window.location.origin;

// --- INTERCEPTEUR FETCH POUR LE JWT ---
const originalFetch = window.fetch;
window.fetch = async function(...args) {
    let url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url ? args[0].url : '');
    
    // Si c'est un appel à NOTRE API (pas OSRM, etc.) et que ce n'est PAS le login
    if (url.startsWith(API_BASE) && !url.includes('/api/auth/login')) {
        const token = sessionStorage.getItem('jwt_token');
        if (token) {
            args[1] = args[1] || {};
            args[1].headers = args[1].headers || {};
            // Injecter le Content-Type s'il est manquant et qu'on a un body
            if (!args[1].headers['Content-Type'] && args[1].body && typeof args[1].body === 'string') {
                args[1].headers['Content-Type'] = 'application/json';
            }
            args[1].headers['Authorization'] = `Bearer ${token}`;
        }
    }
    
    return originalFetch.apply(this, args);
};

let chartInstances = {}; // Stockage global des graphiques pour éviter le crash Canvas
let GLOBAL_STORE = { trajets: [], incidents: [], maintenances: [] }; // Données filtrables


document.addEventListener('DOMContentLoaded', () => {
    initLangToggle();
    initRouter();
    startLiveClock();
    initKeyboardShortcuts();
    
    // Auth Check
    const sessionUser = sessionStorage.getItem('session_user');
    if(sessionUser) {
        // Refresh: affichage instantané sans animation
        showAppSequence(JSON.parse(sessionUser), true);
    } else {
        const lc = document.getElementById('login-container');
        lc.style.display = 'flex';
        lc.style.opacity = '1';
        document.getElementById('app-container').style.display = 'none';
        // GSAP entrance
        if (typeof animateLoginIn === 'function') animateLoginIn();
    }
});

// ==========================================
// ðŸ• HORODATAGE DYNAMIQUE
// ==========================================
function startLiveClock() {
    const el = document.getElementById('live-clock');
    if (!el) return;

    const daysFr = ['Dimanche','Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi'];
    const daysEn = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
    const monthsFr = ['jan.','fév.','mars','avr.','mai','juin','juil.','août','sept.','oct.','nov.','déc.'];
    const monthsEn = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

    const tick = () => {
        const now = new Date();
        const lang = UI_STATE.lang || 'fr';
        const days   = lang === 'en' ? daysEn   : daysFr;
        const months = lang === 'en' ? monthsEn : monthsFr;

        const day   = days[now.getDay()];
        const date  = now.getDate();
        const month = months[now.getMonth()];
        const hh    = String(now.getHours()).padStart(2, '0');
        const mm    = String(now.getMinutes()).padStart(2, '0');
        const ss    = String(now.getSeconds()).padStart(2, '0');

        el.innerHTML = `
            <span style="font-size:11px;color:var(--text-muted);font-weight:500;">${day} ${date} ${month}</span>
            <span id="clock-time" style="font-family:var(--font-heading);font-size:16px;font-weight:700;color:var(--text-main);letter-spacing:1px;">${hh}:${mm}<span style="color:var(--primary);font-size:12px;vertical-align:top;margin-top:2px;display:inline-block;">:${ss}</span></span>
        `;
    };

    tick();
    setInterval(tick, 1000);
}

// ==========================================
// âŒ¨ï¸ RACCOURCIS CLAVIER GLOBAUX
// ==========================================
function initKeyboardShortcuts() {
    // Map: shortcut â†’ handler
    const shortcuts = [
        { key: 'n', ctrl: true, shift: false, label: 'Nouveau Trajet',    action: () => { navigateTo('trajets'); setTimeout(() => openModal('modal-trajets'), 200); } },
        { key: 'b', ctrl: true, shift: false, label: 'Nouveau Bus',       action: () => { navigateTo('fleet');   setTimeout(() => openModal('modal-fleet'), 200); } },
        { key: 'd', ctrl: true, shift: false, label: 'Nouveau Chauffeur', action: () => { navigateTo('staff');   setTimeout(() => openModal('modal-staff'), 200); } },
        { key: 'i', ctrl: true, shift: false, label: 'Signaler Incident', action: () => { navigateTo('incidents'); setTimeout(() => openModal('modal-incidents'), 200); } },
        { key: '/', ctrl: false, shift: false, label: 'Focus Recherche',  action: () => {
            // Focus the search bar of the active view
            const activeView = document.querySelector('.spa-view:not(.hidden)');
            if (!activeView) return;
            const input = activeView.querySelector('.table-search-input');
            if (input) { input.focus(); input.select(); }
        }},
    ];

    document.addEventListener('keydown', (e) => {
        // Skip if user is typing in an input/textarea
        const tag = document.activeElement?.tagName;
        const isTyping = ['INPUT','TEXTAREA','SELECT'].includes(tag) && e.key !== '/';
        if (isTyping) return;

        // Skip if any modal is open
        const modalOpen = document.querySelector('.modal-overlay:not(.hidden)');
        if (modalOpen && e.key !== 'Escape') return;

        for (const sc of shortcuts) {
            const ctrlMatch  = sc.ctrl  ? (e.ctrlKey || e.metaKey) : !(e.ctrlKey || e.metaKey);
            const shiftMatch = sc.shift ? e.shiftKey : !e.shiftKey;
            if (e.key.toLowerCase() === sc.key && ctrlMatch && shiftMatch) {
                e.preventDefault();
                sc.action();
                return;
            }
        }
    });

    // Show shortcuts panel on ? key
    document.addEventListener('keydown', (e) => {
        if (e.key === '?' && !e.ctrlKey && !e.metaKey) {
            const tag = document.activeElement?.tagName;
            if (['INPUT','TEXTAREA'].includes(tag)) return;
            showShortcutsPanel();
        }
    });
}

// Helper: navigate to a view programmatically
function navigateTo(viewId) {
    const navItem = document.querySelector(`.nav-item[data-view="${viewId}"]`);
    if (navItem) navItem.click();
}

// Show a keyboard shortcuts cheatsheet
function showShortcutsPanel() {
    const old = document.getElementById('shortcuts-panel');
    if (old) { old.remove(); return; }

    const panel = document.createElement('div');
    panel.id = 'shortcuts-panel';
    panel.style.cssText = `
        position:fixed;bottom:90px;right:24px;z-index:99998;
        background:#fff;border-radius:20px;padding:0;
        box-shadow:0 20px 60px rgba(0,0,0,0.18);
        border:1px solid rgba(0,0,0,0.07);
        font-family:var(--font-body);
        min-width:280px;
        animation:logoutSlideIn 0.25s cubic-bezier(0.16,1,0.3,1);
        overflow:hidden;
    `;

    const isMac = navigator.platform.toUpperCase().includes('MAC');
    const mod   = isMac ? 'âŒ˜' : 'Ctrl';

    panel.innerHTML = `
        <div style="height:3px;background:linear-gradient(90deg,var(--primary),var(--secondary));"></div>
        <div style="padding:18px 20px 14px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
                <span style="font-family:var(--font-heading);font-size:14px;font-weight:700;color:#0f172a;">
                    <i class="fa-solid fa-keyboard" style="color:var(--primary);margin-right:8px;"></i>Raccourcis Clavier
                </span>
                <span style="font-size:11px;color:var(--text-muted);">Appuyer sur <kbd style="background:#f1f5f9;border:1px solid #e2e8f0;border-radius:4px;padding:2px 6px;font-size:10px;">?</kbd> pour fermer</span>
            </div>
            <div style="display:flex;flex-direction:column;gap:8px;">
                ${[
                    { keys: [mod, 'K'],         label: 'Interroger l\'IA',    icon: 'sparkles',           color: 'var(--secondary)' },
                    { keys: [mod, 'N'],         label: 'Nouveau Trajet',      icon: 'clock-rotate-left',  color: 'var(--warning)'   },
                    { keys: [mod, 'B'],         label: 'Nouveau Bus',         icon: 'bus',                color: 'var(--primary)'   },
                    { keys: [mod, 'D'],         label: 'Nouveau Chauffeur',   icon: 'user-tie',           color: 'var(--primary)'   },
                    { keys: [mod, 'I'],         label: 'Signaler Incident',   icon: 'triangle-exclamation', color: 'var(--danger)' },
                    { keys: ['/'],              label: 'Rechercher',          icon: 'magnifying-glass',   color: '#94a3b8'          },
                    { keys: ['Échap'],          label: 'Fermer une fenêtre',  icon: 'xmark',              color: '#94a3b8'          },
                ].map(sc => `
                    <div style="display:flex;align-items:center;justify-content:space-between;padding:6px 10px;border-radius:8px;background:#f8fafc;">
                        <div style="display:flex;align-items:center;gap:8px;font-size:13px;color:#475569;">
                            <i class="fa-solid fa-${sc.icon}" style="color:${sc.color};width:14px;text-align:center;"></i>
                            ${sc.label}
                        </div>
                        <div style="display:flex;gap:4px;">
                            ${sc.keys.map(k => `<kbd style="background:#fff;border:1px solid #e2e8f0;border-radius:5px;padding:2px 7px;font-size:11px;font-family:var(--font-heading);font-weight:700;color:#1e293b;box-shadow:0 1px 0 #e2e8f0;">${k}</kbd>`).join('<span style="color:#94a3b8;font-size:12px;align-self:center;">+</span>')}
                        </div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;

    document.body.appendChild(panel);

    // Auto-close on outside click or Escape
    setTimeout(() => {
        const close = (e) => { if (!panel.contains(e.target)) { panel.remove(); document.removeEventListener('click', close); } };
        document.addEventListener('click', close);
    }, 100);
}



// ==========================================
// ðŸ” AUTHENTICATION LOGIC
// ==========================================
async function handleLogin(e) {
    e.preventDefault();
    const btn = document.getElementById('btn-login');
    const email = document.getElementById('login-email').value.trim();
    const pwd = document.getElementById('login-password').value;
    
    if (!email || !pwd) return;

    // État de chargement
    const originalHTML = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Vérification...';
    btn.disabled = true;

    try {
        const res = await fetch(`${API_BASE}/api/auth/login`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ email, password: pwd })
        });
        const data = await res.json();
        
        if (data.success) {
            // âœ… Connexion réussie : sauvegarder la session et basculer IMMÉDIATEMENT
            sessionStorage.setItem('session_user', JSON.stringify(data.user));
            sessionStorage.setItem('jwt_token', data.token); // Sauvegarde du token de sécurité
            showAppSequence(data.user, false); // lancer la transition
            // La notification apparaîtra après la transition (dans le dashboard)
            setTimeout(() => {
                showNotification('success', 'Bienvenue ðŸ‘‹', `Connecté en tant que ${data.user.nom}`);
            }, 700);
        } else {
            // âŒ Identifiants incorrects
            showNotification('error', 'Accès Refusé', data.detail || 'Email ou mot de passe incorrect.');
            btn.innerHTML = originalHTML;
            btn.disabled = false;
        }
    } catch(errFetch) {
        showNotification('error', 'Serveur Injoignable', 'Impossible de contacter le serveur. Vérifiez que FastAPI est actif.');
        btn.innerHTML = originalHTML;
        btn.disabled = false;
    }
}


function handleLogout() {
    // Create overlay
    const overlay = document.createElement('div');
    overlay.id = 'logout-confirm-overlay';
    overlay.style.cssText = `
        position: fixed; inset: 0; z-index: 999999;
        background: rgba(15, 23, 42, 0.55);
        backdrop-filter: blur(8px);
        display: flex; align-items: center; justify-content: center;
        animation: fadeInOverlay 0.25s ease;
    `;

    const user = JSON.parse(sessionStorage.getItem('session_user') || '{}');
    const userName = user.prenom || user.nom || 'Utilisateur';

    overlay.innerHTML = `
        <div style="
            background: #ffffff;
            border-radius: 24px;
            padding: 0;
            width: 380px;
            max-width: calc(100vw - 32px);
            box-shadow: 0 30px 80px rgba(0,0,0,0.22), 0 0 0 1px rgba(255,255,255,0.8) inset;
            animation: logoutSlideIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            overflow: hidden;
            font-family: var(--font-body);
        ">
            <!-- Accent bar -->
            <div style="height: 4px; background: linear-gradient(90deg, #ef4444, #f97316); border-radius: 0;"></div>

            <!-- Icon area -->
            <div style="display: flex; flex-direction: column; align-items: center; padding: 32px 28px 0; text-align: center; gap: 14px;">
                <div style="
                    width: 72px; height: 72px;
                    background: rgba(239,68,68,0.09);
                    border: 2px solid rgba(239,68,68,0.18);
                    border-radius: 50%;
                    display: flex; align-items: center; justify-content: center;
                    font-size: 28px;
                    color: #ef4444;
                    animation: logoutIconPulse 1.8s ease infinite;
                ">
                    <i class="fa-solid fa-power-off"></i>
                </div>

                <div>
                    <h3 style="font-family: var(--font-heading); font-size: 20px; font-weight: 700; color: #0f172a; margin: 0 0 8px;">
                        Déconnexion
                    </h3>
                    <p style="font-size: 14px; color: #64748b; line-height: 1.5; margin: 0;">
                        Bonjour <strong style="color: #0f172a;">${userName}</strong>, vous êtes sur le point de quitter votre session.<br>
                        <span style="font-size: 12px; color: #94a3b8;">Toutes les données non sauvegardées seront perdues.</span>
                    </p>
                </div>
            </div>

            <!-- Security note -->
            <div style="
                margin: 20px 28px 0;
                padding: 10px 14px;
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                display: flex;
                align-items: center;
                gap: 10px;
                font-size: 12px;
                color: #64748b;
            ">
                <i class="fa-solid fa-shield-halved" style="color: var(--primary); font-size: 16px; flex-shrink: 0;"></i>
                Votre session sera fermée de façon sécurisée.
            </div>

            <!-- Action buttons -->
            <div style="display: flex; gap: 12px; padding: 24px 28px 28px;">
                <button id="logout-cancel-btn" style="
                    flex: 1; padding: 13px;
                    background: #f1f5f9; color: #475569;
                    border: 1.5px solid #e2e8f0; border-radius: 12px;
                    font-size: 14px; font-weight: 600; cursor: pointer;
                    font-family: var(--font-body);
                    transition: all 0.18s;
                ">
                    <i class="fa-solid fa-xmark"></i> Annuler
                </button>
                <button id="logout-confirm-btn" style="
                    flex: 1; padding: 13px;
                    background: linear-gradient(135deg, #ef4444, #dc2626);
                    color: white; border: none; border-radius: 12px;
                    font-size: 14px; font-weight: 700; cursor: pointer;
                    font-family: var(--font-body);
                    box-shadow: 0 4px 14px rgba(239,68,68,0.35);
                    transition: all 0.18s;
                ">
                    <i class="fa-solid fa-right-from-bracket"></i> Se déconnecter
                </button>
            </div>
        </div>
    `;

    // Inject styles for animations
    if (!document.getElementById('logout-style')) {
        const style = document.createElement('style');
        style.id = 'logout-style';
        style.textContent = `
            @keyframes logoutSlideIn {
                from { opacity: 0; transform: translateY(24px) scale(0.95); }
                to   { opacity: 1; transform: translateY(0)    scale(1); }
            }
            @keyframes fadeInOverlay {
                from { opacity: 0; } to { opacity: 1; }
            }
            @keyframes logoutIconPulse {
                0%, 100% { box-shadow: 0 0 0 0 rgba(239,68,68,0); }
                50%       { box-shadow: 0 0 0 8px rgba(239,68,68,0.12); }
            }
            #logout-cancel-btn:hover { background: #e2e8f0 !important; color: #1e293b !important; }
            #logout-confirm-btn:hover { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(239,68,68,0.5) !important; }
        `;
        document.head.appendChild(style);
    }

    document.body.appendChild(overlay);

    // Cancel
    document.getElementById('logout-cancel-btn').addEventListener('click', () => {
        overlay.style.animation = 'fadeInOverlay 0.2s ease reverse';
        setTimeout(() => overlay.remove(), 200);
    });

    // Close on overlay click
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            overlay.style.animation = 'fadeInOverlay 0.2s ease reverse';
            setTimeout(() => overlay.remove(), 200);
        }
    });

    // Close on Escape
    const onEsc = (e) => { if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', onEsc); } };
    document.addEventListener('keydown', onEsc);

    // Confirm logout
    document.getElementById('logout-confirm-btn').addEventListener('click', () => {
        const confirmBtn = document.getElementById('logout-confirm-btn');
        confirmBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Fermeture...';
        confirmBtn.disabled = true;
        setTimeout(() => {
            sessionStorage.removeItem('session_user');
            sessionStorage.removeItem('jwt_token');
            window.location.reload();
        }, 900);
    });
}

// ==========================================
// ðŸ“± MOBILE SIDEBAR TOGGLE
// ==========================================
function toggleSidebarMobile() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    const isOpen = sidebar.classList.contains('mobile-open');
    if (isOpen) {
        sidebar.classList.remove('mobile-open');
        overlay.style.display = 'none';
    } else {
        sidebar.classList.add('mobile-open');
        overlay.style.display = 'block';
    }
}

function closeSidebarMobile() {
    document.querySelector('.sidebar').classList.remove('mobile-open');
    document.getElementById('sidebar-overlay').style.display = 'none';
}

function showAppSequence(user, instant = false) {
    // Modify Identity Badge
    const initials = user.nom.split(' ').map(n=>n[0]).join('').substring(0,2).toUpperCase();
    document.getElementById('user-avatar').textContent = initials;
    document.getElementById('user-name').textContent = user.nom;
    document.getElementById('user-role').textContent = user.role;
    
    // Alpine Details Profile
    const ddName = document.getElementById('user-dropdown-name');
    const ddEmail = document.getElementById('user-dropdown-email');
    const ddAvatar = document.getElementById('user-avatar-small');
    if(ddName) ddName.textContent = user.nom;
    if(ddEmail) ddEmail.textContent = user.email || 'Admin ERP';
    if(ddAvatar) ddAvatar.textContent = initials;
    
    // Activer le chatbot IA
    document.getElementById('ai-spotlight')?.classList.remove('auth-hidden');
    document.getElementById('ai-backdrop')?.classList.remove('auth-hidden');

    const loginUI = document.getElementById('login-container');
    const appUI = document.getElementById('app-container');
    
    if (instant) {
        // Refresh: pas d'animation, affichage direct
        loginUI.style.display = 'none';
        appUI.style.display = 'flex';
        appUI.style.opacity = '1';
        checkAPIStatus();
        loadDashboardKPIs();
        loadExtendedViews();
        loadDashboardStats();
        setTimeout(() => {
            if (window.transpoBotMap) window.transpoBotMap.invalidateSize();
        }, 400);
    } else {
        // Connexion: transition fluide + GSAP
        loginUI.style.opacity = '0';
        setTimeout(() => {
            loginUI.style.display = 'none';
            appUI.style.display = 'flex';
            setTimeout(() => {
                appUI.style.opacity = '1';
                // GSAP app entrance
                if (typeof animateAppIn === 'function') animateAppIn();
                if (window.transpoBotMap) {
                    setTimeout(() => window.transpoBotMap.invalidateSize(), 300);
                }
            }, 50);
            checkAPIStatus();
            loadDashboardKPIs();
            loadExtendedViews();
            loadDashboardStats();
        }, 500);
    }
}

function togglePassword() {
    const pwdInput = document.getElementById('login-password');
    const eyeIcon = document.getElementById('toggle-pwd');
    if (pwdInput.type === 'password') {
        pwdInput.type = 'text';
        eyeIcon.classList.remove('fa-eye');
        eyeIcon.classList.add('fa-eye-slash');
    } else {
        pwdInput.type = 'password';
        eyeIcon.classList.remove('fa-eye-slash');
        eyeIcon.classList.add('fa-eye');
    }
}

// ==========================================
// ðŸ” FILTRE LIVE DES TABLEAUX
// ==========================================
function filterTable(tableId, query) {
    const table = document.getElementById(tableId);
    if (!table) return;

    const rows = table.querySelectorAll('tbody tr');
    const q = (query || '').toLowerCase().trim();

    // Find the closest search bar parent to show count badge
    const searchInput = document.querySelector(`[oninput*="${tableId}"]`);
    let countBadge = searchInput?.parentElement?.querySelector('.search-count-badge');
    if (!countBadge && searchInput) {
        countBadge = document.createElement('span');
        countBadge.className = 'search-count-badge';
        searchInput.parentElement.appendChild(countBadge);
    }

    let visibleCount = 0;
    let hasEmptyState = false;

    rows.forEach(row => {
        // Don't filter empty-state rows
        if (row.querySelector('.empty-state')) {
            hasEmptyState = true;
            return;
        }
        const text = row.textContent.toLowerCase();
        const match = !q || text.includes(q);
        row.style.display = match ? '' : 'none';
        if (match) visibleCount++;
    });

    // Update count badge
    if (countBadge) {
        if (!q || hasEmptyState) {
            countBadge.style.display = 'none';
        } else {
            countBadge.style.display = '';
            countBadge.textContent = visibleCount === 0
                ? '0 résultat'
                : `${visibleCount} résultat${visibleCount > 1 ? 's' : ''}`;
            countBadge.style.color = visibleCount === 0 ? 'var(--danger)' : 'var(--text-muted)';
            countBadge.style.background = visibleCount === 0 ? 'rgba(239,68,68,0.08)' : 'rgba(0,0,0,0.05)';
        }
    }

    // Show "no results" row if needed
    const noResultId = `${tableId}-no-result`;
    let noResult = document.getElementById(noResultId);
    if (q && visibleCount === 0 && !hasEmptyState) {
        if (!noResult) {
            const colCount = table.querySelectorAll('thead th').length || 5;
            noResult = document.createElement('tr');
            noResult.id = noResultId;
            noResult.innerHTML = `<td colspan="${colCount}" style="text-align:center;padding:40px;color:var(--text-muted);">
                <i class="fa-solid fa-magnifying-glass" style="font-size:1.8rem;display:block;margin-bottom:10px;opacity:0.4;"></i>
                Aucun résultat pour <strong>"${query}"</strong>
            </td>`;
            table.querySelector('tbody').appendChild(noResult);
        } else {
            noResult.style.display = '';
        }
    } else if (noResult) {
        noResult.style.display = 'none';
    }
}

// ==========================================
// ðŸ’¡ NOTIFICATIONS (TOASTS) PRO
// ==========================================

function showNotification(type, title, message) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    
    const icons = {
        'error': 'fa-circle-xmark',
        'success': 'fa-circle-check',
        'warning': 'fa-triangle-exclamation'
    };
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <div class="toast-icon"><i class="fa-solid ${icons[type]}"></i></div>
        <div class="toast-content">
            <div class="toast-title">${title}</div>
            <div class="toast-msg">${message}</div>
        </div>
        <div class="toast-close" onclick="this.parentElement.remove()"><i class="fa-solid fa-xmark"></i></div>
    `;
    
    container.appendChild(toast);
    
    // Animate In
    setTimeout(() => toast.classList.add('show'), 50);
    
    // Animate Out after 4 seconds
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 400);
    }, 4000);
}

// ==========================================
// âœ¨ ANIMATIONS & UTILITAIRES UI
// ==========================================
function animateValue(obj, start, end, duration) {
    let startTimestamp = null;
    const step = (timestamp) => {
        if (!startTimestamp) startTimestamp = timestamp;
        const progress = Math.min((timestamp - startTimestamp) / duration, 1);
        obj.innerHTML = Math.floor(progress * (end - start) + start);
        if (progress < 1) {
            window.requestAnimationFrame(step);
        }
    };
    window.requestAnimationFrame(step);
}

// ==========================================
// ðŸŒ MULTILINGUISME DYNAMIQUE (Vanilla JS)
// ==========================================
function applyTranslations() {
    document.querySelectorAll('.lang-text').forEach(el => {
        if(el.hasAttribute(`data-${UI_STATE.lang}`)) {
            el.innerHTML = el.getAttribute(`data-${UI_STATE.lang}`);
        }
    });

    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
        chatInput.placeholder = UI_STATE.lang === 'fr' ? "Interrogez la BDD en naturel..." : "Query the Database naturally...";
    }
}

function initLangToggle() {
    const toggle = document.getElementById('lang-toggle');
    if(!toggle) return;
    
    // Set default active flag
    document.querySelector('.fr-flag').classList.add('active');

    toggle.addEventListener('change', (e) => {
        UI_STATE.lang = e.target.checked ? 'en' : 'fr';
        
        // CSS indicators
        document.querySelectorAll('.lang-indicator').forEach(el => el.classList.remove('active'));
        document.querySelector(UI_STATE.lang === 'fr' ? '.fr-flag' : '.en-flag').classList.add('active');
        
        applyTranslations();
        loadDashboardStats(); // refresh dates text
    });
}

// ==========================================
// ðŸ§­ ROUTEUR SINGLE PAGE APPLICATION
// ==========================================
function initRouter() {
    const navItems = document.querySelectorAll('.nav-item');
    const views = document.querySelectorAll('.spa-view');

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            
            const performNav = () => {
                // Retirer 'active' de tout le monde
                navItems.forEach(nav => nav.classList.remove('active'));
                views.forEach(view => view.classList.add('hidden'));

                // Ajouter 'active' à l'item cliqué
                item.classList.add('active');
                
                // Afficher la vue correspondante
                const targetView = item.getAttribute('data-view');
                const viewEl = document.getElementById(`view-${targetView}`);
                viewEl.classList.remove('hidden');

                // GSAP view transition
                if (typeof animateViewIn === 'function') animateViewIn(viewEl);

                // Fermer le sidebar sur mobile après navigation
                if (window.innerWidth <= 768) closeSidebarMobile();
            };

            // Transition ultra-fluide type 'React' (View Transitions API)
            if (document.startViewTransition) {
                document.startViewTransition(performNav);
            } else {
                performNav();
            }
        });
    });
}

// ==========================================
// ðŸ”Œ CONNEXION BACKEND & STATISTIQUES (KPI)
// ==========================================
async function checkAPIStatus() {
    const statusBadge = document.getElementById('api-status');
    if (!statusBadge) return;
    try {
        const res = await fetch(`${API_BASE}/`);
        if (res.ok) {
            statusBadge.innerHTML = UI_STATE.lang === 'fr' ? 'Connecté' : 'Online';
            statusBadge.style.color = 'var(--success)';
        }
    } catch (e) {
        console.error("L'API FastAPI est éteinte ou inaccessible.", e);
        if (statusBadge) statusBadge.innerHTML = 'Déconnectée (Lancer Uvicorn)';
    }
}

async function loadDashboardKPIs() {
    try {
        const [vehRes, statRes, tripRes] = await Promise.all([
            fetch(`${API_BASE}/api/data/vehicules`),
            fetch(`${API_BASE}/api/data/chauffeurs-stats`),
            fetch(`${API_BASE}/api/data/trajets-recents`)
        ]);

        const [vehData, statData, tripData] = await Promise.all([
            vehRes.json(), statRes.json(), tripRes.json()
        ]);

        if (vehData.success) populateFleetTable(vehData.data);
        if (statData.success) populateStaffTable(statData.data);
        if (tripData.success) populateTripsTable(tripData.data);

    } catch (e) {
        console.error("Erreur lors de la récupération des KPI Backend :", e);
    }
}

function toggleCustomDatesAndLoad() {
    const period = document.getElementById('dashboard-period').value;
    const customDiv = document.getElementById('custom-date-filters');
    
    if (period === 'custom') {
        customDiv.style.display = 'flex';
        // N'appelle pas loadDashboardStats tout de suite si les dates sont vides
        const dDebut = document.getElementById('db-date-debut').value;
        const dFin = document.getElementById('db-date-fin').value;
        if (dDebut && dFin) {
            loadDashboardStats();
        }
    } else {
        customDiv.style.display = 'none';
        loadDashboardStats();
    }
}

async function loadDashboardStats() {
    try {
        const periodSelect = document.getElementById('dashboard-period');
        const period = periodSelect ? periodSelect.value : 'tout';
        
        const dDebut = document.getElementById('db-date-debut').value;
        const dFin = document.getElementById('db-date-fin').value;
        
        let urlParams = `?period=${period}`;
        let titleText = 'Période';
        
        if (period === 'custom') {
            if (!dDebut || !dFin) return; // Wait until both are filled
            urlParams += `&debut=${dDebut}&fin=${dFin}`;
            titleText = UI_STATE.lang === 'en' 
                ? `From ${new Date(dDebut).toLocaleDateString('en-US')} to ${new Date(dFin).toLocaleDateString('en-US')}` 
                : `Du ${new Date(dDebut).toLocaleDateString('fr-FR')} au ${new Date(dFin).toLocaleDateString('fr-FR')}`;
        } else {
            const labelMappingFr = {
                'tout': 'Toutes les dates', 'semaine_cours': 'Cette semaine', 'semaine_passe': 'Semaine dernière',
                'mois_cours': 'Ce mois-ci', 'mois_passe': 'Mois dernier', 'annee_cours': 'Cette année', 'annee_passe': 'Année dernière'
            };
            const labelMappingEn = {
                'tout': 'All Dates', 'semaine_cours': 'This Week', 'semaine_passe': 'Last Week',
                'mois_cours': 'This Month', 'mois_passe': 'Last Month', 'annee_cours': 'This Year', 'annee_passe': 'Last Year'
            };
            const map = UI_STATE.lang === 'en' ? labelMappingEn : labelMappingFr;
            titleText = map[period] || map['tout'];
        }
        
        // MàJ des titres des cards avec balises bilingues
        const lblT = document.getElementById('kpi-label-trajets');
        const lblR = document.getElementById('kpi-label-recettes');
        const lblI = document.getElementById('kpi-label-incidents');
        if (lblT) lblT.innerHTML = `<span class="lang-text" data-fr="Trajets" data-en="Trips">Trajets</span> <br><span style="font-size:12px;font-weight:400;color:var(--text-muted)">${titleText}</span>`;
        if (lblR) lblR.innerHTML = `<span class="lang-text" data-fr="Recettes FCFA" data-en="Revenue (FCFA)">Recettes FCFA</span> <br><span style="font-size:12px;font-weight:400;color:var(--text-muted)">${titleText}</span>`;
        if (lblI) lblI.innerHTML = `<span class="lang-text" data-fr="Incidents" data-en="Incidents">Incidents</span> <br><span style="font-size:12px;font-weight:400;color:var(--text-muted)">${titleText}</span>`;
        
        const chartRevTitle = document.getElementById('chart-rev-title');
        const chartFleetTitle = document.getElementById('chart-fleet-title');
        if (chartRevTitle) chartRevTitle.innerHTML = `<span class="lang-text" data-fr="Performance Financière" data-en="Financial Performance">Performance Financière</span> <span style="font-size:12px;font-weight:400;color:var(--text-muted)">(${titleText})</span>`;
        if (chartFleetTitle) chartFleetTitle.innerHTML = period === 'tout' 
            ? `<span class="lang-text" data-fr="Répartition de la Flotte" data-en="Fleet Distribution">Répartition de la Flotte</span> <span style="font-size:12px;font-weight:400;color:var(--text-muted)">(${UI_STATE.lang === 'en' ? 'Live' : 'En direct'})</span>`
            : `<span class="lang-text" data-fr="Audit Événements" data-en="Events Audit">Audit Événements</span> <span style="font-size:12px;font-weight:400;color:var(--text-muted)">(${titleText})</span>`;
            
        // Appliquer immédiatement la langue pour ces nouveaux spans
        if(typeof applyTranslations === 'function') applyTranslations();
        
        // Setup text skeleton
        const elTrajets = document.getElementById('kpi-trajets-mois');
        const elRecette = document.getElementById('kpi-recettes-mois');
        const elIncident = document.getElementById('kpi-incidents-mois');
        elTrajets.textContent = '---';
        elRecette.textContent = '---';
        elIncident.textContent = '---';
        elTrajets.classList.add('skeleton', 'skeleton-text');
        elRecette.classList.add('skeleton', 'skeleton-text');
        elIncident.classList.add('skeleton', 'skeleton-text');

        const statRes = await fetch(`${API_BASE}/api/data/dashboard-stats${urlParams}`);
        const statData = await statRes.json();
        if (statData.success) {
            animateValue(elTrajets, 0, statData.kpis.trajets_mois || 0, 1000);
            animateValue(elRecette, 0, statData.kpis.recettes_mois || 0, 1000);
            animateValue(elIncident, 0, statData.kpis.incidents_mois || 0, 1000);
            
            elTrajets.classList.remove('skeleton', 'skeleton-text');
            elRecette.classList.remove('skeleton', 'skeleton-text');
            elIncident.classList.remove('skeleton', 'skeleton-text');
            
            setTimeout(() => {
                elRecette.textContent = Number(elRecette.textContent).toLocaleString('fr-FR') + ' FCFA';
            }, 1050);

            loadDashboardCharts(statData.revenues_7d, statData.fleet_status, titleText);
        }
    } catch(e) { console.error('Dashboard Stats Error', e); }
}

// Global Chart Instances to prevent duplication rendering
let revenueChartInstance = null;
let fleetChartInstance = null;

function loadDashboardCharts(revenues, fleet) {
    if (typeof Chart === 'undefined') return;
    
    // --- 1. Line Chart (Revenues)
    const ctxRev = document.getElementById('revenueChart');
    if (ctxRev && revenues) {
        if (revenueChartInstance) revenueChartInstance.destroy();
        
        const labels = revenues.map(r => new Date(r.date_jour).toLocaleDateString('fr-FR', {weekday:'short', day:'numeric'}));
        const data = revenues.map(r => r.total_recette);
        
        revenueChartInstance = new Chart(ctxRev, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Recette (FCFA)',
                    data: data,
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.08)',
                    borderWidth: 2.5,
                    fill: true,
                    tension: 0.4,
                    pointBackgroundColor: '#10b981',
                    pointBorderColor: 'rgba(16,185,129,0.3)',
                    pointRadius: 4,
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(255,255,255,0.05)', borderDash: [4,4] },
                        ticks: { color: '#475569', font: { size: 11 } }
                    },
                    x: {
                        grid: { display: false },
                        ticks: { color: '#475569', font: { size: 11 } }
                    }
                }
            }
        });
    }
    
    // --- 2. Doughnut Chart (Fleet)
    const ctxFleet = document.getElementById('fleetChart');
    if (ctxFleet && fleet) {
        if (fleetChartInstance) fleetChartInstance.destroy();
        
        const labels = fleet.map(f => f.statut);
        const data = fleet.map(f => f.count);
        // Associer des couleurs strictes aux statuts : actif(vert), panne(rouge), maintenance(orange)
        const colors = labels.map(l => l==='actif' ? '#3b82f6' : (l==='maintenance' ? '#f59e0b' : '#ef4444'));
        
        fleetChartInstance = new Chart(ctxFleet, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    backgroundColor: colors,
                    borderColor: 'rgba(13,17,23,0.8)',
                    borderWidth: 2,
                    hoverOffset: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '70%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            color: '#94a3b8',
                            font: { size: 11, family: "'Plus Jakarta Sans', sans-serif" },
                            padding: 16,
                            boxWidth: 10,
                            boxHeight: 10,
                            usePointStyle: true
                        }
                    }
                }
            }
        });
    }
}

function populateTripsTable(trips) {
    const tbody = document.querySelector('#trajetsTable tbody');
    tbody.innerHTML = '';
    
    trips.forEach((trip, idx) => {
        const tr = document.createElement('tr');
        tr.className = 'fade-in-row';
        tr.style.animationDelay = `${idx * 0.05}s`;
        
        // Dynamic badge color mapping based on status rules in CSS
        const cleanStatus = trip.statut.replace(' ', '_');
        const badgeClass = `badge-status status-${cleanStatus}`;
        
        tr.innerHTML = `
            <td>#${trip.id_trajet}</td>
            <td><strong>${trip.ligne_code}</strong></td>
            <td>${trip.chauffeur}</td>
            <td>${trip.vehicule}</td>
            <td><span class="${badgeClass}">${trip.statut}</span></td>
        `;
        tbody.appendChild(tr);
    });
}

// ðŸš Injection Tableau Flotte
function populateFleetTable(vehicules) {
    const tbody = document.querySelector('#fleetTable tbody');
    tbody.innerHTML = '';
    
    if (!vehicules.length) {
        tbody.innerHTML = `<tr><td colspan="5">
            <div class="empty-state">
                <div class="empty-state-icon" style="background:rgba(37,99,235,0.08);color:var(--primary);">
                    <i class="fa-solid fa-bus"></i>
                </div>
                <h4>Aucun véhicule enregistré</h4>
                <p>La flotte est vide. Ajoutez votre premier bus pour commencer à gérer vos trajets.</p>
                <button class="btn-primary" onclick="openModal('modal-fleet')" style="flex-grow:0;">
                    <i class="fa-solid fa-plus"></i> Ajouter un bus
                </button>
            </div>
        </td></tr>`;
        return;
    }
    
    vehicules.forEach((v, idx) => {
        const tr = document.createElement('tr');
        tr.className = 'fade-in-row';
        tr.style.animationDelay = `${idx * 0.05}s`;
        const badgeClass = `badge-status status-${v.statut.replace(' ', '_')}`;
        tr.innerHTML = `
            <td><strong>${v.immatriculation}</strong></td>
            <td>${v.marque} ${v.modele} (${v.type})</td>
            <td>${v.kilometrage.toLocaleString()} km</td>
            <td><span class="${badgeClass}">${v.statut}</span></td>
            <td><button class="action-btn-delete" title="Supprimer" onclick="deleteEntity('${v.immatriculation}', 'vehicules')"><i class="fa-solid fa-trash"></i></button></td>
        `;
        tbody.appendChild(tr);
    });
}

// ðŸ§‘...âœˆï¸ Injection Tableau Personnel ...” Fix #4 : colonnes stats enrichies
let _currentChauffeurPermis = null; // Fix #2 : permis du chauffeur en cours d'édition

async function loadStaffStats() {
    try {
        const res = await fetch(`${API_BASE}/api/data/chauffeurs-stats`);
        const data = await res.json();
        if (data.success) populateStaffTable(data.data);
    } catch(e) { console.error('Erreur chauffeurs-stats:', e); }
}

function populateStaffTable(chauffeurs) {
    const tbody = document.querySelector('#staffTable tbody');
    tbody.innerHTML = '';

    if (!chauffeurs.length) {
        tbody.innerHTML = `<tr><td colspan="5">
            <div class="empty-state">
                <div class="empty-state-icon" style="background:rgba(37,99,235,0.08);color:var(--primary);">
                    <i class="fa-solid fa-users"></i>
                </div>
                <h4>Aucun chauffeur enregistré</h4>
                <p>Votre registre du personnel est vide. Recrutez votre premier chauffeur pour commencer.</p>
                <button class="btn-primary" onclick="openModal('modal-staff')" style="flex-grow:0;">
                    <i class="fa-solid fa-user-plus"></i> Recruter un chauffeur
                </button>
            </div>
        </td></tr>`;
        return;
    }

    chauffeurs.forEach((c, idx) => {
        const tr = document.createElement('tr');
        tr.className = 'fade-in-row';
        tr.style.animationDelay = `${idx * 0.04}s`;

        const dispBool = (c.disponibilite === 1 || c.disponibilite === true || c.disponibilite === '1');
        const dispText  = dispBool ? 'Disponible' : 'Indisponible';
        const availClass = dispBool ? 'status-En_route' : 'status-En_panne';

        const note = c.note_moyenne !== null && c.note_moyenne !== undefined ? parseFloat(c.note_moyenne).toFixed(1) : null;
        const noteHTML = note ? `<i class="fa-solid fa-star" style="color:var(--warning);font-size:11px"></i> <strong>${note}</strong>` : '<span style="color:var(--text-muted)">N/A</span>';

        const nb      = c.nb_trajets || 0;
        const recette = c.recette_totale !== undefined ? Math.round(c.recette_totale).toLocaleString('fr-FR') + ' FCFA' : '...”';
        const retard  = c.retard_moyen !== undefined ? Math.round(c.retard_moyen) + ' min' : '...”';
        const retardColor = (c.retard_moyen||0) > 15 ? 'var(--danger)' : (c.retard_moyen||0) > 5 ? 'var(--warning)' : 'var(--success)';
        const incidents = c.nb_incidents || 0;
        const incColor  = incidents > 0 ? 'var(--danger)' : 'var(--text-muted)';
        const fullName  = `${c.prenom} ${c.nom}`;

        tr.innerHTML = `
            <td><span style="font-family:var(--font-heading);font-weight:700;color:var(--primary)">${c.numero_permis}</span></td>
            <td>
                <div style="display:flex;flex-direction:column;gap:2px;">
                    <strong style="font-size:14px">${c.prenom} ${c.nom}</strong>
                    <small style="color:var(--text-muted)">${c.telephone || ''}</small>
                    <small style="color:var(--text-muted);font-size:11px">${c.email || ''}</small>
                </div>
            </td>
            <td>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 12px;font-size:12px;">
                    <span title="Trajets"><i class="fa-solid fa-route" style="color:var(--primary);width:12px"></i> ${nb}</span>
                    <span title="Recette" style="white-space:nowrap"><i class="fa-solid fa-sack-dollar" style="color:var(--success);width:12px"></i> ${recette}</span>
                    <span title="Retard moyen" style="color:${retardColor}"><i class="fa-solid fa-clock" style="width:12px"></i> ${retard}</span>
                    <span title="Incidents" style="color:${incColor}"><i class="fa-solid fa-triangle-exclamation" style="width:12px"></i> ${incidents} &nbsp;${noteHTML}</span>
                </div>
            </td>
            <td><span class="badge-status ${availClass}">${dispText}</span></td>
            <td>
                <div style="display:flex;gap:5px;">
                    <button class="action-btn-delete" style="border-color:var(--primary);color:var(--primary)" title="Modifier profil" onclick="openModifierChauffeurModal('${c.numero_permis}', '${c.telephone}', '${c.email}', '${c.vehicule_immatriculation || ''}', ${dispBool}, '${fullName}')"><i class="fa-solid fa-user-pen"></i></button>
                    <button class="action-btn-delete" title="Licencier" onclick="deleteEntity('${c.numero_permis}', 'chauffeurs')"><i class="fa-solid fa-trash"></i></button>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// ==========================================
// ðŸ“ˆ GRAPHIQUES ET COURBES (CHART.JS)
// ==========================================
function drawCharts(vehicules) {
    Chart.defaults.color = '#64748b';
    Chart.defaults.font.family = "'Inter', sans-serif";

    // Détruire les graphiques existants pour éviter le crash Canvas
    if (chartInstances.fleet) chartInstances.fleet.destroy();
    if (chartInstances.revenue) chartInstances.revenue.destroy();

    // 1. Calcul Analytique (Ratio de flotte)
    let act=0, pan=0, maint=0;
    vehicules.forEach(v => {
        const stat = v.statut.toLowerCase();
        if(stat.includes('panne') || stat.includes('hors')) pan++;
        else if(stat.includes('maintenance') || stat.includes('révision')) maint++;
        else act++; // Actif, En route, etc.
    });

    const ctxFleet = document.getElementById('fleetChart').getContext('2d');
    chartInstances.fleet = new Chart(ctxFleet, {
        type: 'doughnut',
        data: {
            labels: ['Actif', 'En Panne', 'En Maintenance'],
            datasets: [{
                data: [act, pan, maint],
                backgroundColor: ['#2563eb', '#ef4444', '#f59e0b'],
                borderColor: '#ffffff',
                borderWidth: 2,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '75%',
            plugins: {
                legend: { position: 'bottom' }
            }
        }
    });

    // 2. Courbe d'Évolution Financière (Mockup Premium 7 Jours M-1)
    const ctxRev = document.getElementById('revenueChart').getContext('2d');
    
    // Dégradé bleu sous la courbe
    const gradient = ctxRev.createLinearGradient(0, 0, 0, 400);
    gradient.addColorStop(0, 'rgba(14, 165, 233, 0.3)');
    gradient.addColorStop(1, 'rgba(14, 165, 233, 0)');

    chartInstances.revenue = new Chart(ctxRev, {
        type: 'line',
        data: {
            labels: ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'],
            datasets: [{
                label: 'Recettes (FCFA)',
                data: [450000, 380000, 520000, 490000, 810000, 950000, 720000],
                borderColor: '#0ea5e9',
                backgroundColor: gradient,
                borderWidth: 3,
                fill: true,
                tension: 0.4,
                pointBackgroundColor: '#ffffff',
                pointBorderColor: '#0ea5e9',
                pointBorderWidth: 2,
                pointRadius: 4,
                pointHoverRadius: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, grid: { color: 'rgba(0,0,0,0.05)' } },
                x: { grid: { display: false } }
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}

// ==========================================
// ðŸ› ï¸ LOGIQUE ADMINISTRATEUR (C.R.U.D)
// ==========================================

window.choicesInstances = {};

function initChoices(selectId) {
    if (typeof Choices === 'undefined') return;
    const el = document.getElementById(selectId);
    if (!el) return;

    if (window.choicesInstances[selectId]) {
        window.choicesInstances[selectId].destroy();
    }

    const isSearchable = el.options && el.options.length > 5;

    window.choicesInstances[selectId] = new Choices(el, {
        searchEnabled: true,
        searchPlaceholderValue: 'Rechercher...',
        itemSelectText: '',
        noResultsText: 'Aucun résultat',
        noChoicesText: 'Aucune option',
        shouldSort: false
    });
}

async function populateSelectDropdown(selectId, endpoint, valueKey, labelCallback) {
    const select = document.getElementById(selectId);
    if (!select) return;
    
    select.innerHTML = '<option value="">Chargement...</option>';
    try {
        const res = await fetch(`${API_BASE}/api/data/${endpoint}`);
        const result = await res.json();
        
        select.innerHTML = '<option value="">-- Choisissez --</option>';
        if (result.success && result.data) {
            result.data.forEach(item => {
                const opt = document.createElement('option');
                opt.value = item[valueKey];
                opt.textContent = labelCallback(item);
                select.appendChild(opt);
            });
        }
    } catch (e) {
        select.innerHTML = '<option value="">Erreur serveur</option>';
    }

    // Activer l'ergonomie premium de la liste
    initChoices(selectId);
}

function openModal(modalId) {
    const modalEl = document.getElementById(modalId);
    if(!modalEl) return;
    
    modalEl.classList.remove('hidden');

    // Initialiser Choices statiques instantanément
    modalEl.querySelectorAll('select.msp-input, select[id^="mt-"]').forEach(sel => {
        if (sel.id) initChoices(sel.id);
    });
    // Pré-remplir les dates avec la date du jour si vides
    const dateField = document.getElementById('c-date-embauche');
    if (dateField && !dateField.value) dateField.value = new Date().toISOString().split('T')[0];
    const mDebut = document.getElementById('m-debut');
    if (mDebut && !mDebut.value) mDebut.value = new Date().toISOString().split('T')[0];
    const tDepart = document.getElementById('t-depart');
    if (tDepart && !tDepart.value) tDepart.value = new Date().toISOString().slice(0, 16);

    // Alimenter les balises select avec les données de la base MySQL
    if (modalId === 'modal-trajets') {
        populateSelectDropdown('t-ligne', 'lignes', 'code', i => `${i.code} - ${i.nom} (${i.origine} \u2192 ${i.destination})`);
        populateSelectDropdown('t-chauffeur', 'chauffeurs', 'numero_permis', i => {
            const disp = i.disponibilite ? '\u{1F7E2} Dispo' : '\u{1F534} Occupé';
            return `[${disp}] ${i.prenom} ${i.nom} (Permis: ${i.numero_permis})`;
        });
        populateSelectDropdown('t-vehicule', 'vehicules', 'immatriculation', i => {
            let statusIcon = '\u{1F534}';
            if (i.statut === 'actif' || i.statut.toLowerCase() === 'en route' || i.statut.toLowerCase() === 'disponible') statusIcon = '\u{1F7E2}';
            else if (i.statut.toLowerCase().includes('maintenance')) statusIcon = '\u{1F6E0}\uFE0F';
            else if (i.statut.toLowerCase().includes('panne')) statusIcon = '\u26A0\uFE0F';
            return `${statusIcon} ${i.immatriculation} (${i.marque} - ${i.statut})`;
        });
    } else if (modalId === 'modal-lignes') {
        initLigneMap();
    } else if (modalId === 'modal-incidents') {
        populateSelectDropdown('i-trajet', 'trajets-all', 'id_trajet', i => `Trajet N°${i.id_trajet} - Ligne ${i.ligne_code}`);
    } else if (modalId === 'modal-maintenances') {
        populateSelectDropdown('m-vehicule', 'vehicules', 'immatriculation', i => `${i.immatriculation} (${i.marque})`);
    } else if (modalId === 'modal-staff') {
        // Multi-step : réinitialiser à l'étape 1
        staffStepReset();
        // Pré-charger les véhicules dans le select de l'étape 3
        staffLoadVehicules();
    }
}

// ==========================================
// \uD83D\uDE4B... \u2708\uFE0F STEPPER MULTI-ÉTAPES CHAUFFEUR
// ==========================================
let _staffCurrentStep = 1;
const _staffStepLabels = ['Étape 1 sur 3 ... Identité', 'Étape 2 sur 3 ... Permis & Catégorie', 'Étape 3 sur 3 ... Affectation & Récap'];
const _staffProgressWidths = ['33.3%', '66.6%', '100%'];

function staffStepReset() {
    _staffCurrentStep = 1;
    staffRenderStep();
    // Réinitialiser le formulaire
    document.getElementById('form-staff').reset();
    document.getElementById('msp-avatar-preview').innerHTML = '<i class="fa-solid fa-camera"></i>';
    document.getElementById('msp-avatar-preview').style.fontSize = '18px';
    // Réinitialiser les cartes catégories
    document.querySelectorAll('.msp-cat-card').forEach(c => c.classList.remove('active'));
    document.querySelector('.msp-cat-card[data-val="D"]').classList.add('active');
    document.getElementById('c-categorie').value = 'D';
    // Réinitialiser toggle dispo
    document.querySelectorAll('.msp-avail-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('.msp-avail-btn').classList.add('active');
    document.getElementById('c-disponibilite').value = '1';
    // Réinitialiser recap
    ['recap-name','recap-email','recap-tel','recap-permis'].forEach(id => {
        const el = document.getElementById(id); if(el) el.textContent = '...';
    });
    document.getElementById('recap-avatar').textContent = '?';
    // Steps dots reset
    for(let i=1;i<=3;i++){
        const dot = document.getElementById(`step-dot-${i}`);
        if(dot){ dot.classList.remove('active','done'); }
    }
    document.querySelectorAll('.msp-step-line').forEach(l => l.classList.remove('done'));
}

function staffRenderStep() {
    const step = _staffCurrentStep;
    // Panels
    for(let i=1;i<=3;i++){
        const p = document.getElementById(`msp-panel-${i}`);
        if(p) p.classList.toggle('hidden', i !== step);
    }
    // Progress
    document.getElementById('msp-progress-fill').style.width = _staffProgressWidths[step-1];
    document.getElementById('msp-step-label').textContent = _staffStepLabels[step-1];
    // Step dots
    for(let i=1;i<=3;i++){
        const dot = document.getElementById(`step-dot-${i}`);
        if(!dot) continue;
        dot.classList.remove('active','done');
        if(i < step) dot.classList.add('done');
        else if(i === step) dot.classList.add('active');
    }
    // Lines
    const lines = document.querySelectorAll('.msp-step-line');
    lines.forEach((l, idx) => l.classList.toggle('done', idx < step-1));
    // Boutons nav
    document.getElementById('msp-btn-prev').style.display  = step > 1 ? '' : 'none';
    document.getElementById('msp-btn-next').style.display  = step < 3 ? '' : 'none';
    document.getElementById('msp-btn-submit').style.display = step === 3 ? '' : 'none';
    // Si étape 3, mettre à jour le recap
    if(step === 3) staffUpdateRecap();
}

function staffStepNext() {
    if(_staffCurrentStep === 1 && !staffValidateStep1()) return;
    if(_staffCurrentStep === 2 && !staffValidateStep2()) return;
    if(_staffCurrentStep < 3) { _staffCurrentStep++; staffRenderStep(); }
}
function staffStepPrev() {
    if(_staffCurrentStep > 1) { _staffCurrentStep--; staffRenderStep(); }
}

function staffValidateStep1() {
    const prenom = document.getElementById('c-prenom').value.trim();
    const nom    = document.getElementById('c-nom').value.trim();
    const email  = document.getElementById('c-email').value.trim();
    const tel    = document.getElementById('c-telephone').value.trim();
    if(!prenom || !nom) { showNotification('error', 'Champs requis', 'Veuillez saisir le prénom et le nom.'); return false; }
    if(!email || !email.includes('@')) { showNotification('error', 'Email invalide', 'Adresse email incorrecte.'); return false; }
    if(!tel) { showNotification('error', 'Téléphone requis', 'Numéro de téléphone obligatoire.'); return false; }
    return true;
}
function staffValidateStep2() {
    const permis = document.getElementById('c-permis').value.trim();
    if(!permis) { showNotification('error', 'Permis requis', 'Le numéro de permis est obligatoire.'); return false; }
    return true;
}

function updateStaffAvatar() {
    const prenom = (document.getElementById('c-prenom').value || '').trim();
    const nom    = (document.getElementById('c-nom').value || '').trim();
    const el     = document.getElementById('msp-avatar-preview');
    if(prenom || nom) {
        const initials = (prenom[0] || '') + (nom[0] || '');
        el.textContent = initials.toUpperCase();
        el.style.fontSize = '20px';
    } else {
        el.innerHTML = '<i class="fa-solid fa-camera"></i>';
        el.style.fontSize = '18px';
    }
}

function staffUpdateRecap() {
    const prenom = document.getElementById('c-prenom').value.trim();
    const nom    = document.getElementById('c-nom').value.trim();
    const email  = document.getElementById('c-email').value.trim();
    const tel    = document.getElementById('c-telephone').value.trim();
    const permis = document.getElementById('c-permis').value.trim();
    const initials = ((prenom[0]||'') + (nom[0]||'')).toUpperCase() || '?';
    document.getElementById('recap-avatar').textContent = initials;
    document.getElementById('recap-name').textContent   = prenom && nom ? `${prenom} ${nom}` : '...';
    document.getElementById('recap-email').textContent  = email  || '...';
    document.getElementById('recap-tel').textContent    = tel    || '...';
    document.getElementById('recap-permis').textContent = permis || '...';
}

function setStaffAvail(available, btn) {
    document.querySelectorAll('.msp-avail-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('c-disponibilite').value = available ? '1' : '0';
}

// Chargement véhicules dans le select étape 3
async function staffLoadVehicules() {
    const sel = document.getElementById('c-vehicule');
    if(!sel) return;
    sel.innerHTML = '<option value="">... Aucun véhicule assigné pour l\'instant ...</option>';
    try {
        const res  = await fetch(`${API_BASE}/api/data/vehicules`);
        const data = await res.json();
        if(data.success) {
            data.data.forEach(v => {
                const opt = document.createElement('option');
                opt.value = v.immatriculation;
                opt.textContent = `${v.immatriculation} ... ${v.marque} ${v.modele} (${v.statut})`;
                sel.appendChild(opt);
            });
        }
    } catch(_) {}
    initChoices('c-vehicule');
}

// Sync catégories permis (radio \u2192 select caché)
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.msp-cat-card').forEach(card => {
        card.addEventListener('click', () => {
            document.querySelectorAll('.msp-cat-card').forEach(c => c.classList.remove('active'));
            card.classList.add('active');
            const val = card.getAttribute('data-val');
            card.querySelector('input[type="radio"]').checked = true;
            document.getElementById('c-categorie').value = val;
        });
    });
});

function closeModal(modalId) {
    document.getElementById(modalId).classList.add('hidden');
    if (modalId === 'modal-lignes') {
        if(typeof resetLigneMapState === 'function') resetLigneMapState();
    }
}

// Map du formulaire -> nom de la modal
const MODAL_MAP = {
    vehicules: 'modal-fleet', chauffeurs: 'modal-staff',
    lignes: 'modal-lignes', trajets: 'modal-trajets',
    incidents: 'modal-incidents', maintenances: 'modal-maintenances'
};

async function handleFormSubmit(event, type) {
    event.preventDefault();

    // \u2014\u2014 Indicateur de chargement sur le bouton submit \u2014\u2014
    const submitBtn = event.target.querySelector('button[type="submit"]');
    const originalHTML = submitBtn ? submitBtn.innerHTML : '';
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> En cours...';
    }

    let payload = {};

    // ─── VALIDATION OBLIGATOIRE (anti-soumission vide) ─────────────────────────
    const required = {
        vehicules:    [['v-immatriculation','Immatriculation'],['v-marque','Marque'],['v-modele','Modèle'],['v-capacite','Capacité']],
        chauffeurs:   [['c-permis','Numéro de permis'],['c-prenom','Prénom'],['c-nom','Nom'],['c-email','Email'],['c-telephone','Téléphone']],
        lignes:       [['l-code','Code ligne'],['l-nom','Nom'],['l-origine','Origine'],['l-destination','Destination']],
        trajets:      [['t-ligne','Ligne'],['t-chauffeur','Chauffeur'],['t-vehicule','Véhicule'],['t-depart','Date départ']],
        incidents:    [['i-trajet','Trajet'],['i-type','Type'],['i-description','Description']],
        maintenances: [['m-vehicule','Véhicule'],['m-type','Type intervention'],['m-debut','Date début']]
    };
    const checks = required[type] || [];
    for(const [id, label] of checks) {
        const el = document.getElementById(id);
        const val = el ? el.value.trim() : '';
        if(!val) {
            showNotification('error', 'Champ obligatoire manquant', `Le champ "${label}" est requis. Veuillez le remplir avant de soumettre.`);
            if(submitBtn) { submitBtn.disabled = false; submitBtn.innerHTML = originalHTML; }
            if(el) { el.focus(); el.style.borderColor = 'var(--danger)'; setTimeout(()=>el.style.borderColor='',3000); }
            return;
        }
    }

    if(type === 'vehicules') {
        payload = {
            immatriculation: document.getElementById('v-immatriculation').value.trim(),
            marque: document.getElementById('v-marque').value.trim(),
            modele: document.getElementById('v-modele').value.trim(),
            capacite: parseInt(document.getElementById('v-capacite').value),
            kilometrage_seuil: parseInt(document.getElementById('v-seuil').value) || 150000,
            type: "bus"
        };
    } else if(type === 'chauffeurs') {
        const dateVal = document.getElementById('c-date-embauche').value;
        payload = {
            numero_permis: document.getElementById('c-permis').value.trim().toUpperCase(),
            prenom: document.getElementById('c-prenom').value.trim(),
            nom: document.getElementById('c-nom').value.trim(),
            email: document.getElementById('c-email').value.trim(),
            telephone: document.getElementById('c-telephone').value.trim(),
            categorie_permis: document.getElementById('c-categorie').value,
            disponibilite: document.getElementById('c-disponibilite').value === '1',
            date_embauche: dateVal || null,
            vehicule_immatriculation: document.getElementById('c-vehicule').value || null
        };
    } else if(type === 'lignes') {
        payload = {
            code: document.getElementById('l-code').value.toUpperCase(),
            nom: document.getElementById('l-nom').value,
            origine: document.getElementById('l-origine').value,
            destination: document.getElementById('l-destination').value,
            distance_km: parseFloat(document.getElementById('l-distance').value) || null,
            duree_minutes: parseInt(document.getElementById('l-duree').value) || null,
            prix: parseFloat(document.getElementById('l-prix').value) || 0.0
        };
    } else if(type === 'trajets') {
        payload = {
            ligne_code: document.getElementById('t-ligne').value.toUpperCase(),
            chauffeur_permis: document.getElementById('t-chauffeur').value,
            vehicule_immatriculation: document.getElementById('t-vehicule').value,
            date_heure_depart: document.getElementById('t-depart').value.replace('T', ' '),
            nb_passagers: parseInt(document.getElementById('t-passagers').value) || 0
        };
    } else if(type === 'incidents') {
        payload = {
            trajet_id: parseInt(document.getElementById('i-trajet').value),
            type: document.getElementById('i-type').value,
            description: document.getElementById('i-description').value,
            gravite: document.getElementById('i-gravite').value,
            cout_reparation: parseFloat(document.getElementById('i-cout').value) || 0
        };
    } else if(type === 'maintenances') {
        payload = {
            vehicule_immatriculation: document.getElementById('m-vehicule').value,
            type_intervention: document.getElementById('m-type').value,
            technicien: document.getElementById('m-technicien').value || null,
            date_debut: document.getElementById('m-debut').value,
            date_fin: document.getElementById('m-fin').value || null,
            cout: parseFloat(document.getElementById('m-cout').value) || null
        };
    }

    try {
        const res = await fetch(`${API_BASE}/api/crud/${type}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        const data = await res.json();

        // Restaurer le bouton dans tous les cas
        if (submitBtn) { submitBtn.disabled = false; submitBtn.innerHTML = originalHTML; }

        if (res.ok && data.success) {
            closeModal(MODAL_MAP[type]);
            event.target.reset();
            const msgOk = {
                vehicules:    'Bus ajouté à la flotte avec succès !',
                chauffeurs:   'Chauffeur embauché avec succès !',
                lignes:       'Ligne créée et enregistrée !',
                trajets:      'Trajet planifié avec succès !',
                incidents:    'Incident signalé et enregistré !',
                maintenances: 'Maintenance programmée !'
            };
            showNotification('success', 'Enregistrement réussi \u2705', msgOk[type] || 'Opération réussie !');
            loadAllViewData();
        } else {
            let errMsg = 'Erreur inconnue du serveur.';
            if (Array.isArray(data.detail)) {
                errMsg = data.detail.map(e => `<b>${e.loc[e.loc.length-1]}</b> : ${e.msg}`).join('<br>');
            } else if (data.detail) {
                errMsg = data.detail;
            } else if (data.error) {
                errMsg = data.error;
            }
            showNotification('error', 'Erreur serveur', errMsg);
        }
    } catch (err) {
        if (submitBtn) { submitBtn.disabled = false; submitBtn.innerHTML = originalHTML; }
        console.error('Erreur réseau / CORS :', err);
        showNotification('error', 'Serveur injoignable', 'Vérifiez que FastAPI est actif.');
    }
}

// ==========================================
// \uD83D\uDEE1\uFE0F SYSTÈME DE CONFIRMATION (MODAL PREMIUM)
// ==========================================
function showConfirmDialog(title, message, confirmCallback, opts = {}) {
    const old = document.getElementById('custom-confirm-modal');
    if (old) old.remove();

    const type    = opts.type    || 'danger';   // 'danger' | 'warning' | 'info'
    const iconKey = opts.icon    || 'triangle-exclamation';
    const confirmLabel = opts.confirmLabel || 'Confirmer';
    const cancelLabel  = opts.cancelLabel  || 'Annuler';

    const colors = {
        danger:  { bar: 'linear-gradient(90deg,#ef4444,#f97316)', icon: '#ef4444', iconBg: 'rgba(239,68,68,0.09)', iconBorder: 'rgba(239,68,68,0.18)', btnGrad: 'linear-gradient(135deg,#ef4444,#dc2626)', btnShadow: 'rgba(239,68,68,0.35)' },
        warning: { bar: 'linear-gradient(90deg,#f59e0b,#f97316)', icon: '#d97706', iconBg: 'rgba(245,158,11,0.09)', iconBorder: 'rgba(245,158,11,0.2)',  btnGrad: 'linear-gradient(135deg,#f59e0b,#d97706)', btnShadow: 'rgba(245,158,11,0.35)' },
        info:    { bar: 'linear-gradient(90deg,#2563eb,#7c3aed)', icon: '#2563eb', iconBg: 'rgba(37,99,235,0.09)',  iconBorder: 'rgba(37,99,235,0.18)',  btnGrad: 'linear-gradient(135deg,#2563eb,#1d4ed8)', btnShadow: 'rgba(37,99,235,0.35)' },
    };
    const c = colors[type];

    const overlay = document.createElement('div');
    overlay.id = 'custom-confirm-modal';
    overlay.style.cssText = `position:fixed;inset:0;z-index:999999;background:rgba(15,23,42,0.5);
        backdrop-filter:blur(8px);display:flex;align-items:center;justify-content:center;
        animation:fadeInOverlay 0.2s ease;`;

    overlay.innerHTML = `
        <div style="background:#0d1117;border-radius:24px;width:400px;max-width:calc(100vw - 28px);
            border:1px solid rgba(255,255,255,0.08);box-shadow:0 30px 80px rgba(0,0,0,0.6);animation:logoutSlideIn 0.3s cubic-bezier(0.16,1,0.3,1);
            overflow:hidden;font-family:var(--font-body);">
            <div style="height:4px;background:${c.bar};"></div>
            <div style="display:flex;flex-direction:column;align-items:center;padding:32px 28px 0;text-align:center;gap:14px;">
                <div style="width:68px;height:68px;background:${c.iconBg};border:2px solid ${c.iconBorder};
                    border-radius:50%;display:flex;align-items:center;justify-content:center;
                    font-size:26px;color:${c.icon};animation:logoutIconPulse 1.8s ease infinite;">
                    <i class="fa-solid fa-${iconKey}"></i>
                </div>
                <div>
                    <h3 style="font-family:var(--font-heading);font-size:19px;font-weight:700;color:#e2e8f0;margin:0 0 8px;">${title}</h3>
                    <p style="font-size:14px;color:#94a3b8;line-height:1.55;margin:0;">${message}</p>
                </div>
            </div>
            <div style="display:flex;gap:12px;padding:24px 28px 28px;">
                <button id="cc-cancel" style="flex:1;padding:13px;background:rgba(255,255,255,0.06);color:#94a3b8;border:1.5px solid rgba(255,255,255,0.1);border-radius:12px;font-size:14px;font-weight:600;
                    cursor:pointer;font-family:var(--font-body);transition:all 0.18s;">
                    <i class="fa-solid fa-xmark"></i> ${cancelLabel}
                </button>
                <button id="cc-confirm" style="flex:1;padding:13px;background:${c.btnGrad};
                    color:white;border:none;border-radius:12px;font-size:14px;font-weight:700;
                    cursor:pointer;font-family:var(--font-body);
                    box-shadow:0 4px 14px ${c.btnShadow};transition:all 0.18s;">
                    <i class="fa-solid fa-check"></i> ${confirmLabel}
                </button>
            </div>
        </div>`;

    document.body.appendChild(overlay);

    const close = () => { overlay.style.opacity='0'; overlay.style.transition='opacity 0.18s'; setTimeout(() => overlay.remove(), 180); };
    overlay.addEventListener('click', e => { if(e.target === overlay) close(); });
    document.getElementById('cc-cancel').addEventListener('click', close);
    const onEsc = e => { if(e.key==='Escape'){ close(); document.removeEventListener('keydown',onEsc); } };
    document.addEventListener('keydown', onEsc);

    document.getElementById('cc-confirm').addEventListener('click', () => {
        close();
        confirmCallback();
    });
}

async function deleteEntity(id, type) {
    const labels = {
        vehicules:    { label: 'ce véhicule',      icon: 'bus',                  type: 'danger' },
        chauffeurs:   { label: 'ce chauffeur',      icon: 'user',                 type: 'danger' },
        lignes:       { label: 'cette ligne',       icon: 'route',                type: 'danger' },
        trajets:      { label: 'ce trajet',         icon: 'clock-rotate-left',    type: 'danger' },
        incidents:    { label: 'cet incident',      icon: 'triangle-exclamation', type: 'warning' },
        maintenances: { label: 'cette maintenance', icon: 'wrench',               type: 'warning' }
    };
    const cfg = labels[type] || { label: 'cet élément', icon: 'trash', type: 'danger' };

    showConfirmDialog(
        'Confirmer la suppression',
        `Êtes-vous sûr de vouloir supprimer définitivement <strong>${cfg.label}</strong> ?<br>
         <span style="font-size:12px;color:#94a3b8;">Cette action est irréversible et ne peut pas être annulée.</span>`,
        async () => {
            try {
                const res = await fetch(`${API_BASE}/api/crud/${type}/${id}`, { method: 'DELETE' });
                const data = await res.json();
                if(res.ok && data.success) {
                    showNotification('success', 'Suppression réussie', 'Entrée supprimée de la base de données.');
                    loadAllViewData();
                } else {
                    showNotification('error', 'Erreur suppression', data.detail || 'Impossible de supprimer.');
                }
            } catch (err) {
                showNotification('error', 'Serveur injoignable', 'Vérifiez que FastAPI est actif.');
            }
        },
        { type: cfg.type, icon: cfg.icon, confirmLabel: 'Supprimer définitivement', cancelLabel: 'Annuler' }
    );
}

async function patchEntity(id, type, action) {
    try {
        let url = `${API_BASE}/api/crud/${type}/${id}/${action}`;
        if(type === 'trajets' && action === 'statut') {
            const statut = prompt("Nouveau statut ? (planifie / en_cours / termine / annule)");
            if(!statut) return;
            url += `?statut=${statut}`;
        }
        const res = await fetch(url, { method: 'PATCH' });
        const data = await res.json();
        if(res.ok && data.success) {
            showNotification('success', 'Mise à jour réussie', 'Le statut a été modifié.');
            loadAllViewData();
        } else {
            showNotification('error', 'Erreur', data.detail || 'Mise à jour échouée.');
        }
    } catch(e) {
        showNotification('error', 'Serveur injoignable', 'Vérifiez que FastAPI est actif.');
    }
}

// ==========================================
// \uD83D\uDD14 SYSTÈME DE NOTIFICATIONS TOAST (compat)
// ==========================================
// Alias vers showNotification() pour compatibilité avec ancien code
function showToast(message, type = 'success') {
    const typeMap = { 'success': 'success', 'error': 'error', 'warning': 'warning' };
    const titleMap = { 'success': 'Succès', 'error': 'Erreur', 'warning': 'Attention' };
    showNotification(typeMap[type] || 'success', titleMap[type] || 'Info', message);
}

// ==========================================
// \uD83D\uDD04 FILTRE TEMPOREL GLOBAL & TRI
// ==========================================
function getWeekNumber(d) {
    if (!d || isNaN(d.getTime())) return null;
    let dCopy = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    dCopy.setUTCDate(dCopy.getUTCDate() + 4 - (dCopy.getUTCDay() || 7));
    let yearStart = new Date(Date.UTC(dCopy.getUTCFullYear(), 0, 1));
    let weekNo = Math.ceil((((dCopy - yearStart) / 86400000) + 1) / 7);
    return dCopy.getUTCFullYear() + "-W" + (weekNo < 10 ? "0" : "") + weekNo;
}

function clearGlobalDateFilter() {
    const input = document.getElementById('global-date-picker');
    if (input) {
        input.value = '';
        applyGlobalDateFilter();
    }
}

function applyGlobalDateFilter() {
    const input = document.getElementById('global-date-picker')?.value;
    const btnClear = document.getElementById('clear-date-filter');
    
    if (btnClear) {
        btnClear.style.display = input ? 'inline-block' : 'none';
    }

    const filterData = (dataList, dateField) => {
        if (!input) return dataList;
        return dataList.filter(item => {
            if (!item[dateField]) return false;
            const itemWeek = getWeekNumber(new Date(item[dateField]));
            return itemWeek === input;
        });
    };

    const fTrajets = filterData(GLOBAL_STORE.trajets || [], 'date_heure_depart');
    const fIncidents = filterData(GLOBAL_STORE.incidents || [], 'date_incident');
    const fMaintenances = filterData(GLOBAL_STORE.maintenances || [], 'date_debut');

    populateTrajetsAllTable(fTrajets);
    populateIncidentsTable(fIncidents);
    populateMaintenancesTable(fMaintenances);

    // \u2014\u2014 NOUVEAU : Synchronisation des KPI du Dashboard \u2014\u2014
    const periodSelect = document.getElementById('dashboard-period');
    const dateDebutInput = document.getElementById('db-date-debut');
    const dateFinInput = document.getElementById('db-date-fin');

    if (input && dateDebutInput && dateFinInput) {
        try {
            // Parser YYYY-Www et convertir en range Date (Lundi à Dimanche)
            const year = parseInt(input.substring(0, 4));
            const week = parseInt(input.substring(6, 8));
            
            const simple = new Date(Date.UTC(year, 0, 1 + (week - 1) * 7));
            const dow = simple.getUTCDay();
            const start = new Date(simple);
            if (dow <= 4) start.setUTCDate(simple.getUTCDate() - simple.getUTCDay() + 1);
            else start.setUTCDate(simple.getUTCDate() + 8 - simple.getUTCDay());
            
            const end = new Date(start);
            end.setUTCDate(start.getUTCDate() + 6);
            
            dateDebutInput.value = start.toISOString().split('T')[0];
            dateFinInput.value = end.toISOString().split('T')[0];
            if (periodSelect) periodSelect.value = 'custom';
            
            // Masquer les inputs custom natifs s'ils existent (car paramétrés globalement)
            const customDiv = document.getElementById('custom-date-filters');
            if(customDiv) customDiv.style.display = 'none';
            
        } catch(e) { console.error('Erreur conversion Semaine -> Dates', e); }
    } else {
        if (periodSelect) periodSelect.value = 'tout';
        if (dateDebutInput) dateDebutInput.value = '';
        if (dateFinInput) dateFinInput.value = '';
    }

    // Charger les KPI Backend avec la nouvelle période !
    loadDashboardStats();
}

function clearGlobalDateFilter() {
    const picker = document.getElementById('global-date-picker');
    if (picker) picker.value = '';
    applyGlobalDateFilter();
}

// ==========================================
// \uD83D\uDD04 CHARGEMENT GLOBAL DE TOUTES LES VUES
// ==========================================
async function loadAllViewData() {
    loadDashboardKPIs(); // Recharge Flotte + Chauffeurs + KPI
    loadExtendedViews(); // Recharge Lignes, Trajets, Incidents, Maintenances
}

async function loadExtendedViews() {
    try {
        const [lignesRes, trajetsRes, incidentsRes, maintRes] = await Promise.all([
            fetch(`${API_BASE}/api/data/lignes`),
            fetch(`${API_BASE}/api/data/trajets-all`),
            fetch(`${API_BASE}/api/data/incidents`),
            fetch(`${API_BASE}/api/data/maintenances`)
        ]);
        const [lignesData, trajetsData, incidentsData, maintData] = await Promise.all([
            lignesRes.json(), trajetsRes.json(), incidentsRes.json(), maintRes.json()
        ]);
        
        if(lignesData.success) populateLignesTable(lignesData.data);
        
        // Stockage et TRIS par défaut (Plus récent -> Plus ancien)
        if(trajetsData.success) {
            GLOBAL_STORE.trajets = trajetsData.data.sort((a, b) => new Date(b.date_heure_depart || 0) - new Date(a.date_heure_depart || 0));
        }
        if(incidentsData.success) {
            GLOBAL_STORE.incidents = incidentsData.data.sort((a, b) => new Date(b.date_incident || 0) - new Date(a.date_incident || 0));
        }
        if(maintData.success) {
            GLOBAL_STORE.maintenances = maintData.data.sort((a, b) => new Date(b.date_debut || 0) - new Date(a.date_debut || 0));
        }

        // Appliquer le filtre (ou afficher tout si aucun filtre) et rafraîchir le DOM
        applyGlobalDateFilter();

    } catch(e) { console.error('Erreur chargement vues:', e); }
}

function populateLignesTable(lignes) {
    const tbody = document.querySelector('#lignesTable tbody');
    tbody.innerHTML = '';

    if (!lignes.length) {
        tbody.innerHTML = `<tr><td colspan="7">
            <div class="empty-state">
                <div class="empty-state-icon" style="background:rgba(0,210,172,0.08);color:var(--secondary);">
                    <i class="fa-solid fa-route"></i>
                </div>
                <h4>Aucune ligne créée</h4>
                <p>Définissez les lignes de votre réseau de transport pour pouvoir planifier des trajets.</p>
                <button class="btn-primary" onclick="openModal('modal-lignes')" style="flex-grow:0;">
                    <i class="fa-solid fa-plus"></i> Créer une ligne
                </button>
            </div>
        </td></tr>`;
        return;
    }

    lignes.forEach((l, idx) => {
        const tr = document.createElement('tr');
        tr.className = 'fade-in-row';
        tr.style.animationDelay = `${idx * 0.05}s`;
        tr.innerHTML = `
            <td><strong style="color:var(--secondary)">${l.code}</strong></td>
            <td>${l.nom || '-'}</td>
            <td>${l.origine}</td>
            <td>${l.destination}</td>
            <td>${l.distance_km ? l.distance_km + ' km' : '-'}</td>
            <td>${l.duree_minutes ? l.duree_minutes + ' min' : '-'}</td>
            <td><button class="action-btn-delete" onclick="deleteEntity('${l.code}', 'lignes')"><i class="fa-solid fa-trash"></i></button></td>
        `;
        tbody.appendChild(tr);
    });
}

// \uD83D\uDE8C TRAJETS ... Boutons contextuels intelligents par statut
let _currentTrajetId = null; // ID du trajet courant pour les modaux

function populateTrajetsAllTable(trajets) {
    const tbody = document.querySelector('#trajetsAllTable tbody');
    tbody.innerHTML = '';

    if (!trajets.length) {
        tbody.innerHTML = `<tr><td colspan="7">
            <div class="empty-state">
                <div class="empty-state-icon" style="background:rgba(245,158,11,0.08);color:var(--warning);">
                    <i class="fa-solid fa-clock-rotate-left"></i>
                </div>
                <h4>Aucun trajet planifié</h4>
                <p>Aucun trajet ne correspond à votre recherche ou période sélectionnée.</p>
                <button class="btn-primary" onclick="openModal('modal-trajets')" style="flex-grow:0;">
                    <i class="fa-solid fa-plus"></i> Planifier un trajet
                </button>
            </div>
        </td></tr>`;
        return;
    }

    trajets.forEach((t, idx) => {
        const tr = document.createElement('tr');
        tr.className = 'fade-in-row';
        tr.style.animationDelay = `${idx * 0.05}s`;

        // Badges de statut premium
        const badgeMap = {
            planifie:  { cls: 'badge-planifie',  icon: 'clock',         label: 'Planifié'  },
            en_cours:  { cls: 'badge-en-cours',   icon: 'circle-dot',   label: 'En cours'  },
            termine:   { cls: 'badge-termine',    icon: 'circle-check', label: 'Terminé'   },
            annule:    { cls: 'badge-annule',     icon: 'circle-xmark', label: 'Annulé'    }
        };
        const badge = badgeMap[t.statut] || { cls: '', icon: 'question', label: t.statut };
        const depart = t.date_heure_depart ? new Date(t.date_heure_depart).toLocaleString('fr-FR', {day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}) : '-';

        // Boutons contextuels par état
        let actionsHTML = '';
        if (t.statut === 'planifie') {
            actionsHTML = `
                <button class="ctx-btn ctx-edit"  onclick="openModifierTrajetModal(${t.id_trajet})" title="Modifier / Réassigner"><i class="fa-solid fa-pen-to-square"></i></button>
                <button class="ctx-btn ctx-start" onclick="demarrerTrajet(${t.id_trajet})"           title="Démarrer le trajet"><i class="fa-solid fa-play"></i></button>
                <button class="ctx-btn ctx-delete" onclick="deleteEntity(${t.id_trajet}, 'trajets')" title="Supprimer"><i class="fa-solid fa-trash"></i></button>`;
        } else if (t.statut === 'en_cours') {
            actionsHTML = `
                <button class="ctx-btn ctx-done"   onclick="openClotureModal(${t.id_trajet}, '${t.ligne_code}')" title="Clôturer le trajet"><i class="fa-solid fa-flag-checkered"></i></button>
                <button class="ctx-btn ctx-cancel" onclick="annulerTrajet(${t.id_trajet})"                        title="Annuler le trajet"><i class="fa-solid fa-ban"></i></button>`;
        } else {
            actionsHTML = `<span class="ctx-locked" title="Trajet '${t.statut}' ... document comptable protégé"><i class="fa-solid fa-lock"></i></span>`;
        }

        tr.innerHTML = `
            <td><span style="color:var(--text-muted);font-size:12px">#</span>${t.id_trajet}</td>
            <td><strong style="color:var(--secondary)">${t.ligne_code}</strong></td>
            <td>${t.chauffeur_nom || '<span style="color:var(--text-muted)">...</span>'}</td>
            <td style="font-size:13px">${t.vehicule_immatriculation}</td>
            <td style="font-size:12px;color:var(--text-muted)">${depart}</td>
            <td><span class="badge-status ${badge.cls}"><i class="fa-solid fa-${badge.icon}"></i> ${badge.label}</span></td>
            <td><div class="ctx-actions">${actionsHTML}</div></td>
        `;
        tbody.appendChild(tr);
    });
}

// \u2014\u2014 Démarrer un trajet (planifie \u2192 en_cours) \u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014
async function demarrerTrajet(id) {
    try {
        const res = await fetch(`${API_BASE}/api/crud/trajets/${id}/demarrer`, { method: 'PATCH' });
        const data = await res.json();
        if (res.ok && data.success) {
            showNotification('success', 'Trajet Démarré \uD83D\uDE8C', `Trajet #${id} en cours. Chauffeur en route !`);
            loadAllViewData();
        } else {
            showNotification('error', 'Impossible de démarrer', data.detail || data.error || 'Erreur inconnue.');
        }
    } catch (e) {
        showNotification('error', 'Serveur injoignable', 'Vérifiez que FastAPI est actif.');
    }
}

// \u2014\u2014 Ouvrir modal de clôture \u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014
let _currentTarifNormal = 0;

async function openClotureModal(id, ligneCode) {
    _currentTrajetId = id;

    // Pré-remplir heure d'arrivée avec maintenant
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
    document.getElementById('c2-arrivee').value = now.toISOString().slice(0,16);
    document.getElementById('c2-retard').value   = '0';

    document.getElementById('modal-cloture').classList.remove('hidden');
}

// \u2014\u2014 Soumettre la clôture \u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014
async function handleClotureSubmit(event) {
    event.preventDefault();
    const btn = event.target.querySelector('button[type="submit"]');
    const orig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Clôture...';

    const payload = {
        date_heure_arrivee: document.getElementById('c2-arrivee').value.replace('T', ' '),
        retard_minutes:     parseInt(document.getElementById('c2-retard').value) || 0
    };

    try {
        const res  = await fetch(`${API_BASE}/api/crud/trajets/${_currentTrajetId}/terminer`, {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
        });
        const data = await res.json();
        btn.disabled = false; btn.innerHTML = orig;
        if (res.ok && data.success) {
            closeModal('modal-cloture');
            document.getElementById('form-cloture').reset();
            showNotification('success', 'Trajet Clôturé \u2705', `Trajet #${_currentTrajetId} terminé. Chauffeur libéré.`);
            loadAllViewData();
        } else {
            showNotification('error', 'Erreur Clôture', data.detail || data.error || 'Erreur inconnue.');
        }
    } catch(e) { btn.disabled = false; btn.innerHTML = orig; showNotification('error', 'Serveur injoignable', 'Vérifiez FastAPI.'); }
}

// \u2014\u2014 Annuler un trajet \u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014
async function annulerTrajet(id) {
    showConfirmDialog(
        'Annuler le trajet',
        `Vous êtes sur le point d'annuler le trajet <strong>#${id}</strong>.<br>
         <span style="font-size:12px;color:#94a3b8;">Le chauffeur et le bus seront immédiatement libérés.</span>`,
        async () => {
            try {
                const res  = await fetch(`${API_BASE}/api/crud/trajets/${id}/annuler`, { method: 'PATCH' });
                const data = await res.json();
                if (res.ok && data.success) {
                    showNotification('warning', 'Trajet Annulé', `Trajet #${id} annulé. Chauffeur libéré.`);
                    loadAllViewData();
                } else {
                    showNotification('error', 'Erreur annulation', data.detail || data.error || 'Erreur inconnue.');
                }
            } catch(e) {
                showNotification('error', 'Serveur injoignable', 'Vérifiez que FastAPI est actif.');
            }
        },
        { type: 'warning', icon: 'ban', confirmLabel: 'Oui, annuler', cancelLabel: 'Garder' }
    );
}

// \u2014\u2014 Ouvrir modal de modification \u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014\u2014
async function openModifierTrajetModal(id) {
    _currentTrajetId = id;
    // Charger les selects
    await Promise.all([
        populateSelectDropdown('mt-chauffeur', 'chauffeurs', 'numero_permis', i => {
            const dispo = i.disponibilite ? 'ðŸŸ¢' : 'ðŸ”´';
            return `${dispo} ${i.prenom} ${i.nom} (${i.numero_permis})`;
        }),
        populateSelectDropdown('mt-vehicule', 'vehicules', 'immatriculation', i => {
            let statusIcon = 'ðŸ”´';
            if (i.statut === 'actif' || i.statut.toLowerCase() === 'en route' || i.statut.toLowerCase() === 'disponible') statusIcon = 'ðŸŸ¢';
            else if (i.statut.toLowerCase().includes('maintenance')) statusIcon = 'ðŸ› ï¸';
            else if (i.statut.toLowerCase().includes('panne')) statusIcon = 'âš ï¸';
            return `${statusIcon} ${i.immatriculation} ...” ${i.marque} ${i.modele} (${i.statut})`;
        }),
        populateSelectDropdown('mt-ligne', 'lignes', 'code', i => `${i.code} ...” ${i.nom} (${i.origine} â†’ ${i.destination})`)
    ]);
    // Ajouter option "conserver" en tête de chaque select
    ['mt-chauffeur','mt-vehicule','mt-ligne'].forEach(id => {
        const sel = document.getElementById(id);
        const opt = document.createElement('option');
        opt.value = ''; opt.textContent = '...” Conserver l\'actuel ...”';
        sel.insertBefore(opt, sel.firstChild);
        sel.value = '';
    });
    document.getElementById('mt-depart').value = '';
    document.getElementById('modal-modifier-trajet').classList.remove('hidden');
}

// â”€â”€ Soumettre la modification â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
async function handleModifierTrajetSubmit(event) {
    event.preventDefault();
    const btn = event.target.querySelector('button[type="submit"]');
    const orig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Sauvegarde...';

    // Ne transmettre que les champs remplis
    const payload = {};
    const chauffeur = document.getElementById('mt-chauffeur').value;
    const vehicule  = document.getElementById('mt-vehicule').value;
    const ligne     = document.getElementById('mt-ligne').value;
    const depart    = document.getElementById('mt-depart').value;
    if (chauffeur) payload.chauffeur_permis          = chauffeur;
    if (vehicule)  payload.vehicule_immatriculation  = vehicule;
    if (ligne)     payload.ligne_code                = ligne;
    if (depart)    payload.date_heure_depart          = depart.replace('T', ' ');

    if (!Object.keys(payload).length) {
        btn.disabled = false; btn.innerHTML = orig;
        showToast('Aucune modification saisie.', 'info'); return;
    }

    try {
        const res  = await fetch(`${API_BASE}/api/crud/trajets/${_currentTrajetId}/modifier`, {
            method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
        });
        const data = await res.json();
        btn.disabled = false; btn.innerHTML = orig;
        if (res.ok && data.success) {
            closeModal('modal-modifier-trajet');
            showToast(`âœï¸ Trajet #${_currentTrajetId} modifié avec succès !`, 'success');
            loadAllViewData();
        } else {
            showToast('Erreur : ' + (data.detail || data.error), 'error');
        }
    } catch(e) { btn.disabled = false; btn.innerHTML = orig; showToast('Serveur injoignable.', 'error'); }
}

// âš ï¸ INCIDENTS
let _currentIncidentId = null;

function populateIncidentsTable(incidents) {
    const tbody = document.querySelector('#incidentsTable tbody');
    tbody.innerHTML = '';
    incidents.forEach((i, idx) => {
        const tr = document.createElement('tr');
        tr.className = 'fade-in-row';
        tr.style.animationDelay = `${idx * 0.05}s`;
        const gravColors = { faible:'status-En_route', moyen:'status-Terminal', grave:'status-En_panne' };
        const gravClass = gravColors[i.gravite] || 'status-Terminal';
        const resolved = i.resolu;
        const date = i.date_incident ? new Date(i.date_incident).toLocaleDateString('fr-FR') : '-';
        tr.innerHTML = `
            <td>#${i.trajet_id} <small style="color:var(--text-muted)">(${i.ligne_code})</small></td>
            <td><i class="fa-solid fa-${i.type==='panne'?'gear':i.type==='accident'?'car-burst':'clock'}"></i> ${i.type}</td>
            <td style="font-size:12px; max-width:150px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${i.description}</td>
            <td><span class="badge-status ${gravClass}">${i.gravite}</span></td>
            <td style="font-size:12px">${date}</td>
            <td>${resolved ? '<span style="color:var(--success)"><i class="fa-solid fa-check-circle"></i> Résolu</span>' : '<span style="color:var(--warning)"><i class="fa-solid fa-clock"></i> En cours</span>'}</td>
            <td style="display:flex; gap:5px;">
                ${!resolved ? `
                    <button class="action-btn-delete" style="border-color:var(--success);color:var(--success)" onclick="openResoudreIncidentModal(${i.id_incident})" title="Résoudre"><i class="fa-solid fa-check"></i></button>
                    <button class="action-btn-delete" onclick="deleteEntity(${i.id_incident}, 'incidents')" title="Supprimer"><i class="fa-solid fa-trash"></i></button>
                ` : `
                    <span class="ctx-locked" title="Incident résolu ...” archive inaltérable"><i class="fa-solid fa-lock"></i></span>
                `}
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function toggleIncidentWarning(gravite) {
    const w = document.getElementById('incident-warning');
    if (gravite === 'grave') {
        w.style.display = 'flex';
    } else {
        w.style.display = 'none';
        document.getElementById('i-type').addEventListener('change', (e) => {
            if(e.target.value === 'panne' || e.target.value === 'accident'){
                w.style.display = 'flex';
            } else if (document.getElementById('i-gravite').value !== 'grave') {
                w.style.display = 'none';
            }
        });
    }
}

document.getElementById('i-type')?.addEventListener('change', (e) => {
    const w = document.getElementById('incident-warning');
    if(e.target.value === 'panne' || e.target.value === 'accident' || document.getElementById('i-gravite').value === 'grave'){
        w.style.display = 'flex';
    } else {
        w.style.display = 'none';
    }
});

function openResoudreIncidentModal(id) {
    _currentIncidentId = id;
    document.getElementById('ir-cout').value = '0';
    document.getElementById('modal-resoudre-incident').classList.remove('hidden');
}

async function handleResoudreIncidentSubmit(event) {
    event.preventDefault();
    const btn = event.target.querySelector('button[type="submit"]');
    const orig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Traitement...';
    
    const cout = parseFloat(document.getElementById('ir-cout').value) || 0;
    try {
        const res = await fetch(`${API_BASE}/api/crud/incidents/${_currentIncidentId}/resoudre`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ cout_reparation: cout })
        });
        const data = await res.json();
        btn.disabled = false; btn.innerHTML = orig;
        if (res.ok && data.success) {
            closeModal('modal-resoudre-incident');
            showToast('âœ… Incident clôturé et coût enregistré !', 'success');
            loadAllViewData();
        } else {
            showToast('Erreur : ' + (data.detail || data.error), 'error');
        }
    } catch(e) { btn.disabled = false; btn.innerHTML = orig; showToast('Serveur injoignable.', 'error'); }
}

// ðŸ”§ MAINTENANCES
let _currentMaintenanceId = null;

function populateMaintenancesTable(maintenances) {
    const tbody = document.querySelector('#maintenancesTable tbody');
    tbody.innerHTML = '';
    maintenances.forEach((m, idx) => {
        const tr = document.createElement('tr');
        tr.className = 'fade-in-row';
        tr.style.animationDelay = `${idx * 0.05}s`;
        const statClass = m.statut === 'terminee' ? 'status-En_route' : 'status-En_panne';
        tr.innerHTML = `
            <td><strong>${m.vehicule_immatriculation}</strong><br><small style="color:var(--text-muted)">${m.marque} ${m.modele}</small></td>
            <td>${m.type_intervention}</td>
            <td>${m.technicien || '-'}</td>
            <td style="font-size:12px">${m.date_debut}</td>
            <td>${m.cout ? m.cout.toLocaleString() + ' FCFA' : '-'}</td>
            <td><span class="badge-status ${statClass}">${m.statut}</span></td>
            <td style="display:flex; gap:5px;">
                ${m.statut === 'en_cours' ? `
                    <button class="action-btn-delete" style="border-color:var(--success);color:var(--success)" onclick="openClotureMaintenanceModal(${m.id_maintenance})" title="Clôturer"><i class="fa-solid fa-check"></i></button>
                    <button class="action-btn-delete" onclick="deleteEntity(${m.id_maintenance}, 'maintenances')" title="Supprimer"><i class="fa-solid fa-trash"></i></button>
                ` : `
                    <span class="ctx-locked" title="Maintenance terminée ...” archive inaltérable"><i class="fa-solid fa-lock"></i></span>
                `}
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function openClotureMaintenanceModal(id) {
    _currentMaintenanceId = id;
    document.getElementById('cm-technicien').value = '';
    document.getElementById('cm-cout').value = '0';
    document.getElementById('modal-cloture-maintenance').classList.remove('hidden');
}

async function handleClotureMaintenanceSubmit(event) {
    event.preventDefault();
    const btn = event.target.querySelector('button[type="submit"]');
    const orig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Traitement...';
    
    const tech = document.getElementById('cm-technicien').value;
    const cout = parseFloat(document.getElementById('cm-cout').value) || 0;
    
    try {
        const res = await fetch(`${API_BASE}/api/crud/maintenances/${_currentMaintenanceId}/terminer`, {
            method: 'PATCH',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ technicien: tech, cout: cout })
        });
        const data = await res.json();
        btn.disabled = false; btn.innerHTML = orig;
        if (res.ok && data.success) {
            closeModal('modal-cloture-maintenance');
            showToast('âœ… Maintencance terminée. Véhicule remis en service !', 'success');
            loadAllViewData();
        } else {
            showToast('Erreur : ' + (data.detail || data.error), 'error');
        }
    } catch(e) { btn.disabled = false; btn.innerHTML = orig; showToast('Serveur injoignable.', 'error'); }
}

let _currentChauffeurNom    = '';    // Nom complet pour les confirmations

async function openModifierChauffeurModal(permis, telephone, email, vehicule, dispBool, nomComplet = '') {
    _currentChauffeurPermis = permis;
    _currentChauffeurNom    = nomComplet || permis; // fallback sur le permis si pas de nom

    // Libellé informatif
    document.getElementById('mc-permis-label').textContent = `Modification du profil ...” ${_currentChauffeurNom} (Permis : ${permis})`;

    // Pré-remplir les champs
    document.getElementById('mc-telephone').value = telephone !== 'undefined' ? telephone : '';
    document.getElementById('mc-email').value     = email     !== 'undefined' ? email     : '';

    // Charger les véhicules dans le select
    const sel = document.getElementById('mc-vehicule');
    sel.innerHTML = '<option value="">...” Désaffecter / Aucun bus ...”</option>';
    try {
        const res  = await fetch(`${API_BASE}/api/data/vehicules`);
        const data = await res.json();
        if (data.success) {
            data.data.forEach(v => {
                const opt = document.createElement('option');
                opt.value = v.immatriculation;
                opt.textContent = `${v.immatriculation} ...” ${v.marque} ${v.modele} (${v.statut})`;
                if (vehicule && v.immatriculation === vehicule) opt.selected = true;
                sel.appendChild(opt);
            });
        }
    } catch(_) {}

    // Mettre à jour l'état visuel du toggle de disponibilité
    const btnConge = document.getElementById('btn-mise-en-conge');
    const btnService = document.getElementById('btn-retour-service');
    if (dispBool) {
        btnService.classList.add('active');
        btnConge.classList.remove('active');
    } else {
        btnConge.classList.add('active');
        btnService.classList.remove('active');
    }

    document.getElementById('modal-modifier-chauffeur').classList.remove('hidden');
}

async function handleModifierChauffeurSubmit(event) {
    event.preventDefault();
    const btn  = event.target.querySelector('button[type="submit"]');
    const orig = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Sauvegarde...';

    const payload = {};
    const tel     = document.getElementById('mc-telephone').value.trim();
    const email   = document.getElementById('mc-email').value.trim();
    const vehicule = document.getElementById('mc-vehicule').value;

    if (tel)     payload.telephone                = tel;
    if (email)   payload.email                    = email;
    // On envoie toujours vehicule_immatriculation ("" = désaffecter)
    payload.vehicule_immatriculation = vehicule || '';

    if (!tel && !email && vehicule === undefined) {
        btn.disabled = false; btn.innerHTML = orig;
        showToast('Aucune modification saisie.', 'info'); return;
    }

    try {
        const res  = await fetch(`${API_BASE}/api/crud/chauffeurs/${_currentChauffeurPermis}/modifier`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        btn.disabled = false; btn.innerHTML = orig;
        if (res.ok && data.success) {
            closeModal('modal-modifier-chauffeur');
            showNotification('success', 'Profil mis à jour âœ…', `Informations de ${_currentChauffeurPermis} sauvegardées.`);
            loadAllViewData();
        } else {
            showNotification('error', 'Erreur', data.detail || data.error || 'Mise à jour échouée.');
        }
    } catch(e) {
        btn.disabled = false; btn.innerHTML = orig;
        showNotification('error', 'Serveur injoignable', 'Vérifiez que FastAPI est actif.');
    }
}

// ==========================================
// ðŸ–ï¸ TOGGLE DISPONIBILITÉ CHAUFFEUR (Fix #5)
// ==========================================
async function toggleDisponibiliteChauffeur(disponible) {
    if (!_currentChauffeurPermis) return;

    const name = _currentChauffeurNom || _currentChauffeurPermis;

    if (disponible) {
        // Retour en service ...” confirmation info (verte)
        showConfirmDialog(
            'Retour en service',
            `Confirmer le retour en service de <strong>${name}</strong> ?<br>
             <span style="font-size:12px;color:#94a3b8;">Le chauffeur repassera au statut <b>Disponible</b> et pourra être assigné à un trajet.</span>`,
            () => _doToggleDisponibilite(true),
            { type: 'info', icon: 'circle-check', confirmLabel: 'Oui, en service', cancelLabel: 'Annuler' }
        );
    } else {
        // Mise en congé ...” confirmation warning (orange)
        showConfirmDialog(
            'Mise en congé',
            `Mettre <strong>${name}</strong> en congé ?<br>
             <span style="font-size:12px;color:#94a3b8;">Le chauffeur sera marqué <b>Indisponible</b>. Aucun trajet ne pourra lui être attribué pendant son absence.</span>`,
            () => _doToggleDisponibilite(false),
            { type: 'warning', icon: 'umbrella-beach', confirmLabel: 'Oui, mettre en congé', cancelLabel: 'Annuler' }
        );
    }
}

async function _doToggleDisponibilite(disponible) {
    const name = _currentChauffeurNom || _currentChauffeurPermis;
    try {
        const res  = await fetch(`${API_BASE}/api/crud/chauffeurs/${_currentChauffeurPermis}/disponibilite`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ disponible })
        });
        const data = await res.json();
        if (res.ok && data.success) {
            closeModal('modal-modifier-chauffeur');
            if (disponible) {
                showNotification('success', 'âœ… Retour en service', `${name} est de retour en service et disponible pour les trajets.`);
            } else {
                showNotification('warning', 'ðŸ–ï¸ En congé', `${name} est désormais en congé et marqué indisponible.`);
            }
            loadAllViewData();
        } else {
            showNotification('error', 'Erreur', data.detail || data.error || 'Mise à jour échouée.');
        }
    } catch(e) { showNotification('error', 'Serveur injoignable', 'Vérifiez que FastAPI est actif.'); }
}

/* ==========================================
   ðŸ—ºï¸ CARTE INTERACTIVE LIGNES (Leaflet + Nominatim + OSRM)
   ========================================== */
let transpoBotLigneMap = null;
let tblMarkerA = null;
let tblMarkerB = null;
let tblRouteLine = null;

function initLigneMap() {
    setTimeout(() => {
        if (!transpoBotLigneMap) {
            transpoBotLigneMap = L.map('l-map').setView([14.6928, -17.4467], 11); // Dakar center
            L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png', {
                attribution: 'Â© OpenStreetMap | OSRM'
            }).addTo(transpoBotLigneMap);

            transpoBotLigneMap.on('click', async function(e) {
                const lat = e.latlng.lat;
                const lng = e.latlng.lng;

                if (!tblMarkerA) {
                    tblMarkerA = L.marker([lat, lng], {icon: L.divIcon({className: 'map-pin start', html:'<div>A</div>'})}).addTo(transpoBotLigneMap);
                    document.getElementById('l-origine').value = "Calcul géocodé...";
                    let city = await reverseGeocode(lat, lng);
                    document.getElementById('l-origine').value = city;
                } 
                else if (!tblMarkerB) {
                    tblMarkerB = L.marker([lat, lng], {icon: L.divIcon({className: 'map-pin end', html:'<div>B</div>'})}).addTo(transpoBotLigneMap);
                    document.getElementById('l-destination').value = "Calcul géocodé...";
                    let city = await reverseGeocode(lat, lng);
                    document.getElementById('l-destination').value = city;
                    fetchOSRMRoute(tblMarkerA.getLatLng(), tblMarkerB.getLatLng());
                } else {
                    resetLigneMapMarkers();
                    tblMarkerA = L.marker([lat, lng], {icon: L.divIcon({className: 'map-pin start', html:'<div>A</div>'})}).addTo(transpoBotLigneMap);
                    document.getElementById('l-origine').value = "Calcul géocodé...";
                    document.getElementById('l-destination').value = "";
                    document.getElementById('l-distance').value = "";
                    document.getElementById('l-duree').value = "";
                    let city = await reverseGeocode(lat, lng);
                    document.getElementById('l-origine').value = city;
                }
            });
        }
        transpoBotLigneMap.invalidateSize();
    }, 200);
}

function resetLigneMapMarkers() {
    if (tblMarkerA) { transpoBotLigneMap.removeLayer(tblMarkerA); tblMarkerA = null; }
    if (tblMarkerB) { transpoBotLigneMap.removeLayer(tblMarkerB); tblMarkerB = null; }
    if (tblRouteLine) { transpoBotLigneMap.removeLayer(tblRouteLine); tblRouteLine = null; }
}

function resetLigneMapState() {
    resetLigneMapMarkers();
    const o = document.getElementById('l-origine'); if(o) o.value = "";
    const d = document.getElementById('l-destination'); if(d) d.value = "";
    const km = document.getElementById('l-distance'); if(km) km.value = "";
    const dur = document.getElementById('l-duree'); if(dur) dur.value = "";
}

async function reverseGeocode(lat, lng) {
    try {
        const res = await fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=10&addressdetails=1`);
        const data = await res.json();
        if(data && data.address) {
            return data.address.city || data.address.town || data.address.county || data.address.state || "Secteur Inconnu";
        }
        return "Zone Inconnue";
    } catch(e) { return "Erreur Réseau Géocodage"; }
}

async function fetchOSRMRoute(pointA, pointB) {
    document.getElementById('l-distance').value = "...";
    document.getElementById('l-duree').value = "...";
    try {
        const res = await fetch(`https://router.project-osrm.org/route/v1/driving/${pointA.lng},${pointA.lat};${pointB.lng},${pointB.lat}?overview=full&geometries=geojson`);
        const data = await res.json();
        if(data.code !== 'Ok' || !data.routes || !data.routes.length) {
            showNotification('warning', 'Routage Impossible', "Aucune route carrossable trouvée entre ces points.");
            document.getElementById('l-distance').value = ""; document.getElementById('l-duree').value = "";
            return;
        }
        const route = data.routes[0];
        if(tblRouteLine) transpoBotLigneMap.removeLayer(tblRouteLine);
        tblRouteLine = L.geoJSON(route.geometry, { style: {color: '#8b5cf6', weight: 4, opacity: 0.8} }).addTo(transpoBotLigneMap);
        transpoBotLigneMap.fitBounds(tblRouteLine.getBounds(), {padding: [30,30]});

        const distKm = (route.distance / 1000).toFixed(1);
        const dureeMin = Math.round(route.duration / 60);
        document.getElementById('l-distance').value = distKm;
        document.getElementById('l-duree').value = dureeMin;
    } catch(e) {
        showNotification('error', 'Erreur Serveur GPS', "OSRM injoignable.");
        document.getElementById('l-distance').value = ""; document.getElementById('l-duree').value = "";
    }
}


