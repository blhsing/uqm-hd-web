[CmdletBinding()]
param(
    [string]$ExecutablePath = 'C:\Games\UQM-HD-TW\uqm.exe',
    [int64]$CurrentActivityRva = 0x13E580
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

if (-not ('UqmHdMemoryReader' -as [type])) {
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

public static class UqmHdMemoryReader
{
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern IntPtr OpenProcess(uint access, bool inherit, int processId);

    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern bool ReadProcessMemory(
        IntPtr process, IntPtr address, byte[] buffer, int size, out IntPtr bytesRead);

    [DllImport("kernel32.dll")]
    public static extern bool CloseHandle(IntPtr process);
}
'@
}

$process = Get-Process -Id $processes[0].ProcessId
$handle = [UqmHdMemoryReader]::OpenProcess(0x410, $false, $process.Id)
if ($handle -eq [IntPtr]::Zero) {
    throw 'OpenProcess failed.'
}
$buffer = New-Object byte[] 2
$bytesRead = [IntPtr]::Zero
$address = [IntPtr]($process.MainModule.BaseAddress.ToInt64() + $CurrentActivityRva)
try {
    if (-not [UqmHdMemoryReader]::ReadProcessMemory(
            $handle, $address, $buffer, $buffer.Length, [ref]$bytesRead)) {
        throw 'ReadProcessMemory failed.'
    }
}
finally {
    [UqmHdMemoryReader]::CloseHandle($handle) | Out-Null
}

$activity = [BitConverter]::ToUInt16($buffer, 0)
[pscustomobject]@{
    ProcessId = $process.Id
    ImageBase = '0x{0:X}' -f $process.MainModule.BaseAddress.ToInt64()
    CurrentActivity = '0x{0:X4}' -f $activity
    InBattle = ($activity -band 0x0200) -ne 0
    CheckAbort = ($activity -band 0x4000) -ne 0
}
