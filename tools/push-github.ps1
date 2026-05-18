# Sync the GitHub mirror.
#
# Workflow:
#   1. You commit + push to Codeberg (origin) as normal.
#   2. Run this script to update GitHub with the same code + stub README.
#
# It rebuilds the `github-mirror` branch from main + a single commit that
# swaps README.md for tools/README.github.md, then force-pushes that branch
# to GitHub as `main`.

$ErrorActionPreference = 'Stop'

# Sanity checks
$root = git rev-parse --show-toplevel
Set-Location $root

$current = git rev-parse --abbrev-ref HEAD
if ($current -ne 'main') {
    Write-Host "Switching to main (was on $current)"
    git checkout main
}

if (-not (Test-Path 'tools/README.github.md')) {
    Write-Error "tools/README.github.md not found"
    exit 1
}

# Recreate the mirror branch from current main
git fetch github
if (git show-ref --verify --quiet refs/heads/github-mirror) {
    git branch -D github-mirror | Out-Null
}
git checkout -b github-mirror main

# Override README.md with the stub and commit
Copy-Item tools/README.github.md README.md -Force
git add README.md
git commit -m "GitHub-only stub README" | Out-Null

# Push to GitHub's main
git push github github-mirror:main --force-with-lease

# Back to main, clean up
git checkout main
git branch -D github-mirror | Out-Null

Write-Host ""
Write-Host "GitHub mirror updated."
