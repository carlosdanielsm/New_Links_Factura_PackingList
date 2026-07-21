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

    $line = Get-Content -LiteralPath $Path |
        Where-Object { $_.Trim() -match "^OPENAI_API_KEY=sk-\S+$" } |
        Select-Object -First 1
    return -not [string]::IsNullOrWhiteSpace($line)
}

function Get-EnvValue {
    param(
        [string]$Path,
        [string]$Name
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    $match = Select-String -LiteralPath $Path -Pattern "^$Name=(.+)$" | Select-Object -First 1
    if (-not $match) {
        return $null
    }

    return $match.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
}

function Get-MaskedKey {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return "no configurada"
    }

    $key = $Value.Trim().Trim('"').Trim("'")
    if ($key.Length -le 12) {
        return "configurada, pero demasiado corta"
    }

    return "$($key.Substring(0, 7))...$($key.Substring($key.Length - 4)) ($($key.Length) caracteres)"
}

function Import-RuntimeEnv {
    $projectEnvPath = Join-Path $ProjectRoot ".env.local"
    $projectDotEnvPath = Join-Path $ProjectRoot ".env"
    $sourcePath = $null

    if (Test-EnvFileHasKey $projectEnvPath) {
        $sourcePath = $projectEnvPath
    }
    elseif (Test-EnvFileHasKey $projectDotEnvPath) {
        $sourcePath = $projectDotEnvPath
    }

    if (-not $sourcePath) {
        return $false
    }

    $apiKey = Get-EnvValue $sourcePath "OPENAI_API_KEY"
    $model = Get-EnvValue $sourcePath "OPENAI_MODEL"

    if (-not [string]::IsNullOrWhiteSpace($apiKey)) {
        $env:OPENAI_API_KEY = $apiKey
        Write-Host "OPENAI_API_KEY cargada desde $(Split-Path -Leaf $sourcePath): $(Get-MaskedKey $apiKey)" -ForegroundColor Green
    }

    if ([string]::IsNullOrWhiteSpace($model) -or $model -eq "gpt-5.4-mini") {
        $model = "gpt-4.1-mini"
    }
    $env:OPENAI_MODEL = $model
    Write-Host "OPENAI_MODEL activo: $env:OPENAI_MODEL" -ForegroundColor Green

    return $true
}

function Sync-ProjectEnvFromUserStore {
    $userConfigDir = Join-Path $env:LOCALAPPDATA "ProveedorIA"
    $userEnvPath = Join-Path $userConfigDir ".env.local"
    $projectEnvPath = Join-Path $ProjectRoot ".env.local"
    $projectDotEnvPath = Join-Path $ProjectRoot ".env"

    if (Test-EnvFileHasKey $projectEnvPath) {
        if (-not (Test-Path -LiteralPath $userConfigDir)) {
            New-Item -ItemType Directory -Path $userConfigDir | Out-Null
        }
        try {
            Copy-Item -LiteralPath $projectEnvPath -Destination $userEnvPath -Force -ErrorAction Stop
        }
        catch {
            Write-Host "Aviso: no se pudo sincronizar la API key al guardado local de usuario. Se usara .env.local del proyecto." -ForegroundColor Yellow
        }
        return $true
    }

    if (Test-EnvFileHasKey $projectDotEnvPath) {
        if (-not (Test-Path -LiteralPath $userConfigDir)) {
            New-Item -ItemType Directory -Path $userConfigDir | Out-Null
        }
        Copy-Item -LiteralPath $projectDotEnvPath -Destination $projectEnvPath -Force
        try {
            Copy-Item -LiteralPath $projectDotEnvPath -Destination $userEnvPath -Force -ErrorAction Stop
        }
        catch {
            Write-Host "Aviso: no se pudo sincronizar la API key al guardado local de usuario. Se usara .env.local del proyecto." -ForegroundColor Yellow
        }
        Write-Host "Se encontro OPENAI_API_KEY en .env y se sincronizo con .env.local." -ForegroundColor Green
        return $true
    }

    if (Test-EnvFileHasKey $userEnvPath) {
        Copy-Item -LiteralPath $userEnvPath -Destination $projectEnvPath -Force
        Write-Host "Se copio la API key guardada localmente a .env.local." -ForegroundColor Green
        return $true
    }

    return $false
}

function Save-EnvEverywhere {
    param([string]$Contents)

    $userConfigDir = Join-Path $env:LOCALAPPDATA "ProveedorIA"
    $userEnvPath = Join-Path $userConfigDir ".env.local"
    $projectEnvPath = Join-Path $ProjectRoot ".env.local"
    $projectDotEnvPath = Join-Path $ProjectRoot ".env"

    if (-not (Test-Path -LiteralPath $userConfigDir)) {
        New-Item -ItemType Directory -Path $userConfigDir | Out-Null
    }

    [IO.File]::WriteAllText($projectEnvPath, $Contents, [Text.UTF8Encoding]::new($false))
    [IO.File]::WriteAllText($projectDotEnvPath, $Contents, [Text.UTF8Encoding]::new($false))
    try {
        [IO.File]::WriteAllText($userEnvPath, $Contents, [Text.UTF8Encoding]::new($false))
    }
    catch {
        Write-Host "Aviso: no se pudo guardar la API key en el guardado local de usuario. Quedo guardada en .env y .env.local." -ForegroundColor Yellow
    }
}

function Request-OpenAIKey {
    Write-Host ""
    Write-Host "No se encontro OPENAI_API_KEY configurada." -ForegroundColor Yellow
    Write-Host "Pega tu API key de OpenAI. Se guardara en .env, .env.local y en el guardado local de usuario."
    Write-Host "No se mostrara en pantalla." -ForegroundColor DarkGray

    $secureKey = Read-Host "OPENAI_API_KEY" -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureKey)

    try {
        $apiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }

    if ([string]::IsNullOrWhiteSpace($apiKey) -or -not $apiKey.StartsWith("sk-")) {
        Stop-WithMessage "La clave no parece valida. Debe comenzar con sk-."
    }

    $envContents = "OPENAI_API_KEY=$apiKey`r`nOPENAI_MODEL=gpt-4.1-mini`r`n"
    Save-EnvEverywhere $envContents
    $apiKey = $null
    Write-Host "API key guardada correctamente." -ForegroundColor Green
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
    Request-OpenAIKey
}

if (-not (Import-RuntimeEnv)) {
    Stop-WithMessage "No se pudo cargar OPENAI_API_KEY al entorno de ejecucion. Ejecuta npm run key e intenta de nuevo."
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
