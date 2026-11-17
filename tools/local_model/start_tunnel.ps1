# Keeps the deployed site's link to the local model alive: the key-checking proxy
# (tunnel_proxy.py on 127.0.0.1:8790) and the ngrok tunnel in front of it.
#
#   powershell -ExecutionPolicy Bypass -File tools\local_model\start_tunnel.ps1             run (checks every minute)
#   powershell -ExecutionPolicy Bypass -File tools\local_model\start_tunnel.ps1 -Install    start with Windows (Startup folder)
#   powershell -ExecutionPolicy Bypass -File tools\local_model\start_tunnel.ps1 -Uninstall  stop starting with Windows
#
# Ollama starts with Windows on its own. The tunnel address comes from LASERMCP_TUNNEL_URL
# in the project's .env (the ngrok static domain), so it never changes between restarts.
# Logs: output\tunnel_proxy.log, output\ngrok.log, output\start_tunnel.log.

param([switch]$Install, [switch]$Uninstall)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Out = Join-Path $Root "output"
$Shortcut = Join-Path ([Environment]::GetFolderPath("Startup")) "LaserMCP tunnel.lnk"

if ($Install) {
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($Shortcut)
    $link.TargetPath = "powershell.exe"
    $link.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    $link.WorkingDirectory = $Root
    $link.WindowStyle = 7
    $link.Save()
    Write-Output "Starts with Windows: $Shortcut"
    return
}
if ($Uninstall) {
    if (Test-Path $Shortcut) { Remove-Item $Shortcut }
    Write-Output "No longer starts with Windows."
    return
}

New-Item -ItemType Directory -Force $Out | Out-Null
$Log = Join-Path $Out "start_tunnel.log"
function Note($text) { Add-Content -Path $Log -Value ("{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $text) -Encoding utf8 }

function EnvValue($name) {
    $file = Join-Path $Root ".env"
    if (-not (Test-Path $file)) { return "" }
    foreach ($line in Get-Content $file) {
        $parts = $line -split "=", 2
        if ($parts.Count -eq 2 -and $parts[0].Trim() -eq $name) { return $parts[1].Trim().Trim('"').Trim("'") }
    }
    return ""
}

$Url = EnvValue "LASERMCP_TUNNEL_URL"
if (-not $Url) { Note "LASERMCP_TUNNEL_URL is missing from .env; stopping."; exit 1 }

$Python = Join-Path $Root ".venv\Scripts\pythonw.exe"
$Ngrok = (Get-Command ngrok -ErrorAction SilentlyContinue).Source
if (-not $Ngrok) {
    $Ngrok = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Ngrok.Ngrok*\ngrok.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $Ngrok) { Note "ngrok.exe not found; stopping."; exit 1 }

function ProxyUp {
    try { (Test-NetConnection 127.0.0.1 -Port 8790 -InformationLevel Quiet -WarningAction SilentlyContinue) } catch { $false }
}
function TunnelUp {
    try { (Invoke-RestMethod http://127.0.0.1:4040/api/tunnels -TimeoutSec 5).tunnels.Count -gt 0 } catch { $false }
}

Note "watching proxy and tunnel ($Url)"
while ($true) {
    if (-not (ProxyUp)) {
        Note "starting proxy"
        Start-Process -FilePath $Python -ArgumentList "tools\local_model\tunnel_proxy.py" -WorkingDirectory $Root `
            -WindowStyle Hidden -RedirectStandardError (Join-Path $Out "tunnel_proxy.log")
    }
    if (-not (TunnelUp)) {
        Get-Process ngrok -ErrorAction SilentlyContinue | Stop-Process -Force
        Note "starting ngrok"
        Start-Process -FilePath $Ngrok -ArgumentList "http", "8790", "--url=$Url", "--log=$(Join-Path $Out 'ngrok.log')", "--log-format=logfmt" `
            -WindowStyle Hidden
    }
    Start-Sleep -Seconds 60
}
