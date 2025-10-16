<# 
.SYNOPSIS
  BubblePanel backend tester for Windows PowerShell 5.1+
  - Uploads an image (curl.exe multipart)
  - Calls /run in encoder mode (JSON)
  - Optional timeout override
  - Targets Render directly or the Netlify proxy

.EXAMPLES
  # Direct to Render
  .\bubblepanel_test_v3.ps1 -Base "https://bubblepanel-webui-1.onrender.com" -LocalImage "C:\path\page_0002.png"

  # Through Netlify proxy
  .\bubblepanel_test_v3.ps1 -Base "https://bubblebeta.netlify.app/api" -LocalImage "C:\path\page_0002.png"

  # Longer timeout (first-run model downloads)
  .\bubblepanel_test_v3.ps1 -LocalImage "C:\path\page_0002.png" -TimeoutSec 900

  # Enable LLM summaries (requires a reachable Ollama host in your backend config)
  .\bubblepanel_test_v3.ps1 -Summarize
#>

param(
  [string]$Base       = "https://bubblepanel-webui-1.onrender.com",  # use https://<netlify>/api for proxy
  [string]$LocalImage = "C:\path\to\image.png",
  [string]$OutRel     = "./data/outputs/ocr_test",
  [string]$Jsonl      = "panels.jsonl",
  [int]$TimeoutSec    = 900,
  [switch]$DryRun,
  [switch]$Summarize    # OFF by default to avoid Ollama errors
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Show-Err($ex) {
  try {
    $resp = $ex.Response
    if ($resp -and $resp.GetResponseStream) {
      $rs = $resp.GetResponseStream()
      $sr = New-Object System.IO.StreamReader($rs)
      $body = $sr.ReadToEnd()
      $sr.Close()
      Write-Host "`n--- Error body from server ---`n$body`n-------------------------------" -ForegroundColor Yellow
    }
  } catch {}
}

function J($obj) { $obj | ConvertTo-Json -Compress -Depth 8 }

function UrlJoin([string]$a,[string]$b) {
  if ($a.EndsWith('/')) { $a = $a.TrimEnd('/') }
  if ($b.StartsWith('/')) { $b = $b.TrimStart('/') }
  return "$a/$b"
}

function Get-Status {
  param([string]$Base)
  $url = UrlJoin $Base "status"
  Write-Host "GET $url" -ForegroundColor Cyan
  Invoke-RestMethod -Uri $url -Method GET
}

function Upload-Image {
  param([string]$Base,[string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) { throw "LocalImage not found: $Path" }
  $url = UrlJoin $Base "upload"
  Write-Host "Uploading via curl.exe -> $url" -ForegroundColor Cyan
  # Robust quoting for windows paths with spaces:
  $quoted = '"' + $Path + '"'
  $raw = & curl.exe -s -F "file=@$quoted" "$url"
  if (-not $raw) { throw "Upload failed: empty response" }
  try { $resp = $raw | ConvertFrom-Json } catch { throw "Upload failed: not JSON. Raw: $raw" }
  if (-not $resp.ok) { throw "Upload failed" }
  return $resp.ui_path
}

function Run-Encoder {
  param([string]$Base,[string]$UiPath,[string]$OutRel,[string]$Jsonl,[int]$TimeoutSec,[switch]$DryRun,[switch]$Summarize)
  $url = UrlJoin $Base "run"
  $body = J @{
    input = $UiPath
    out   = $OutRel
    jsonl = $Jsonl
    engine = "encoder"
    page_summarize = [bool]$Summarize    # <- OFF by default to avoid Ollama
    page_style     = "paragraph"
    timeout_seconds = $TimeoutSec
    dry_run = [bool]$DryRun
  }
  Write-Host "POST $url" -ForegroundColor Cyan
  Invoke-RestMethod -Uri $url -Method POST -ContentType 'application/json' -Body $body
}

function Download-Artifact {
  param([string]$Base,[string]$ServerPath,[string]$OutFile)
  if (-not $OutFile) { $OutFile = Split-Path -Leaf $ServerPath }
  $url = UrlJoin $Base ("file?path=" + [uri]::EscapeDataString($ServerPath))
  Write-Host "GET $url -> $OutFile" -ForegroundColor Cyan
  Invoke-WebRequest -Uri $url -OutFile $OutFile | Out-Null
}

try {
  $st = Get-Status -Base $Base
  Write-Host ("Backend OK. script_exists={0}" -f $st.script_exists) -ForegroundColor Green

  $ui = Upload-Image -Base $Base -Path $LocalImage
  Write-Host "ui_path=$ui" -ForegroundColor Green

  $resp = Run-Encoder -Base $Base -UiPath $ui -OutRel $OutRel -Jsonl $Jsonl -TimeoutSec $TimeoutSec -DryRun:$DryRun -Summarize:$Summarize
  $resp | ConvertTo-Json -Depth 8 | Out-Host

  if (-not $DryRun) {
    if ($resp.overlays -and $resp.overlays.Count -gt 0) { Download-Artifact -Base $Base -ServerPath $resp.overlays[0] }
    if ($resp.text_files -and $resp.text_files.Count -gt 0) { Download-Artifact -Base $Base -ServerPath $resp.text_files[0] }
    if ($resp.jsonls -and $resp.jsonls.Count -gt 0) { Download-Artifact -Base $Base -ServerPath $resp.jsonls[0] }
  } else {
    Write-Host "(Dry run) Skipping downloads." -ForegroundColor Yellow
  }

  Write-Host "`nDone." -ForegroundColor Green
} catch {
  Show-Err $_.Exception
  throw
}
