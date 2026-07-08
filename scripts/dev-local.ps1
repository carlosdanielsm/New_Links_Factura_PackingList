$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

function Stop-WithMessage {
    param([string]$Message)
    Write-Host ""
    Write-Host $Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Presiona Enter para cerrar esta terminal."
    Read-Host | Out-Null
    exit 1
}

function Test-EnvFileHasKey {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }

    $content = Get-Content -Raw -LiteralPath $Path
    return $content -match "(?m)^OPENAI_API_KEY=sk-[^\s]+$"
}

function Sync-ProjectEnvFromUserStore {
    $userConfigDir = Join-Path $env:LOCALAPPDATA "ProveedorIA"
    $userEnvPath = Join-Path $userConfigDir ".env.local"
    $projectEnvPath = Join-Path $ProjectRoot ".env.local"

    if (Test-EnvFileHasKey $projectEnvPath) {
        if (-not (Test-Path -LiteralPath $userConfigDir)) {
            New-Item -ItemType Directory -Path $userConfigDir | Out-Null
        }
        Copy-Item -LiteralPath $projectEnvPath -Destination $userEnvPath -Force
        return $true
    }

    if (Test-EnvFileHasKey $userEnvPath) {
        Copy-Item -LiteralPath $userEnvPath -Destination $projectEnvPath -Force
        Write-Host "Se copio la API key guardada localmente a .env.local." -ForegroundColor Green
        return $true
    }

    return $false
}

function Test-PortAvailable {
    param([int]$Port)

    $listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    return -not ($listeners | Where-Object { $_.Port -eq $Port })
}

function Test-FileLocked {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }

    $stream = $null
    try {
        $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        return $false
    }
    catch {
        return $true
    }
    finally {
        if ($stream) {
            $stream.Close()
        }
    }
}

function Get-ListeningPids {
    param(
        [int]$Start = 3000,
        [int]$End = 3010
    )

    $lines = netstat -ano | Select-String "LISTENING"
    $items = @()
    foreach ($line in $lines) {
        $text = $line.ToString().Trim()
        if ($text -match ":(\d+)\s+.*\s+LISTENING\s+(\d+)$") {
            $port = [int]$Matches[1]
            $processId = [int]$Matches[2]
            if ($port -ge $Start -and $port -le $End) {
                $items += [pscustomobject]@{ Port = $port; PID = $processId }
            }
        }
    }

    return $items | Sort-Object Port, PID -Unique
}

function Get-AvailablePort {
    param(
        [int]$Start = 3000,
        [int]$End = 3010
    )

    for ($port = $Start; $port -le $End; $port++) {
        if (Test-PortAvailable $port) {
            return $port
        }
    }

    return $null
}

Write-Host ""
Write-Host "Iniciando Proveedor IA desde VSCode/consola..." -ForegroundColor Cyan
Write-Host "Carpeta del proyecto: $ProjectRoot"

if (-not (Get-Command node.exe -ErrorAction SilentlyContinue)) {
    Stop-WithMessage "Node.js no esta instalado. Instala Node.js 20 o superior desde https://nodejs.org"
}

if (-not (Test-Path -LiteralPath "node_modules")) {
    Stop-WithMessage "No se encontro node_modules. Ejecuta primero: npm install"
}

$nextPath = Join-Path $ProjectRoot "node_modules\.bin\next.cmd"
if (-not (Test-Path -LiteralPath $nextPath)) {
    Stop-WithMessage "No se encontro Next.js instalado. Ejecuta primero: npm install"
}

$hasKey = Sync-ProjectEnvFromUserStore
if (-not $hasKey) {
    Write-Host ""
    Write-Host "Aviso: no existe .env.local con OPENAI_API_KEY en esta carpeta ni en el guardado local." -ForegroundColor Yellow
    Write-Host "La pantalla abrira, pero las busquedas con IA fallaran hasta configurar OPENAI_API_KEY."
    Write-Host "Puedes configurarla ejecutando: .\INSTALAR-Y-EJECUTAR.bat"
}

$lockPath = Join-Path $ProjectRoot ".next\dev\lock"
if (Test-FileLocked $lockPath) {
    $listeners = Get-ListeningPids
    $first = $listeners | Select-Object -First 1

    Write-Host ""
    Write-Host "Ya hay un servidor de desarrollo de este proyecto ejecutandose." -ForegroundColor Yellow
    if ($first) {
        Write-Host "Puedes abrir: http://localhost:$($first.Port)" -ForegroundColor Green
        Write-Host "PID detectado: $($first.PID)"
    }
    Write-Host ""
    Write-Host "Si quieres reiniciarlo desde cero, ejecuta primero:" -ForegroundColor Cyan
    Write-Host "npm run stop" -ForegroundColor Yellow
    Write-Host "y luego:"
    Write-Host "npm run dev" -ForegroundColor Yellow
    exit 0
}

$port = Get-AvailablePort
if (-not $port) {
    Stop-WithMessage "No hay puertos libres entre 3000 y 3010. Cierra otros servidores Next.js e intenta de nuevo."
}

Write-Host ""
Write-Host "Servidor local: http://localhost:$port" -ForegroundColor Green
Write-Host "Para detenerlo, presiona Ctrl+C." -ForegroundColor Yellow
Write-Host ""

& $nextPath dev -p $port

if ($LASTEXITCODE -ne 0) {
    Stop-WithMessage "Next.js se detuvo con codigo $LASTEXITCODE. Revisa el mensaje anterior para ver la causa."
}
