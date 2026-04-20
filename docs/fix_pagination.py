"""
Script pour:
1. Supprimer page-break-inside: avoid des .page (laisse Chrome découper naturellement)
2. Limiter la taille des images en impression
3. Diviser le Chapitre III (trop long) en plusieurs blocs de page
4. Diviser le Chapitre VI si nécessaire
"""
import re
import os

HTML_PATH = r"c:\Users\kalog\Documents\transpobot\docs\rapport_transpobot.html"

with open(HTML_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# ============================================================
# 1. CORRIGER LE CSS PRINT
# ============================================================
# Remplacer page-break-inside: avoid; par rien (laisser Chrome gérer les sauts)
# et ajouter max-height sur les images en print
old_page_print = """    .page {\n      margin: 0 !important;\n      padding: 20mm 20mm 18mm 25mm !important;\n      box-shadow: none !important;\n      width: 100% !important;\n      min-height: auto !important;\n      page-break-inside: avoid;\n    }"""

new_page_print = """    .page {\n      margin: 0 !important;\n      padding: 20mm 20mm 18mm 25mm !important;\n      box-shadow: none !important;\n      width: 100% !important;\n      min-height: auto !important;\n    }"""

if old_page_print in html:
    html = html.replace(old_page_print, new_page_print)
    print("OK CSS: page-break-inside: avoid removed from .page")
else:
    print("WARN: Could not find the exact CSS block for .page print rule")

# Ajouter des règles pour les images et les éléments non-rupturables
old_footer_print = """    /* Page footer */\n    .page-footer { position: relative !important; bottom: auto !important; left: auto !important; right: auto !important; margin-top: 15px !important; }\n  }"""

new_footer_print = """    /* Page footer */\n    .page-footer { position: relative !important; bottom: auto !important; left: auto !important; right: auto !important; margin-top: 15px !important; }\n    /* Limiter la taille des images */\n    img { max-height: 180px !important; object-fit: contain !important; }\n    /* Éviter les coupures dans les petits blocs */\n    .fonc-box, .callout, h1, h2, h3 { break-inside: avoid !important; }\n  }"""

if old_footer_print in html:
    html = html.replace(old_footer_print, new_footer_print)
    print("OK CSS: Added img max-height and break-inside avoidance for small elements")
else:
    print("WARN: Could not find the page-footer print rule to insert extra rules")

# ============================================================
# 2. DIVISER LE CHAPITRE III (trop long)
# ============================================================
# --- SPLIT 1: Séparer l'intro/tableau récapitulatif de III.1 ---
# On cherche la fin du tableau récapitulatif et le début de III.1
split1_old = """    </tbody>
  </table>

  <!-- III.1 REQUIS -->
  <h2 class=\"subsection-title\" id=\"chap3-1\">III.1 Fonctionnalités requises</h2>"""

split1_new = """    </tbody>
  </table>
</div>

<div class="page page-break">
  <!-- III.1 REQUIS -->
  <h2 class=\"subsection-title\" id=\"chap3-1\">III.1 Fonctionnalités requises</h2>"""

if split1_old in html:
    html = html.replace(split1_old, split1_new)
    print("OK HTML: Split Chapter III - comparison table separated from III.1")
else:
    print("WARN: Could not find Chapter III split #1 marker")

# --- SPLIT 2: Séparer III.2 IA de III.3 Supplémentaires ---
split2_old = """  <!-- III.3 SUPPLÉMENTAIRES -->
  <h2 class=\"subsection-title\" id=\"chap3-3\">III.3 Fonctionnalités supplémentaires développées</h2>"""

split2_new = """</div>

<div class="page page-break">
  <!-- III.3 SUPPLÉMENTAIRES -->
  <h2 class=\"subsection-title\" id=\"chap3-3\">III.3 Fonctionnalités supplémentaires développées</h2>"""

if split2_old in html:
    html = html.replace(split2_old, split2_new)
    print("OK HTML: Split Chapter III - III.2 IA separated from III.3 Supplementaires")
else:
    print("WARN: Could not find Chapter III split #2 marker (III.3)")

# ============================================================
# 3. DIVISER LE CHAPITRE VI (Déploiement) si trop long
# ============================================================
split3_old = """  <h2 class=\"subsection-title\">VI.2 Initialisation de la Base de Données &amp; Sécurisation absolue</h2>"""

split3_new = """</div>

<div class="page page-break">
  <h2 class=\"subsection-title\">VI.2 Initialisation de la Base de Données &amp; Sécurisation absolue</h2>"""

if split3_old in html:
    html = html.replace(split3_old, split3_new)
    print("OK HTML: Split Chapter VI - Deployment diagram separated from DB init section")
else:
    print("WARN: Could not find Chapter VI split marker")

# ============================================================
# 4. MISE À JOUR DU JS DE NUMÉROTATION (les index ont changé)
# ============================================================
# Le script du footer doit ignorer la Page de Garde (index 0)
# et mettre "Table des Matières" sur index 1
# Les nouvelles sections ajoutées seront automatiquement numérotées
# Le JS actuel est correct dans son concept, on vérifie juste qu'il est bien là
if "// index 1 = Table des Matières (pas de numérotation chiffrée)" in html:
    print("OK JS: Page numbering script is already in place")
else:
    print("WARN: Could not verify page numbering script")

# ============================================================
# SAUVEGARDER
# ============================================================
with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print(f"OK HTML saved: {HTML_PATH}")
print(f"   File size: {os.path.getsize(HTML_PATH) / 1024 / 1024:.2f} MB")
