<#
.SYNOPSIS
  BubblePanel tester (PowerShell, Windows-friendly).
  - Uploads an image (via curl.exe)
  - Calls /run in encoder mode (no Ollama)
  - Optional: dry-run, custom timeout, Netlify proxy

.EXAMPLES
  .\bubblepanel_test_v3.ps1 -LocalImage "C:\path\page.png"
  .\bubblepanel_test_v3.ps1 -LocalImage "C:\path\page.png" -OutRel "./data/outputs/page_web" -TimeoutSeconds 900
  .\bubblepanel_test_v3.ps1 -LocalImage "C:\path\page.png" -UseNetlify -NetlifyBase "https://bubblebeta.netlify.app"
#>

param(
  [string]$RenderBase   = "https://bubblepanel-webui-1.onrender.com",
  [string]$NetlifyBase  = "https://bubblebeta.netlify.app",
  [switch]$UseNetlify,
  [string]$LocalImage   = "C:\path\to\image.png",
  [string]$OutRel       = "./data/outputs/ocr_test",
  [string]$Jsonl        = "panels.jsonl",
  [int]$TimeoutSeconds  = 600,
  [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Show-ErrorBody {
  param([Parameter(Mandatory)][System.Exception]$Exception)
  try {
    $resp = $Exception.Response
    if ($resp -and $resp.GetResponseStream) {
      $rs = $resp.GetResponseStream()
      $sr = New-Object System.IO.StreamReader($rs)
      $body = $sr.ReadToEnd()
      $sr.Close()
      Write-Host "`n--- Error body from server ---`n$body`n-------------------------------" -ForegroundColor Yellow
    }
  } catch { }
}

function Get-Json {
  param([Parameter(Mandatory)][hashtable]$Obj)
  return ($Obj | ConvertTo-Json -Compress -Depth 6)
}

function BaseUrl {
  if ($UseNetlify) { return "$NetlifyBase/api" } else { return $RenderBase }
}

function Test-Backend {
  $base = BaseUrl
  Write-Host "Checking backend status at $($base)/status ..." -ForegroundColor Cyan
  $st = Invoke-RestMethod "$($base)/status" -Method GET
  Write-Host ("Backend OK. script_exists={0}" -f $st.script_exists) -ForegroundColor Green
}

function Upload-Image {
  param([Parameter(Mandatory)][string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) {
    throw "LocalImage not found: $Path"
  }
  $base = BaseUrl
  Write-Host "Uploading $Path via curl.exe -> $($base)/upload ..." -ForegroundColor Cyan
  $json = & curl.exe -s -F "file=@$Path" "$($base)/upload"
  if (-not $json) { throw "Upload failed: empty response." }
  try {
    $resp = $json | ConvertFrom-Json
  } catch {
    throw "Upload failed: response was not JSON. Raw: $json"
  }
  if (-not $resp.ok) { throw "Upload failed." }
  Write-Host ("Uploaded. ui_path={0}" -f ($resp.ui_path ?? $resp.path)) -ForegroundColor Green
  return ($resp.ui_path ?? $resp.path)
}

function Run-OCR {
  param(
    [Parameter(Mandatory)][string]$UiPath,
    [Parameter(Mandatory)][string]$OutRel,
    [Parameter(Mandatory)][string]$Jsonl,
    [int]$TimeoutSeconds,
    [switch]$DryRun
  )
  $base = BaseUrl
  $body = Get-Json @{
    input          = $UiPath
    out            = $OutRel
    jsonl          = $Jsonl
    engine         = "encoder"     # No Ollama
    page_summarize = $true
    page_style     = "paragraph"
    dry_run        = [bool]$DryRun
    timeout_seconds= [int]$TimeoutSeconds
  }

  Write-Host "POST $($base)/run (encoder mode) ..." -ForegroundColor Cyan
  $resp = Invoke-RestMethod -Uri "$($base)/run" -Method POST -ContentType "application/json" -Body $body
  if (-not $resp.ok) { throw "Server returned ok=false. See stdout/stderr in response." }

  Write-Host "`n--- Command ---`n$($resp.command)`n" -ForegroundColor Magenta
  if ($resp.stdout) { Write-Host "--- stdout (tail) ---" -ForegroundColor DarkCyan; $resp.stdout | Out-Host }
  if ($resp.stderr) { Write-Host "`n--- stderr (tail) ---" -ForegroundColor DarkYellow; $resp.stderr | Out-Host }

  $overlayCount = ($resp.overlays | Measure-Object).Count
  $textCount    = ($resp.text_files | Measure-Object).Count
  $jsonlCount   = ($resp.jsonls | Measure-Object).Count
  Write-Host ("`nArtifacts: overlays={0} text_files={1} jsonls={2}" -f $overlayCount, $textCount, $jsonlCount) -ForegroundColor Green

  return $resp
}

function Download-Artifact {
  param([Parameter(Mandatory)][string]$ServerPath, [string]$OutFile)
  $base = BaseUrl
  if (-not $OutFile) { $OutFile = Split-Path -Leaf $ServerPath }
  $url = "$($base)/file?path=$([uri]::EscapeDataString($ServerPath))"
  Write-Host "Downloading $ServerPath -> $OutFile" -ForegroundColor Cyan
  Invoke-WebRequest -Uri $url -OutFile $OutFile
}

# ---------------- Main ----------------
try {
  Test-Backend

  $ui = Upload-Image -Path $LocalImage

  $result = Run-OCR -UiPath $ui -OutRel $OutRel -Jsonl $Jsonl -TimeoutSeconds $TimeoutSeconds -DryRun:$DryRun

  if (-not $DryRun) {
    if ($result.overlays -and $result.overlays.Count -gt 0) {
      Download-Artifact -ServerPath $result.overlays[0]
    }
    if ($result.text_files -and $result.text_files.Count -gt 0) {
      Download-Artifact -ServerPath $result.text_files[0]
    }
    if ($result.jsonls -and $result.jsonls.Count -gt 0) {
      Download-Artifact -ServerPath $result.jsonls[0]
    }
  } else {
    Write-Host "`n(Dry run only; no artifacts to download.)" -ForegroundColor Yellow
  }

  Write-Host "`nDone." -ForegroundColor Green
} catch {
  Show-ErrorBody -Exception $_.Exception
  throw
}
