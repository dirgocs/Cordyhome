# Remove o Cordyhome do Windows. Pergunta antes de apagar os dados (contas, histórico de energia).

$ErrorActionPreference = 'Continue'
$Port = 8420
$Root = Join-Path $env:LOCALAPPDATA 'Cordyhome'
$App = Join-Path $Root 'app'
$Data = Join-Path $env:USERPROFILE '.cordyhome'

Write-Host ''
Write-Host '  Desinstalar o Cordyhome' -ForegroundColor Cyan
$answer = Read-Host '  Remover o Cordyhome deste PC? (S/N)'
if ($answer -notmatch '^[sS]') { exit 0 }

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

Remove-Item (Join-Path ([Environment]::GetFolderPath('Startup')) 'Cordyhome.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Cordyhome.url') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Programs')) 'Cordyhome') -Recurse -Force -ErrorAction SilentlyContinue

Write-Host '  O Windows vai pedir permissao para remover as regras do firewall: clique em Sim.'
try {
    Start-Process powershell.exe -Verb RunAs -Wait -WindowStyle Hidden `
        -ArgumentList "-NoProfile -Command `"Remove-NetFirewallRule -Group 'Cordyhome' -ErrorAction SilentlyContinue`""
} catch {
    Write-Host '  Regras do firewall mantidas (permissao negada).' -ForegroundColor Yellow
}

Remove-Item $Root -Recurse -Force -ErrorAction SilentlyContinue

if (Test-Path $Data) {
    $answer = Read-Host "  Apagar tambem os dados (conta, aparelhos e historico de energia em $Data)? (S/N)"
    if ($answer -match '^[sS]') {
        Remove-Item $Data -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host '  Dados apagados.'
    } else {
        Write-Host '  Dados mantidos. Se instalar de novo, tudo volta como estava.'
    }
}

Write-Host ''
Write-Host '  Cordyhome removido.' -ForegroundColor Green
Read-Host '  Pressione Enter para fechar'
