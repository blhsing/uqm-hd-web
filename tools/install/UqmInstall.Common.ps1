Set-StrictMode -Version 2.0

$script:UqmProductId = 'uqm-hd-zh-tw'
$script:UqmMarkerName = '.uqm-hd-zh-tw-install.json'
$script:UqmInstallingMarkerName = '.uqm-hd-zh-tw-installing.json'
$script:UqmPlayerOneRightAltBinding = '1.special.3 = STRING:key RightAlt'
$script:UqmPackNames = @('native1080-zh_TW.uqm')

function Get-UqmFullPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [switch]$MustExist,
        [switch]$MustBeDirectory
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw 'A required path was empty.'
    }
    # All filesystem operations in this installer use -LiteralPath. Windows
    # permits '[' and ']' in real filenames (the stock UQM keyboard font uses
    # `[.png`), even though PowerShell's wildcard parser treats '[' specially.
    # Reject only wildcard characters that Windows itself cannot store.
    if ($Path.IndexOfAny([char[]]@([char]42, [char]63)) -ge 0) {
        throw "Wildcard characters are not allowed in managed paths: $Path"
    }
    if ($Path.IndexOfAny([char[]]@([char]0, [char]10, [char]13, [char]34)) -ge 0) {
        throw "The path contains an unsupported control or quote character: $Path"
    }

    $candidate = [Environment]::ExpandEnvironmentVariables($Path)
    if (-not [IO.Path]::IsPathRooted($candidate)) {
        $candidate = Join-Path -Path (Get-Location).ProviderPath -ChildPath $candidate
    }
    try {
        $full = [IO.Path]::GetFullPath($candidate)
    }
    catch {
        throw "The path is invalid: $Path. $($_.Exception.Message)"
    }

    $volumeRoot = [IO.Path]::GetPathRoot($full)
    if ($full.Length -gt $volumeRoot.Length) {
        $full = $full.TrimEnd([char[]]'\/')
    }

    if ($MustExist -and -not (Test-Path -LiteralPath $full)) {
        throw "The required path does not exist: $full"
    }
    if ($MustBeDirectory -and (Test-Path -LiteralPath $full) -and
        -not (Test-Path -LiteralPath $full -PathType Container)) {
        throw "The path must be a directory: $full"
    }
    return $full
}

function Test-UqmPathEqual {
    param([string]$Left, [string]$Right)
    return [string]::Equals(
        (Get-UqmFullPath -Path $Left),
        (Get-UqmFullPath -Path $Right),
        [StringComparison]::OrdinalIgnoreCase)
}

function Test-UqmPathInside {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Root,
        [switch]$AllowRoot
    )

    $fullPath = Get-UqmFullPath -Path $Path
    $fullRoot = Get-UqmFullPath -Path $Root
    if ([string]::Equals($fullPath, $fullRoot, [StringComparison]::OrdinalIgnoreCase)) {
        return [bool]$AllowRoot
    }
    $prefix = $fullRoot.TrimEnd([char[]]'\/') + [IO.Path]::DirectorySeparatorChar
    return $fullPath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
}

function Assert-UqmNotVolumeRoot {
    param([Parameter(Mandatory = $true)][string]$Path, [string]$Role = 'Destination')
    $full = Get-UqmFullPath -Path $Path
    $volumeRoot = [IO.Path]::GetPathRoot($full)
    if ([string]::Equals($full, $volumeRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "$Role cannot be a filesystem volume root: $full"
    }

    $protected = @(
        $env:SystemRoot,
        $env:ProgramData,
        $env:USERPROFILE,
        [Environment]::GetFolderPath([Environment+SpecialFolder]::Windows),
        [Environment]::GetFolderPath([Environment+SpecialFolder]::System)
    ) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    foreach ($item in $protected) {
        if (Test-UqmPathEqual -Left $full -Right $item) {
            throw "$Role cannot replace a protected directory: $full"
        }
    }
}

function Assert-UqmNoReparseComponents {
    param([Parameter(Mandatory = $true)][string]$Path)

    $full = Get-UqmFullPath -Path $Path
    $volumeRoot = [IO.Path]::GetPathRoot($full)
    $current = $volumeRoot
    $remainder = $full.Substring($volumeRoot.Length)
    foreach ($part in $remainder.Split([char[]]'\/', [StringSplitOptions]::RemoveEmptyEntries)) {
        $current = Join-Path -Path $current -ChildPath $part
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Managed paths cannot cross a reparse point: $current"
            }
        }
    }
}

