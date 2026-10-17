# Instalador do Cordyhome para Windows.
#
# Copia o hub e a interface para %LOCALAPPDATA%\Cordyhome, instala o uv (que baixa o Python),
# libera o firewall na rede privada, configura o início automático com o Windows e abre o app.
# Rodar de novo atualiza a instalação; os dados ficam em %USERPROFILE%\.cordyhome.

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$Port = 8420
$Src = $PSScriptRoot
$Root = Join-Path $env:LOCALAPPDATA 'Cordyhome'
$App = Join-Path $Root 'app'
$Log = Join-Path $Root 'cordyhome.log'
$Launcher = Join-Path $Root 'iniciar.vbs'
$Exe = Join-Path $App 'hub\.venv\Scripts\cordyhome.exe'

function Step($text) { Write-Host "`n> $text" -ForegroundColor Cyan }
function Info($text) { Write-Host "  $text" }
function Warn($text) { Write-Host "  $text" -ForegroundColor Yellow }

function Fail($text) {
    Write-Host "`n  $text" -ForegroundColor Red
    Write-Host '  A instalacao nao terminou. Mande um print desta janela para quem esta te ajudando.'
    exit 1
}

function Stop-Cordyhome {
    $listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $listening) {
        $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -in @('python', 'pythonw', 'cordyhome')) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and $_.Path.StartsWith($App, [StringComparison]::OrdinalIgnoreCase) } |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

function Test-Hub {
    try {
        $null = Invoke-WebRequest "http://127.0.0.1:$Port/api/auth/status" -UseBasicParsing -TimeoutSec 2
        return $true
    } catch {
        return $false
    }
}

function New-Shortcut($path, $target, $arguments, $icon) {
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = $target
    $link.Arguments = $arguments
    $link.WorkingDirectory = $Root
    if ($icon) { $link.IconLocation = $icon }
    $link.Save()
}

function New-UrlShortcut($path, $icon) {
    $content = "[InternetShortcut]`r`nURL=http://localhost:$Port/`r`nIconFile=$icon`r`nIconIndex=0`r`n"
    Set-Content -Path $path -Value $content -Encoding Unicode
}

$version = ''
$versionFile = Join-Path $Src 'app\VERSION'
if (Test-Path $versionFile) { $version = (Get-Content $versionFile -Raw).Trim() }

Write-Host ''
Write-Host '  Cordyhome' -ForegroundColor Green -NoNewline
Write-Host "  instalador para Windows $version"

if (-not (Test-Path (Join-Path $Src 'app\hub\pyproject.toml'))) {
    Fail 'Arquivos do Cordyhome nao encontrados. Extraia o ZIP inteiro antes de instalar.'
}

# 1. Arquivos ---------------------------------------------------------------------------------
Step 'Copiando os arquivos'
Get-ChildItem -Path $Src -Recurse -File | Unblock-File -ErrorAction SilentlyContinue
$wasRunning = Test-Hub
Stop-Cordyhome
New-Item -ItemType Directory -Force -Path $Root | Out-Null
# /MIR espelha a pasta nova; .venv fica para não reinstalar as dependências a cada atualização.
& robocopy (Join-Path $Src 'app') $App /MIR /XD .venv __pycache__ /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { Fail "Falha ao copiar os arquivos para $App (robocopy $LASTEXITCODE)." }
Copy-Item (Join-Path $Src 'desinstalar.ps1') $Root -Force
Copy-Item (Join-Path $Src 'cordyhome.ico') $Root -Force
$Icon = Join-Path $Root 'cordyhome.ico'
Info "Instalado em $Root"

# 2. uv e Python -------------------------------------------------------------------------------
Step 'Preparando o Python'
$uv = $null
$found = Get-Command uv -ErrorAction SilentlyContinue
if ($found) { $uv = $found.Source }
foreach ($candidate in @("$env:USERPROFILE\.local\bin\uv.exe", "$env:USERPROFILE\.cargo\bin\uv.exe")) {
    if (-not $uv -and (Test-Path $candidate)) { $uv = $candidate }
}
if (-not $uv) {
    Info 'Instalando o uv (gerenciador de Python, gratuito)...'
    try {
        Invoke-RestMethod 'https://astral.sh/uv/install.ps1' | Invoke-Expression
    } catch {
        Fail "Nao consegui baixar o uv. Verifique a internet. Detalhe: $($_.Exception.Message)"
    }
    $uv = "$env:USERPROFILE\.local\bin\uv.exe"
    if (-not (Test-Path $uv)) { Fail 'O uv foi instalado, mas nao encontrei o uv.exe.' }
}
Info 'Baixando o Python e as bibliotecas (a primeira vez leva alguns minutos)...'
# Python gerenciado pelo uv: evita o atalho da Microsoft Store e versões antigas instaladas no PC.
$env:UV_PYTHON_PREFERENCE = 'only-managed'
& $uv sync --frozen --no-dev --python 3.12 --project (Join-Path $App 'hub')
if ($LASTEXITCODE -ne 0) { Fail 'Falha ao instalar as bibliotecas do Cordyhome.' }
if (-not (Test-Path $Exe)) { Fail "Nao encontrei $Exe depois da instalacao." }
$python = & (Join-Path $App 'hub\.venv\Scripts\python.exe') -c 'import sys; print(sys._base_executable)'
$python = "$python".Trim()

# 3. Rede e firewall ---------------------------------------------------------------------------
Step 'Liberando o Cordyhome na rede de casa'
$setPrivate = @()
$profiles = Get-NetConnectionProfile -ErrorAction SilentlyContinue |
    Where-Object { $_.IPv4Connectivity -ne 'NoTraffic' }
