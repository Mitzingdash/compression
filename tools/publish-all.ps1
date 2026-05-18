# Build cross-platform release artifacts for SmartCompress.
#
# Produces self-contained single-file builds for each supported RID and
# packages them under publish/artifacts/ ready to attach to a release.
#
#   publish/<rid>/             extracted contents (binary + config.json + LICENSE)
#   publish/artifacts/         one archive per platform

$ErrorActionPreference = 'Stop'

$root = git rev-parse --show-toplevel
Set-Location $root

# Version comes from config.json so artifact filenames track the bump.
$configJson = Get-Content SmartCompress.CLI/config.json -Raw | ConvertFrom-Json
$version = $configJson.version
Write-Host "Building SmartCompress v$version" -ForegroundColor Cyan

$rids = @('win-x64', 'linux-x64', 'osx-x64', 'osx-arm64')
$publishRoot  = Join-Path $root 'publish'
$artifactsDir = Join-Path $publishRoot 'artifacts'

if (Test-Path $publishRoot) { Remove-Item $publishRoot -Recurse -Force }
New-Item -ItemType Directory -Path $artifactsDir | Out-Null

# Force Windows-native tar (bsdtar). The GNU tar shipped with Git Bash mis-parses
# Windows paths like "C:\..." as remote `host:path` and fails the upload.
$tarExe = if ($env:OS -eq 'Windows_NT') {
    Join-Path $env:SystemRoot 'System32\tar.exe'
} else { 'tar' }

foreach ($rid in $rids) {
    $outDir = Join-Path $publishRoot $rid
    Write-Host "`n=== $rid ===" -ForegroundColor Cyan

    dotnet publish SmartCompress.CLI/SmartCompress.CLI.csproj `
        -c Release `
        -r $rid `
        --self-contained true `
        -p:PublishSingleFile=true `
        -p:EnableCompressionInSingleFile=true `
        -o $outDir
    if ($LASTEXITCODE -ne 0) { Write-Error "publish failed for $rid"; exit 1 }

    # Trim things users don't need.
    Get-ChildItem $outDir -Filter *.pdb | Remove-Item -Force
    Copy-Item (Join-Path $root 'LICENSE') $outDir

    # .zip for Windows, .tar.gz for Unix. tar preserves the directory layout cleanly;
    # +x bit is not preserved across Windows->Unix tar so the install docs tell
    # Linux/macOS users to `chmod +x SmartCompress` after extracting.
    $stem = "SmartCompress-v$version-$rid"
    if ($rid -eq 'win-x64') {
        $archive = Join-Path $artifactsDir "$stem.zip"
        Compress-Archive -Path (Join-Path $outDir '*') -DestinationPath $archive -Force
    } else {
        $archive = Join-Path $artifactsDir "$stem.tar.gz"
        & $tarExe -czf $archive -C $outDir .
        if ($LASTEXITCODE -ne 0) { Write-Error "tar failed for $rid"; exit 1 }
    }
    Write-Host "  -> $archive" -ForegroundColor Green
}

Write-Host "`nDone." -ForegroundColor Green
Get-ChildItem $artifactsDir |
    Sort-Object Name |
    Format-Table Name, @{Name='Size (MB)'; Expression={[math]::Round($_.Length / 1MB, 1)}}
