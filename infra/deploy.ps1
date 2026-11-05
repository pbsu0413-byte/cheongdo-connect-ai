<#
  청도 돌봄 도우미를 Azure App Service(Linux, Python 3.12)에 반복 가능하게 배포한다.
  여러 번 실행해도 같은 결과가 되도록, 이미 있는 리소스는 재사용하고 코드만 다시 배포한다.

  사전 조건: Azure CLI 설치, `az login` 완료.
  비밀: 환경변수 COPILOT_GITHUB_TOKEN이 설정되어 있으면 앱 설정으로 주입한다(값은 출력하지 않는다).
        SIGNING_KEY는 앱에 아직 없을 때만 임의로 생성해 넣는다.
#>
param(
  [string]$Name = "cheongdo-care-pbs",
  [string]$ResourceGroup = "rg-cheongdo-care",
  [string]$Plan = "plan-cheongdo-care",
  [string]$Location = "japaneast",
  [string]$Sku = "B1"
)

$ErrorActionPreference = "Stop"
$az = (Get-Command az -ErrorAction SilentlyContinue).Source
if (-not $az) { $az = "C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd" }
function Az { & $az @args; if ($LASTEXITCODE -ne 0) { throw "az $($args -join ' ') 실패" } }

$root = Split-Path $PSScriptRoot -Parent
$stage = Join-Path ([IO.Path]::GetTempPath()) "care-deploy"
$zip = Join-Path ([IO.Path]::GetTempPath()) "care-deploy.zip"

# 배포 패키지: 실행에 필요한 파일만 담는다(.env, 테스트, 문서는 제외).
Remove-Item $stage, $zip -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory $stage | Out-Null
Copy-Item (Join-Path $root "app") (Join-Path $stage "app") -Recurse
Copy-Item (Join-Path $root "data") (Join-Path $stage "data") -Recurse
Copy-Item (Join-Path $root "requirements.txt") $stage
Get-ChildItem $stage -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
# Windows PowerShell 5.1의 Compress-Archive는 경로 구분자를 역슬래시로 저장해 Linux에서 파일이 깨진다. 슬래시로 직접 압축한다.
Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::Open($zip, [IO.Compression.ZipArchiveMode]::Create)
try {
  Get-ChildItem $stage -Recurse -File | ForEach-Object {
    $entryName = $_.FullName.Substring($stage.Length + 1).Replace('\', '/')
    [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, $_.FullName, $entryName)
  }
} finally { $archive.Dispose() }

Az group create --name $ResourceGroup --location $Location --output none
Az appservice plan create --name $Plan --resource-group $ResourceGroup --location $Location --sku $Sku --is-linux --output none

$exists = & $az webapp show --name $Name --resource-group $ResourceGroup --query name -o tsv 2>$null
if (-not $exists) {
  Az webapp create --name $Name --resource-group $ResourceGroup --plan $Plan --runtime "PYTHON:3.12" --output none
}

# 앱 설정(환경 변수). Copilot 런타임은 첫 사용 때 내려받으므로 쓰기 가능한 /home 아래를 캐시 경로로 쓴다.
$settings = @("WEBSITES_PORT=8000", "COPILOT_CLI_EXTRACT_DIR=/home/copilot-cli", "SCM_DO_BUILD_DURING_DEPLOYMENT=true")
$hasKey = & $az webapp config appsettings list --name $Name --resource-group $ResourceGroup --query "[?name=='SIGNING_KEY'].name" -o tsv
if (-not $hasKey) {
  $bytes = New-Object byte[] 48
  [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
  $settings += "SIGNING_KEY=$([Convert]::ToBase64String($bytes))"
}
Az webapp config appsettings set --name $Name --resource-group $ResourceGroup --settings $settings --output none

if ($env:COPILOT_GITHUB_TOKEN) {
  $tmp = Join-Path ([IO.Path]::GetTempPath()) "care-token.json"
  try {
    @{ COPILOT_GITHUB_TOKEN = $env:COPILOT_GITHUB_TOKEN } | ConvertTo-Json -Compress | Set-Content $tmp -Encoding ascii
    Az webapp config appsettings set --name $Name --resource-group $ResourceGroup --settings "@$tmp" --output none
  } finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
} else {
  Write-Warning "COPILOT_GITHUB_TOKEN이 없어 AI 호출 대신 규칙 기반 대체 결과가 표시됩니다."
}

# 안정성과 보안: 항상 켜 두기, 헬스체크, HTTPS 강제, FTP 끄기, TLS 1.2 이상.
Az webapp config set --name $Name --resource-group $ResourceGroup `
  --startup-file "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000" `
  --always-on true --ftps-state Disabled --min-tls-version 1.2 `
  --generic-configurations "@$(Join-Path $PSScriptRoot 'site-config.json')" --output none
Az webapp update --name $Name --resource-group $ResourceGroup --https-only true --output none

# 시작 상태 추적은 끄고(오탐으로 10분을 기다릴 수 있음) 아래 헬스체크로 직접 확인한다.
Az webapp deploy --name $Name --resource-group $ResourceGroup --src-path $zip --type zip --track-status false --output none

$url = "https://$Name.azurewebsites.net"
for ($i = 0; $i -lt 12; $i++) {
  try {
    $r = Invoke-WebRequest "$url/api/health" -UseBasicParsing -TimeoutSec 30
    if ($r.StatusCode -eq 200) { Write-Output "배포 완료: $url (health 200)"; exit 0 }
  } catch { Start-Sleep 15 }
}
throw "헬스체크가 200을 반환하지 않았습니다: $url/api/health"
