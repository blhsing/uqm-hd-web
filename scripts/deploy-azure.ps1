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

if (-not (Test-Path -LiteralPath (Join-Path $output 'index.html'))) {
    throw 'Run npm run build:azure before deployment.'
}
if (-not (Test-Path -LiteralPath (Join-Path $output 'game\uqm-hd.html'))) {
    throw 'Build and stage the WebAssembly game before deployment.'
}
if (-not $SubscriptionId) {
    $SubscriptionId = (az account show --query id -o tsv).Trim()
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
    az webapp restart --resource-group $ResourceGroup --name $AppName | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw 'The files were uploaded, but the app could not be restarted.'
    }
}

Write-Host "Published: https://$($AppName.ToLowerInvariant()).azurewebsites.net/starcontrol2/"
