<#
VayuDrishti local hosting: everything on one address, with no console windows.

  http://localhost:3001
    /             the website (frontend/dist)
    /api/...      the FastAPI backend with the three trained models (forwarded to 127.0.0.1:8001)
    /bench        model test bench
    /evaluation   metrics dashboard

Two background processes do the work, both hidden: the FastAPI backend (uvicorn on 127.0.0.1:8001, used only
through :3001) and the site server (node tests/model-bench/server.mjs on 127.0.0.1:3001). This script only
starts, stops and reports on them. It changes nothing in the website, the test bench or the dashboard.

  powershell -ExecutionPolicy Bypass -File hosting\vayudrishti.ps1 start          start whatever is not running
  powershell -ExecutionPolicy Bypass -File hosting\vayudrishti.ps1 stop
  powershell -ExecutionPolicy Bypass -File hosting\vayudrishti.ps1 restart
  powershell -ExecutionPolicy Bypass -File hosting\vayudrishti.ps1 status
  powershell -ExecutionPolicy Bypass -File hosting\vayudrishti.ps1 autostart      start hidden at every Windows sign-in
  powershell -ExecutionPolicy Bypass -File hosting\vayudrishti.ps1 no-autostart

Logs: %LOCALAPPDATA%\VayuDrishti\logs (backend.log / backend.err.log, site.log / site.err.log, hosting.log).
After changing the frontend, rebuild with `npx vite build` in frontend/. The site server serves the new build
without a restart.
#>
param(
    [Parameter(Position = 0)]
    [ValidateSet("start", "stop", "restart", "status", "autostart", "no-autostart", "launch")]
    [string]$Action = "status",
    [string]$NodePath = ""
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
$Logs = Join-Path $env:LOCALAPPDATA "VayuDrishti\logs"
$Shortcut = Join-Path ([Environment]::GetFolderPath("Startup")) "VayuDrishti (localhost).lnk"
$Url = "http://localhost:3001"

$Services = @(
    [pscustomobject]@{
        Name = "backend"; Port = 8001; Dir = (Join-Path $Repo "backend")
        Exe = (Join-Path $Repo "backend\.venv\Scripts\python.exe")
        Args = "-m uvicorn server:app --host 127.0.0.1 --port 8001"
        Ready = "http://127.0.0.1:8001/api/health"; WaitSeconds = 180
    },
    [pscustomobject]@{
        Name = "site"; Port = 3001; Dir = $Repo
        Exe = "node"
        Args = "tests/model-bench/server.mjs"
        Ready = "http://127.0.0.1:3001/"; WaitSeconds = 30
    }
)

function Get-Listener([int]$Port) {
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
}

function Test-Url([string]$Uri) {
    try { return (Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 5).StatusCode -eq 200 } catch { return $false }
}

function Resolve-Exe([string]$Exe) {
    $cmd = Get-Command $Exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd) { throw "Cannot find '$Exe'. Install it or add it to PATH." }
    return $cmd.Source
}

function Write-HostingLog([string]$Message) {
    New-Item -ItemType Directory -Force -Path $Logs | Out-Null
    "$(Get-Date -Format s)  $Message" | Add-Content -Path (Join-Path $Logs "hosting.log")
}

