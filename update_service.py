import hashlib
import json
import os
import re
import shutil
import socket
import ssl
import stat
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from app_version import (
    INSTALLED_VERSION_FILE,
    get_app_version,
    normalize_version,
)


REPOSITORY = "krishnashashanth-sks/campus-library"
LATEST_RELEASE_URL = (
    f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
)
RELEASE_HISTORY_URL = (
    f"https://api.github.com/repos/{REPOSITORY}/releases"
)
RELEASES_PAGE_URL = f"https://github.com/{REPOSITORY}/releases"
PACKAGE_NAME = "Library-Windows.zip"
MAX_PACKAGE_BYTES = 1_000_000_000
MAX_EXTRACTED_BYTES = 2_000_000_000


class _UpdateSignals(QObject):
    finished = pyqtSignal(object)
    progress = pyqtSignal(int)


def _version_parts(version):
    match = re.fullmatch(
        r"v?(\d+(?:\.\d+){1,3})",
        str(version).strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"Unsupported release version: {version}")
    parts = tuple(int(part) for part in match.group(1).split("."))
    return parts + (0,) * (4 - len(parts))


def is_newer_version(candidate, current=None):
    current = current or get_app_version()
    return _version_parts(candidate) > _version_parts(current)


def is_packaged_application():
    return sys.platform == "win32" and bool(
        getattr(sys, "frozen", False)
    )


def _request(url, headers=None, timeout=20):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Campus-Library-Updater",
            **(headers or {}),
        },
    )
    return urllib.request.urlopen(request, timeout=timeout)


def format_update_error(error):
    if isinstance(error, urllib.error.HTTPError):
        if error.code == 403:
            return (
                "GitHub temporarily refused the request. Check the network "
                "connection and try again later."
            )
        if error.code == 404:
            return (
                "GitHub could not find the requested release. Confirm that "
                "the release is published and try again."
            )
        if error.code == 429:
            return (
                "GitHub is receiving too many requests. Wait a few minutes "
                "and try again."
            )
        if error.code >= 500:
            return (
                f"GitHub is temporarily unavailable (HTTP {error.code}). "
                "Try again later."
            )
        return f"GitHub rejected the request (HTTP {error.code})."

    reason = (
        error.reason
        if isinstance(error, urllib.error.URLError)
        else error
    )
    reason_text = str(reason).casefold()
    reason_code = getattr(reason, "errno", None)
    if (
        isinstance(reason, socket.gaierror)
        or reason_code in {
            11001, 11002, 11003, 11004,
            getattr(socket, "EAI_AGAIN", object()),
            getattr(socket, "EAI_NONAME", object()),
        }
        or "getaddrinfo failed" in reason_text
        or "name resolution" in reason_text
    ):
        return (
            "Cannot reach GitHub because Windows could not resolve its "
            "server address. Check the internet connection, DNS, proxy, "
            "or firewall, then retry."
        )
    if isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in reason_text:
        return "The connection to GitHub timed out. Check the internet connection and retry."
    if isinstance(reason, ssl.SSLError):
        return (
            "A secure connection to GitHub could not be established. "
            "Check the system date, network security settings, and retry."
        )
    if isinstance(reason, ConnectionRefusedError):
        return (
            "The connection to GitHub was refused. Check proxy or firewall "
            "settings, then retry."
        )
    if isinstance(error, json.JSONDecodeError):
        return (
            "GitHub returned an unreadable response. Retry later; if this "
            "continues, check GitHub's service status."
        )
    if isinstance(error, zipfile.BadZipFile):
        return "The downloaded release package is not a valid ZIP file."
    if isinstance(error, PermissionError):
        return (
            "Windows denied access to the application files. Install the "
            "app in a writable user folder and retry."
        )
    if isinstance(error, OSError):
        return f"Windows could not complete the update operation ({error})."
    return f"The update operation failed: {error}"


