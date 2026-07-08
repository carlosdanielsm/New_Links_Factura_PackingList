$ErrorActionPreference = "Stop"

function Test-EnvFileHasKey {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }

    $content = Get-Content -Raw -LiteralPath $Path
    return $content -match "(?m)^OPENAI_API_KEY=sk-[^\s]+$"
}

function Test-PortAvailable {
    param([int]$Port)

    $listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    return -not ($listeners | Where-Object { $_.Port -eq $Port })
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
$userEnvPath = Join-Path (Join-Path $env:LOCALAPPDATA "ProveedorIA") ".env.local"

if (Test-EnvFileHasKey $projectEnvPath) {
    Write-Host ".env.local del proyecto: API key encontrada" -ForegroundColor Green
}
else {
    Write-Host ".env.local del proyecto: no encontrado o sin API key valida" -ForegroundColor Yellow
}

if (Test-EnvFileHasKey $userEnvPath) {
    Write-Host "Guardado local de usuario: API key encontrada" -ForegroundColor Green
}
else {
    Write-Host "Guardado local de usuario: no encontrado" -ForegroundColor Yellow
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
