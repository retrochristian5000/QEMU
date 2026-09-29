#requires -Version 5.1
<#
.SYNOPSIS
    Windows PowerShell launcher for the WHP QEMU build.
.DESCRIPTION
    PowerShell owns Windows-side shell discovery only. The existing build.sh
    remains the single build-policy entry point so QEMU and firmware builds do
    not drift into a second orchestration implementation.
#>

[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$SeaBIOSUefi,
    [switch]$NoSourceUpdate,
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Targets = @()
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$SourceDir = $PSScriptRoot
$BuildScript = Join-Path -Path $SourceDir -ChildPath 'build.sh'
if (-not (Test-Path -LiteralPath $BuildScript -PathType Leaf)) {
    throw "build.sh is missing: $BuildScript"
}

function Resolve-BashCandidate {
    param([string]$Candidate)

    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        return $null
    }
    if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
        return (Resolve-Path -LiteralPath $Candidate).Path
    }

    $command = Get-Command -Name $Candidate -CommandType Application -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }
    return $null
}

function Test-WindowsPosixBash {
    param([string]$BashPath)

    try {
        $probe = @(& $BashPath --noprofile --norc -c 'kernel="$(uname -s 2>/dev/null || true)"; case "$kernel" in CYGWIN*|MINGW*|MSYS*) command -v cygpath >/dev/null 2>&1 || exit 3; printf "%s\n" "$kernel" ;; *) exit 2 ;; esac' 2>$null)
        if ($LASTEXITCODE -ne 0 -or $probe.Count -eq 0) {
            return $false
        }
        return ($probe[-1].Trim() -match '^(CYGWIN|MINGW|MSYS)')
    }
    catch {
        return $false
    }
}

function Find-WindowsPosixBash {
    if (-not [string]::IsNullOrWhiteSpace($env:WHP_WINDOWS_BASH)) {
        $explicit = Resolve-BashCandidate $env:WHP_WINDOWS_BASH
        if ($null -eq $explicit -or -not (Test-WindowsPosixBash $explicit)) {
            throw "WHP_WINDOWS_BASH is not an MSYS2/Git-for-Windows/Cygwin Bash: $env:WHP_WINDOWS_BASH"
        }
        return $explicit
    }

    $candidates = New-Object System.Collections.Generic.List[string]

    if (-not [string]::IsNullOrWhiteSpace($env:WHP_BUILD_BASH) -and
        (Test-Path -LiteralPath $env:WHP_BUILD_BASH -PathType Leaf)) {
        $candidates.Add($env:WHP_BUILD_BASH)
    }

    $candidates.Add((Join-Path -Path $SourceDir -ChildPath 'msys64\usr\bin\bash.exe'))
    if (-not [string]::IsNullOrWhiteSpace($env:MSYS2_ROOT)) {
        $candidates.Add((Join-Path -Path $env:MSYS2_ROOT -ChildPath 'usr\bin\bash.exe'))
    }
    $candidates.Add('C:\msys64\usr\bin\bash.exe')
    $candidates.Add('C:\tools\msys64\usr\bin\bash.exe')

    $pathBash = Get-Command -Name 'bash.exe' -CommandType Application -ErrorAction SilentlyContinue
    if ($null -ne $pathBash) {
        $candidates.Add($pathBash.Source)
    }

    $programFiles = [Environment]::GetEnvironmentVariable('ProgramFiles')
    if (-not [string]::IsNullOrWhiteSpace($programFiles)) {
        $candidates.Add((Join-Path -Path $programFiles -ChildPath 'Git\bin\bash.exe'))
        $candidates.Add((Join-Path -Path $programFiles -ChildPath 'Git\usr\bin\bash.exe'))
    }
    $programFilesX86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
    if (-not [string]::IsNullOrWhiteSpace($programFilesX86)) {
        $candidates.Add((Join-Path -Path $programFilesX86 -ChildPath 'Git\bin\bash.exe'))
    }
    $candidates.Add('C:\cygwin64\bin\bash.exe')

    $seen = @{}
    foreach ($candidate in $candidates) {
        $resolved = Resolve-BashCandidate $candidate
        if ($null -eq $resolved) {
            continue
        }
        $key = $resolved.ToLowerInvariant()
        if ($seen.ContainsKey($key)) {
            continue
        }
        $seen[$key] = $true

        if (Test-WindowsPosixBash $resolved) {
            return $resolved
        }
    }

    throw @'
No Windows-native POSIX Bash was found.
Install MSYS2 (preferred for QEMU builds), Git for Windows, or Cygwin, or set
WHP_WINDOWS_BASH to the full path of bash.exe. WSL Bash is intentionally not
used here because it selects a Linux host ABI instead of the Windows build ABI.
'@
}