# Runs detached and hidden (started by Invoke-Start): starts each server that is not already listening.
function Invoke-Launch {
    New-Item -ItemType Directory -Force -Path $Logs | Out-Null
    foreach ($s in $Services) {
        if (Get-Listener $s.Port) { continue }
        if ($s.Name -eq "backend") {
            # At Windows sign-in the MongoDB service may still be starting; the backend connects once at startup.
            $deadline = (Get-Date).AddSeconds(60)
            while (-not (Get-Listener 27017) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 2 }
            if (-not (Get-Listener 27017)) { Write-HostingLog "MongoDB is not listening on 27017; starting the backend anyway (sign-in will fail until it is up)" }
        }
        try {
            $exe = if ($s.Name -eq "site" -and $NodePath) { $NodePath } else { Resolve-Exe $s.Exe }
            Start-Process -FilePath $exe -ArgumentList $s.Args -WorkingDirectory $s.Dir -WindowStyle Hidden `
                -RedirectStandardOutput (Join-Path $Logs "$($s.Name).log") -RedirectStandardError (Join-Path $Logs "$($s.Name).err.log")
            Write-HostingLog "started $($s.Name) on port $($s.Port)"
        } catch {
            Write-HostingLog "could not start $($s.Name): $($_.Exception.Message)"
        }
    }
}

function Show-Status {
    foreach ($s in $Services) {
        $l = Get-Listener $s.Port
        $state = if ($l) { "running (PID $($l.OwningProcess))" } else { "stopped" }
        "  {0,-8} 127.0.0.1:{1}  {2}" -f $s.Name, $s.Port, $state
    }
    try {
        $h = Invoke-RestMethod -Uri "http://127.0.0.1:3001/api/health" -TimeoutSec 5
        $word = { param($ok) if ($ok) { "ready" } else { "NOT loaded" } }
        "  models   identification {0}, classification {1}, prediction {2}" -f (& $word $h.services.identification_model), (& $word $h.services.classification_model), (& $word $h.services.prediction_model)
    } catch {
        "  models   not reachable through :3001"
    }
    "  autostart at Windows sign-in: $(if (Test-Path $Shortcut) { 'on' } else { 'off' })"
    "  logs     $Logs"
    ""
    "  Open $Url   (website /, test bench /bench, metrics dashboard /evaluation)"
}

function Invoke-Start {
    $missing = @($Services | Where-Object { -not (Get-Listener $_.Port) })
    if ($missing.Count -gt 0) {
        "Starting $(($missing | ForEach-Object { $_.Name }) -join ' and ') in the background (no windows)..."
        $node = ""
        try { $node = Resolve-Exe "node" } catch { }
        # Launch through WMI so the servers are not children of this terminal (or of an editor or agent session):
        # closing the window that ran this script never stops them.
        $command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" launch"
        if ($node) { $command += " -NodePath `"$node`"" }
        $startup = ([wmiclass]"Win32_ProcessStartup").CreateInstance()
        $startup.ShowWindow = 0
        $result = ([wmiclass]"Win32_Process").Create($command, $Repo, $startup)
        if ($result.ReturnValue -ne 0) { throw "Could not start the background launcher (Win32_Process.Create returned $($result.ReturnValue))." }
    }
    foreach ($s in $Services) {
        $deadline = (Get-Date).AddSeconds($s.WaitSeconds)
        while (-not (Test-Url $s.Ready) -and (Get-Date) -lt $deadline) { Start-Sleep -Seconds 2 }
    }
    Show-Status
}

function Invoke-Stop {
    foreach ($s in $Services) {
        $l = Get-Listener $s.Port
        if (-not $l) { "  $($s.Name): not running"; continue }
        $p = Get-CimInstance Win32_Process -Filter "ProcessId=$($l.OwningProcess)"
        $parent = if ($p) { Get-CimInstance Win32_Process -Filter "ProcessId=$($p.ParentProcessId)" } else { $null }
        Stop-Process -Id $l.OwningProcess -Force -ErrorAction SilentlyContinue
        # The venv's python.exe is a small launcher that runs the real interpreter as its child; stop it too.
        if ($parent -and $parent.Name -eq "python.exe" -and $parent.ExecutablePath -like "$Repo*") {
            Stop-Process -Id $parent.ProcessId -Force -ErrorAction SilentlyContinue
        }
        "  $($s.Name): stopped"
    }
    $deadline = (Get-Date).AddSeconds(15)
    while (($Services | Where-Object { Get-Listener $_.Port }) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
}

function Set-Autostart {
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($Shortcut)
    $link.TargetPath = Join-Path $PSHOME "powershell.exe"
    $link.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" start"
    $link.WorkingDirectory = $Repo
    $link.WindowStyle = 7
    $link.Description = "Host VayuDrishti on $Url in the background"
    $link.Save()
    "  autostart on: VayuDrishti starts hidden at every Windows sign-in ($Shortcut)"
}

switch ($Action) {
    "launch"       { Invoke-Launch }
    "start"        { Invoke-Start }
    "stop"         { Invoke-Stop }
    "restart"      { Invoke-Stop; Invoke-Start }
    "status"       { Show-Status }
    "autostart"    { Set-Autostart }
    "no-autostart" {
        if (Test-Path $Shortcut) { Remove-Item $Shortcut; "  autostart off" } else { "  autostart was already off" }
    }
}
