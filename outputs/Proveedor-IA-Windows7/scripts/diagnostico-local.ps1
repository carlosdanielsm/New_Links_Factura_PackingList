$ErrorActionPreference = "Stop"

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

function Test-PortAvailable {
    param([int]$Port)

    $listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    return -not ($listeners | Where-Object { $_.Port -eq $Port })
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

Write-Host ""
Write-Host "Diagnostico local de Proveedor IA" -ForegroundColor Cyan
Write-Host "Carpeta actual: $(Get-Location)"

if (-not (Test-Path -LiteralPath "package.json")) {
    Write-Host ""
    Write-Host "No se encontro package.json en esta carpeta." -ForegroundColor Red
    Write-Host "Abre la terminal de VSCode dentro de la carpeta del proyecto y vuelve a ejecutar:"
    Write-Host "npm run diagnostico" -ForegroundColor Yellow
    exit 1
}

if (-not (Get-Command node.exe -ErrorAction SilentlyContinue)) {
    Write-Host "Node.js: NO encontrado" -ForegroundColor Red
    Write-Host "Instala Node.js 20 o superior desde https://nodejs.org"
    exit 1
}

$nodeVersion = (& node.exe --version).Trim()
Write-Host "Node.js: $nodeVersion" -ForegroundColor Green

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    Write-Host "npm: NO encontrado" -ForegroundColor Red
    exit 1
}

$npmVersion = (& npm.cmd --version).Trim()
Write-Host "npm: $npmVersion" -ForegroundColor Green

$projectEnvPath = Join-Path (Get-Location) ".env.local"
$projectDotEnvPath = Join-Path (Get-Location) ".env"
$userEnvPath = Join-Path (Join-Path $env:LOCALAPPDATA "ProveedorIA") ".env.local"
$projectEnvKey = Get-EnvValue $projectEnvPath "OPENAI_API_KEY"
$projectDotEnvKey = Get-EnvValue $projectDotEnvPath "OPENAI_API_KEY"
$userEnvKey = Get-EnvValue $userEnvPath "OPENAI_API_KEY"
$processEnvKey = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "Process")
$userWindowsEnvKey = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "User")
$machineWindowsEnvKey = [Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "Machine")

if (Test-EnvFileHasKey $projectEnvPath) {
    Write-Host ".env.local del proyecto: API key encontrada - $(Get-MaskedKey $projectEnvKey)" -ForegroundColor Green
}
else {
    Write-Host ".env.local del proyecto: no encontrado o sin API key valida" -ForegroundColor Yellow
}

if (Test-EnvFileHasKey $projectDotEnvPath) {
    Write-Host ".env del proyecto: API key encontrada - $(Get-MaskedKey $projectDotEnvKey)" -ForegroundColor Green
}
else {
    Write-Host ".env del proyecto: no encontrado o sin API key valida" -ForegroundColor Yellow
}

if (Test-EnvFileHasKey $userEnvPath) {
    Write-Host "Guardado local de usuario: API key encontrada - $(Get-MaskedKey $userEnvKey)" -ForegroundColor Green
}
else {
    Write-Host "Guardado local de usuario: no encontrado" -ForegroundColor Yellow
}

if (-not [string]::IsNullOrWhiteSpace($processEnvKey)) {
    Write-Host "Variable OPENAI_API_KEY de esta consola: $(Get-MaskedKey $processEnvKey)" -ForegroundColor Yellow
}

if (-not [string]::IsNullOrWhiteSpace($userWindowsEnvKey)) {
    Write-Host "Variable OPENAI_API_KEY de Windows/Usuario: $(Get-MaskedKey $userWindowsEnvKey)" -ForegroundColor Yellow
}

if (-not [string]::IsNullOrWhiteSpace($machineWindowsEnvKey)) {
    Write-Host "Variable OPENAI_API_KEY de Windows/Sistema: $(Get-MaskedKey $machineWindowsEnvKey)" -ForegroundColor Yellow
}

$configuredKeys = @(
    $projectEnvKey,
    $projectDotEnvKey,
    $userEnvKey,
    $processEnvKey,
    $userWindowsEnvKey,
    $machineWindowsEnvKey
) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique
if ($configuredKeys.Count -gt 1) {
    Write-Host "Aviso: hay API keys distintas entre archivos, guardado local y/o variables de Windows." -ForegroundColor Yellow
    Write-Host "Para dejar una sola clave en todos lados ejecuta: npm run key" -ForegroundColor Yellow
}

$configuredModel = Get-EnvValue $projectEnvPath "OPENAI_MODEL"
if (-not $configuredModel) {
    $configuredModel = Get-EnvValue $projectDotEnvPath "OPENAI_MODEL"
}
if (-not $configuredModel) {
    $configuredModel = Get-EnvValue $userEnvPath "OPENAI_MODEL"
}

if ($configuredModel) {
    if ($configuredModel -eq "gpt-5.4-mini") {
        Write-Host "OPENAI_MODEL: $configuredModel (valor viejo; la app usara gpt-4.1-mini como respaldo)" -ForegroundColor Yellow
    }
    else {
        Write-Host "OPENAI_MODEL: $configuredModel" -ForegroundColor Green
    }
}
else {
    Write-Host "OPENAI_MODEL: no configurado; se usara gpt-4.1-mini" -ForegroundColor Yellow
}

if (Test-Path -LiteralPath "node_modules") {
    Write-Host "node_modules: encontrado" -ForegroundColor Green
}
else {
    Write-Host "node_modules: NO encontrado. Ejecuta npm install" -ForegroundColor Yellow
}

$busyPorts = 3000..3010 | Where-Object { -not (Test-PortAvailable $_) }
if ($busyPorts.Count -gt 0) {
    Write-Host "Puertos ocupados entre 3000 y 3010: $($busyPorts -join ', ')" -ForegroundColor Yellow
}
else {
    Write-Host "Puertos 3000-3010: libres" -ForegroundColor Green
}

Write-Host ""
Write-Host "Para correrlo desde VSCode usa:" -ForegroundColor Cyan
Write-Host "npm run dev" -ForegroundColor Yellow
Write-Host ""
Write-Host "No uses npm start para desarrollo, porque requiere haber ejecutado npm run build antes."
