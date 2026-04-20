"""
Script to:
1. Embed all images as base64 in the HTML (so they work in PDF from anywhere)
2. Fix page numbering (TDM = "Table des Matières", Intro = Page 1)
3. Fix CSS print formatting (proper @page margins, overflow, links visible)
"""
import base64
import re
import os

DOCS_DIR = r"c:\Users\kalog\Documents\transpobot\docs"
HTML_PATH = os.path.join(DOCS_DIR, "rapport_transpobot.html")
IMAGES_DIR = os.path.join(DOCS_DIR, "images")

# Read HTML
with open(HTML_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# 1. Embed images as base64
def encode_image(img_path):
    ext = os.path.splitext(img_path)[1].lower()
    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    with open(img_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"

def replace_image_src(match):
    rel_path = match.group(1)
    abs_path = os.path.join(DOCS_DIR, rel_path)
    if os.path.exists(abs_path):
        data_uri = encode_image(abs_path)
        return f'src="{data_uri}"'
    return match.group(0)

html = re.sub(r'src="(images/[^"]+)"', replace_image_src, html)
print("OK Images embedded as base64")

# 2. Fix CSS - improve print rules, add link visibility, fix page numbering
old_print_css = """  @media print {
    body { background: white; }
    .page {
      margin: 0; padding: 25mm 25mm 20mm 30mm;
      box-shadow: none; width: 100%;
    }
    .page-break { page-break-before: always; }
    .no-print { display: none; }
  }
  @page { size: A4; margin: 0; }"""

new_print_css = """  @media print {
    body { background: white; margin: 0; padding: 0; }
    .page {
      margin: 0 !important;
      padding: 20mm 20mm 18mm 25mm !important;
      box-shadow: none !important;
      width: 100% !important;
      min-height: auto !important;
      page-break-inside: avoid;
    }
    .page-break { page-break-before: always !important; }
    .no-print { display: none !important; }
    /* Make links visible and clickable in PDF */
    a { color: #1565C0 !important; text-decoration: underline !important; }
    .doc-link { 
      border: 1px solid #1565C0 !important;
      background: #fff !important;
      color: #1565C0 !important;
      padding: 4px 8px !important;
      display: inline-block !important;
    }
    /* Prevent code blocks from overflowing */
    pre { white-space: pre-wrap !important; word-break: break-word !important; overflow: hidden !important; }
    /* Prevent tables from overflowing */ 
    table { width: 100% !important; font-size: 9pt !important; }
    td, th { padding: 4px 5px !important; }
    /* Page footer */
    .page-footer { position: relative !important; bottom: auto !important; left: auto !important; right: auto !important; margin-top: 15px !important; }
  }
  @page { size: A4 portrait; margin: 15mm 15mm 15mm 20mm; }"""

html = html.replace(old_print_css, new_print_css)
print("OK CSS print rules fixed")

# 3. Fix page numbering JS - TDM gets special label, then Introduction = Page 1
old_script = """<script>
  document.addEventListener("DOMContentLoaded", () => {
    let pages = document.querySelectorAll('.page');
    let pageNum = 1;
    pages.forEach((p, index) => {
      // Ignorer la page de garde pour la numérotation
      if (index === 0) return;
      let footer = document.createElement('div');
      footer.className = 'page-footer';
      footer.innerHTML = `<span>Projet TranspoBot — ESP/DIC1</span><span>Page ${pageNum}</span>`;
      p.appendChild(footer);
      pageNum++;
    });
  });
</script>"""

new_script = """<script>
  document.addEventListener("DOMContentLoaded", () => {
    let pages = document.querySelectorAll('.page');
    let pageNum = 1;
    pages.forEach((p, index) => {
      // index 0 = Page de Garde (pas de numéro)
      if (index === 0) return;
      
      let footer = document.createElement('div');
      footer.className = 'page-footer';
      
      // index 1 = Table des Matières (pas de numérotation chiffrée)
      if (index === 1) {
        footer.innerHTML = `<span>Projet TranspoBot — ESP/DIC1</span><span>Table des Matières</span>`;
        p.appendChild(footer);
        return;
      }
      
      // index 2+ = Introduction = Page 1, puis 2, 3...
      footer.innerHTML = `<span>Projet TranspoBot — ESP/DIC1</span><span>Page ${pageNum}</span>`;
      p.appendChild(footer);
      pageNum++;
    });
  });
</script>"""

html = html.replace(old_script, new_script)
print("OK Page numbering JS fixed")

# 4. Fix the page-footer CSS to work with @page margins (not absolute positioning)
old_footer_css = """  .page-footer {
    position: absolute; bottom: 15mm; left: 30mm; right: 25mm;
    display: flex; justify-content: space-between; align-items: center;
    border-top: 1px solid #ddd; padding-top: 6px;
    font-size: 9pt; color: #999;
  }"""

new_footer_css = """  .page-footer {
    position: relative;
    margin-top: 20px;
    display: flex; justify-content: space-between; align-items: center;
    border-top: 1px solid #ddd; padding-top: 6px;
    font-size: 9pt; color: #999;
  }"""

html = html.replace(old_footer_css, new_footer_css)
print("OK Footer CSS fixed")

# Write back
with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print(f"OK HTML saved: {HTML_PATH}")
print(f"   File size: {os.path.getsize(HTML_PATH) / 1024 / 1024:.2f} MB")
