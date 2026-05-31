$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:PYTHONPATH = "$Root;$env:PYTHONPATH"

Write-Host "[pipeline] Processing CCTV clips..."
python -m pipeline.detect --data-dir data --clips-dir data/clips --output data/output/events.jsonl @args

Write-Host "[pipeline] Feeding API (if running)..."
if (Test-Path "data/output/events.jsonl") {
  python scripts/feed_events.py --file data/output/events.jsonl
}
Write-Host "[pipeline] Done. Events at data/output/events.jsonl"
