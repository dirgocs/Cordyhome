@echo off
title Instalador do Cordyhome
if not exist "%~dp0instalar.ps1" (
  echo.
  echo  Extraia o arquivo ZIP antes de instalar:
  echo  clique com o botao direito no ZIP, escolha "Extrair tudo" e
  echo  rode o "Instalar Cordyhome" de dentro da pasta extraida.
  echo.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar.ps1"
echo.
pause
