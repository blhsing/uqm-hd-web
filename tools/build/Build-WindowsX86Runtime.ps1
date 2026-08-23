[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Msys2Root,

    [Parameter(Mandatory = $true)]
    [string]$OutputDir,

    [string]$WorkDir,
    [string]$ExecutablePath,
    [string]$RepoRoot,
    [switch]$RequireCleanSource,
    [switch]$AllowAdditionalPackages
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Join-Path $PSScriptRoot '..\..'
}

function Get-FullPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    return [IO.Path]::GetFullPath($Path)
}

function Test-PathWithin {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Candidate
    )
    $rootPath = (Get-FullPath -Path $Root).TrimEnd('\', '/')
    $candidatePath = (Get-FullPath -Path $Candidate).TrimEnd('\', '/')
    return [string]::Equals($rootPath, $candidatePath, [StringComparison]::OrdinalIgnoreCase) -or
        $candidatePath.StartsWith(
            $rootPath + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase)
}

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return (($sha.ComputeHash($stream) | ForEach-Object { $_.ToString('x2') }) -join '')
    }
    finally {
        $sha.Dispose()
        $stream.Dispose()
    }
}

function Get-BytesSha256 {
    param([Parameter(Mandatory = $true)][byte[]]$Bytes)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        return (($sha.ComputeHash($Bytes) | ForEach-Object { $_.ToString('x2') }) -join '')
    }
    finally {
        $sha.Dispose()
    }
}

function Get-LockMap {
    param([Parameter(Mandatory = $true)][string]$Path)
    $result = @{}
    foreach ($line in Get-Content -LiteralPath $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) {
            continue
        }
        if ($trimmed -notmatch '^([^ ]+) +(.+)$') {
            throw "Malformed package-lock line in ${Path}: $line"
        }
        if ($result.ContainsKey($Matches[1])) {
            throw "Duplicate package in ${Path}: $($Matches[1])"
        }
        $result[$Matches[1]] = $Matches[2]
    }
    return $result
}