function Assert-UqmDirectoryComponents {
    param([Parameter(Mandatory = $true)][string]$Path)

    $full = Get-UqmFullPath -Path $Path
    $volumeRoot = [IO.Path]::GetPathRoot($full)
    $current = $volumeRoot
    $remainder = $full.Substring($volumeRoot.Length)
    foreach ($part in $remainder.Split([char[]]'\/', [StringSplitOptions]::RemoveEmptyEntries)) {
        $current = Join-Path -Path $current -ChildPath $part
        if (-not (Test-Path -LiteralPath $current)) {
            continue
        }
        $item = Get-Item -LiteralPath $current -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Managed paths cannot cross a reparse point: $current"
        }
        if (-not $item.PSIsContainer) {
            throw "A normal file blocks a required directory path: $current"
        }
    }
}

function Assert-UqmFileDestinationPreflight {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$ManagedRoot,
        [switch]$ParentAlreadyChecked
    )

    $full = Get-UqmFullPath -Path $Path
    if (-not (Test-UqmPathInside -Path $full -Root $ManagedRoot)) {
        throw "File destination escaped the exact managed root: $full"
    }
    $parent = [IO.Path]::GetDirectoryName($full)
    if (-not $ParentAlreadyChecked) {
        Assert-UqmDirectoryComponents -Path $parent
    }
    if (Test-Path -LiteralPath $full) {
        $item = Get-Item -LiteralPath $full -Force
        if ($item.PSIsContainer) {
            throw "A directory occupies a required file path: $full"
        }
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing to replace a file reparse point: $full"
        }
    }
}

function Assert-UqmManagedFilePlanDestinations {
    param(
        [Parameter(Mandatory = $true)][string]$ManagedRoot,
        [Parameter(Mandatory = $true)][string[]]$RelativePaths
    )

    $root = Get-UqmFullPath -Path $ManagedRoot -MustBeDirectory
    Assert-UqmDirectoryComponents -Path $root
    $rootPrefix = $root.TrimEnd([char[]]'\/') + [IO.Path]::DirectorySeparatorChar
    $plannedFiles = @{}
    $plannedDirectories = @{}
    foreach ($relativePath in $RelativePaths) {
        if ([string]::IsNullOrWhiteSpace($relativePath) -or
            [IO.Path]::IsPathRooted($relativePath) -or
            $relativePath.IndexOfAny([char[]]@([char]0, [char]10, [char]13)) -ge 0) {
            throw "Unsafe managed-file plan path: $relativePath"
        }
        $portable = $relativePath.Replace('\', '/')
        $candidate = [IO.Path]::GetFullPath(
            [IO.Path]::Combine($root, $portable.Replace('/', [IO.Path]::DirectorySeparatorChar)))
        if (-not $candidate.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Managed-file plan path escaped its exact root: $relativePath"
        }
        $plannedFiles[$portable] = $true
        $parent = [IO.Path]::GetDirectoryName($portable.Replace('/', [IO.Path]::DirectorySeparatorChar))
        while (-not [string]::IsNullOrEmpty($parent)) {
            $plannedDirectories[$parent.Replace('\', '/')] = $true
            $parent = [IO.Path]::GetDirectoryName($parent)
        }
    }

    if (-not (Test-Path -LiteralPath $root)) {
        return
    }
    foreach ($item in Get-ChildItem -LiteralPath $root -Force -Recurse) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "The managed install tree contains a reparse point: $($item.FullName)"
        }
        $relative = $item.FullName.Substring($rootPrefix.Length).Replace('\', '/')
        if ($item.PSIsContainer -and $plannedFiles.ContainsKey($relative)) {
            throw "A directory occupies a required managed-file path: $($item.FullName)"
        }
        if (-not $item.PSIsContainer -and $plannedDirectories.ContainsKey($relative)) {
            throw "A normal file blocks a required managed directory: $($item.FullName)"
        }
    }
}

function Get-UqmRelativePath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Root
    )
    $fullPath = Get-UqmFullPath -Path $Path
    $fullRoot = Get-UqmFullPath -Path $Root
    $prefix = $fullRoot.TrimEnd([char[]]'\/') + [IO.Path]::DirectorySeparatorChar
    if (-not $fullPath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is not below the expected root. Path: $fullPath Root: $fullRoot"
    }
    return $fullPath.Substring($prefix.Length)
}

