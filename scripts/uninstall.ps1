[CmdletBinding(SupportsShouldProcess)]
param()
$ErrorActionPreference = 'Stop'
if (-not [Environment]::Is64BitProcess) { throw 'Use 64-bit PowerShell.' }
$base = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'StepPreview'
$statePath = Join-Path $base 'registration.json'
$clsid = '{FAD54C2D-A5A1-4D8E-9149-779862E2E961}'
if (-not (Test-Path $statePath)) { Write-Host 'STEP Preview is not registered for this user.'; return }
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
if ($state.clsid -ne $clsid) { throw 'Unexpected registration backup' }
if (-not $PSCmdlet.ShouldProcess($base, 'Unregister STEP Preview, restore previous thumbnail providers and remove deployed versions')) { return }
$user = [Microsoft.Win32.RegistryKey]::OpenBaseKey('CurrentUser', 'Registry64')
try {
    foreach ($entry in $state.entries) {
        if ($entry.path -notmatch '^Software\\Classes\\[^\\]+\\ShellEx\\\{E357FCCD-A995-4576-B01F-234630154E96\}$' -and
            $entry.path -notmatch '^Software\\Classes\\SystemFileAssociations\\\.st(ep|p)\\ShellEx\\\{E357FCCD-A995-4576-B01F-234630154E96\}$') {
            throw 'Unexpected registry path in backup'
        }
        $key = $user.OpenSubKey($entry.path, $true)
        if (-not $key) { continue }
        try {
            # A CAD application installed later may now own the thumbnail slot.
            if ($key.GetValue('') -ne $clsid) { continue }
            if ($entry.hadValue) {
                $kind = if ($entry.kind) { [Microsoft.Win32.RegistryValueKind]::$($entry.kind) } else { [Microsoft.Win32.RegistryValueKind]::String }
                $key.SetValue('', $entry.value, $kind)
            }
            else { $key.DeleteValue('', $false) }
        } finally { $key.Dispose() }
    }
    $key = $user.OpenSubKey("Software\Classes\CLSID\$clsid\InprocServer32")
    $owned = $false
    if ($key) {
        $owned = ([string]$key.GetValue('')).StartsWith($base + '\', [StringComparison]::OrdinalIgnoreCase)
        $key.Dispose()
    }
    if ($owned) { $user.DeleteSubKeyTree("Software\Classes\CLSID\$clsid", $false) }
    $user.DeleteSubKeyTree('Software\Microsoft\Windows\CurrentVersion\Uninstall\StepPreview', $false)
    Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class StepPreviewRemoveNotify { [DllImport("shell32.dll")] public static extern void SHChangeNotify(uint e, uint f, IntPtr a, IntPtr b); }'
    [StepPreviewRemoveNotify]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
    $versions = Join-Path $base 'versions'
    if (Test-Path $versions) {
        foreach ($directory in Get-ChildItem -LiteralPath $versions -Directory) {
            $resolved = [IO.Path]::GetFullPath($directory.FullName)
            if (-not $resolved.StartsWith($versions + '\', [StringComparison]::OrdinalIgnoreCase) -or
                ($directory.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe installation directory' }
            try { Remove-Item -LiteralPath $resolved -Recurse -Force }
            catch { Write-Warning "Some files are still in use: $resolved. Sign out and run Uninstall again." }
        }
    }
    Write-Host 'STEP Preview has been unregistered. Previous thumbnail registrations were restored where still owned.'
    Write-Host "Registration backup retained at: $statePath"
} finally { $user.Dispose() }
