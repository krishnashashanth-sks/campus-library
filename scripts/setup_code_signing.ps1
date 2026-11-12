<#
.SYNOPSIS
Creates, trusts, or verifies an institutional Authenticode Code Signing certificate
for Library Management System (Govt Polytechnic College Hyderabad).

.DESCRIPTION
- CreateCert: Generates a self-contained RSA-2048 Code Signing certificate in
  `certs/library_codesign.pfx` (private key, gitignored) and `certs/library_codesign.cer`
  (public certificate for campus lab PCs).
- TrustCert: Installs the public `.cer` into Windows `Root` and `TrustedPublisher`
  stores so campus PCs recognize the publisher and do not show "Unknown publisher".
- Verify: Prints PE VersionInfo and Authenticode signature status for `Library.exe`
  and `OutputInstaller/LibraryInstaller.exe`.

NOTE: Public internet downloads outside campus PCs require a publicly trusted Code
Signing certificate from a commercial CA (e.g., Azure Trusted Signing, SSL.com,
DigiCert, Sectigo) passed to `scripts/build_windows.ps1` or GitHub Release Secrets.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("CreateCert", "TrustCert", "Verify")]
    [string]$Action,

    [string]$SubjectName = "CN=Govt Polytechnic College Hyderabad, O=Govt Polytechnic College Hyderabad",
    [string]$OutDir = "certs",
    [string]$PfxPassword = "",
    [int]$ValidYears = 5,
    [string]$CertPath = "certs\library_codesign.cer",
    [ValidateSet("CurrentUser", "LocalMachine")]
    [string]$Scope = "CurrentUser"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $RepoRoot

try {
    switch ($Action) {
        "CreateCert" {
            if (-not $PfxPassword) {
                throw "Please supply -PfxPassword when creating a PFX certificate."
            }
            $targetDir = Join-Path $RepoRoot $OutDir
            if (-not (Test-Path -LiteralPath $targetDir)) {
                New-Item -ItemType Directory -Path $targetDir | Out-Null
            }
            $pfxOut = Join-Path $targetDir "library_codesign.pfx"
            $cerOut = Join-Path $targetDir "library_codesign.cer"

            $cert = New-SelfSignedCertificate `
                -Type CodeSigningCert `
                -Subject $SubjectName `
                -FriendlyName "Library Management System Code Signing" `
                -KeyAlgorithm RSA `
                -KeyLength 2048 `
                -HashAlgorithm SHA256 `
                -NotAfter (Get-Date).AddYears($ValidYears) `
                -CertStoreLocation "Cert:\CurrentUser\My"

            $secPass = ConvertTo-SecureString -String $PfxPassword -Force -AsPlainText
            Export-PfxCertificate -Cert $cert -FilePath $pfxOut -Password $secPass | Out-Null
            Export-Certificate -Cert $cert -FilePath $cerOut | Out-Null

            Write-Host "Created Code Signing certificate:"
            Write-Host "  Thumbprint : $($cert.Thumbprint)"
            Write-Host "  PFX (keep secret, gitignored): $pfxOut"
            Write-Host "  CER (distribute to campus PCs): $cerOut"
            Write-Host ""
            Write-Host "Next steps:"
            Write-Host "  1. Trust on this PC: .\scripts\setup_code_signing.ps1 -Action TrustCert -Scope CurrentUser"
            Write-Host "  2. Build signed app: .\scripts\build_windows.ps1 -PfxPath `"$pfxOut`" -PfxPassword `"***`""
        }

        "TrustCert" {
            $resolvedCer = if ([System.IO.Path]::IsPathRooted($CertPath)) {
                $CertPath
            }
            else {
                Join-Path $RepoRoot $CertPath
            }
            if (-not (Test-Path -LiteralPath $resolvedCer)) {
                throw "Public certificate file not found: $resolvedCer"
            }
            $storePrefix = "Cert:\$Scope"
            Import-Certificate -FilePath $resolvedCer -CertStoreLocation "$storePrefix\Root" | Out-Null
            Import-Certificate -FilePath $resolvedCer -CertStoreLocation "$storePrefix\TrustedPublisher" | Out-Null
            Write-Host "Trusted certificate '$resolvedCer' in $Scope\Root and $Scope\TrustedPublisher."
        }

        "Verify" {
            $targets = @(
                (Join-Path $RepoRoot "dist\main\Library.exe"),
                (Join-Path $RepoRoot "OutputInstaller\LibraryInstaller.exe")
            )
            foreach ($path in $targets) {
                if (-not (Test-Path -LiteralPath $path)) {
                    Write-Host "Missing: $path"
                    continue
                }
                $vi = (Get-Item -LiteralPath $path).VersionInfo
                $sig = Get-AuthenticodeSignature -FilePath $path
                Write-Host "File: $path"
                Write-Host "  ProductName : $($vi.ProductName)"
                Write-Host "  CompanyName : $($vi.CompanyName)"
                Write-Host "  FileVersion : $($vi.FileVersion)"
                Write-Host "  Sig Status  : $($sig.Status) ($($sig.StatusMessage))"
                if ($sig.SignerCertificate) {
                    Write-Host "  Signer      : $($sig.SignerCertificate.Subject)"
                }
            }
        }
    }
}
finally {
    Pop-Location
}

