# Faceless Engine — One-Shot Launcher (Windows)
# Run this to generate, distribute, and report in one command

Write-Host "=== Faceless Engine ===" -ForegroundColor Cyan
Write-Host "Bootstraping content cycle..." -ForegroundColor Yellow

python orchestrator.py --mode bootstrap

Write-Host "Done." -ForegroundColor Green
