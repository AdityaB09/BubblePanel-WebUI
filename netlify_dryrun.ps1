<# Quick DRY-RUN through Netlify proxy (fast response; proves /api/* works) #>

# HARD-CODED for your project
$Base       = "https://bubblebeta.netlify.app/api"
$LocalImage = "C:\Users\adity\Downloads\BubblePanel-WebUI\BubblePanel-main\data\chapter\smoke_chapter\page_0002.png"

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function J($o){ $o | ConvertTo-Json -Compress -Depth 8 }

Write-Host "GET $Base/status" -ForegroundColor Cyan
$st = Invoke-RestMethod -Uri "$Base/status" -Method GET -TimeoutSec 30
Write-Host ("Backend OK. script_exists={0}" -f $st.script_exists) -ForegroundColor Green

if(-not (Test-Path -LiteralPath $LocalImage)){ throw "LocalImage not found: $LocalImage" }
Write-Host "Uploading via curl.exe -> $Base/upload" -ForegroundColor Cyan
$raw = & curl.exe -s -F "file=@`"$LocalImage`"" "$Base/upload"
if(-not $raw){ throw "Upload failed: empty response" }
try { $u = $raw | ConvertFrom-Json } catch { throw "Upload failed: not JSON. Raw: $raw" }
if(-not $u.ok){ throw "Upload failed." }
$ui = $u.ui_path
Write-Host "ui_path=$ui" -ForegroundColor Green

$body = J @{
  input=$ui; out="./data/outputs/ocr_test"; jsonl="panels.jsonl"
  engine="encoder"; page_summarize=$false; page_style="paragraph"
  timeout_seconds=900; dry_run=$true
}

Write-Host "POST $Base/run (dry_run)" -ForegroundColor Cyan
$resp = Invoke-RestMethod -Uri "$Base/run" -Method POST -ContentType 'application/json' -Body $body -TimeoutSec 30
$resp | ConvertTo-Json -Depth 8 | Out-Host
Write-Host "`n(Dry run) OK." -ForegroundColor Green
