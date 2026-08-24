[CmdletBinding()]
param(
    [string]$AppName = 'test-officialWebSite',
    [string]$ResourceGroup = 'OfficialWebsite',
    [string]$SubscriptionId
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$output = Join-Path $projectRoot 'out'
$dist = Join-Path $projectRoot 'dist'
$archive = Join-Path $dist 'starcontrol2-vapp.zip'
$addonRoot = Join-Path $projectRoot 'public\game\content\addons'
$assetSpecs = @(
    [pscustomobject]@{ Name = 'hires4x.zip'; Bytes = 369756672; Sha256 = '76af440bd845a63bd42b88913347374eb62c40c149d0bea37045a10bd0bd6618' },
    [pscustomobject]@{ Name = 'native1080-zh_TW.uqm'; Bytes = 189687374; Sha256 = 'f24d1f55e326fe20bb577c53eb12836ecff71af7a8b34ea2520537ec4ef1aef2' },
    [pscustomobject]@{ Name = '3dovoice.zip'; Bytes = 146438532; Sha256 = 'a14dc7d655297e1b6c6eedc2a4dee30a164646e6525e353bb7fdc5da75232b09' },
    [pscustomobject]@{ Name = '3domusic.zip'; Bytes = 21934569; Sha256 = '7142332040c13a153856d22487aaf82e6b30fc4d22333bcf7607712843bca689' }
)

if (-not (Test-Path -LiteralPath (Join-Path $output 'index.html'))) {
    throw 'Run npm run build:azure before deployment.'
}
if (-not (Test-Path -LiteralPath (Join-Path $output 'game\uqm-hd.html'))) {
    throw 'Build and stage the WebAssembly game before deployment.'
}
foreach ($asset in $assetSpecs) {
    $assetPath = Join-Path $addonRoot $asset.Name
    if (-not (Test-Path -LiteralPath $assetPath -PathType Leaf)) {
        throw "Required staged asset is missing: $assetPath"
    }
    $assetFile = Get-Item -LiteralPath $assetPath
    if ($assetFile.Length -ne $asset.Bytes) {
        throw "$($asset.Name) has $($assetFile.Length) bytes; expected $($asset.Bytes)."
    }
    $assetHash = (Get-FileHash -LiteralPath $assetPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($assetHash -ne $asset.Sha256) {
        throw "$($asset.Name) has SHA-256 $assetHash; expected $($asset.Sha256)."
    }
}
if (-not $SubscriptionId) {
    $SubscriptionId = (az account show --query id -o tsv).Trim()
}

# App Service otherwise lets the legacy iisnode handler select its bundled
# Node 0.x runtime, which cannot execute the relay. Keep this aligned with the
# package.json runtime requirement.
az webapp config appsettings set `
    --resource-group $ResourceGroup `
    --name $AppName `
    --settings WEBSITE_NODE_DEFAULT_VERSION=~24 `
    --output none
if ($LASTEXITCODE -ne 0) {
    throw 'Could not configure the Node.js runtime required by the network relay.'
}

New-Item -ItemType Directory -Path $dist -Force | Out-Null
if (Test-Path -LiteralPath $archive) {
    Remove-Item -LiteralPath $archive -Force
}
Compress-Archive -Path (Join-Path $output '*') -DestinationPath $archive -CompressionLevel Fastest

Write-Host 'Deploying the Star Control II virtual application...'
$deployArguments = @(
    'webapp', 'deploy',
    '--resource-group', $ResourceGroup,
    '--name', $AppName,
    '--src-path', $archive,
    '--type', 'zip',
    '--target-path', '/home/site/starcontrol2-app',
    '--clean', 'false',
    '--restart', 'false',
    '--track-status', 'true'
)
& az @deployArguments
if ($LASTEXITCODE -ne 0) {
    throw "Azure deployment failed with exit code $LASTEXITCODE"
}

$configUrl = "https://management.azure.com/subscriptions/$SubscriptionId/resourceGroups/$ResourceGroup/providers/Microsoft.Web/sites/$AppName/config/web?api-version=2023-12-01"
$current = az rest --method get --url $configUrl | ConvertFrom-Json
$virtualApplications = @($current.properties.virtualApplications)
$entry = $virtualApplications | Where-Object { $_.virtualPath -eq '/starcontrol2' }
if (-not $entry) {
    $virtualApplications += [pscustomobject]@{
        virtualPath = '/starcontrol2'
        physicalPath = 'site\starcontrol2-app'
        preloadEnabled = $true
    }

    $bodyPath = Join-Path $dist 'starcontrol2-vapps.json'
    @{ properties = @{ virtualApplications = $virtualApplications } } |
        ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath $bodyPath -Encoding utf8
    az rest --method patch --url $configUrl --body "@$bodyPath" | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'The files were uploaded, but /starcontrol2 could not be registered.'
    }
} else {
    if ($entry.physicalPath -ne 'site\starcontrol2-app') {
        throw "/starcontrol2 already points to an unexpected physical path: $($entry.physicalPath)"
    }
}

foreach ($asset in $assetSpecs) {
    $assetPath = Join-Path $addonRoot $asset.Name
    $targetPath = "/home/site/starcontrol2-app/game/content/addons/$($asset.Name)"
    Write-Host "Deploying verified game asset $($asset.Name)..."
    $assetDeployed = $false
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        & az webapp deploy `
            --resource-group $ResourceGroup `
            --name $AppName `
            --src-path $assetPath `
            --type static `
            --target-path $targetPath `
            --clean false `
            --restart false `
            --track-status false `
            --timeout 3600000 `
            --only-show-errors `
            --output none
        if ($LASTEXITCODE -eq 0) {
            $assetDeployed = $true
            break
        }
        if ($attempt -lt 3) {
            Write-Warning "$($asset.Name) deployment attempt $attempt failed; retrying."
            Start-Sleep -Seconds 15
        }
    }
    if (-not $assetDeployed) {
        throw "The application was uploaded, but $($asset.Name) could not be deployed."
    }
}

az webapp restart --resource-group $ResourceGroup --name $AppName | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'The files were uploaded, but the app could not be restarted.'
}

Write-Host "Published: https://$($AppName.ToLowerInvariant()).azurewebsites.net/starcontrol2/"
