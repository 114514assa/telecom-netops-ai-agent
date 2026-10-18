# V3.1.1 isolated Windows environment bootstrap (PowerShell)
# dot-source: . .\RUN_V3_1_ENV.ps1 [-VenvPython 'C:\...\.venv\Scripts\python.exe']
param([string]$VenvPython = '')
$Project = $PSScriptRoot
$Candidates = @()
if ($VenvPython) { $Candidates += $VenvPython }
$Candidates += (Join-Path $Project '.venv\Scripts\python.exe')
$Candidates += (Join-Path (Split-Path $Project -Parent) 'telecom-netops-ai-agent-hardened\.venv\Scripts\python.exe')

$Py = $Candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1
if (-not $Py) { throw 'Cannot locate Python. Use: . .\RUN_V3_1_ENV.ps1 -VenvPython "FULL_PATH_TO_EXISTING_PYTHON_EXE"' }
Set-Location -LiteralPath $Project
$env:APP_ENV = 'development'
$env:RUNTIME_DIR = 'runtime_v3_1_1'
$env:CHECKPOINT_DB = 'runtime_v3_1_1/checkpoints.sqlite3'
$env:INVENTORY_DB = 'runtime_v3_1_1/inventory.sqlite3'
$env:REPORT_DIR = 'runtime_v3_1_1/reports'
$env:AUDIT_LOG = 'runtime_v3_1_1/audit.jsonl'
$env:VECTOR_INDEX_PATH = 'runtime_v3_1_1/vector_index/knowledge.faiss'
$env:VECTOR_METADATA_PATH = 'runtime_v3_1_1/vector_index/metadata.json'
$env:RAG_KNOWLEDGE_DIR = 'knowledge/sanitized'
$env:LLM_BACKEND = 'local_hf'
$env:LOCAL_LLM_QUANTIZATION = 'int4'
$env:DEMO_AUTH_ENABLED = 'false'
$env:REQUIRE_APPROVAL = 'true'
$env:LLM_ENABLED = 'false'
$env:RAG_ENABLED = 'false'
Write-Host "V3.1.1 PROJECT: $Project"
Write-Host "V3.1.1 PYTHON:  $Py"
Write-Host "V3.1.1 OUTPUT:  $env:RUNTIME_DIR"
& $Py --version