foreach ($p in $profiles) {
    if ($p.NetworkCategory -eq 'Public') {
        Warn "A rede '$($p.Name)' esta marcada como Publica. Assim o celular e as tomadas nao enxergam o Cordyhome."
        $answer = Read-Host '  Esta e a rede da sua casa? Marcar como Privada? (S/N)'
        if ($answer -match '^[sS]') { $setPrivate += $p.InterfaceIndex }
    }
}

$firewall = Join-Path $Root 'firewall.ps1'
$programs = @($python, (Join-Path $App 'hub\.venv\Scripts\python.exe')) | Where-Object { $_ -and (Test-Path $_) }
$lines = @(
    '$ErrorActionPreference = ''Continue'''
    'Remove-NetFirewallRule -Group ''Cordyhome'' -ErrorAction SilentlyContinue'
    "New-NetFirewallRule -DisplayName 'Cordyhome (interface)' -Group 'Cordyhome' -Direction Inbound -Protocol TCP -LocalPort $Port -Profile Private,Domain -Action Allow | Out-Null"
    "New-NetFirewallRule -DisplayName 'Cordyhome (descoberta das tomadas)' -Group 'Cordyhome' -Direction Inbound -Protocol UDP -LocalPort 6666,6667,7000 -Profile Private,Domain -Action Allow | Out-Null"
)
foreach ($program in $programs) {
    $lines += "New-NetFirewallRule -DisplayName 'Cordyhome (Python)' -Group 'Cordyhome' -Direction Inbound -Program '$program' -Profile Private,Domain -Action Allow | Out-Null"
}
foreach ($index in $setPrivate) {
    $lines += "Set-NetConnectionProfile -InterfaceIndex $index -NetworkCategory Private"
}
Set-Content -Path $firewall -Value $lines -Encoding Unicode

Info 'O Windows vai pedir permissao de administrador: clique em Sim.'
try {
    $proc = Start-Process powershell.exe -Verb RunAs -Wait -PassThru -WindowStyle Hidden `
        -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$firewall`""
    if ($proc.ExitCode -eq 0) {
        Info 'Firewall liberado para redes privadas.'
    } else {
        Warn 'Nao consegui confirmar a liberacao do firewall.'
    }
} catch {
    Warn 'Permissao negada. Se o Windows perguntar sobre o Python, marque "Redes privadas" e clique em Permitir.'
}
Remove-Item $firewall -Force -ErrorAction SilentlyContinue

# 4. Início automático e atalhos ---------------------------------------------------------------
Step 'Criando atalhos e o inicio automatico'
$cmd = 'cmd /c ""' + $Exe + '" > "' + $Log + '" 2>&1"'
$vbs = @(
    'Set shell = CreateObject("WScript.Shell")'
    'shell.Environment("Process")("PYTHONUTF8") = "1"'
    ('shell.CurrentDirectory = "' + $Root + '"')
    ('shell.Run "' + $cmd.Replace('"', '""') + '", 0, False')
)
Set-Content -Path $Launcher -Value $vbs -Encoding Unicode

$wscript = Join-Path $env:WINDIR 'System32\wscript.exe'
$startup = [Environment]::GetFolderPath('Startup')
New-Shortcut (Join-Path $startup 'Cordyhome.lnk') $wscript "`"$Launcher`"" $Icon

$desktop = [Environment]::GetFolderPath('Desktop')
New-UrlShortcut (Join-Path $desktop 'Cordyhome.url') $Icon

$menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'Cordyhome'
New-Item -ItemType Directory -Force -Path $menu | Out-Null
New-UrlShortcut (Join-Path $menu 'Cordyhome.url') $Icon
New-Shortcut (Join-Path $menu 'Iniciar o Cordyhome.lnk') $wscript "`"$Launcher`"" $Icon
New-Shortcut (Join-Path $menu 'Desinstalar o Cordyhome.lnk') 'powershell.exe' `
    "-NoProfile -ExecutionPolicy Bypass -File `"$Root\desinstalar.ps1`"" $Icon
Info 'Atalho na area de trabalho e no menu Iniciar. O Cordyhome liga junto com o Windows.'

# 5. Iniciar ---------------------------------------------------------------------------------
Step 'Iniciando o Cordyhome'
Start-Process $wscript -ArgumentList "`"$Launcher`""
$ok = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Hub) { $ok = $true; break }
}
if (-not $ok) {
    Write-Host ''
    if (Test-Path $Log) { Get-Content $Log -Tail 25 | ForEach-Object { Write-Host "  $_" } }
    Fail "O Cordyhome nao respondeu na porta $Port. Registro completo em $Log"
}

$ips = @(Get-NetIPConfiguration -ErrorAction SilentlyContinue |
    Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
    ForEach-Object { $_.IPv4Address.IPAddress })

Write-Host ''
Write-Host '  Pronto! O Cordyhome esta no ar.' -ForegroundColor Green
Write-Host "  Neste PC:   http://localhost:$Port"
foreach ($ip in $ips) { Write-Host "  No celular: http://${ip}:$Port  (conectado no mesmo Wi-Fi)" }
if ($wasRunning) { Write-Host '  Atualizacao concluida; seus dados foram mantidos.' }
Write-Host ''
Write-Host '  Primeiro acesso: crie sua conta e va em Ajustes > Tomadas Tuya > Conectar conta.'
Start-Process "http://localhost:$Port/"
