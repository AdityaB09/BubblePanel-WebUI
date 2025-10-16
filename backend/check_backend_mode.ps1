<# Detect if /run is ASYNC (returns {id}) or SYNC (returns full result) #>

param(
  [string]$RenderBase  = "https://bubblepanel-webui-1.onrender.com",
  [string]$NetlifyBase = "https://bubblebeta.netlify.app/api"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-Endpoint {
  param([string]$Base)
  Write-Host "=== Testing $Base ===" -ForegroundColor Cyan
  # quick status
  try {
    $st = Invoke-RestMethod -Uri "$Base/status" -Method GET -TimeoutSec 15
    Write-Host ("status ok; script_exists={0}" -f $st.script_exists) -ForegroundColor Green
  } catch {
    Write-Host "status failed: $($_.Exception.Message)" -ForegroundColor Red
    return
  }

  # minimal upload (required so /run has a path)
  $tmp = "$env:TEMP\bp_probe.txt"
  Set-Content -LiteralPath $tmp -Value "probe" -Encoding UTF8
  $raw = & curl.exe -s -F "file=@`"$tmp`"" "$Base/upload"
  Remove-Item $tmp -Force -ErrorAction SilentlyContinue
  if(-not $raw){ Write-Host "upload: empty response" -ForegroundColor Red; return }
  try { $u = $raw | ConvertFrom-Json } catch { Write-Host "upload: not JSON"; return }
  if(-not $u.ok){ Write-Host "upload: not ok"; return }
  $ui = $u.ui_path
  Write-Host "upload ok; ui_path=$ui" -ForegroundColor Green

  # post /run with DRY RUN (should be fast)
  $body = @{
    input=$ui; out="./data/outputs/probe"; jsonl="panels.jsonl"
    engine="encoder"; page_summarize=$false; page_style="paragraph"
    timeout_seconds=60; dry_run=$true
  } | ConvertTo-Json -Compress

  try {
    $resp = Invoke-RestMethod -Uri "$Base/run" -Method POST -ContentType 'application/json' -Body $body -TimeoutSec 20
  } catch {
    Write-Host "/run failed: $($_.Exception.Message)" -ForegroundColor Red
    return
  }

  $hasId = $false
  if ($resp -and $resp.PSObject -and $resp.PSObject.Properties) {
    $hasId = $resp.PSObject.Properties.Name -contains 'id'
  }

  if($hasId -and $resp.id){
    Write-Host "**ASYNC**: /run returned id=$($resp.id)" -ForegroundColor Yellow
    # quick poll once
    $s = Invoke-RestMethod -Uri "$Base/run/$($resp.id)" -Method GET -TimeoutSec 20
    Write-Host ("poll status={0}" -f $s.status) -ForegroundColor DarkYellow
  } else {
    Write-Host "**SYNC**: /run returned full result (no id)" -ForegroundColor Yellow
  }
  Write-Host ""
}

Test-Endpoint -Base $RenderBase
Test-Endpoint -Base $NetlifyBase
