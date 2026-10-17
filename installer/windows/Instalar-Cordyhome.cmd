@echo off
rem Instalador do Cordyhome para Windows. Dê dois cliques neste arquivo.
rem A parte de baixo (depois de #<PS>) é um script PowerShell executado a partir daqui.
chcp 65001 >nul
set "CORDY_SELF=%~f0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s = Get-Content -LiteralPath $env:CORDY_SELF -Raw -Encoding UTF8; $i = $s.IndexOf('#<' + 'PS>'); Invoke-Expression $s.Substring($i)"
echo.
pause
exit /b
#<PS>
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

$Repo = 'dirgocs/Cordyhome'
$PackageUrl = "https://github.com/$Repo/releases/latest/download/cordyhome.zip"
$Port = 8420
$InstallDir = Join-Path $env:LOCALAPPDATA 'Cordyhome'
$AppDir = Join-Path $InstallDir 'app'

function Step($text) { Write-Host ''; Write-Host "==> $text" -ForegroundColor Cyan }
function Ok($text) { Write-Host "    $text" -ForegroundColor Green }
function Warn($text) { Write-Host "    $text" -ForegroundColor Yellow }

function Find-Uv {
    $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $user = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = "$machine;$user;$env:Path"
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($p in @("$env:USERPROFILE\.local\bin\uv.exe", "$env:USERPROFILE\.cargo\bin\uv.exe")) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

# O lançador fica em %LOCALAPPDATA%\Cordyhome\cordyhome.ps1 e é usado pelos atalhos.
$Launcher = @'
param([ValidateSet('start', 'stop')][string]$Action = 'start', [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$InstallDir = '__INSTALL_DIR__'
$Port = __PORT__
$Url = "http://localhost:$Port"
$Exe = Join-Path $InstallDir 'app\hub\.venv\Scripts\cordyhome.exe'

function Test-Running {
    try {
        Invoke-WebRequest "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
        return $true
    } catch { return $false }
}

function Stop-Cordyhome {
    Get-Process cordyhome -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -like "$InstallDir\*" } | Stop-Process -Force
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}

if ($Action -eq 'stop') { Stop-Cordyhome; exit 0 }

if (-not (Test-Running)) {
    $env:CORDYHOME_PORT = "$Port"
    $env:CORDYHOME_WEB = Join-Path $InstallDir 'app\web\build'
    $logs = Join-Path $InstallDir 'logs'
    New-Item -ItemType Directory -Force $logs | Out-Null
    # Via cmd, num console próprio e oculto: o hub continua rodando depois que esta
    # janela fecha, e a saída vai para o log.
    $log = Join-Path $logs 'cordyhome.log'
    Start-Process cmd -WindowStyle Hidden -WorkingDirectory $InstallDir `
        -ArgumentList "/c `"`"$Exe`" > `"$log`" 2>&1`""
    for ($i = 0; $i -lt 60 -and -not (Test-Running); $i++) { Start-Sleep -Milliseconds 500 }
}

if (-not $NoBrowser) { Start-Process $Url }
'@

try {
    Write-Host ''
    Write-Host '  Instalador do Cordyhome' -ForegroundColor White
    Write-Host '  -----------------------'

    Step 'Verificando o uv (ele cuida do Python)'
    $uv = Find-Uv
    if (-not $uv) {
        Warn 'uv não encontrado. Instalando...'
        & powershell -NoProfile -ExecutionPolicy Bypass -Command 'irm https://astral.sh/uv/install.ps1 | iex'
        $uv = Find-Uv
        if (-not $uv) { throw 'Não consegui instalar o uv. Veja https://docs.astral.sh/uv/ e rode este instalador de novo.' }
    } else {
        & $uv self update 2>$null | Out-Null
    }
    Ok "uv pronto: $uv"

    Step 'Parando o Cordyhome, se estiver rodando'
    $launcherPath = Join-Path $InstallDir 'cordyhome.ps1'
    if (Test-Path $launcherPath) {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $launcherPath -Action stop
        Start-Sleep -Seconds 1
    }
    Ok 'Ok'

    Step 'Baixando a versão mais recente do Cordyhome'
    New-Item -ItemType Directory -Force $InstallDir | Out-Null
    $zip = Join-Path $env:TEMP 'cordyhome.zip'
    Invoke-WebRequest $PackageUrl -OutFile $zip -UseBasicParsing
    if (Test-Path $AppDir) { Remove-Item $AppDir -Recurse -Force }
    Expand-Archive $zip -DestinationPath $AppDir -Force
    Remove-Item $zip -Force
    Ok "Instalado em $AppDir"

    Step 'Preparando o Python e as dependências (a primeira vez demora alguns minutos)'
    $env:UV_PYTHON_PREFERENCE = 'only-managed'
    Push-Location (Join-Path $AppDir 'hub')
    try {
        & $uv sync --frozen --no-dev --python 3.12
        if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar as dependências do Python.' }
    } finally { Pop-Location }
    Ok 'Dependências prontas'

    Step 'Criando os atalhos'
    $Launcher.Replace('__INSTALL_DIR__', $InstallDir).Replace('__PORT__', "$Port") |
        Set-Content -LiteralPath $launcherPath -Encoding UTF8
    $icon = Join-Path $AppDir 'cordyhome.ico'
    $ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $shell = New-Object -ComObject WScript.Shell
    function New-Shortcut($path, $arguments, $description) {
        $lnk = $shell.CreateShortcut($path)
        $lnk.TargetPath = $ps
        $lnk.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$launcherPath`" $arguments"
        $lnk.WorkingDirectory = $InstallDir
        $lnk.Description = $description
        if (Test-Path $icon) { $lnk.IconLocation = $icon }
        $lnk.Save()
    }
    $desktop = [Environment]::GetFolderPath('Desktop')
    $programs = [Environment]::GetFolderPath('Programs')
    $startup = [Environment]::GetFolderPath('Startup')
    New-Shortcut (Join-Path $desktop 'Cordyhome.lnk') '' 'Abrir o Cordyhome'
    New-Shortcut (Join-Path $programs 'Cordyhome.lnk') '' 'Abrir o Cordyhome'
    New-Shortcut (Join-Path $programs 'Parar Cordyhome.lnk') '-Action stop' 'Parar o Cordyhome'
    # Inicia junto com o Windows, sem abrir o navegador, para gravar o consumo o tempo todo.
    New-Shortcut (Join-Path $startup 'Cordyhome.lnk') '-NoBrowser' 'Iniciar o Cordyhome'
    Ok 'Atalho na área de trabalho e no menu Iniciar; o Cordyhome também inicia com o Windows'

    Step 'Liberando o Cordyhome no firewall (redes privadas)'
    $rules = "New-NetFirewallRule -DisplayName 'Cordyhome (interface)' -Direction Inbound -Protocol TCP -LocalPort $Port -Profile Private -Action Allow | Out-Null; " +
             "New-NetFirewallRule -DisplayName 'Cordyhome (tomadas Tuya)' -Direction Inbound -Protocol UDP -LocalPort 6666,6667 -Profile Private -Action Allow | Out-Null"
    $existing = Get-NetFirewallRule -DisplayName 'Cordyhome (interface)' -ErrorAction SilentlyContinue
    if ($existing) {
        Ok 'Regras já existem'
    } else {
        Warn 'O Windows vai pedir permissão de administrador. Clique em Sim.'
        try {
            $p = Start-Process powershell -Verb RunAs -Wait -PassThru -WindowStyle Hidden `
                -ArgumentList '-NoProfile', '-Command', $rules
            if ($p.ExitCode -eq 0) { Ok 'Firewall liberado' }
            else { Warn 'Não consegui criar as regras. Se o Windows perguntar sobre o firewall, permita em redes privadas.' }
        } catch {
            Warn 'Permissão negada. Se o Windows perguntar sobre o firewall, permita em redes privadas.'
        }
    }
    $public = Get-NetConnectionProfile -ErrorAction SilentlyContinue | Where-Object { $_.NetworkCategory -eq 'Public' }
    if ($public) {
        Warn "A rede '$($public[0].Name)' está como Pública. As tomadas só são encontradas em rede Privada:"
        Warn 'Configurações > Rede e Internet > Wi-Fi ou Ethernet > Propriedades > Privada.'
    }

    Step 'Iniciando o Cordyhome'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $launcherPath
    $ip = Get-NetIPConfiguration -ErrorAction SilentlyContinue |
        Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
        Select-Object -First 1 | ForEach-Object { $_.IPv4Address.IPAddress } | Select-Object -First 1

    Write-Host ''
    Write-Host '  Pronto! O Cordyhome está rodando.' -ForegroundColor Green
    Write-Host "  Neste PC:    http://localhost:$Port"
    if ($ip) { Write-Host "  No celular:  http://${ip}:$Port  (no mesmo Wi-Fi)" }
    Write-Host ''
    Write-Host '  Crie a sua conta e vá em Ajustes > Tomadas Tuya > Conectar conta.'
    Write-Host '  Para atualizar no futuro, rode este instalador de novo. Seus dados são mantidos.'
} catch {
    Write-Host ''
    Write-Host "  Erro: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host '  Tire um print desta janela e mande para o Claude.' -ForegroundColor Red
}