def _read_release_package(release):
    version = release.get("tag_name", "")
    asset = next(
        (
            item
            for item in release.get("assets", [])
            if item.get("name") == PACKAGE_NAME
        ),
        None,
    )
    if not asset:
        raise RuntimeError(f"Release {version} does not include {PACKAGE_NAME}.")

    download_url = asset.get("browser_download_url", "")
    expected_prefix = (
        f"https://github.com/{REPOSITORY}/releases/download/"
    )
    if not download_url.startswith(expected_prefix):
        raise RuntimeError("The release package URL is not trusted.")
    asset_size = int(asset.get("size", 0))
    if asset_size <= 0 or asset_size > MAX_PACKAGE_BYTES:
        raise RuntimeError("The release package exceeds the size limit.")
    digest = asset.get("digest")
    if not isinstance(digest, str) or not re.fullmatch(
        r"sha256:[0-9a-fA-F]{64}",
        digest,
    ):
        raise RuntimeError(
            "The release package has no GitHub SHA-256 digest and cannot "
            "be verified."
        )
    return {
        "download_url": download_url,
        "digest": digest,
        "size": asset_size,
    }


def _fetch_release():
    try:
        with _request(
            LATEST_RELEASE_URL,
            {"Accept": "application/vnd.github+json"},
        ) as response:
            metadata = response.read(2_000_001)
            if len(metadata) > 2_000_000:
                raise RuntimeError(
                    "The GitHub release metadata is too large."
                )
            release = json.loads(metadata.decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {
                "release_not_published": True,
                "release_page_url": RELEASES_PAGE_URL,
            }
        raise

    version = release.get("tag_name", "")
    current_version = get_app_version()
    newer = is_newer_version(version, current_version)
    if not newer:
        return {
            "available": False,
            "current_version": current_version,
            "latest_version": version,
        }

    return {
        "available": True,
        "current_version": current_version,
        "latest_version": version,
        "release_notes": str(release.get("body") or "")[:5000],
        "release_url": release.get("html_url", ""),
        **_read_release_package(release),
    }


def _fetch_release_history():
    current_version = get_app_version()
    releases = []
    for page in range(1, 11):
        url = f"{RELEASE_HISTORY_URL}?per_page=100&page={page}"
        with _request(
            url,
            {"Accept": "application/vnd.github+json"},
        ) as response:
            metadata = response.read(5_000_001)
            if len(metadata) > 5_000_000:
                raise RuntimeError("GitHub release history response is too large.")
            page_releases = json.loads(metadata.decode("utf-8"))
        if not isinstance(page_releases, list):
            raise RuntimeError("GitHub returned an invalid release history.")
        if not page_releases:
            break

        for release in page_releases:
            if release.get("draft") or release.get("prerelease"):
                continue
            tag = str(release.get("tag_name") or "")
            try:
                version = normalize_version(tag)
            except ValueError:
                continue
            try:
                package = _read_release_package(release)
                installable = True
                reason = ""
            except (RuntimeError, TypeError, ValueError) as error:
                package = {}
                installable = False
                reason = str(error)
            releases.append({
                "version": version,
                "tag_name": tag,
                "published_at": str(
                    release.get("published_at")
                    or release.get("created_at")
                    or ""
                )[:10],
                "release_notes": str(release.get("body") or "")[:5000],
                "release_url": str(release.get("html_url") or ""),
                "current": version == current_version,
                "installable": installable,
                "reason": reason,
                **package,
            })
        if len(page_releases) < 100:
            break
    return {
        "current_version": current_version,
        "releases": releases,
    }


class UpdateCheckWorker(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = _UpdateSignals()

    def run(self):
        try:
            self.signals.finished.emit(_fetch_release())
        except Exception as error:
            self.signals.finished.emit({
                "error": format_update_error(error),
            })


class VersionHistoryWorker(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = _UpdateSignals()

    def run(self):
        try:
            self.signals.finished.emit(_fetch_release_history())
        except Exception as error:
            self.signals.finished.emit({
                "error": format_update_error(error),
            })


def _safe_extract_package(archive_path, destination):
    destination = Path(destination).resolve()
    extracted_bytes = 0

    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if os.path.commonpath(
                (str(destination), str(target))
            ) != str(destination):
                raise RuntimeError(
                    "The update archive contains an unsafe file path."
                )

            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise RuntimeError(
                    "The update archive contains a symbolic link."
                )

            extracted_bytes += member.file_size
            if extracted_bytes > MAX_EXTRACTED_BYTES:
                raise RuntimeError(
                    "The extracted update exceeds the size limit."
                )

        archive.extractall(destination)

    if not (destination / "Library.exe").is_file():
        raise RuntimeError(
            f"The update package must contain Library.exe at its root."
        )


def _download_and_stage(release, progress_callback):
    temporary_root = Path(
        tempfile.mkdtemp(prefix="library-update-")
    )
    archive_path = temporary_root / PACKAGE_NAME
    stage_path = temporary_root / "application"
    digest = hashlib.sha256()
    downloaded = 0

    try:
        with _request(
            release["download_url"],
            timeout=60,
        ) as response, archive_path.open("wb") as package_file:
            final_url = urllib.parse.urlparse(response.geturl())
            valid_host = (
                final_url.hostname == "github.com"
                or final_url.hostname == "release-assets.githubusercontent.com"
                or final_url.hostname == "objects.githubusercontent.com"
                or bool(
                    final_url.hostname
                    and final_url.hostname.endswith(".githubusercontent.com")
                )
            )
            if final_url.scheme != "https" or not valid_host:
                raise RuntimeError(
                    "The release download redirected to an untrusted host."
                )

            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_PACKAGE_BYTES:
                raise RuntimeError(
                    "The release package exceeds the size limit."
                )

            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > MAX_PACKAGE_BYTES:
                    raise RuntimeError(
                        "The release package exceeds the size limit."
                    )
                digest.update(chunk)
                package_file.write(chunk)
                if content_length:
                    progress_callback(
                        min(100, downloaded * 100 // int(content_length))
                    )

        expected_digest = release.get("digest")
        if expected_digest:
            if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", expected_digest):
                raise RuntimeError(
                    "The release has an invalid SHA-256 digest."
                )
            if digest.hexdigest().casefold() != expected_digest[7:].casefold():
                raise RuntimeError(
                    "The downloaded package failed its SHA-256 check."
                )

        stage_path.mkdir()
        _safe_extract_package(archive_path, stage_path)
        installed_version = normalize_version(
            release["latest_version"]
        )
        (stage_path / INSTALLED_VERSION_FILE).write_text(
            installed_version,
            encoding="ascii",
        )
        return str(stage_path)
    except Exception:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise


class UpdateDownloadWorker(QRunnable):
    def __init__(self, release):
        super().__init__()
        self.release = release
        self.signals = _UpdateSignals()

    def run(self):
        try:
            staged_path = _download_and_stage(
                self.release,
                self.signals.progress.emit,
            )
            self.signals.finished.emit(
                {"staged_path": staged_path}
            )
        except Exception as error:
            self.signals.finished.emit({
                "error": format_update_error(error),
            })


_UPDATE_HELPER = r"""
param(
    [int]$TargetProcessId,
    [string]$InstallDirectory,
    [string]$StageDirectory,
    [string]$ExecutableName,
    [string]$HelperPath
)
$ErrorActionPreference = 'Stop'
$install = [IO.Path]::GetFullPath($InstallDirectory)
$stage = [IO.Path]::GetFullPath($StageDirectory)
$parent = [IO.Path]::GetDirectoryName($install)
$leaf = [IO.Path]::GetFileName($install)
$nonce = [Guid]::NewGuid().ToString('N')
$newDirectory = Join-Path $parent ".$leaf-update-$nonce"
$backupDirectory = Join-Path $parent ".$leaf-backup-$nonce"
$logPath = Join-Path $env:TEMP 'LibraryUpdate.log'
$updateApplied = $false

try {
    while (Get-Process -Id $TargetProcessId -ErrorAction SilentlyContinue) {
        Start-Sleep -Milliseconds 400
    }

    New-Item -ItemType Directory -Path $newDirectory | Out-Null
    Copy-Item -Path (Join-Path $stage '*') -Destination $newDirectory -Recurse -Force
    if (-not (Test-Path -LiteralPath (Join-Path $newDirectory $ExecutableName))) {
        throw 'The staged application executable is missing.'
    }

    Move-Item -LiteralPath $install -Destination $backupDirectory
    try {
        Move-Item -LiteralPath $newDirectory -Destination $install
    }
    catch {
        Move-Item -LiteralPath $backupDirectory -Destination $install
        throw
    }

    Start-Process -FilePath (Join-Path $install $ExecutableName)
    $updateApplied = $true
    try {
        Remove-Item -LiteralPath $backupDirectory -Recurse -Force
    }
    catch {
        Add-Content -LiteralPath $logPath -Value ("Old version cleanup warning: " + $_.Exception.Message)
    }
    Remove-Item -LiteralPath (Split-Path $stage -Parent) -Recurse -Force
}
catch {
    Add-Content -LiteralPath $logPath -Value ("Update failed: " + $_.Exception.Message)
    if (-not $updateApplied) {
        if (Test-Path -LiteralPath $backupDirectory) {
            if (Test-Path -LiteralPath $install) {
                $failedDirectory = Join-Path $parent ".$leaf-failed-$nonce"
                Move-Item -LiteralPath $install -Destination $failedDirectory
                Move-Item -LiteralPath $backupDirectory -Destination $install
                Remove-Item -LiteralPath $failedDirectory -Recurse -Force
            }
            else {
                Move-Item -LiteralPath $backupDirectory -Destination $install
            }
        }
        $oldExecutable = Join-Path $install $ExecutableName
        if (Test-Path -LiteralPath $oldExecutable) {
            Start-Process -FilePath $oldExecutable
        }
    }
    Remove-Item -LiteralPath (Split-Path $stage -Parent) -Recurse -Force -ErrorAction SilentlyContinue
}
finally {
    Remove-Item -LiteralPath $HelperPath -Force -ErrorAction SilentlyContinue
}
"""


def can_replace_application(install_directory):
    parent = Path(install_directory).resolve().parent
    try:
        descriptor, probe_path = tempfile.mkstemp(
            prefix=".library-update-check-",
            dir=parent,
        )
        os.close(descriptor)
        os.unlink(probe_path)
        return True
    except OSError:
        return False


def schedule_application_update(stage_path):
    if not is_packaged_application():
        raise RuntimeError(
            "Automatic replacement is available only in the packaged "
            "Windows application."
        )

    install_directory = Path(sys.executable).resolve().parent
    if not can_replace_application(install_directory):
        raise PermissionError(
            "The application folder cannot be updated with the current "
            "Windows permissions."
        )

    helper_descriptor, helper_path = tempfile.mkstemp(
        prefix="library-update-",
        suffix=".ps1",
    )
    try:
        with os.fdopen(helper_descriptor, "w", encoding="utf-8") as helper:
            helper.write(_UPDATE_HELPER)

        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        powershell = os.path.join(
            system_root,
            "System32",
            "WindowsPowerShell",
            "v1.0",
            "powershell.exe",
        )
        if not os.path.isfile(powershell):
            raise RuntimeError("Windows PowerShell could not be found.")

        subprocess.Popen(
            [
                powershell,
                "-NoProfile",
                "-NonInteractive",
                "-WindowStyle",
                "Hidden",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                helper_path,
                str(os.getpid()),
                str(install_directory),
                str(Path(stage_path).resolve()),
                Path(sys.executable).name,
                helper_path,
            ],
            close_fds=True,
            startupinfo=_hidden_process_startup_info(),
            creationflags=subprocess.CREATE_NO_WINDOW,
            cwd=tempfile.gettempdir(),
        )
    except Exception:
        try:
            os.unlink(helper_path)
        except OSError:
            pass
        raise


def _hidden_process_startup_info():
    startup_info = subprocess.STARTUPINFO()
    startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup_info.wShowWindow = subprocess.SW_HIDE
    return startup_info