function Get-GameTreeFingerprint {
    param([Parameter(Mandatory = $true)][string]$GameRoot)
    $rootPrefix = $GameRoot.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    $entries = New-Object System.Collections.Generic.List[object]
    foreach ($item in Get-ChildItem -LiteralPath $GameRoot -File -Force -Recurse) {
        $relative = $item.FullName.Substring($rootPrefix.Length).Replace('\', '/')
        [void]$entries.Add([pscustomobject]@{
            Path = $relative
            Hash = (Get-Sha256 -Path $item.FullName)
        })
    }
    $orderedPaths = @($entries | ForEach-Object Path)
    [Array]::Sort($orderedPaths, [StringComparer]::Ordinal)
    $hashByPath = @{}
    foreach ($entry in $entries) {
        $hashByPath[$entry.Path] = $entry.Hash
    }
    $builder = New-Object Text.StringBuilder
    foreach ($relative in $orderedPaths) {
        [void]$builder.Append($hashByPath[$relative])
        [void]$builder.Append('  ')
        [void]$builder.Append($relative)
        [void]$builder.Append("`n")
    }
    $bytes = [Text.UTF8Encoding]::new($false).GetBytes($builder.ToString())
    return [pscustomobject]@{
        FileCount = $orderedPaths.Count
        Sha256 = (Get-BytesSha256 -Bytes $bytes)
    }
}

function Convert-ToPosixPath {
    param(
        [Parameter(Mandatory = $true)][string]$Cygpath,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $value = & $Cygpath -u $Path
    if ($LASTEXITCODE -ne 0 -or -not $value) {
        throw "cygpath could not convert: $Path"
    }
    return ([string]$value).Trim()
}

function Convert-ToMixedPath {
    param(
        [Parameter(Mandatory = $true)][string]$Cygpath,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $value = & $Cygpath -m $Path
    if ($LASTEXITCODE -ne 0 -or -not $value) {
        throw "cygpath could not convert: $Path"
    }
    return ([string]$value).Trim()
}

function Quote-Sh {
    param([Parameter(Mandatory = $true)][string]$Value)
    $replacement = "'" + '"' + "'" + '"' + "'"
    return "'" + $Value.Replace("'", $replacement) + "'"
}

function Get-PeImports {
    param(
        [Parameter(Mandatory = $true)][string]$Objdump,
        [Parameter(Mandatory = $true)][string]$Path
    )
    $details = @(& $Objdump -p $Path 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "objdump could not inspect $Path`n$($details -join "`n")"
    }
    $detailsText = $details -join "`n"
    if ($detailsText -notmatch 'file format pei-i386' -or $detailsText -notmatch 'Magic\s+010b') {
        throw "Runtime binary is not PE32/i386: $Path"
    }
    $imports = New-Object System.Collections.Generic.List[string]
    foreach ($line in $details) {
        if ([string]$line -match 'DLL Name:\s*(\S+)') {
            [void]$imports.Add($Matches[1])
        }
    }
    $values = @($imports | Select-Object -Unique)
    [Array]::Sort($values, [StringComparer]::OrdinalIgnoreCase)
    return $values
}

function Copy-LicenseTree {
    param(
        [Parameter(Mandatory = $true)][string]$SourceRoot,
        [Parameter(Mandatory = $true)][string]$DestinationRoot,
        [Parameter(Mandatory = $true)][string]$ManifestPrefix
    )
    if (-not (Test-Path -LiteralPath $SourceRoot -PathType Container)) {
        throw "License source is missing: $SourceRoot"
    }
    $sourcePrefix = $SourceRoot.TrimEnd('\', '/') + [IO.Path]::DirectorySeparatorChar
    $files = @(Get-ChildItem -LiteralPath $SourceRoot -File -Force -Recurse)
    if ($files.Count -eq 0) {
        throw "License source contains no files: $SourceRoot"
    }
    $relativePaths = @($files | ForEach-Object {
        $_.FullName.Substring($sourcePrefix.Length).Replace('\', '/')
    })
    [Array]::Sort($relativePaths, [StringComparer]::Ordinal)
    $manifestPaths = New-Object System.Collections.Generic.List[string]
    foreach ($relative in $relativePaths) {
        $source = Join-Path $SourceRoot $relative.Replace('/', '\')
        $destination = Join-Path $DestinationRoot $relative.Replace('/', '\')
        $parent = Split-Path -Parent $destination
        if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
            [void](New-Item -ItemType Directory -Path $parent -Force)
        }
        Copy-Item -LiteralPath $source -Destination $destination
        [void]$manifestPaths.Add("$ManifestPrefix/$relative")
    }
    return $manifestPaths.ToArray()
}

$repo = Get-FullPath -Path $RepoRoot
$msys = Get-FullPath -Path $Msys2Root
$output = Get-FullPath -Path $OutputDir
$gameRoot = Join-Path $repo 'game'
$recipeRoot = Join-Path $repo 'tools\build\windows-x86'
$lockPath = Join-Path $recipeRoot 'msys2-packages.lock'
$explicitLockPath = Join-Path $recipeRoot 'msys2-explicit-packages.lock'
$metadataPath = Join-Path $recipeRoot 'runtime-packages.json'
$bootstrapPath = Join-Path $recipeRoot 'toolchain-bootstrap.json'
$configStatePath = Join-Path $recipeRoot 'config.state'
$svnversionPath = Join-Path $recipeRoot 'bin\svnversion'
$bash = Join-Path $msys 'usr\bin\bash.exe'
$cygpath = Join-Path $msys 'usr\bin\cygpath.exe'
$pacman = Join-Path $msys 'usr\bin\pacman.exe'
$objdump = Join-Path $msys 'mingw32\bin\objdump.exe'
$mingwBin = Join-Path $msys 'mingw32\bin'

foreach ($required in @(
    (Join-Path $gameRoot 'build.sh'), $lockPath, $explicitLockPath,
    $metadataPath, $bootstrapPath, $configStatePath, $svnversionPath, $bash, $cygpath,
    $pacman, $objdump)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required build input is missing: $required"
    }
}

if (Test-PathWithin -Root $gameRoot -Candidate $output) {
    throw "OutputDir must not be inside the source input tree game/: $output"
}

if (Test-Path -LiteralPath $output) {
    if (-not (Test-Path -LiteralPath $output -PathType Container)) {
        throw "OutputDir is not a directory: $output"
    }
    if (@(Get-ChildItem -LiteralPath $output -Force).Count -ne 0) {
        throw "OutputDir must not exist or must be empty: $output"
    }
}
else {
    [void](New-Item -ItemType Directory -Path $output)
}

$lockedPackages = Get-LockMap -Path $lockPath
$lockedExplicitPackages = Get-LockMap -Path $explicitLockPath
$actualPackageLines = @(& $pacman -Q 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "pacman -Q failed:`n$($actualPackageLines -join "`n")"
}
$actualPackages = @{}
foreach ($line in $actualPackageLines) {
    if ([string]$line -notmatch '^([^ ]+) +(.+)$') {
        throw "Unexpected pacman -Q output: $line"
    }
    $actualPackages[$Matches[1]] = $Matches[2]
}
$packageErrors = New-Object System.Collections.Generic.List[string]
foreach ($name in $lockedPackages.Keys) {
    if (-not $actualPackages.ContainsKey($name)) {
        [void]$packageErrors.Add("missing $name $($lockedPackages[$name])")
    }
    elseif ($actualPackages[$name] -cne $lockedPackages[$name]) {
        [void]$packageErrors.Add("$name is $($actualPackages[$name]); expected $($lockedPackages[$name])")
    }
}
if (-not $AllowAdditionalPackages) {
    foreach ($name in $actualPackages.Keys) {
        if (-not $lockedPackages.ContainsKey($name)) {
            [void]$packageErrors.Add("unexpected package $name $($actualPackages[$name])")
        }
    }
}
$actualExplicitLines = @(& $pacman -Qqe 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "pacman -Qqe failed:`n$($actualExplicitLines -join "`n")"
}
$actualExplicit = @{}
foreach ($nameValue in $actualExplicitLines) {
    $name = ([string]$nameValue).Trim()
    if ($name) {
        $actualExplicit[$name] = $actualPackages[$name]
    }
}
foreach ($name in $lockedExplicitPackages.Keys) {
    if (-not $actualExplicit.ContainsKey($name) -or
        $actualExplicit[$name] -cne $lockedExplicitPackages[$name]) {
        [void]$packageErrors.Add("explicit package mismatch: $name $($lockedExplicitPackages[$name])")
    }
}
if ($packageErrors.Count -ne 0) {
    throw "Portable MSYS2 environment differs from its lock:`n - $($packageErrors -join "`n - ")"
}

$sourceBefore = Get-GameTreeFingerprint -GameRoot $gameRoot
$gitCommitLines = @(& git -C $repo rev-parse HEAD 2>&1)
$gitCommitExitCode = $LASTEXITCODE
$gitCommit = ([string]($gitCommitLines | Select-Object -First 1)).Trim()
if ($gitCommitExitCode -ne 0 -or $gitCommit -notmatch '^[0-9a-fA-F]{40}$') {
    throw 'The repository must have a readable Git commit.'
}
$sourceDateEpochLines = @(& git -C $repo show -s --format=%ct HEAD 2>&1)
$sourceDateEpochExitCode = $LASTEXITCODE
$sourceDateEpochText = ([string]($sourceDateEpochLines | Select-Object -First 1)).Trim()
if ($sourceDateEpochExitCode -ne 0 -or $sourceDateEpochText -notmatch '^\d+$') {
    throw 'Could not read the source commit timestamp.'
}
$sourceDateEpoch = [Int64]$sourceDateEpochText
$gameStatus = @(& git -C $repo status --porcelain=v1 --untracked-files=all -- game 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "Could not inspect game/ source state:`n$($gameStatus -join "`n")"
}
$sourceTreeState = if ($gameStatus.Count -eq 0) { 'clean' } else { 'dirty' }
if ($RequireCleanSource -and $sourceTreeState -ne 'clean') {
    throw "game/ has $($gameStatus.Count) changed or untracked entries; a release build requires clean source."
}

$buildPerformed = [string]::IsNullOrWhiteSpace($ExecutablePath)
if ($buildPerformed) {
    if ([string]::IsNullOrWhiteSpace($WorkDir)) {
        throw 'WorkDir is required unless ExecutablePath is supplied.'
    }
    $work = Get-FullPath -Path $WorkDir
    if (Test-PathWithin -Root $gameRoot -Candidate $work) {
        throw "WorkDir must not be inside the source input tree game/: $work"
    }
    if ((Test-PathWithin -Root $work -Candidate $output) -or
        (Test-PathWithin -Root $output -Candidate $work)) {
        throw 'WorkDir and OutputDir must be separate, non-nested directories.'
    }
    if (Test-Path -LiteralPath $work) {
        if (-not (Test-Path -LiteralPath $work -PathType Container) -or
            @(Get-ChildItem -LiteralPath $work -Force).Count -ne 0) {
            throw "WorkDir must not exist or must be empty: $work"
        }
    }
    else {
        [void](New-Item -ItemType Directory -Path $work)
    }
    Copy-Item -LiteralPath $configStatePath -Destination (Join-Path $work 'config.state')
    $generatedBin = Join-Path $work '.recipe-bin'
    [void](New-Item -ItemType Directory -Path $generatedBin)
    Copy-Item -LiteralPath $svnversionPath -Destination (Join-Path $generatedBin 'svnversion')

    $gamePosix = Convert-ToPosixPath -Cygpath $cygpath -Path $gameRoot
    $generatedBinPosix = Convert-ToPosixPath -Cygpath $cygpath -Path $generatedBin
    $workMixed = Convert-ToMixedPath -Cygpath $cygpath -Path $work
    $command = @(
        'set -eu',
        'export MSYSTEM=MINGW32',
        'export BUILD_SYSTEM=$(uname -s)',
        'export HOST_SYSTEM=$BUILD_SYSTEM',
        'case $HOST_SYSTEM in MINGW32*) ;; *) echo Expected_MINGW32_host_got_$HOST_SYSTEM >&2; exit 1 ;; esac',
        "chmod +x $(Quote-Sh $generatedBinPosix)/svnversion",
        "export PATH=$(Quote-Sh $generatedBinPosix):/mingw32/bin:/usr/bin",
        "export BUILD_WORK=$(Quote-Sh $workMixed)",
        "export SOURCE_DATE_EPOCH=$(Quote-Sh $sourceDateEpochText)",
        "cd $(Quote-Sh $gamePosix)",
        './build.sh uqm reprocess_config',
        './build.sh uqm depend',
        './build.sh uqm'
    ) -join '; '
    $previousMsystem = $env:MSYSTEM
    $previousChereInvoking = $env:CHERE_INVOKING
    try {
        $env:MSYSTEM = 'MINGW32'
        $env:CHERE_INVOKING = '1'
        & $bash -lc $command
        $buildExitCode = $LASTEXITCODE
    }
    finally {
        if ($null -eq $previousMsystem) {
            Remove-Item Env:MSYSTEM -ErrorAction SilentlyContinue
        }
        else {
            $env:MSYSTEM = $previousMsystem
        }
        if ($null -eq $previousChereInvoking) {
            Remove-Item Env:CHERE_INVOKING -ErrorAction SilentlyContinue
        }
        else {
            $env:CHERE_INVOKING = $previousChereInvoking
        }
    }
    if ($buildExitCode -ne 0) {
        throw "Canonical UQM-HD release build failed with exit code $buildExitCode."
    }
    $sourceExecutable = Join-Path $work 'uqm-hd.exe'
}
else {
    $sourceExecutable = Get-FullPath -Path $ExecutablePath
}
if (-not (Test-Path -LiteralPath $sourceExecutable -PathType Leaf)) {
    throw "Built executable is missing: $sourceExecutable"
}

$runtimeMetadata = Get-Content -LiteralPath $metadataPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ([int]$runtimeMetadata.schemaVersion -ne 1) {
    throw 'Unsupported runtime-packages.json schemaVersion.'
}
$systemDlls = @{}
foreach ($name in @($runtimeMetadata.systemDlls)) {
    $systemDlls[[string]$name] = $true
}
$metadataByDll = @{}
$metadataByPackage = @{}
foreach ($package in @($runtimeMetadata.packages)) {
    $packageName = [string]$package.name
    if (-not $lockedPackages.ContainsKey($packageName)) {
        throw "Runtime package is not present in the package lock: $packageName"
    }
    $metadataByPackage[$packageName] = $package
    $databaseFiles = Join-Path $msys "var\lib\pacman\local\$packageName-$($lockedPackages[$packageName])\files"
    if (-not (Test-Path -LiteralPath $databaseFiles -PathType Leaf)) {
        throw "Pinned package database entry is missing: $databaseFiles"
    }
    $ownedPaths = @(Get-Content -LiteralPath $databaseFiles -Encoding UTF8)
    foreach ($binary in @($package.binaries)) {
        $binaryName = [string]$binary
        if ($metadataByDll.ContainsKey($binaryName)) {
            throw "Duplicate runtime binary metadata: $binaryName"
        }
        $ownedPath = "mingw32/bin/$binaryName"
        if (-not ($ownedPaths -ccontains $ownedPath)) {
            throw "$packageName does not own $ownedPath according to the local pacman database."
        }
        $metadataByDll[$binaryName] = $package
    }
}

$stagedExecutable = Join-Path $output 'uqm-hd.exe'
Copy-Item -LiteralPath $sourceExecutable -Destination $stagedExecutable
$queue = New-Object System.Collections.Generic.Queue[string]
$queue.Enqueue($stagedExecutable)
$seen = @{}
$seen['uqm-hd.exe'] = $true
$importGraph = New-Object System.Collections.Generic.List[object]
while ($queue.Count -ne 0) {
    $binaryPath = $queue.Dequeue()
    $binaryName = Split-Path -Leaf $binaryPath
    $bundledImports = New-Object System.Collections.Generic.List[string]
    $systemImports = New-Object System.Collections.Generic.List[string]
    foreach ($import in @(Get-PeImports -Objdump $objdump -Path $binaryPath)) {
        if ($systemDlls.ContainsKey($import)) {
            [void]$systemImports.Add($import)
            continue
        }
        if (-not $metadataByDll.ContainsKey($import)) {
            throw "Unresolved non-system PE import $import required by $binaryName."
        }
        $dependencySource = Join-Path $mingwBin $import
        if (-not (Test-Path -LiteralPath $dependencySource -PathType Leaf)) {
            throw "Pinned runtime DLL is missing: $dependencySource"
        }
        [void]$bundledImports.Add($import)
        if (-not $seen.ContainsKey($import)) {
            $dependencyDestination = Join-Path $output $import
            Copy-Item -LiteralPath $dependencySource -Destination $dependencyDestination
            $seen[$import] = $true
            $queue.Enqueue($dependencyDestination)
        }
    }
    [void]$importGraph.Add([ordered]@{
        path = $binaryName
        bundledImports = $bundledImports.ToArray()
        systemImports = $systemImports.ToArray()
    })
}

$licensesRoot = Join-Path $output 'LICENSES'
[void](New-Item -ItemType Directory -Path $licensesRoot)
$uqmLicenseDir = Join-Path $licensesRoot 'uqm-hd'
[void](New-Item -ItemType Directory -Path $uqmLicenseDir)
Copy-Item -LiteralPath (Join-Path $gameRoot 'COPYING') -Destination (Join-Path $uqmLicenseDir 'COPYING')
$licensePathsByPackage = @{}
$usedPackageNames = @($seen.Keys | Where-Object { $_ -ne 'uqm-hd.exe' } | ForEach-Object {
    [string]$metadataByDll[$_].name
} | Select-Object -Unique)
[Array]::Sort($usedPackageNames, [StringComparer]::Ordinal)
foreach ($packageName in $usedPackageNames) {
    $package = $metadataByPackage[$packageName]
    $sourceSpec = [string]$package.licenseSource
    if ($sourceSpec.StartsWith('repo:', [StringComparison]::Ordinal)) {
        $licenseSource = Join-Path $repo $sourceSpec.Substring(5).Replace('/', '\')
    }
    else {
        $licenseSource = Join-Path $msys $sourceSpec.Replace('/', '\')
    }
    $packageLicenseDir = Join-Path $licensesRoot $packageName
    [void](New-Item -ItemType Directory -Path $packageLicenseDir)
    $licensePathsByPackage[$packageName] = @(Copy-LicenseTree `
        -SourceRoot $licenseSource `
        -DestinationRoot $packageLicenseDir `
        -ManifestPrefix "LICENSES/$packageName")
}

$sourceAfter = Get-GameTreeFingerprint -GameRoot $gameRoot
if ($sourceAfter.FileCount -ne $sourceBefore.FileCount -or
    $sourceAfter.Sha256 -cne $sourceBefore.Sha256) {
    throw 'game/ changed during the build; runtime provenance would be ambiguous.'
}

$payloadNames = @($seen.Keys)
[Array]::Sort($payloadNames, [StringComparer]::OrdinalIgnoreCase)
$payloadNames = @('uqm-hd.exe') + @($payloadNames | Where-Object { $_ -ne 'uqm-hd.exe' })
$files = New-Object System.Collections.Generic.List[object]
foreach ($name in $payloadNames) {
    $path = Join-Path $output $name
    $item = Get-Item -LiteralPath $path
    if ($name -eq 'uqm-hd.exe') {
        $provenance = [ordered]@{
            type = if ($buildPerformed) { 'source-build' } else { 'caller-supplied-executable' }
            sourceGitCommit = $gitCommit.ToLowerInvariant()
            sourceTreeState = $sourceTreeState
            sourceRevision = [string]$runtimeMetadata.sourceRevision
            sourcePath = 'game'
            sourceTreeFileCount = [int]$sourceBefore.FileCount
            sourceTreeFingerprintSha256 = [string]$sourceBefore.Sha256
            sourceTreeFingerprintMethod = "SHA-256 of UTF-8 lines '<lowercase-file-sha256>  <forward-slash-relative-path>\\n' for every regular file below game/, sorted with StringComparer.Ordinal"
            buildPerformedByRecipe = [bool]$buildPerformed
            buildMode = 'release'
            compilerPackage = "mingw-w64-i686-gcc $($lockedPackages['mingw-w64-i686-gcc'])"
            compilerFlags = '-O3 -DNDEBUG'
            packageLockSha256 = (Get-Sha256 -Path $lockPath)
            runtimeMetadataSha256 = (Get-Sha256 -Path $metadataPath)
            configStateSha256 = (Get-Sha256 -Path $configStatePath)
            revisionWrapperSha256 = (Get-Sha256 -Path $svnversionPath)
        }
        [void]$files.Add([ordered]@{
            path = $name
            installPath = 'uqm.exe'
            length = [Int64]$item.Length
            sha256 = (Get-Sha256 -Path $path)
            kind = 'executable'
            package = 'uqm-hd'
            version = [string]$runtimeMetadata.productVersion
            license = 'GPL-2.0-or-later'
            licenseFiles = @('LICENSES/uqm-hd/COPYING')
            provenance = $provenance
        })
    }
    else {
        $package = $metadataByDll[$name]
        $packageName = [string]$package.name
        [void]$files.Add([ordered]@{
            path = $name
            installPath = $name
            length = [Int64]$item.Length
            sha256 = (Get-Sha256 -Path $path)
            kind = 'runtime-library'
            package = $packageName
            version = [string]$lockedPackages[$packageName]
            license = [string]$package.license
            licenseFiles = @($licensePathsByPackage[$packageName])
            provenance = [ordered]@{
                type = 'msys2-mingw32-package'
                repository = 'MSYS2 MINGW32'
                package = $packageName
                version = [string]$lockedPackages[$packageName]
                binarySource = "mingw32/bin/$name"
                ownershipVerifiedBy = 'exact package lock plus pacman local database files list'
                packagePage = "https://packages.msys2.org/package/$packageName"
                licenseSource = [string]$package.licenseSource
                licenseOrigin = if ($null -ne $package.PSObject.Properties['licenseOrigin']) {
                    [string]$package.licenseOrigin
                } else {
                    [string]$package.licenseSource
                }
            }
        })
    }
}

$orderedGraph = @($importGraph | Sort-Object { $_.path.ToLowerInvariant() })
$manifest = [ordered]@{
    schemaVersion = 1
    platform = 'windows-x86'
    executable = 'uqm-hd.exe'
    files = $files.ToArray()
    build = [ordered]@{
        recipe = 'tools/build/Build-WindowsX86Runtime.ps1'
        recipeSha256 = (Get-Sha256 -Path $PSCommandPath)
        packageLock = 'tools/build/windows-x86/msys2-packages.lock'
        packageLockSha256 = (Get-Sha256 -Path $lockPath)
        toolchainBootstrap = 'tools/build/windows-x86/toolchain-bootstrap.json'
        toolchainBootstrapSha256 = (Get-Sha256 -Path $bootstrapPath)
        runtimeMetadata = 'tools/build/windows-x86/runtime-packages.json'
        runtimeMetadataSha256 = (Get-Sha256 -Path $metadataPath)
        configState = 'tools/build/windows-x86/config.state'
        configStateSha256 = (Get-Sha256 -Path $configStatePath)
        revisionWrapper = 'tools/build/windows-x86/bin/svnversion'
        revisionWrapperSha256 = (Get-Sha256 -Path $svnversionPath)
        sourceDateEpoch = $sourceDateEpoch
        canonicalCommands = @(
            './build.sh uqm reprocess_config',
            './build.sh uqm depend',
            './build.sh uqm'
        )
    }
    verification = [ordered]@{
        peFormat = 'PE32/i386'
        importClosure = 'complete'
        payloadFiles = $files.Count
        unresolvedNonSystemImports = 0
        method = 'recursive PE import inspection with pinned mingw32 bin ownership and a fixed Windows system-DLL allowlist'
        imports = $orderedGraph
    }
}
$json = $manifest | ConvertTo-Json -Depth 12
if ($json -match '(?i)"[a-z]:[\\/]') {
    throw 'Generated manifest contains an absolute Windows path.'
}
$manifestPath = Join-Path $output 'runtime-manifest.json'
[IO.File]::WriteAllText($manifestPath, $json + "`n", [Text.UTF8Encoding]::new($false))

$normalizedTime = [DateTimeOffset]::FromUnixTimeSeconds($sourceDateEpoch).UtcDateTime
foreach ($item in Get-ChildItem -LiteralPath $output -File -Force -Recurse) {
    $item.LastWriteTimeUtc = $normalizedTime
}

Write-Host "Staged $($files.Count) verified PE32 payload files at $output"
Write-Host "game/ fingerprint: $($sourceBefore.Sha256) ($($sourceBefore.FileCount) files; $sourceTreeState)"
Write-Host "runtime manifest: $(Get-Sha256 -Path $manifestPath)"
