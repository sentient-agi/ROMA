# ============================================================================
# PTC Repository Setup Script for Windows PowerShell
# ROMA + PTC Integration - Phase 1
# ============================================================================

Write-Host "`n=== PTC Repository Setup ===" -ForegroundColor Cyan

# Navigate to projects directory
Set-Location "C:\Users\dkell\projects"

# Clone PTC repository
Write-Host "`n[1/5] Cloning open-ptc-agent repository..." -ForegroundColor Yellow
git clone https://github.com/Mtolivepickle/open-ptc-agent.git

# Enter PTC directory
Set-Location "open-ptc-agent"

# Install dependencies
Write-Host "`n[2/5] Installing dependencies with uv..." -ForegroundColor Yellow
uv sync

# Create .env from template
Write-Host "`n[3/5] Creating .env file..." -ForegroundColor Yellow
Copy-Item .env.example .env

# Configure .env with API keys
Write-Host "`n[4/5] Configuring API keys..." -ForegroundColor Yellow
$envContent = Get-Content .env
$envContent = $envContent -replace '^ANTHROPIC_API_KEY=.*', 'ANTHROPIC_API_KEY=sk-wgfw2sEL0ZTO9zgVPGuVdlQVpn2G7SbUvvSn0uCoPGy4ICCq'
$envContent = $envContent -replace '^DAYTONA_API_KEY=.*', 'DAYTONA_API_KEY=dtn_fee7f751e8e48c1a44bdd405464e157a0efe4d8f8a9ff0d1f78fb8ded99b2a84'
$envContent | Set-Content .env

# Validate setup
Write-Host "`n[5/5] Validating PTC setup..." -ForegroundColor Yellow
Write-Host "`nTesting LangChain import..." -ForegroundColor Cyan
uv run python -c "import langchain; print('✓ LangChain OK')"

Write-Host "`nTesting Daytona SDK import..." -ForegroundColor Cyan
uv run python -c "from daytona_sdk import Daytona; print('✓ Daytona SDK OK')"

Write-Host "`n=== PTC Setup Complete ===" -ForegroundColor Green
Write-Host "`nNext: Run Phase 1 validation from ROMA directory" -ForegroundColor Yellow
Write-Host "cd ..\ROMA" -ForegroundColor White
Write-Host "uv run python scripts/ptc/validate_phase1.py" -ForegroundColor White