function Convert-ToPosixPath {
    param(
        [string]$BashPath,
        [string]$WindowsPath
    )

    $converted = @(& $BashPath --noprofile --norc -c 'cygpath -u "$1"' _ $WindowsPath 2>$null)
    if ($LASTEXITCODE -ne 0 -or $converted.Count -eq 0) {
        throw "could not convert Windows path for Bash: $WindowsPath"
    }
    return $converted[-1].Trim()
}

function Add-WindowsPosixToolPath {
    param([string]$BashPath)

    $usrBin = Split-Path -Parent $BashPath
    $root = Split-Path -Parent (Split-Path -Parent $usrBin)
    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
        return
    }

    if ([string]::IsNullOrWhiteSpace($env:MSYSTEM)) {
        $env:MSYSTEM = 'MINGW64'
    }

    $abiDir = switch ($env:MSYSTEM.ToUpperInvariant()) {
        'UCRT64' { 'ucrt64' }
        'CLANG64' { 'clang64' }
        'CLANGARM64' { 'clangarm64' }
        'MINGW32' { 'mingw32' }
        default { 'mingw64' }
    }

    $prepend = New-Object System.Collections.Generic.List[string]
    $abiBin = Join-Path -Path $root -ChildPath "$abiDir\bin"
    if (Test-Path -LiteralPath $abiBin -PathType Container) {
        $prepend.Add($abiBin)
    }
    if (Test-Path -LiteralPath $usrBin -PathType Container) {
        $prepend.Add($usrBin)
    }
    if ($prepend.Count -gt 0) {
        $env:PATH = (($prepend.ToArray() + @($env:PATH)) -join [IO.Path]::PathSeparator)
    }
}

$BashPath = Find-WindowsPosixBash
Add-WindowsPosixToolPath $BashPath

$PosixBuildScript = Convert-ToPosixPath $BashPath $BuildScript
$PosixBash = Convert-ToPosixPath $BashPath $BashPath
$env:WHP_BUILD_BASH = $PosixBash

if ([string]::IsNullOrWhiteSpace($env:CHERE_INVOKING)) {
    $env:CHERE_INVOKING = 'yes'
}
if ([string]::IsNullOrWhiteSpace($env:MSYS)) {
    $env:MSYS = 'winsymlinks:native'
}

if ($NoSourceUpdate) {
    $env:WHP_SOURCE_UPDATE = '0'
}

if ($SeaBIOSUefi) {
    $env:BUILD_SEABIOS_GRUB = '1'
    $env:BUILD_SEABIOS_HYBRID_ISO = '1'
    if ([string]::IsNullOrWhiteSpace($env:GRUB_I386_BOOTSTRAP)) {
        $env:GRUB_I386_BOOTSTRAP = '1'
    }
    Write-Host 'WHP SeaBIOS UEFI lane: enabled'
}

$kernelOutput = @(& $BashPath --noprofile --norc -c 'uname -s' 2>$null)
$Kernel = $kernelOutput[-1].Trim()
Write-Host "WHP Windows Bash: $BashPath ($Kernel)"

& $BashPath --noprofile --norc $PosixBuildScript @Targets
$BuildExitCode = $LASTEXITCODE
if ($null -eq $BuildExitCode) {
    $BuildExitCode = 0
}
exit $BuildExitCode
