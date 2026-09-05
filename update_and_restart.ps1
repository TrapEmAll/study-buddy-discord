[CmdletBinding()]
param(
    [string]$Repository = "TrapEmAll/study-buddy-discord",
    [string]$Branch = "main",
    [string]$InstallPath = $PSScriptRoot,
    [int]$PollSeconds = 300,
    [switch]$Once
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Get-RemoteCommit {
    $uri = "https://api.github.com/repos/$Repository/commits/$Branch"
    return (Invoke-RestMethod -Uri $uri -Headers @{ "User-Agent" = "study-buddy-updater" }).sha
}

function Stop-Bot {
    param([System.Diagnostics.Process]$BotProcess)
    if ($null -ne $BotProcess -and -not $BotProcess.HasExited) {
        Write-Host "Stopping bot process $($BotProcess.Id)..."
        $BotProcess.CloseMainWindow() | Out-Null
        if (-not $BotProcess.WaitForExit(30000)) {
            Stop-Process -Id $BotProcess.Id -Force
        }
    }
}

function Update-Checkout {
    param([string]$Commit)

    $tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("study-buddy-update-" + [guid]::NewGuid())
    $zipPath = Join-Path $tempRoot "source.zip"
    $extractPath = Join-Path $tempRoot "extracted"
    $archiveUri = "https://github.com/$Repository/archive/refs/heads/$Branch.zip"

    New-Item -ItemType Directory -Path $tempRoot, $extractPath -Force | Out-Null
    try {
        Write-Host "Downloading $Repository@$Branch..."
        Invoke-WebRequest -Uri $archiveUri -OutFile $zipPath
        Expand-Archive -Path $zipPath -DestinationPath $extractPath -Force
        $source = Get-ChildItem -Path $extractPath -Directory | Select-Object -First 1
        if ($null -eq $source) { throw "GitHub archive did not contain a source directory." }

        # Copy application files only. These exclusions are the data-safety boundary:
        # runtime secrets, databases, user data, logs, and environments stay in place.
        $excludedDirectories = @(".git", ".github", ".venv", "data", "logs", "__pycache__")
        $excludedFiles = @(".env", "*.sqlite3", "*.db", ".study-buddy-version")
        $arguments = @($source.FullName, $InstallPath, "/E", "/R:2", "/W:2", "/NFL", "/NDL", "/NJH", "/NJS")
        foreach ($directory in $excludedDirectories) { $arguments += @("/XD", (Join-Path $source.FullName $directory)) }
        # /XF receives file names/patterns, not full paths. Full paths with
        # wildcards are rejected by Robocopy as invalid parameters.
        foreach ($file in $excludedFiles) { $arguments += @("/XF", $file) }
        # Invoke the executable directly so PowerShell passes paths containing
        # spaces as single arguments (Start-Process re-tokenizes ArgumentList).
        & robocopy.exe @arguments
        if ($LASTEXITCODE -gt 7) { throw "File extraction failed with robocopy exit code $LASTEXITCODE." }

        Set-Content -Path (Join-Path $InstallPath ".study-buddy-version") -Value $Commit -NoNewline
        Write-Host "Updated to $($Commit.Substring(0, 12))."
    }
    finally {
        Remove-Item -Path $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}

function Start-Bot {
    return Start-Process -FilePath "python" -ArgumentList @("-m", "study_buddy") -WorkingDirectory $InstallPath -PassThru -NoNewWindow
}

$botProcess = $null
try {
    while ($true) {
        $remoteCommit = Get-RemoteCommit
        $versionFile = Join-Path $InstallPath ".study-buddy-version"
        $localCommit = if (Test-Path $versionFile) { (Get-Content $versionFile -Raw).Trim() } else { "" }

        if ($remoteCommit -ne $localCommit) {
            Stop-Bot $botProcess
            Update-Checkout $remoteCommit
            $botProcess = Start-Bot
            Write-Host "Started bot process $($botProcess.Id)."
        } elseif ($null -eq $botProcess -or $botProcess.HasExited) {
            $botProcess = Start-Bot
            Write-Host "Started bot process $($botProcess.Id)."
        }

        if ($Once) { break }
        Start-Sleep -Seconds $PollSeconds
    }
}
finally {
    Stop-Bot $botProcess
}
