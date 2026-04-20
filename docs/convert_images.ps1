# Script to convert images to base64 and output a JSON file
$images = @('chat_vehicules.png','chat_chauffeurs.png','chat_rejet.png','superadmin_logs.png','crud_succes.png','dashboard_kpi.png','login_refuse.png','soc_logs.png','render_env.png','ucad.jpg')
$result = @{}
foreach ($img in $images) {
    $path = "c:\Users\kalog\Documents\transpobot\docs\images\$img"
    if (Test-Path $path) {
        $bytes = [System.IO.File]::ReadAllBytes($path)
        $b64 = [Convert]::ToBase64String($bytes)
        $ext = [System.IO.Path]::GetExtension($img).TrimStart('.')
        if ($ext -eq 'jpg') { $mime = 'image/jpeg' } else { $mime = 'image/png' }
        $result[$img] = "data:$mime;base64,$b64"
    }
}
$jsonOut = $result | ConvertTo-Json -Depth 2
[System.IO.File]::WriteAllText("c:\Users\kalog\Documents\transpobot\docs\images_b64.json", $jsonOut, [System.Text.Encoding]::UTF8)
Write-Host "Done - images_b64.json created"
