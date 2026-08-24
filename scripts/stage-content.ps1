[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceRoot,
    [switch]$Minimal
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$source = (Resolve-Path -LiteralPath $SourceRoot).Path
$target = Join-Path $projectRoot 'engine\content'
$engineRoot = (Resolve-Path (Join-Path $projectRoot 'engine')).Path
$targetFull = [IO.Path]::GetFullPath($target)
$workRoot = Join-Path $projectRoot 'work'
$addonTarget = [IO.Path]::GetFullPath((Join-Path $workRoot 'web-addons'))

if (-not $targetFull.StartsWith($engineRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to stage content outside the project engine directory: $targetFull"
}
if (-not $addonTarget.StartsWith([IO.Path]::GetFullPath($workRoot) + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to stage add-ons outside the project work directory: $addonTarget"
}

$baseArchive = 'base.uqm'
$baseFiles = @('menu.key', 'uqm.key', 'uqm.rmp', 'version')
$addonFiles = @(
    '3domusic.zip',
    '3dovideo.zip',
    '3dovoice.zip',
    'hires4x.zip',
    'native1080-zh_TW.uqm'
)

function Remove-UqmVisibleEditionWording {
    param([Parameter(Mandatory = $true)][string]$ArchivePath)

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $utf8 = [Text.UTF8Encoding]::new($false)
    $archive = [IO.Compression.ZipFile]::Open(
        $ArchivePath,
        [IO.Compression.ZipArchiveMode]::Update
    )
    try {
        $entries = @($archive.Entries | Where-Object { $_.FullName.EndsWith('.txt') })
        foreach ($entry in $entries) {
            $reader = [IO.StreamReader]::new($entry.Open(), $utf8, $true)
            try {
                $original = $reader.ReadToEnd()
            } finally {
                $reader.Dispose()
            }

            $updated = $original.Replace('The Ur-Quan Masters HD', 'The Ur-Quan Masters')
            $updated = $updated.Replace('Ur-Quan Masters HD', 'Ur-Quan Masters')
            $updated = $updated.Replace('UQM-HD', 'UQM')
            $updated = $updated.Replace('Web Edition', '')
            $updated = $updated.Replace('較高解析度', '較細緻畫面')
            $updated = $updated.Replace('高解析度', '解析度')
            $updated = $updated.Replace('烏爾關霸主 HD', '烏爾關霸主')
            $updated = $updated.Replace('網頁版', '')

            if ($updated -eq $original) {
                continue
            }

            $stream = $entry.Open()
            try {
                $stream.SetLength(0)
                $writer = [IO.StreamWriter]::new($stream, $utf8, 1024, $true)
                try {
                    $writer.Write($updated)
                    $writer.Flush()
                } finally {
                    $writer.Dispose()
                }
            } finally {
                $stream.Dispose()
            }
        }
    } finally {
        $archive.Dispose()
    }
}

foreach ($name in @($baseArchive) + $baseFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $source $name))) {
        throw "Required upstream content is missing: $name"
    }
}

if (-not $Minimal) {
    foreach ($name in $addonFiles) {
        if (-not (Test-Path -LiteralPath (Join-Path $source 'addons' $name))) {
            throw "Required full-game add-on is missing: $name"
        }
    }
}

if (Test-Path -LiteralPath $targetFull) {
    $resolvedTarget = (Resolve-Path -LiteralPath $targetFull).Path
    if (-not $resolvedTarget.StartsWith($engineRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clear unexpected content target: $resolvedTarget"
    }
    Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
}
if (Test-Path -LiteralPath $addonTarget) {
    $resolvedAddons = (Resolve-Path -LiteralPath $addonTarget).Path
    if (-not $resolvedAddons.StartsWith([IO.Path]::GetFullPath($workRoot) + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clear unexpected add-on target: $resolvedAddons"
    }
    Remove-Item -LiteralPath $resolvedAddons -Recurse -Force
}

New-Item -ItemType Directory -Path $targetFull -Force | Out-Null
foreach ($name in $baseFiles) {
    Copy-Item -LiteralPath (Join-Path $source $name) -Destination $targetFull
}
$packagesTarget = Join-Path $targetFull 'packages'
New-Item -ItemType Directory -Path $packagesTarget -Force | Out-Null
$basePackageTarget = Join-Path $packagesTarget $baseArchive
Copy-Item -LiteralPath (Join-Path $source $baseArchive) -Destination $basePackageTarget
Remove-UqmVisibleEditionWording -ArchivePath $basePackageTarget

if (-not $Minimal) {
    New-Item -ItemType Directory -Path $addonTarget -Force | Out-Null
    foreach ($name in $addonFiles) {
        Copy-Item -LiteralPath (Join-Path $source 'addons' $name) -Destination $addonTarget
    }
    Remove-UqmVisibleEditionWording -ArchivePath (Join-Path $addonTarget 'native1080-zh_TW.uqm')
}

$files = @(
    Get-ChildItem -LiteralPath $targetFull -File -Recurse
    if (Test-Path -LiteralPath $addonTarget) {
        Get-ChildItem -LiteralPath $addonTarget -File -Recurse
    }
) | Sort-Object FullName
$manifest = @(
    foreach ($file in $files) {
        [pscustomobject]@{
            path = if ($file.FullName.StartsWith($targetFull, [StringComparison]::OrdinalIgnoreCase)) {
                [IO.Path]::GetRelativePath($targetFull, $file.FullName).Replace('\', '/')
            } else {
                'addons/' + $file.Name
            }
            bytes = $file.Length
            sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }
)

$manifestPath = Join-Path $workRoot 'web-content-manifest.json'
New-Item -ItemType Directory -Path $workRoot -Force | Out-Null
$manifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $manifestPath -Encoding utf8
$totalMiB = (($files | Measure-Object Length -Sum).Sum) / 1MB
Write-Host "Staged $($files.Count) content files ($($totalMiB.ToString('N1')) MiB)."
