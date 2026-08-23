[CmdletBinding()]
param(
    [string]$InstallRoot = 'C:\Games\UQM-HD-TW',
    [string]$ProfileDir,
    [string]$PacksDir,
    [ValidateRange(3, 120)][int]$SmokeTimeoutSeconds = 12,
    [switch]$SkipHashes,
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = 'Stop'
. (Join-Path -Path $PSScriptRoot -ChildPath 'UqmInstall.Common.ps1')

$failures = New-Object System.Collections.ArrayList
$passes = New-Object System.Collections.ArrayList

function Add-VerificationFailure {
    param([string]$Message)
    [void]$failures.Add($Message)
    Write-Warning $Message
}

function Add-VerificationPass {
    param([string]$Message)
    [void]$passes.Add($Message)
    Write-Verbose $Message
}

$install = Get-UqmFullPath -Path $InstallRoot -MustExist -MustBeDirectory
Assert-UqmNotVolumeRoot -Path $install -Role 'InstallRoot'
Assert-UqmNoReparseComponents -Path $install
$marker = Read-UqmInstallMarker -InstallRoot $install
if ($null -eq $marker) {
    throw "No managed-install marker exists in InstallRoot: $install"
}
if ($marker.State -ne 'complete') {
    Add-VerificationFailure -Message "Installation marker state is not complete: $($marker.State)"
}
else {
    Add-VerificationPass -Message 'Installation marker state is complete.'
}

if ($PSBoundParameters.ContainsKey('ProfileDir')) {
    $profile = Get-UqmFullPath -Path $ProfileDir
    if (-not (Test-UqmPathEqual -Left $profile -Right $marker.ProfileDir)) {
        Add-VerificationFailure -Message "ProfileDir differs from the installed profile. Expected: $($marker.ProfileDir) Actual: $profile"
    }
}
else {
    $profile = Get-UqmFullPath -Path $marker.ProfileDir
}
Assert-UqmNotVolumeRoot -Path $profile -Role 'ProfileDir'
if ((Test-UqmPathInside -Path $install -Root $profile -AllowRoot) -or
    (Test-UqmPathInside -Path $profile -Root $install -AllowRoot)) {
    Add-VerificationFailure -Message 'ProfileDir and InstallRoot are nested; the profile is not isolated.'
}

$flightConfiguration = Join-UqmContainedPath -Root $profile -RelativePath 'flight.cfg'
try {
    if (-not (Test-Path -LiteralPath $flightConfiguration -PathType Leaf)) {
        throw "Player 1 flight configuration is missing: $flightConfiguration"
    }
    $flightConfigurationItem = Get-Item -LiteralPath $flightConfiguration -Force
    if (($flightConfigurationItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Player 1 flight configuration is a reparse point: $flightConfiguration"
    }
    $flightConfigurationText = [IO.File]::ReadAllText($flightConfiguration)
    $rightAltMatches = [Text.RegularExpressions.Regex]::Matches(
        $flightConfigurationText,
        '(?m)^[ \t]*1\.special\.3[ \t]*=[ \t]*STRING:key[ \t]+RightAlt[ \t]*\r?$')
    if ($rightAltMatches.Count -ne 1) {
        throw 'Player 1 RightAlt special-ability binding is missing or duplicated.'
    }
    Add-VerificationPass -Message 'Player 1 RightAlt is configured as the hidden third special-ability binding.'
}
catch {
    Add-VerificationFailure -Message $_.Exception.Message
}

$executable = Join-UqmContainedPath -Root $install -RelativePath 'uqm.exe'
$runtimeKind = 'legacy-patched'
if ($null -ne $marker.PSObject.Properties['Runtime']) {
    if ($null -eq $marker.Runtime.PSObject.Properties['Kind']) {
        Add-VerificationFailure -Message 'Installation marker Runtime record has no Kind.'
    }
    else {
        $runtimeKind = [string]$marker.Runtime.Kind
    }
}
if ($runtimeKind -notin @('legacy-patched', 'custom')) {
    Add-VerificationFailure -Message "Installation marker has an unsupported runtime kind: $runtimeKind"
}
elseif ($runtimeKind -eq 'custom') {
    try {
        if ($null -eq $marker.Runtime.PSObject.Properties['Platform'] -or
            -not [string]::Equals(
                [string]$marker.Runtime.Platform,
                'windows-x86',
                [StringComparison]::Ordinal)) {
            throw 'Custom runtime marker platform is not windows-x86.'
        }
        if ($null -eq $marker.Runtime.PSObject.Properties['ManifestSha256'] -or
            -not [Text.RegularExpressions.Regex]::IsMatch(
                [string]$marker.Runtime.ManifestSha256,
                '\A[0-9a-fA-F]{64}\z')) {
            throw 'Custom runtime marker has no valid manifest SHA-256.'
        }
        Add-VerificationPass -Message 'Custom Windows x86 runtime metadata is present.'
    }
    catch {
        Add-VerificationFailure -Message $_.Exception.Message
    }
}
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    Add-VerificationFailure -Message "Installed executable is missing: $executable"
}
elseif ($runtimeKind -eq 'legacy-patched') {
    Add-VerificationPass -Message 'Installed executable exists.'
    try {
        $executableBytes = [IO.File]::ReadAllBytes($executable)
        $rightAltHook = ConvertTo-UqmHexString -Bytes $executableBytes[0x2D612..0x2D616]
        $rightAltCave = ConvertTo-UqmHexString -Bytes $executableBytes[0x75351..0x7536E]
        if ($rightAltHook -cne 'E83A7D0400' -or
            $rightAltCave -cne '8B442404817808330100007507C740082F01000050E8A596FBFF83C404C3') {
            throw 'Installed executable does not contain the verified Player 1 RightAlt binding patch.'
        }
        Add-VerificationPass -Message 'Installed executable contains the verified Player 1 RightAlt binding patch.'

        $pickerEscapeHook = ConvertTo-UqmHexString -Bytes $executableBytes[0xEA975..0xEA97B]
        $pickerEscapeCave = ConvertTo-UqmHexString -Bytes $executableBytes[0x68061..0x6807D]
        if ($pickerEscapeHook -cne 'E9E7D6F7FF9090' -or
            $pickerEscapeCave -cne '6A00E8A86F000059A8207405E8CE6F0000C7450801000000E9FE280800') {
            throw 'Installed executable does not contain the verified Super Melee picker-Escape patch.'
        }
        Add-VerificationPass -Message 'Installed executable maps physical Escape to the Super Melee picker red-X confirmation path.'
    }
    catch {
        Add-VerificationFailure -Message $_.Exception.Message
    }
}
else {
    Add-VerificationPass -Message 'Installed custom executable exists.'
}

if ($null -eq $marker.PSObject.Properties['Files']) {
    Add-VerificationFailure -Message 'Installation marker has no managed-file manifest.'
}
else {
    $seenManifestPaths = @{}
    $managedFiles = @($marker.Files)
    if ($managedFiles.Count -eq 0) {
        Add-VerificationFailure -Message 'Installation marker has an empty managed-file manifest.'
    }
    if ($runtimeKind -eq 'custom') {
        $customExecutableEntries = @($managedFiles | Where-Object {
            [string]::Equals([string]$_.Path, 'uqm.exe', [StringComparison]::OrdinalIgnoreCase) -and
            [string]::Equals([string]$_.Kind, 'custom-runtime-executable', [StringComparison]::Ordinal)
        })
        $customLibraryEntries = @($managedFiles | Where-Object {
            [string]::Equals([string]$_.Kind, 'custom-runtime-library', [StringComparison]::Ordinal)
        })
        if ($customExecutableEntries.Count -ne 1) {
            Add-VerificationFailure -Message 'Custom runtime manifest does not contain exactly one managed uqm.exe.'
        }
        elseif ($customLibraryEntries.Count -eq 0) {
            Add-VerificationFailure -Message 'Custom runtime manifest contains no managed runtime libraries.'
        }
        else {
            Add-VerificationPass -Message "Custom runtime records one executable and $($customLibraryEntries.Count) libraries."
        }
    }
    for ($index = 0; $index -lt $managedFiles.Count; $index++) {
        $entry = $managedFiles[$index]
        try {
            if ($seenManifestPaths.ContainsKey([string]$entry.Path)) {
                throw "Duplicate case-insensitive manifest path: $($entry.Path)"
            }
            $seenManifestPaths[[string]$entry.Path] = $true
            $path = Join-UqmContainedPath -Root $install -RelativePath ([string]$entry.Path)
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
                throw "Managed file is missing: $($entry.Path)"
            }
            $item = Get-Item -LiteralPath $path -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Managed file is a reparse point: $($entry.Path)"
            }
            if ([Int64]$item.Length -ne [Int64]$entry.Length) {
                throw "Managed file length differs: $($entry.Path)"
            }
            if (-not $SkipHashes) {
                Write-Progress -Activity 'Verifying installed SHA-256 hashes' -Status $entry.Path `
                    -PercentComplete (($index * 100) / $managedFiles.Count)
                $actualHash = Get-UqmSha256 -Path $path
                if (-not [string]::Equals($actualHash, [string]$entry.Sha256, [StringComparison]::OrdinalIgnoreCase)) {
                    throw "Managed file SHA-256 differs: $($entry.Path)"
                }
            }
        }
        catch {
            Add-VerificationFailure -Message $_.Exception.Message
        }
    }
    Write-Progress -Activity 'Verifying installed SHA-256 hashes' -Completed

    $binaryInventoryFailures = 0
    foreach ($binary in Get-ChildItem -LiteralPath $install -Force -Recurse) {
        try {
            if (($binary.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "The installed tree contains a reparse point: $($binary.FullName)"
            }
            if ($binary.PSIsContainer -or
                @('.exe', '.dll') -notcontains $binary.Extension.ToLowerInvariant()) {
                continue
            }
            $relativeBinary = (Get-UqmRelativePath -Path $binary.FullName -Root $install).Replace('\', '/')
            if (-not $seenManifestPaths.ContainsKey($relativeBinary)) {
                throw "Installed executable/runtime library is absent from the managed manifest: $relativeBinary"
            }
            if ($runtimeKind -eq 'custom' -and $relativeBinary.IndexOf('/') -lt 0) {
                $binaryEntry = @($managedFiles | Where-Object {
                    [string]::Equals([string]$_.Path, $relativeBinary, [StringComparison]::OrdinalIgnoreCase)
                }) | Select-Object -First 1
                $expectedKind = if ($binary.Extension -ieq '.exe') {
                    'custom-runtime-executable'
                }
                else {
                    'custom-runtime-library'
                }
                if (-not [string]::Equals(
                    [string]$binaryEntry.Kind,
                    $expectedKind,
                    [StringComparison]::Ordinal)) {
                    throw "A top-level custom-runtime binary has the wrong managed kind: $relativeBinary"
                }
            }
        }
        catch {
            $binaryInventoryFailures++
            Add-VerificationFailure -Message $_.Exception.Message
        }
    }
    if ($binaryInventoryFailures -eq 0) {
        Add-VerificationPass -Message 'Every installed EXE/DLL is present in the managed manifest.'
    }

    if ($failures.Count -eq 0) {
        if ($SkipHashes) {
            Add-VerificationPass -Message "Verified existence and length of $($managedFiles.Count) managed files; hashes were skipped by request."
        }
        else {
            Add-VerificationPass -Message "Verified SHA-256 for $($managedFiles.Count) managed files."
        }
    }
}

$referencePacks = $null
if ($PSBoundParameters.ContainsKey('PacksDir')) {
    $referencePacks = Get-UqmFullPath -Path $PacksDir -MustExist -MustBeDirectory
}
elseif ($null -ne $marker.PSObject.Properties['PacksDir'] -and
    (Test-Path -LiteralPath ([string]$marker.PacksDir) -PathType Container)) {
    $referencePacks = Get-UqmFullPath -Path ([string]$marker.PacksDir) -MustExist -MustBeDirectory
}

foreach ($packName in $script:UqmPackNames) {
    $relative = 'content/addons/' + $packName
    $installedPack = Join-UqmContainedPath -Root $install -RelativePath $relative
    try {
        if (-not (Test-Path -LiteralPath $installedPack -PathType Leaf)) {
            throw "Installed Traditional Chinese pack is missing: $relative"
        }
        $actualLeaf = (Get-Item -LiteralPath $installedPack).Name
        if (-not [string]::Equals($actualLeaf, $packName, [StringComparison]::Ordinal)) {
            throw "Installed pack filename casing differs. Expected: $packName Actual: $actualLeaf"
        }
        $entryCount = Assert-UqmArchive -Path $installedPack
        if ($entryCount -le 0) {
            throw "Installed pack contains no entries: $packName"
        }

        $packRecord = $null
        if ($null -ne $marker.PSObject.Properties['Packs']) {
            $packRecord = @($marker.Packs) | Where-Object { $_.Name -ceq $packName } | Select-Object -First 1
        }
        if ($null -eq $packRecord) {
            throw "Marker has no exact pack record for: $packName"
        }
        $installedPackItem = Get-Item -LiteralPath $installedPack
        if ([Int64]$installedPackItem.Length -ne [Int64]$packRecord.Length) {
            throw "Pack length differs from marker: $packName"
        }
        if (-not $SkipHashes) {
            $installedHash = Get-UqmSha256 -Path $installedPack
            if (-not [string]::Equals($installedHash, [string]$packRecord.Sha256, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Pack SHA-256 differs from marker: $packName"
            }
            if ($null -ne $referencePacks) {
                $referencePath = Join-UqmContainedPath -Root $referencePacks -RelativePath $packName
                if (-not (Test-Path -LiteralPath $referencePath -PathType Leaf)) {
                    throw "Reference pack is missing: $referencePath"
                }
                $referenceHash = Get-UqmSha256 -Path $referencePath
                if (-not [string]::Equals($installedHash, $referenceHash, [StringComparison]::OrdinalIgnoreCase)) {
                    throw "Installed pack differs from its build output: $packName"
                }
            }
        }
        Add-VerificationPass -Message "Pack archive is valid: $packName ($entryCount entries)."
    }
    catch {
        Add-VerificationFailure -Message $_.Exception.Message
    }
}

try {
    $expectedShortcuts = Get-UqmShortcutSpecifications -InstallRoot $install -ProfileDir $profile
    $expectedDefaultArguments = Get-UqmLaunchArguments `
        -ResolutionFactor 3 -Addon 'native1080-zh_TW' -ProfileDir $profile -Fullscreen
    if ($null -eq $marker.PSObject.Properties['DefaultArguments'] -or
        -not [string]::Equals(
            [string]$marker.DefaultArguments,
            $expectedDefaultArguments,
            [StringComparison]::Ordinal)) {
        throw 'Marker default launch arguments differ from the native 1080p fullscreen specification.'
    }
    Add-VerificationPass -Message 'Marker default launch arguments are exact.'
    foreach ($expected in $expectedShortcuts) {
        try {
            $shortcutPath = Get-UqmFullPath -Path $expected.Path
            if (-not (Test-UqmPathInside -Path $shortcutPath -Root $expected.AllowedRoot)) {
                throw "Shortcut is outside its exact expected root: $shortcutPath"
            }
            if (-not (Test-Path -LiteralPath $shortcutPath -PathType Leaf)) {
                throw "Expected shortcut is missing: $shortcutPath"
            }
            $actual = Get-UqmShortcutDetails -Path $shortcutPath
            if (-not (Test-UqmShortcutMatches -Actual $actual -Expected $expected)) {
                throw "Shortcut target, arguments, working directory, or icon differs: $shortcutPath"
            }

            $markerShortcut = $null
            if ($null -ne $marker.PSObject.Properties['Shortcuts']) {
                $markerShortcut = @($marker.Shortcuts) | Where-Object {
                    $_.Kind -eq $expected.Kind -and (Test-UqmPathEqual -Left $_.Path -Right $shortcutPath)
                } | Select-Object -First 1
            }
            if ($null -eq $markerShortcut) {
                throw "Marker does not list the expected shortcut: $shortcutPath"
            }
            if (-not (Test-UqmPathEqual -Left ([string]$markerShortcut.Target) -Right $expected.Target) -or
                -not [string]::Equals([string]$markerShortcut.IconLocation, [string]$expected.IconLocation, [StringComparison]::OrdinalIgnoreCase) -or
                -not (Test-UqmPathEqual -Left ([string]$markerShortcut.WorkingDirectory) -Right $expected.WorkingDirectory) -or
                -not [string]::Equals([string]$markerShortcut.Arguments, [string]$expected.Arguments, [StringComparison]::Ordinal) -or
                [int]$markerShortcut.ResolutionFactor -ne [int]$expected.ResolutionFactor -or
                -not [string]::Equals([string]$markerShortcut.Addon, [string]$expected.Addon, [StringComparison]::Ordinal)) {
                throw "Marker shortcut metadata differs from the shared specification: $shortcutPath"
            }
            Add-VerificationPass -Message "Shortcut is exact: $($expected.Kind)."
        }
        catch {
            Add-VerificationFailure -Message $_.Exception.Message
        }
    }
}
catch {
    Add-VerificationFailure -Message $_.Exception.Message
}

if ($failures.Count -gt 0) {
    throw ("Static installation verification failed with {0} issue(s):`n - {1}" -f
        $failures.Count, ($failures -join "`n - "))
}

$smokeStatus = 'Skipped by request'
$smokeLog = $null
if (-not $SkipSmokeTest) {
    if (-not (Test-Path -LiteralPath $profile)) {
        [void](New-Item -ItemType Directory -Path $profile)
    }
    Assert-UqmNoReparseComponents -Path $profile
    $smokeLog = Join-UqmContainedPath -Root $profile -RelativePath 'uqm-install-smoke.log'
    if (Test-Path -LiteralPath $smokeLog) {
        $smokeLogItem = Get-Item -LiteralPath $smokeLog -Force
        if ($smokeLogItem.PSIsContainer -or
            (($smokeLogItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw "Smoke log path is not a normal managed file: $smokeLog"
        }
        Remove-Item -LiteralPath $smokeLog -Force
    }

    $defaultArguments = Get-UqmLaunchArguments -ResolutionFactor 3 -Addon 'native1080-zh_TW' -ProfileDir $profile -Fullscreen
    $smokeArguments = $defaultArguments + ' -l ' + (Quote-UqmArgument -Value $smokeLog)
    Write-Host "Starting hidden $SmokeTimeoutSeconds-second smoke test..."
    try {
        $process = Start-Process -FilePath $executable -ArgumentList $smokeArguments `
            -WorkingDirectory $install -WindowStyle Hidden -PassThru
    }
    catch {
        throw "Failed to start the installed executable: $($_.Exception.Message)"
    }

    $exitedEarly = $process.WaitForExit($SmokeTimeoutSeconds * 1000)
    if ($exitedEarly) {
        $exitCode = $process.ExitCode
        $logTail = ''
        if (Test-Path -LiteralPath $smokeLog -PathType Leaf) {
            $logTail = (Get-Content -LiteralPath $smokeLog -Tail 30 -ErrorAction SilentlyContinue) -join [Environment]::NewLine
        }
        throw "UQM-HD exited before the smoke-test timeout (exit code $exitCode). Log tail:`n$logTail"
    }

    try {
        Stop-Process -Id $process.Id -Force -ErrorAction Stop
        [void]$process.WaitForExit(5000)
    }
    catch {
        if (-not $process.HasExited) {
            throw "Smoke-test process could not be stopped safely (PID $($process.Id)): $($_.Exception.Message)"
        }
    }

    if (-not (Test-Path -LiteralPath $smokeLog -PathType Leaf)) {
        throw "UQM-HD stayed alive but did not create its requested smoke log: $smokeLog"
    }
    $logText = Get-Content -LiteralPath $smokeLog -Raw -ErrorAction Stop
    if ($logText -match '(?im)^\s*Fatal error\b' -or
        $logText -match '(?im)^\s*(Assertion failed|Aborted)\b') {
        throw "UQM-HD smoke log contains a fatal diagnostic: $smokeLog"
    }
    if ($logText -match 'TFB_DrawCanvas_Rescale_Bilinear:\s*(Tried to deal with unknown BPP|Could not convert)') {
        throw "UQM-HD smoke log contains a failed image-conversion diagnostic: $smokeLog"
    }
    if ($logText -notmatch "Loading addon 'native1080-zh_TW'") {
        throw "UQM-HD smoke test did not load the native 1080p Traditional Chinese add-on: $smokeLog"
    }
    $nativeResolution = Get-UqmNativeResolution
    $nativeResolutionPattern = 'Set the resolution to:\s*' + [regex]::Escape($nativeResolution) + 'x32'
    if ($logText -notmatch $nativeResolutionPattern) {
        throw "UQM-HD smoke test did not initialize the expected $nativeResolution fullscreen surface: $smokeLog"
    }
    if ($logText -notmatch '\(res_cat 3\)') {
        throw "UQM-HD smoke test did not initialize the native supersampling tier (res_cat 3): $smokeLog"
    }
    $smokeStatus = "Passed: process stayed alive for $SmokeTimeoutSeconds seconds, loaded native1080-zh_TW at $nativeResolution with res_cat 3, and logged no fatal diagnostic"
    Add-VerificationPass -Message $smokeStatus
}

[pscustomobject][ordered]@{
    Status = 'Verified'
    InstallRoot = $install
    ProfileDir = $profile
    ManagedFiles = @($marker.Files).Count
    HashesChecked = -not [bool]$SkipHashes
    PacksChecked = $script:UqmPackNames.Count
    ShortcutsChecked = @($expectedShortcuts).Count
    SmokeTest = $smokeStatus
    SmokeLog = $smokeLog
    PassedChecks = $passes.Count
}
