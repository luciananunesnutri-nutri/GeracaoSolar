@echo off
cd /d "C:\desenv_build\projetos\GeracaoSolar"

echo [%date% %time%] Iniciando GeracaoSolar... >> logs\startup.log

start "GeracaoSolar-Web" /min "C:\Users\1334\AppData\Local\Python\pythoncore-3.14-64\python.exe" web_server.py

timeout /t 5 /nobreak >nul

start "GeracaoSolar-Scheduler" /min "C:\Users\1334\AppData\Local\Python\pythoncore-3.14-64\python.exe" main.py

echo [%date% %time%] Servicos iniciados. >> logs\startup.log
