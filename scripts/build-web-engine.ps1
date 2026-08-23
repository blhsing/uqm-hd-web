[CmdletBinding()]
param(
    [string]$EmsdkRoot = 'C:\Tools\emsdk',
    [string]$MsysBash = 'C:\Tools\msys64\usr\bin\bash.exe',
    [int]$Jobs = [Math]::Max(2, [Environment]::ProcessorCount),
    [switch]$SkipConfigure
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$engineRoot = (Resolve-Path (Join-Path $projectRoot 'engine')).Path
$contentRoot = Join-Path $engineRoot 'content'
$addonStage = Join-Path $projectRoot 'work\web-addons'
$emsdkEnv = Join-Path $EmsdkRoot 'emsdk_env.bat'

if (-not (Test-Path -LiteralPath $emsdkEnv)) {
    throw "Emscripten SDK was not found at $EmsdkRoot"
}
if (-not (Test-Path -LiteralPath $MsysBash)) {
    throw "MSYS2 bash was not found at $MsysBash"
}
if (-not (Test-Path -LiteralPath (Join-Path $contentRoot 'packages\base.uqm'))) {
    throw 'Stage the official game content before building the browser engine.'
}

function Convert-ToMsysPath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "Cannot convert path to MSYS format: $full"
    }
    return '/' + $Matches[1].ToLowerInvariant() + '/' + $Matches[2].Replace('\', '/')
}

$engineMsys = Convert-ToMsysPath $engineRoot
$msysBashWindows = [IO.Path]::GetFullPath($MsysBash).Replace('\', '/')
$buildSteps = @("cd '$engineMsys'")
if (-not $SkipConfigure) {
    $buildSteps += 'cp wasm/config.state.expected config.state'
    $buildSteps += "printf '\n' | emconfigure '$msysBashWindows' ./build.sh uqm config"
}
$buildSteps += "MAKEFLAGS=-j$Jobs ./build.sh uqm"
$buildCommands = $buildSteps -join ' && '

$command = 'call "{0}" >nul && "{1}" -c "{2}"' -f $emsdkEnv, $MsysBash, $buildCommands
& $env:ComSpec /d /s /c $command
if ($LASTEXITCODE -ne 0) {
    throw "WebAssembly engine build failed with exit code $LASTEXITCODE"
}

$outputDirectory = Join-Path $projectRoot 'public\game'
$publicRoot = (Resolve-Path (Join-Path $projectRoot 'public')).Path
$outputFull = [IO.Path]::GetFullPath($outputDirectory)
if (-not $outputFull.StartsWith($publicRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to replace unexpected game output directory: $outputFull"
}
if (Test-Path -LiteralPath $outputFull) {
    $resolvedOutput = (Resolve-Path -LiteralPath $outputFull).Path
    if (-not $resolvedOutput.StartsWith($publicRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clear unexpected game output directory: $resolvedOutput"
    }
    Remove-Item -LiteralPath $resolvedOutput -Recurse -Force
}
New-Item -ItemType Directory -Path $outputFull -Force | Out-Null

$artifactNames = @(
    'uqm-hd.html',
    'uqm-hd.js',
    'uqm-hd.wasm',
    'uqm-hd.data',
    'uqm-hd.worker.js'
)
$artifacts = Get-ChildItem -LiteralPath $engineRoot -File |
    Where-Object { $_.Name -in $artifactNames }
if (-not ($artifacts | Where-Object Name -eq 'uqm-hd.html')) {
    throw 'The build completed without producing uqm-hd.html.'
}
$artifacts | Copy-Item -Destination $outputFull

if (Test-Path -LiteralPath $addonStage) {
    $addonOutput = Join-Path $outputFull 'content\addons'
    New-Item -ItemType Directory -Path $addonOutput -Force | Out-Null
    Get-ChildItem -LiteralPath $addonStage -File | Copy-Item -Destination $addonOutput
}

Write-Host "Browser engine copied to $outputFull"
