<#
.SYNOPSIS
  One-click tester for BubblePanel backend (Render). Uploads an image, runs OCR (encoder mode), and prints artifacts.

.EXAMPLE
  .\bubblepanel_test.ps1 -LocalImage "C:\Users\adity\Downloads\BubblePanel-WebUI\BubblePanel-main\data\chapter\smoke_chapter\page_0002.png"

.PARAMETER RenderBase
  Base URL of your Render backend (e.g., https://bubblepanel-webui-1.onrender.com).

.PARAMETER LocalImage
  Full local path to the image you want to upload.

.PARAMETER OutRel
  Output folder (Linux-style, relative to BubblePanel-main), e.g., ./data/outputs/ocr_test

.PARAMETER Jsonl
  Name for the panels jsonl file. Will be placed inside OutRel if relative.

.PARAMETER DryRun
  If set, the server will validate and echo the command without running the full OCR.
#>

param(
  [string]$RenderBase = "https://bubblepanel-webui-1.onrender.com",
  [string]$LocalImage = "C:\path\to\image.png",
  [string]$OutRel     = "./data/outputs/ocr_test",
  [string]$Jsonl      = "panels.jsonl",
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

function Test-Backend {
  Write-Host "Checking backend status at $RenderBase/status ..." -ForegroundColor Cyan
  $st = Invoke-RestMethod "$RenderBase/status" -Method GET
  Write-Host ("Backend OK. bp_root={0} upload_dir={1} script_exists={2}" -f $st.bp_root, $st.upload_dir, $st.script_exists) -ForegroundColor Green
}

function Upload-Image {
  param([Parameter(Mandatory)][string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) {
    throw "LocalImage not found: $Path"
  }
  Write-Host "Uploading $Path ..." -ForegroundColor Cyan
  $resp = Invoke-RestMethod -Uri "$RenderBase/upload" -Method POST -Form @{ file = Get-Item -LiteralPath $Path }
  if (-not $resp.ok) { throw "Upload failed." }
  Write-Host ("Uploaded. ui_path={0}" -f $resp.ui_path) -ForegroundColor Green
  return $resp.ui_path
}

function Run-OCR {
  param(
    [Parameter(Mandatory)][string]$UiPath,
    [Parameter(Mandatory)][string]$OutRel,
    [Parameter(Mandatory)][string]$Jsonl,
    [switch]$DryRun
  )
  $body = Get-Json @{
    input          = $UiPath
    out            = $OutRel
    jsonl          = $Jsonl
    engine         = "encoder"     # No Ollama
    page_summarize = $true
    page_style     = "paragraph"
    dry_run        = [bool]$DryRun
  }

  Write-Host "POST /run (encoder mode) ..." -ForegroundColor Cyan
  $resp = Invoke-RestMethod -Uri "$RenderBase/run" -Method POST -ContentType "application/json" -Body $body
  if (-not $resp.ok) { throw "Server returned ok=false. See stdout/stderr in response." }

  # Pretty print key fields
  Write-Host "`n--- Command ---`n$($resp.command)`n" -ForegroundColor Magenta
  if ($resp.stdout) { Write-Host "--- stdout (tail) ---" -ForegroundColor DarkCyan; $resp.stdout | Out-Host }
  if ($resp.stderr) { Write-Host "`n--- stderr (tail) ---" -ForegroundColor DarkYellow; $resp.stderr | Out-Host }

  # Artifacts summary
  $overlayCount = ($resp.overlays | Measure-Object).Count
  $textCount    = ($resp.text_files | Measure-Object).Count
  $jsonlCount   = ($resp.jsonls | Measure-Object).Count
  Write-Host ("`nArtifacts: overlays={0} text_files={1} jsonls={2}" -f $overlayCount, $textCount, $jsonlCount) -ForegroundColor Green

  return $resp
}

function Download-Artifact {
  param(
    [Parameter(Mandatory)][string]$ServerPath,
    [string]$OutFile
  )
  if (-not $OutFile) {
    $OutFile = Split-Path -Leaf $ServerPath
  }
  $url = "$RenderBase/file?path=$([uri]::EscapeDataString($ServerPath))"
  Write-Host "Downloading $ServerPath -> $OutFile" -ForegroundColor Cyan
  Invoke-WebRequest -Uri $url -OutFile $OutFile
}

# ---------------- Main ----------------
try {
  Test-Backend

  $ui = Upload-Image -Path $LocalImage

  $result = Run-OCR -UiPath $ui -OutRel $OutRel -Jsonl $Jsonl -DryRun:$DryRun

  if (-not $DryRun) {
    # Optionally download the first overlay/text/jsonl to the current folder
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
