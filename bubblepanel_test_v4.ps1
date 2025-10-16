<# 
.SYNOPSIS
  Netlify-safe tester for BubblePanel backend.
  - Uploads image via /api/upload (curl.exe)
  - Posts /api/run (DRY-RUN by default to avoid Netlify 504)
  - If server returns { id }, polls /api/run/{id} until done
  - If server returns full result, handles it directly
#>

param(
  [string]$Base         = "https://bubblebeta.netlify.app/api",   # Netlify proxy by default
  [string]$LocalImage   = "C:\path\to\image.png",
  [string]$OutRel       = "./data/outputs/ocr_test",
  [string]$Jsonl        = "panels.jsonl",
  [int]   $TimeoutSec   = 900,                                     # passed to backend when supported
  [int]   $PollEverySec = 2,                                       # polling interval for async runs
  [int]   $MaxWaitSec   = 600,                                     # total poll budget
  [switch]$DryRun       = $true,                                   # default true so Netlify won't 504
  [switch]$Summarize    = $false                                   # keep OFF unless a real LLM host is configured
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function J($o){ $o | ConvertTo-Json -Compress -Depth 8 }
function UrlJoin([string]$a,[string]$b){ if($a[-1] -eq '/'){$a=$a.TrimEnd('/')} if($b[0] -eq '/'){ $b=$b.TrimStart('/') }; "$a/$b" }
function ShowErrBody($ex){ try{$r=$ex.Response;if($r -and $r.GetResponseStream){$sr=New-Object IO.StreamReader($r.GetResponseStream());$b=$sr.ReadToEnd();$sr.Close();Write-Host "`n--- Server error body ---`n$b`n-------------------------" -ForegroundColor Yellow}}catch{} }

function Get-Status {
  $u = UrlJoin $Base "status"
  Write-Host "GET $u" -ForegroundColor Cyan
  Invoke-RestMethod -Uri $u -Method GET
}

function Upload-Image {
  param([string]$Path)
  if(-not (Test-Path -LiteralPath $Path)){ throw "LocalImage not found: $Path" }
  $u = UrlJoin $Base "upload"
  Write-Host "Uploading via curl.exe -> $u" -ForegroundColor Cyan
  $q = '"' + $Path + '"'  # robust quoting for spaces
  $raw = & curl.exe -s -F "file=@$q" "$u"
  if(-not $raw){ throw "Upload failed: empty response" }
  try { $resp = $raw | ConvertFrom-Json } catch { throw "Upload failed: not JSON. Raw: $raw" }
  if(-not $resp.ok){ throw "Upload failed." }
  $resp.ui_path
}

function Post-Run {
  param([string]$UiPath)
  $u = UrlJoin $Base "run"
  $body = J @{
    input           = $UiPath
    out             = $OutRel
    jsonl           = $Jsonl
    engine          = "encoder"           # no Ollama
    page_summarize  = [bool]$Summarize    # keep false unless LLM host set up
    page_style      = "paragraph"
    timeout_seconds = $TimeoutSec
    dry_run         = [bool]$DryRun
  }
  Write-Host "POST $u" -ForegroundColor Cyan
  Invoke-RestMethod -Uri $u -Method POST -ContentType 'application/json' -Body $body
}

function Poll-Job {
  param([string]$JobId)
  $deadline = (Get-Date).AddSeconds($MaxWaitSec)
  do {
    Start-Sleep -Seconds $PollEverySec
    $u = UrlJoin $Base ("run/" + $JobId)
    $s = Invoke-RestMethod -Uri $u -Method GET
    if($s.status -eq "done"){ return $s.result }
    if($s.status -eq "error"){ throw "Job error: $($s.error)" }
  } while((Get-Date) -lt $deadline)
  throw "Polling timed out after ${MaxWaitSec}s (job id: $JobId)."
}

function Download-Artifact {
  param([string]$ServerPath,[string]$OutFile)
  if(-not $OutFile){ $OutFile = Split-Path -Leaf $ServerPath }
  $u = UrlJoin $Base ("file?path=" + [uri]::EscapeDataString($ServerPath))
  Write-Host "GET $u -> $OutFile" -ForegroundColor Cyan
  Invoke-WebRequest -Uri $u -OutFile $OutFile | Out-Null
}

try {
  # 1) quick status
  $st = Get-Status
  Write-Host ("Backend OK. script_exists={0}" -f $st.script_exists) -ForegroundColor Green

  # 2) upload
  $ui = Upload-Image -Path $LocalImage
  Write-Host "ui_path=$ui" -ForegroundColor Green

  # 3) /run
  $resp = Post-Run -UiPath $ui

  # ---- robust: detect async vs sync safely ----
  $hasId = $false
  if ($resp -and $resp.PSObject -and $resp.PSObject.Properties) {
    $hasId = $resp.PSObject.Properties.Name -contains 'id'
  }

  if ($hasId -and $resp.id) {
    Write-Host ("Job queued: id={0} (polling every {1}s, max {2}s)" -f $resp.id,$PollEverySec,$MaxWaitSec) -ForegroundColor DarkCyan
    $result = Poll-Job -JobId $resp.id
  } else {
    # Treat as direct result
    $result = $resp
  }

  # Show result
  $result | ConvertTo-Json -Depth 8 | Out-Host

  # 4) Download first artifacts if it was a real run
  if(-not $DryRun){
    if($result.overlays -and $result.overlays.Count -gt 0){ Download-Artifact -ServerPath $result.overlays[0] }
    if($result.text_files -and $result.text_files.Count -gt 0){ Download-Artifact -ServerPath $result.text_files[0] }
    if($result.jsonls -and $result.jsonls.Count -gt 0){ Download-Artifact -ServerPath $result.jsonls[0] }
  } else {
    Write-Host "(Dry run) Skipping downloads." -ForegroundColor Yellow
  }

  Write-Host "`nDone." -ForegroundColor Green
} catch {
  ShowErrBody $_.Exception
  throw
}