function Join-UqmContainedPath {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$RelativePath
    )
    if ([IO.Path]::IsPathRooted($RelativePath) -or
        [string]::IsNullOrWhiteSpace($RelativePath) -or
        $RelativePath.IndexOfAny([char[]]@([char]0, [char]10, [char]13)) -ge 0) {
        throw "Unsafe relative path: $RelativePath"
    }
    $fullRoot = Get-UqmFullPath -Path $Root
    $combined = Get-UqmFullPath -Path (Join-Path -Path $fullRoot -ChildPath $RelativePath)
    if (-not (Test-UqmPathInside -Path $combined -Root $fullRoot)) {
        throw "Relative path escapes its managed root: $RelativePath"
    }
    return $combined
}

function Get-UqmSha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    $full = Get-UqmFullPath -Path $Path -MustExist
    $stream = [IO.File]::Open($full, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try {
        $algorithm = [Security.Cryptography.SHA256]::Create()
        try {
            $bytes = $algorithm.ComputeHash($stream)
            return ([BitConverter]::ToString($bytes)).Replace('-', '').ToLowerInvariant()
        }
        finally {
            $algorithm.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
}

function ConvertTo-UqmHexString {
    param([Parameter(Mandatory = $true)][byte[]]$Bytes)
    return ([BitConverter]::ToString($Bytes)).Replace('-', '')
}

function Move-UqmStagedFileIntoPlace {
    param(
        [Parameter(Mandatory = $true)][string]$StagedPath,
        [Parameter(Mandatory = $true)][string]$DestinationPath
    )
    $staged = Get-UqmFullPath -Path $StagedPath -MustExist
    $destination = Get-UqmFullPath -Path $DestinationPath
    $stagedParent = [IO.Path]::GetDirectoryName($staged)
    $destinationParent = [IO.Path]::GetDirectoryName($destination)
    if (-not (Test-UqmPathEqual -Left $stagedParent -Right $destinationParent)) {
        throw 'A staged replacement must be on the same directory and volume as its exact destination.'
    }
    if (Test-Path -LiteralPath $destination) {
        $destinationItem = Get-Item -LiteralPath $destination -Force
        if ($destinationItem.PSIsContainer -or
            (($destinationItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw "Refusing to replace a destination that is not a normal file: $destination"
        }
        $backup = Join-Path -Path $destinationParent -ChildPath ('.uqm-backup-' + [Guid]::NewGuid().ToString('N') + '.tmp')
        try {
            [IO.File]::Replace($staged, $destination, $backup, $true)
        }
        finally {
            if (Test-Path -LiteralPath $backup) {
                Remove-Item -LiteralPath $backup -Force
            }
        }
    }
    else {
        [IO.File]::Move($staged, $destination)
    }
}

function Quote-UqmArgument {
    param([Parameter(Mandatory = $true)][string]$Value)
    if ($Value.IndexOfAny([char[]]@([char]0, [char]10, [char]13, [char]34)) -ge 0) {
        throw 'A command-line path contains an unsupported control or quote character.'
    }
    return '"' + $Value + '"'
}

function Get-UqmNativeResolution {
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        $bounds = [Windows.Forms.Screen]::PrimaryScreen.Bounds
        if ($bounds.Width -lt 1 -or $bounds.Height -lt 1) {
            throw 'Windows returned an empty primary-screen rectangle.'
        }
        return ('{0}x{1}' -f $bounds.Width, $bounds.Height)
    }
    catch {
        throw "Unable to detect the primary display's native resolution. $($_.Exception.Message)"
    }
}

function Get-UqmLaunchArguments {
    param(
        [Parameter(Mandatory = $true)][ValidateSet(3)][int]$ResolutionFactor,
        [Parameter(Mandatory = $true)][ValidateSet('native1080-zh_TW')][string]$Addon,
        [Parameter(Mandatory = $true)][string]$ProfileDir,
        [switch]$Fullscreen
    )
    $profile = Get-UqmFullPath -Path $ProfileDir
    if ($Fullscreen) {
        $nativeResolution = Get-UqmNativeResolution
        return ('-o -r {0} -f -k -c bilinear --resfactor=3 -C {1} --addon native1080-zh_TW' -f
            $nativeResolution, (Quote-UqmArgument -Value $profile))
    }
    $nativeResolution = Get-UqmNativeResolution
    return ('-o -r {0} -w -k -c bilinear --resfactor=3 -C {1} --addon native1080-zh_TW' -f
        $nativeResolution, (Quote-UqmArgument -Value $profile))
}

function Get-UqmShortcutSpecifications {
    param(
        [Parameter(Mandatory = $true)][string]$InstallRoot,
        [Parameter(Mandatory = $true)][string]$ProfileDir
    )

    $install = Get-UqmFullPath -Path $InstallRoot
    $profile = Get-UqmFullPath -Path $ProfileDir
    $exe = Join-UqmContainedPath -Root $install -RelativePath 'uqm.exe'
    $icon = Join-UqmContainedPath -Root $install -RelativePath 'uqm-hd-zh-tw.ico'
    $desktop = Get-UqmFullPath -Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::DesktopDirectory))
    $programs = Get-UqmFullPath -Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::Programs))
    if ([string]::IsNullOrWhiteSpace($desktop) -or [string]::IsNullOrWhiteSpace($programs)) {
        throw 'Windows did not provide the current user Desktop or Start Menu Programs path.'
    }

    # WScript.Shell can expose an ANSI-only CreateShortcut implementation on
    # otherwise Unicode-capable Windows installations.  Keep shortcut paths in
    # ASCII so creation remains reliable regardless of the system code page;
    # the localized game data and UI remain Traditional Chinese.
    $desktopLeaf = 'The Ur-Quan Masters HD - Traditional Chinese.lnk'
    $startLeaf = 'The Ur-Quan Masters HD - Traditional Chinese.lnk'

    return @(
        [pscustomobject][ordered]@{
            Kind = 'desktop-default'
            Path = Join-Path -Path $desktop -ChildPath $desktopLeaf
            Target = $exe
            IconLocation = $icon + ',0'
            Arguments = Get-UqmLaunchArguments -ResolutionFactor 3 -Addon 'native1080-zh_TW' -ProfileDir $profile -Fullscreen
            WorkingDirectory = $install
            ResolutionFactor = 3
            Addon = 'native1080-zh_TW'
            AllowedRoot = $desktop
        },
        [pscustomobject][ordered]@{
            Kind = 'start-menu-fullscreen'
            Path = Join-Path -Path $programs -ChildPath $startLeaf
            Target = $exe
            IconLocation = $icon + ',0'
            Arguments = Get-UqmLaunchArguments -ResolutionFactor 3 -Addon 'native1080-zh_TW' -ProfileDir $profile -Fullscreen
            WorkingDirectory = $install
            ResolutionFactor = 3
            Addon = 'native1080-zh_TW'
            AllowedRoot = $programs
        }
    )
}

