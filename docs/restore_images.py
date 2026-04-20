"""
Diagnostic and fix: remove base64 images and restore relative paths.
The file at 2.63MB with embedded base64 images is too large for Chrome to print to PDF reliably.
Solution: restore relative image paths - Chrome loads local files just fine when printing.
"""
import re
import os

HTML_PATH = r"c:\Users\kalog\Documents\transpobot\docs\rapport_transpobot.html"
IMAGES_DIR = r"c:\Users\kalog\Documents\transpobot\docs\images"

with open(HTML_PATH, "r", encoding="utf-8") as f:
    html = f.read()

print(f"File size before: {len(html)/1024/1024:.2f} MB")

# Count base64 images
b64_count = len(re.findall(r'src="data:image', html))
print(f"Base64 images found: {b64_count}")

# Map of base64 mime types to extensions (rough detection by looking at the first chars after base64,)
# We need to restore the original filenames
# The images were: chat_vehicules.png, chat_chauffeurs.png, chat_rejet.png,
#                  superadmin_logs.png, crud_succes.png, dashboard_kpi.png,
#                  login_refuse.png, soc_logs.png, render_env.png, ucad.jpg

# Re-encode each image to identify which one it is
import base64

IMAGE_MAP = {}
images_folder = IMAGES_DIR
for fname in os.listdir(images_folder):
    fpath = os.path.join(images_folder, fname)
    with open(fpath, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    ext = os.path.splitext(fname)[1].lower()
    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    data_uri = f"data:{mime};base64,{b64}"
    IMAGE_MAP[data_uri] = f"images/{fname}"

print(f"Images mapped: {len(IMAGE_MAP)}")

# Replace all base64 data URIs with relative paths
replacements = 0
for data_uri, rel_path in IMAGE_MAP.items():
    if data_uri in html:
        html = html.replace(data_uri, rel_path)
        replacements += 1
        print(f"  Restored: {rel_path}")

print(f"Total replacements: {replacements}")
print(f"File size after: {len(html)/1024/1024:.2f} MB")

with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print(f"OK: HTML saved to {HTML_PATH}")
