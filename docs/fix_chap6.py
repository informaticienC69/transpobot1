"""
Fix Chapter VI split - finds the exact text pattern and splits the div
"""
import os

HTML_PATH = r"c:\Users\kalog\Documents\transpobot\docs\rapport_transpobot.html"

with open(HTML_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# Find the exact VI.2 heading to split Chapter VI there
marker_vi2 = 'VI.2 Initialisation de la Base de Donn'
idx = html.find(marker_vi2)
if idx != -1:
    # Find the <h2 tag start before this
    h2_start = html.rfind('<h2', 0, idx)
    # The text right before the h2 should be a blank line or </ul>
    # We want to close the div before this h2 and open a new page-break div
    # Find what's immediately before the <h2
    pre_h2 = html[max(0, h2_start-5):h2_start]
    print(f"Text before <h2: [{pre_h2}]")
    print(f"Found VI.2 at index {idx}, h2 starts at {h2_start}")
    print(f"Context: {html[h2_start:h2_start+100]}")
    
    # Insert </div>\n\n<div class="page page-break"> just before the <h2
    html = html[:h2_start] + '</div>\n\n<div class="page page-break">\n  ' + html[h2_start:]
    print("OK: Split Chapter VI before VI.2")
else:
    print("WARN: Could not find VI.2 marker")

with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print(f"OK HTML saved: {HTML_PATH}")
print(f"   File size: {os.path.getsize(HTML_PATH) / 1024 / 1024:.2f} MB")