function Get-UqmShortcutDetails {
    param([Parameter(Mandatory = $true)][string]$Path)
    $full = Get-UqmFullPath -Path $Path -MustExist
    if (-not $full.EndsWith('.lnk', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Shortcut path must end in .lnk: $full"
    }

    $shell = New-Object -ComObject WScript.Shell
    try {
        $shortcut = $shell.CreateShortcut($full)
        try {
            return [pscustomobject][ordered]@{
                Path = $full
                Target = $shortcut.TargetPath
                Arguments = $shortcut.Arguments
                WorkingDirectory = $shortcut.WorkingDirectory
                IconLocation = $shortcut.IconLocation
            }
        }
        finally {
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shortcut)
        }
    }
    finally {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)
    }
}

function Test-UqmShortcutMatches {
    param(
        [Parameter(Mandatory = $true)]$Actual,
        [Parameter(Mandatory = $true)]$Expected
    )
    if (-not (Test-UqmPathEqual -Left $Actual.Target -Right $Expected.Target)) { return $false }
    if (-not (Test-UqmPathEqual -Left $Actual.WorkingDirectory -Right $Expected.WorkingDirectory)) { return $false }
    if (-not [string]::Equals($Actual.Arguments, $Expected.Arguments, [StringComparison]::Ordinal)) { return $false }
    if (-not [string]::Equals($Actual.IconLocation, $Expected.IconLocation, [StringComparison]::OrdinalIgnoreCase)) { return $false }
    return $true
}

