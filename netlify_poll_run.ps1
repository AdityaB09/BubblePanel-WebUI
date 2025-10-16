<# Full OCR job through Netlify with async /run polling #>
param(
  [string]$Base         = "https://bubblebeta.netlify.app/api",
  [string]$LocalImage   = "C:\path\to\image.png",
  [string]$OutRel       = "./data/outputs/ocr_test",
  [string]$Jsonl        = "panels.jsonl",
  [int]   $TimeoutSec   = 900,
  [int]   $PollEverySec = 2,
  [int]   $MaxWaitSec   = 900
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function J($o){ $o | ConvertTo-Json -Compress -Depth 8 }
function UrlJoin([string]$a,[string]$b){ if($a[-1] -eq '/'){ $a=$a.TrimEnd('/') }; if($b[0] -eq '/'){ $b=$b.TrimStart('/') }; "$a/$b" }

# sanity: status
Write-Host "GET $Base/status" -ForegroundColor Cyan
$st = Invoke-RestMethod -Uri "$Base/status" -Method GET -TimeoutSec 30
Write-Host ("Backend OK. script_exists={0}" -f $st.script_exists) -ForegroundColor Green

# upload image
if(-not (Test-Path -LiteralPath $LocalImage)){ throw "LocalImage not found: $LocalImage" }
Write-Host "Uploading via curl.exe -> $Base/upload" -ForegroundColor Cyan
$raw = & curl.exe -s -F "file=@`"$LocalImage`"" "$Base/upload"
if(-not $raw){ throw "Upload failed: empty response" }
try { $u = $raw | ConvertFrom-Json } catch { throw "Upload failed: not JSON. Raw: $raw" }
if(-not $u.ok){ throw "Upload failed." }
$ui = $u.ui_path
Write-Host "ui_path=$ui" -ForegroundColor Green

# post run (must return id quickly)
$body = J @{
  input=$ui; out=$OutRel; jsonl=$Jsonl
  engine="encoder"; page_summarize=$false; page_style="paragraph"
  timeout_seconds=$TimeoutSec; dry_run=$false
}

Write-Host "POST $Base/run" -ForegroundColor Cyan
$resp = Invoke-RestMethod -Uri "$Base/run" -Method POST -ContentType 'application/json' -Body $body -TimeoutSec 30

$hasId = $false
if ($resp -and $resp.PSObject -and $resp.PSObject.Properties) {
  $hasId = $resp.PSObject.Properties.Name -contains 'id'
}
if(-not ($hasId -and $resp.id)){
  Write-Host "This endpoint is SYNC (no 'id' in response). Netlify will 504 on long runs. Deploy async /run first." -ForegroundColor Red
  exit 2
}

$jobId = $resp.id
Write-Host ("Job queued: id={0}" -f $jobId) -ForegroundColor DarkYellow

# poll
$deadline = (Get-Date).AddSeconds($MaxWaitSec)
do {
  Start-Sleep -Seconds $PollEverySec
  $s = Invoke-RestMethod -Uri "$Base/run/$jobId" -Method GET -TimeoutSec 30
  if($s.status -eq "done"){ $result = $s.result; break }
  if($s.status -eq "error"){ throw "Job error: $($s.error)" }
  Write-Host ("status={0}" -f $s.status) -NoNewline
  Write-Host " ."
} while((Get-Date) -lt $deadline)

if(-not $result){ throw "Polling timed out after ${MaxWaitSec}s." }

# show result
$result | ConvertTo-Json -Depth 8 | Out-Host

# download first artifacts
function GetFile($path){
  $url = UrlJoin $Base ("file?path=" + [uri]::EscapeDataString($path))
  $name = Split-Path -Leaf $path
  Write-Host "GET $url -> $name" -ForegroundColor Cyan
  Invoke-WebRequest -Uri $url -OutFile $name | Out-Null
}
if($result.overlays -and $result.overlays.Count -gt 0){ GetFile $result.overlays[0] }
if($result.text_files -and $result.text_files.Count -gt 0){ GetFile $result.text_files[0] }
if($result.jsonls -and $result.jsonls.Count -gt 0){ GetFile $result.jsonls[0] }

Write-Host "`nDone." -ForegroundColor Green
