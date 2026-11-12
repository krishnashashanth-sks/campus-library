[CmdletBinding()]
param(
    [string]$Version = "",
    [string]$PythonExe = "",
    [string]$PfxPath = "",
    [string]$PfxPassword = "",
    [string]$CertThumbprint = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [switch]$SkipTimestamp,
    [switch]$RequireSigned,
    [switch]$SkipInstaller
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepoRoot

$TempPfxPath = $null
$PrevBuildVersionEnv = [Environment]::GetEnvironmentVariable("LIBRARY_BUILD_VERSION", "Process")

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

    function Resolve-SignTool {
        $fromPath = Get-Command signtool.exe -ErrorAction SilentlyContinue
        if ($fromPath) {
            return $fromPath.Source
        }

        $kitRoots = @(
            "${env:ProgramFiles(x86)}\Windows Kits\10\bin",
            "$env:ProgramFiles\Windows Kits\10\bin",
            "${env:ProgramFiles(x86)}\Windows Kits\8.1\bin"
        )
        foreach ($root in $kitRoots) {
            if (-not ($root -and (Test-Path -LiteralPath $root))) {
                continue
            }
            $found = Get-ChildItem -Path $root -Recurse -Filter "signtool.exe" -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -match '\\(x64|amd64|x86)\\signtool\.exe$' } |
                Sort-Object { $_.FullName -match '\\(x64|amd64)\\' } -Descending |
                Select-Object -First 1
            if ($found) {
                return $found.FullName
            }
        }
        return $null
    }

    function Invoke-SignFile {
        param(
            [string]$SignToolPath,
            [string]$TargetPath,
            [string]$ResolvedPfx,
            [string]$ResolvedPass,
            [string]$ResolvedThumbprint,
            [string]$TsUrl,
            [switch]$NoTimestamp
        )

        $baseArgs = @(
            "sign",
            "/fd", "sha256",
            "/d", "Library Management System",
            "/du", "https://github.com/krishnashashanth-sks/campus-library"
        )
        if ($ResolvedThumbprint) {
            $baseArgs += @("/sha1", $ResolvedThumbprint)
        }
        elseif ($ResolvedPfx) {
            $baseArgs += @("/f", $ResolvedPfx)
            if ($ResolvedPass) {
                $baseArgs += @("/p", $ResolvedPass)
            }
        }

        $timestampCandidates = if ($NoTimestamp) { @("") } else { @($TsUrl, "http://timestamp.sectigo.com") | Select-Object -Unique }
        $signed = $false
        foreach ($ts in $timestampCandidates) {
            $argsToRun = @($baseArgs)
            if ($ts) {
                $argsToRun += @("/tr", $ts, "/td", "sha256")
            }
            $argsToRun += $TargetPath
            & $SignToolPath @argsToRun
            if ($LASTEXITCODE -eq 0) {
                $signed = $true
                break
            }
            Write-Warning "signtool failed with timestamp '$ts' on $TargetPath; trying fallback..."
        }
        if (-not $signed -and -not $NoTimestamp) {
            Write-Warning "Timestamp servers unreachable; retrying Authenticode signature without timestamp..."
            $argsNoTs = @($baseArgs) + @($TargetPath)
            & $SignToolPath @argsNoTs
            if ($LASTEXITCODE -eq 0) {
                $signed = $true
            }
        }
        if (-not $signed) {
            throw "Authenticode code signing failed for $TargetPath."
        }
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
        Write-Warning "Build version ($Version) differs from app_version.py ($SourceVersion). Stamping PE VersionInfo, library_version.txt, and installer metadata with $Version."
    }

    # Resolve optional code-signing credentials from args or environment
    if (-not $PfxPath) {
        $PfxPath = [string]([Environment]::GetEnvironmentVariable("SIGNING_PFX_PATH"))
    }
    if (-not $PfxPassword) {
        $PfxPassword = [string]([Environment]::GetEnvironmentVariable("SIGNING_PFX_PASSWORD"))
    }
    if (-not $CertThumbprint) {
        $CertThumbprint = [string]([Environment]::GetEnvironmentVariable("SIGNING_CERT_THUMBPRINT"))
    }
    $PfxBase64 = [string]([Environment]::GetEnvironmentVariable("SIGNING_PFX_BASE64"))
    if (-not $PfxPath -and $PfxBase64) {
        $TempPfxPath = Join-Path ([System.IO.Path]::GetTempPath()) ("library_sign_" + [System.Guid]::NewGuid().ToString("N") + ".pfx")
        [System.IO.File]::WriteAllBytes($TempPfxPath, [System.Convert]::FromBase64String($PfxBase64.Trim()))
        $PfxPath = $TempPfxPath
    }
    if ($PfxPath) {
        if (-not (Test-Path -LiteralPath $PfxPath)) {
            throw "Specified PFX certificate file not found: $PfxPath"
        }
        $PfxPath = (Resolve-Path -LiteralPath $PfxPath).Path
    }

    $SigningRequested = [bool]($PfxPath -or $CertThumbprint)
    $SignTool = if ($SigningRequested -or $RequireSigned) { Resolve-SignTool } else { $null }
    if ($SigningRequested -and -not $SignTool) {
        throw "Code signing credentials were provided, but signtool.exe was not found. Install the Windows 10/11 SDK."
    }
    if ($RequireSigned -and -not $SigningRequested) {
        throw "-RequireSigned was specified, but no -PfxPath/-CertThumbprint or SIGNING_* environment variable was provided."
    }

    [Environment]::SetEnvironmentVariable("LIBRARY_BUILD_VERSION", $Version, "Process")

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
    $ExePath = Join-Path $DistMain "Library.exe"
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

    if ($SigningRequested) {
        Write-Host "Signing Library.exe with Authenticode ($SignTool)..."
        Invoke-SignFile `
            -SignToolPath $SignTool `
            -TargetPath $ExePath `
            -ResolvedPfx $PfxPath `
            -ResolvedPass $PfxPassword `
            -ResolvedThumbprint $CertThumbprint `
            -TsUrl $TimestampUrl `
            -NoTimestamp:$SkipTimestamp
    }
    else {
        Write-Warning "Building unsigned binaries (no signing certificate configured). Windows SmartScreen may show 'Unknown publisher' until signed with a trusted Code Signing certificate (see scripts/setup_code_signing.ps1 or DEPLOYMENT.md)."
    }

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

        $IsccArgs = @("/DAppVersion=$Version")
        if ($SigningRequested) {
            $signCmdParts = @("`"$SignTool`" sign /fd sha256 /d `"Library Management System`" /du `"https://github.com/krishnashashanth-sks/campus-library`"")
            if ($CertThumbprint) {
                $signCmdParts += "/sha1 `"$CertThumbprint`""
            }
            elseif ($PfxPath) {
                $signCmdParts += "/f `"$PfxPath`""
                if ($PfxPassword) {
                    $signCmdParts += "/p `"$PfxPassword`""
                }
            }
            if (-not $SkipTimestamp -and $TimestampUrl) {
                $signCmdParts += "/tr `"$TimestampUrl`" /td sha256"
            }
            $signCmdParts += "`$f"
            $signToolValue = $signCmdParts -join " "
            $IsccArgs += "/DUseSignTool=1"
            $IsccArgs += "/SLibrarySignTool=$signToolValue"
        }
        $IsccArgs += "installer_scipt.iss"

        Write-Host "Compiling Windows installer with Inno Setup ($Iscc)..."
        & $Iscc @IsccArgs
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

    Write-Host ""
    Write-Host "Binary PE & Signature Verification:"
    $verifyList = @($ExePath)
    if (-not $SkipInstaller) {
        $verifyList += (Join-Path $RepoRoot "OutputInstaller\LibraryInstaller.exe")
    }
    foreach ($bin in $verifyList) {
        $vi = (Get-Item -LiteralPath $bin).VersionInfo
        $sig = Get-AuthenticodeSignature -FilePath $bin
        Write-Host ("  {0} -> Company='{1}', Version='{2}', Signature={3}" -f `
            [System.IO.Path]::GetFileName($bin), $vi.CompanyName, $vi.FileVersion, $sig.Status)
    }
}
finally {
    [Environment]::SetEnvironmentVariable("LIBRARY_BUILD_VERSION", $PrevBuildVersionEnv, "Process")
    if ($TempPfxPath -and (Test-Path -LiteralPath $TempPfxPath)) {
        Remove-Item -LiteralPath $TempPfxPath -Force -ErrorAction SilentlyContinue
    }
    Pop-Location
}