function Write-UqmShortcut {
    param(
        [Parameter(Mandatory = $true)]$Specification,
        [switch]$AllowManagedReplacement
    )

    $path = Get-UqmFullPath -Path $Specification.Path
    $allowedRoot = Get-UqmFullPath -Path $Specification.AllowedRoot
    if (-not (Test-UqmPathInside -Path $path -Root $allowedRoot)) {
        throw "Shortcut is outside its exact allowed root: $path"
    }
    if (-not $path.EndsWith('.lnk', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Shortcut path must end in .lnk: $path"
    }
    Assert-UqmNoReparseComponents -Path ([IO.Path]::GetDirectoryName($path))

    if (Test-Path -LiteralPath $path) {
        $existingItem = Get-Item -LiteralPath $path -Force
        if (($existingItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Refusing to replace a shortcut reparse point: $path"
        }
        $existingMatches = $false
        try {
            $existing = Get-UqmShortcutDetails -Path $path
            $existingMatches = Test-UqmShortcutMatches -Actual $existing -Expected $Specification
        }
        catch {
            if (-not $AllowManagedReplacement) {
                throw "An unmanaged shortcut exists but cannot be validated: $path. $($_.Exception.Message)"
            }
        }
        if ($existingMatches) {
            return 'unchanged'
        }
        if (-not $AllowManagedReplacement) {
            throw "An unmanaged shortcut already exists with different settings: $path"
        }
    }

    $directory = [IO.Path]::GetDirectoryName($path)
    if (-not (Test-Path -LiteralPath $directory)) {
        [void](New-Item -ItemType Directory -Path $directory)
    }
    $temporary = Join-Path -Path $directory -ChildPath ('.uqm-shortcut-' + [Guid]::NewGuid().ToString('N') + '.lnk')
    $shell = New-Object -ComObject WScript.Shell
    try {
        $shortcut = $shell.CreateShortcut($temporary)
        try {
            $shortcut.TargetPath = $Specification.Target
            $shortcut.Arguments = $Specification.Arguments
            $shortcut.WorkingDirectory = $Specification.WorkingDirectory
            $shortcut.IconLocation = $Specification.IconLocation
            $shortcut.Description = 'The Ur-Quan Masters HD - Traditional Chinese'
            $shortcut.Save()
        }
        finally {
            [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shortcut)
        }
    }
    finally {
        [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell)
    }

    try {
        $written = Get-UqmShortcutDetails -Path $temporary
        if (-not (Test-UqmShortcutMatches -Actual $written -Expected $Specification)) {
            throw "The staged shortcut did not retain its exact target, arguments, working directory, and icon: $path"
        }
        Move-UqmStagedFileIntoPlace -StagedPath $temporary -DestinationPath $path
    }
    finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
    return 'written'
}

function Assert-UqmArchive {
    param([Parameter(Mandatory = $true)][string]$Path)
    $full = Get-UqmFullPath -Path $Path -MustExist
    if ((Get-Item -LiteralPath $full).Length -le 0) {
        throw "The UQM add-on archive is empty: $full"
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    try {
        $archive = [IO.Compression.ZipFile]::OpenRead($full)
    }
    catch {
        throw "The UQM add-on is not a readable ZIP-compatible archive: $full. $($_.Exception.Message)"
    }
    try {
        if ($archive.Entries.Count -eq 0) {
            throw "The UQM add-on archive has no entries: $full"
        }
        foreach ($entry in $archive.Entries) {
            $name = $entry.FullName.Replace('\', '/')
            if ($name.StartsWith('/') -or $name -match '(^|/)\.\.(/|$)' -or $name.IndexOf([char]0) -ge 0) {
                throw "The UQM add-on contains an unsafe member path: $name"
            }
        }
        return $archive.Entries.Count
    }
    finally {
        $archive.Dispose()
    }
}

function Write-UqmUtf8JsonAtomic {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)]$Value,
        [int]$Depth = 8
    )
    $full = Get-UqmFullPath -Path $Path
    $parent = [IO.Path]::GetDirectoryName($full)
    if (-not (Test-Path -LiteralPath $parent)) {
        [void](New-Item -ItemType Directory -Path $parent)
    }
    $temporary = Join-Path -Path $parent -ChildPath ('.uqm-json-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    $encoding = New-Object Text.UTF8Encoding($false)
    try {
        $json = $Value | ConvertTo-Json -Depth $Depth
        [IO.File]::WriteAllText($temporary, $json + [Environment]::NewLine, $encoding)
        Move-UqmStagedFileIntoPlace -StagedPath $temporary -DestinationPath $full
    }
    finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
}

function Get-UqmStaleManagedFilePlan {
    param(
        $PreviousMarker,
        [Parameter(Mandatory = $true)][string[]]$CurrentRelativePaths,
        [Parameter(Mandatory = $true)][string]$InstallRoot
    )

    if ($null -eq $PreviousMarker) {
        return @()
    }

    $install = Get-UqmFullPath -Path $InstallRoot -MustExist -MustBeDirectory
    Assert-UqmDirectoryComponents -Path $install
    $currentPaths = @{}
    foreach ($relativePath in $CurrentRelativePaths) {
        [void](Join-UqmContainedPath -Root $install -RelativePath $relativePath)
        $currentPaths[$relativePath] = $true
    }

    if ($null -eq $PreviousMarker.PSObject.Properties['Files']) {
        if ([string]::Equals([string]$PreviousMarker.State, 'complete', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'The previous complete marker has no managed-file manifest.'
        }
        return @()
    }

    $seenPaths = @{}
    $staleFiles = New-Object System.Collections.ArrayList
    foreach ($entry in @($PreviousMarker.Files)) {
        foreach ($property in @('Path', 'Length', 'Sha256')) {
            if ($null -eq $entry.PSObject.Properties[$property]) {
                throw "A previous managed-file entry is missing required property: $property"
            }
        }
        $relativePath = [string]$entry.Path
        if ([string]::IsNullOrWhiteSpace($relativePath)) {
            throw 'A previous managed-file entry has an empty path.'
        }
        $fullPath = Join-UqmContainedPath -Root $install -RelativePath $relativePath
        if ($seenPaths.ContainsKey($relativePath)) {
            throw "The previous marker contains a duplicate case-insensitive path: $relativePath"
        }
        $seenPaths[$relativePath] = $true
        if ($currentPaths.ContainsKey($relativePath)) {
            continue
        }

        try { $expectedLength = [Int64]$entry.Length }
        catch { throw "The previous marker has an invalid file length: $relativePath" }
        if ($expectedLength -lt 0) {
            throw "The previous marker has a negative file length: $relativePath"
        }
        $expectedHash = ([string]$entry.Sha256).ToLowerInvariant()
        if (-not [Text.RegularExpressions.Regex]::IsMatch($expectedHash, '\A[0-9a-f]{64}\z')) {
            throw "The previous marker has an invalid file SHA-256: $relativePath"
        }
        if (-not (Test-Path -LiteralPath $fullPath)) {
            continue
        }
        Assert-UqmFileDestinationPreflight -Path $fullPath -ManagedRoot $install
        $item = Get-Item -LiteralPath $fullPath -Force
        if ([Int64]$item.Length -ne $expectedLength -or
            -not [string]::Equals(
                (Get-UqmSha256 -Path $fullPath),
                $expectedHash,
                [StringComparison]::OrdinalIgnoreCase)) {
            throw "A previously managed file changed; refusing to delete it as stale: $relativePath"
        }
        [void]$staleFiles.Add([pscustomobject][ordered]@{
            RelativePath = $relativePath
            FullPath = $fullPath
            Length = $expectedLength
            Sha256 = $expectedHash
        })
    }
    return @($staleFiles)
}

function Remove-UqmStaleManagedFiles {
    param(
        [Parameter(Mandatory = $true)][object[]]$Files,
        [Parameter(Mandatory = $true)][string]$InstallRoot
    )

    $install = Get-UqmFullPath -Path $InstallRoot -MustExist -MustBeDirectory
    $removed = 0
    foreach ($entry in $Files) {
        $fullPath = Join-UqmContainedPath -Root $install -RelativePath ([string]$entry.RelativePath)
        if (-not (Test-UqmPathEqual -Left $fullPath -Right ([string]$entry.FullPath))) {
            throw "A stale-file plan changed its destination: $($entry.RelativePath)"
        }
        if (-not (Test-Path -LiteralPath $fullPath)) {
            continue
        }
        Assert-UqmFileDestinationPreflight -Path $fullPath -ManagedRoot $install
        $item = Get-Item -LiteralPath $fullPath -Force
        if ([Int64]$item.Length -ne [Int64]$entry.Length -or
            -not [string]::Equals(
                (Get-UqmSha256 -Path $fullPath),
                [string]$entry.Sha256,
                [StringComparison]::OrdinalIgnoreCase)) {
            throw "A stale managed file changed after preflight; refusing to delete it: $($entry.RelativePath)"
        }
        Remove-Item -LiteralPath $fullPath -Force
        if (Test-Path -LiteralPath $fullPath) {
            throw "A stale managed file could not be removed: $($entry.RelativePath)"
        }
        $removed++
    }
    return $removed
}

function Assert-UqmPlayerOneRightAltBindingTarget {
    param([Parameter(Mandatory = $true)][string]$ProfileDir)

    $profile = Get-UqmFullPath -Path $ProfileDir -MustBeDirectory
    Assert-UqmNotVolumeRoot -Path $profile -Role 'ProfileDir'
    Assert-UqmDirectoryComponents -Path $profile
    $path = Join-UqmContainedPath -Root $profile -RelativePath 'flight.cfg'
    Assert-UqmFileDestinationPreflight -Path $path -ManagedRoot $profile
}

function Set-UqmPlayerOneRightAltBinding {
    param([Parameter(Mandatory = $true)][string]$ProfileDir)

    $profile = Get-UqmFullPath -Path $ProfileDir -MustExist -MustBeDirectory
    Assert-UqmPlayerOneRightAltBindingTarget -ProfileDir $profile
    $path = Join-UqmContainedPath -Root $profile -RelativePath 'flight.cfg'
    $encoding = New-Object Text.UTF8Encoding($false)
    $text = ''
    if (Test-Path -LiteralPath $path) {
        $item = Get-Item -LiteralPath $path -Force
        if ($item.PSIsContainer -or
            (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
            throw "Refusing to update a flight configuration that is not a normal file: $path"
        }
        $text = [IO.File]::ReadAllText($path, $encoding)
    }

    $bindingPattern = '(?m)^[ \t]*1\.special\.3[ \t]*=[^\r\n]*(?:\r\n|\n|\r)?'
    $matches = [Text.RegularExpressions.Regex]::Matches($text, $bindingPattern)
    if ($matches.Count -eq 1 -and
        $matches[0].Value.Trim() -ceq $script:UqmPlayerOneRightAltBinding) {
        return 'unchanged'
    }

    $newline = if ($text.Contains("`r`n")) { "`r`n" } else { "`n" }
    $updated = [Text.RegularExpressions.Regex]::Replace($text, $bindingPattern, '')
    if ($updated.Length -gt 0 -and
        -not ($updated.EndsWith("`r") -or $updated.EndsWith("`n"))) {
        $updated += $newline
    }
    $updated += $script:UqmPlayerOneRightAltBinding + $newline

    $temporary = Join-Path -Path $profile -ChildPath `
        ('.uqm-flight-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    try {
        [IO.File]::WriteAllText($temporary, $updated, $encoding)
        Move-UqmStagedFileIntoPlace -StagedPath $temporary -DestinationPath $path
    }
    finally {
        if (Test-Path -LiteralPath $temporary) {
            Remove-Item -LiteralPath $temporary -Force
        }
    }
    return 'written'
}

function Read-UqmMarkerFile {
    param(
        [Parameter(Mandatory = $true)][string]$InstallRoot,
        [Parameter(Mandatory = $true)][string]$MarkerName
    )
    $install = Get-UqmFullPath -Path $InstallRoot
    $markerPath = Join-UqmContainedPath -Root $install -RelativePath $MarkerName
    if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
        return $null
    }
    $markerItem = Get-Item -LiteralPath $markerPath -Force
    if (($markerItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "The existing installation marker is a reparse point: $markerPath"
    }
    try {
        $marker = Get-Content -LiteralPath $markerPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        throw "The existing installation marker is not valid JSON: $markerPath. $($_.Exception.Message)"
    }
    if ($marker.SchemaVersion -ne 1 -or $marker.ProductId -ne $script:UqmProductId) {
        throw "The existing marker is not for this installer: $markerPath"
    }
    if (-not (Test-UqmPathEqual -Left $marker.InstallRoot -Right $install)) {
        throw "The installation marker names a different install root: $($marker.InstallRoot)"
    }
    return $marker
}

function Read-UqmInstallMarker {
    param([Parameter(Mandatory = $true)][string]$InstallRoot)
    return (Read-UqmMarkerFile -InstallRoot $InstallRoot -MarkerName $script:UqmMarkerName)
}

function Read-UqmInstallingMarker {
    param([Parameter(Mandatory = $true)][string]$InstallRoot)
    $marker = Read-UqmMarkerFile -InstallRoot $InstallRoot -MarkerName $script:UqmInstallingMarkerName
    if ($null -ne $marker -and
        -not [string]::Equals([string]$marker.State, 'installing', [StringComparison]::OrdinalIgnoreCase)) {
        throw 'The pending-install marker does not have state installing.'
    }
    return $marker
}
