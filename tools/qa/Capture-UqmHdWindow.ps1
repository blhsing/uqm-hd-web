[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [string]$ExecutablePath = 'C:\Games\UQM-HD-TW\uqm.exe'
)

$ErrorActionPreference = 'Stop'
$expected = [System.IO.Path]::GetFullPath($ExecutablePath)
$processes = @(
    Get-CimInstance Win32_Process -Filter "Name='uqm.exe'" |
        Where-Object { $_.ExecutablePath -eq $expected }
)
if ($processes.Count -ne 1) {
    throw "Expected exactly one UQM process at '$expected'; found $($processes.Count)."
}

Add-Type -AssemblyName System.Drawing
if (-not ('UqmHdWindowCapture' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class UqmHdWindowCapture
{
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr window, out RECT rectangle);

    [DllImport("user32.dll")]
    public static extern bool PrintWindow(IntPtr window, IntPtr deviceContext, uint flags);
}
'@
}

$process = Get-Process -Id $processes[0].ProcessId
$rectangle = New-Object UqmHdWindowCapture+RECT
if (-not [UqmHdWindowCapture]::GetWindowRect($process.MainWindowHandle, [ref]$rectangle)) {
    throw 'GetWindowRect failed.'
}
$width = $rectangle.Right - $rectangle.Left
$height = $rectangle.Bottom - $rectangle.Top
if ($width -lt 100 -or $height -lt 100) {
    throw "Refusing invalid game-window dimensions ${width}x${height}."
}

$destination = [System.IO.Path]::GetFullPath($OutputPath)
$parent = [System.IO.Path]::GetDirectoryName($destination)
if (-not [System.IO.Directory]::Exists($parent)) {
    throw "Output directory does not exist: $parent"
}

$bitmap = New-Object System.Drawing.Bitmap $width, $height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$deviceContext = $graphics.GetHdc()
try {
    if (-not [UqmHdWindowCapture]::PrintWindow(
            $process.MainWindowHandle, $deviceContext, 2)) {
        throw 'PrintWindow failed.'
    }
}
finally {
    $graphics.ReleaseHdc($deviceContext)
    $graphics.Dispose()
}
try {
    $bitmap.Save($destination, [System.Drawing.Imaging.ImageFormat]::Png)
}
finally {
    $bitmap.Dispose()
}

Get-Item -LiteralPath $destination
