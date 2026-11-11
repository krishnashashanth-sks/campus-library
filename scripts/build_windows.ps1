[CmdletBinding()]
param(
    [string]$Version = "",
    [string]$PythonExe = "",
    [switch]$SkipInstaller
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepoRoot

try {
    function Resolve-PythonExecutable {
        param([string]$Requested)

        if ($Requested) {
            if (-not (Test-Path -LiteralPath $Requested)) {
                throw "Specified Python executable not found: $Requested"
            }
            return (Resolve-Path -LiteralPath $Requested).Path
        }

        $candidates = @()
        $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
        $pathPython = Get-Command python -ErrorAction SilentlyContinue
        if ($pathPython) { $candidates += $pathPython.Source }
        if (Test-Path -LiteralPath $venvPython) { $candidates += $venvPython }

        foreach ($candidate in ($candidates | Select-Object -Unique)) {
            & $candidate -c "import PyInstaller, PyQt6" 2>$null
            if ($LASTEXITCODE -eq 0) {
                return $candidate
            }
        }

        throw "No Python environment with both PyInstaller and PyQt6 was found. Install dependencies with 'pip install -r requirements-dev.txt'."
    }

    function Resolve-InnoSetupCompiler {
        $fromPath = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($fromPath) {
            return $fromPath.Source
        }

        $knownPaths = @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
        )
        foreach ($candidate in $knownPaths) {
            if ($candidate -and (Test-Path -LiteralPath $candidate)) {
                return $candidate
            }
        }
        return $null
    }

    $Python = Resolve-PythonExecutable -Requested $PythonExe
    Write-Host "Using Python: $Python"

    if (-not $Version) {
        $Version = (& $Python -c "import app_version; print(app_version.APP_VERSION)").Trim()
        if ($LASTEXITCODE -ne 0 -or -not $Version) {
            throw "Could not determine application version from app_version.py."
        }
    }

    $Version = $Version.Trim()
    if ($Version -match '^[vV](.+)$') {
        $Version = $Matches[1]
    }
    if ($Version -notmatch '^\d+(?:\.\d+){1,3}$') {
        throw "Unsupported version '$Version'. Expected numeric format like 1.0, 2.0, or 2.1.0."
    }

    $SourceVersion = (& $Python -c "import app_version; print(app_version.APP_VERSION)").Trim()
    if ($SourceVersion -ne $Version) {
        Write-Warning "Build version ($Version) differs from app_version.py ($SourceVersion). Stamping library_version.txt and installer metadata with $Version."
    }

    Write-Host "Cleaning previous build artifacts..."
    $cleanTargets = @("build", "dist", "Library-Windows.zip", "SHA256SUMS.txt")
    if (-not $SkipInstaller) {
        $cleanTargets += "OutputInstaller"
    }
    foreach ($artifact in $cleanTargets) {
        $target = Join-Path $RepoRoot $artifact
        if (Test-Path -LiteralPath $target) {
            Remove-Item -LiteralPath $target -Recurse -Force
        }
    }

    Write-Host "Running PyInstaller (main.spec)..."
    & $Python -m PyInstaller --noconfirm --clean main.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller build failed with exit code $LASTEXITCODE."
    }

    $DistMain = Join-Path $RepoRoot "dist\main"
    $RequiredFiles = @(
        "Library.exe",
        "_internal\assets\library_icon.ico",
        "_internal\assets\library_icon.png",
        "_internal\barcode\fonts\DejaVuSansMono.ttf"
    )
    foreach ($rel in $RequiredFiles) {
        $fullPath = Join-Path $DistMain $rel
        if (-not (Test-Path -LiteralPath $fullPath)) {
            throw "Expected packaged file missing: $fullPath"
        }
    }

    $VersionFile = Join-Path $DistMain "library_version.txt"
    [System.IO.File]::WriteAllText($VersionFile, $Version, [System.Text.Encoding]::ASCII)
    Write-Host "Stamped $VersionFile with version $Version"

    $ZipPath = Join-Path $RepoRoot "Library-Windows.zip"
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::CreateFromDirectory(
        $DistMain,
        $ZipPath,
        [System.IO.Compression.CompressionLevel]::Optimal,
        $false
    )

    $ZipArchive = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $EntryNames = $ZipArchive.Entries | ForEach-Object { $_.FullName }
        if ($EntryNames -notcontains "Library.exe" -or $EntryNames -notcontains "library_version.txt") {
            throw "Library-Windows.zip verification failed: Library.exe and library_version.txt must reside at the ZIP root."
        }
    }
    finally {
        $ZipArchive.Dispose()
    }
    Write-Host "Created updater package: $ZipPath"

    $HashTargets = @()
    if (-not $SkipInstaller) {
        $Iscc = Resolve-InnoSetupCompiler
        if (-not $Iscc) {
            throw "Inno Setup compiler (ISCC.exe) not found. Install Inno Setup 6 or re-run with -SkipInstaller."
        }

        Write-Host "Compiling Windows installer with Inno Setup ($Iscc)..."
        & $Iscc "/DAppVersion=$Version" "installer_scipt.iss"
        if ($LASTEXITCODE -ne 0) {
            throw "Inno Setup compilation failed with exit code $LASTEXITCODE."
        }

        $InstallerPath = Join-Path $RepoRoot "OutputInstaller\LibraryInstaller.exe"
        if (-not (Test-Path -LiteralPath $InstallerPath)) {
            throw "Expected installer was not created: $InstallerPath"
        }
        Write-Host "Created Windows installer: $InstallerPath"
        $HashTargets += $InstallerPath
    }
    else {
        Write-Host "Skipping Inno Setup installer compilation (-SkipInstaller)."
    }

    $HashTargets += $ZipPath
    $ChecksumLines = foreach ($file in $HashTargets) {
        $hash = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
        $name = [System.IO.Path]::GetFileName($file)
        "$hash  $name"
    }
    $ChecksumsPath = Join-Path $RepoRoot "SHA256SUMS.txt"
    [System.IO.File]::WriteAllLines($ChecksumsPath, $ChecksumLines, [System.Text.UTF8Encoding]::new($false))
    Write-Host "Generated checksums: $ChecksumsPath"
    $ChecksumLines | ForEach-Object { Write-Host "  $_" }
}
finally {
    Pop-Location
}
