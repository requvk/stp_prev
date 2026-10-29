[CmdletBinding(SupportsShouldProcess)]
param()
$ErrorActionPreference = 'Stop'
if (-not [Environment]::Is64BitOperatingSystem -or -not [Environment]::Is64BitProcess -or
    $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { throw 'Windows x64 and 64-bit PowerShell are required.' }
$clsid = '{FAD54C2D-A5A1-4D8E-9149-779862E2E961}'
$thumbnail = '{E357FCCD-A995-4576-B01F-234630154E96}'
$base = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'StepPreview'
$source = $PSScriptRoot
foreach ($file in 'StepThumbnail.dll', 'StepRaster.dll', 'render_step.py', 'runtime\python.exe', 'package-manifest.json', 'setup.ps1') {
    if (-not (Test-Path (Join-Path $source $file))) { throw "Incomplete package: $file" }
}
$hashAlgorithm = [Security.Cryptography.SHA256]::Create()
$manifestStream = [IO.File]::OpenRead((Join-Path $source 'package-manifest.json'))
try { $identity = ([BitConverter]::ToString($hashAlgorithm.ComputeHash($manifestStream))).Replace('-', '').Substring(0, 12) }
finally { $manifestStream.Dispose(); $hashAlgorithm.Dispose() }
$suffix = [Guid]::NewGuid().ToString('N').Substring(0, 8)
$version = Join-Path $base "versions\1.0.0-$identity-$suffix"
$statePath = Join-Path $base 'registration.json'
$user = [Microsoft.Win32.RegistryKey]::OpenBaseKey('CurrentUser', 'Registry64')
$classes = [Microsoft.Win32.RegistryKey]::OpenBaseKey('ClassesRoot', 'Registry64')
try {
    $paths = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    foreach ($extension in '.stp', '.step') {
        [void]$paths.Add("Software\Classes\$extension\ShellEx\$thumbnail")
        [void]$paths.Add("Software\Classes\SystemFileAssociations\$extension\ShellEx\$thumbnail")
        $key = $classes.OpenSubKey($extension)
        $progId = if ($key) { $key.GetValue('') }
        if ($key) { $key.Dispose() }
        $choice = $user.OpenSubKey("Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\$extension\UserChoice")
        $chosenProgId = if ($choice) { $choice.GetValue('ProgId') }
        if ($choice) { $choice.Dispose() }
        foreach ($id in @($progId, $chosenProgId)) {
            if ($id -and $id -match '^[A-Za-z0-9_.{}-]+$') {
                [void]$paths.Add("Software\Classes\$id\ShellEx\$thumbnail")
            }
        }
    }
    $oldDll = $null
    $existing = $user.OpenSubKey("Software\Classes\CLSID\$clsid\InprocServer32")
    if ($existing) {
        $oldDll = [string]$existing.GetValue('')
        $existing.Dispose()
        if (-not $oldDll.StartsWith($base + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'The component CLSID is already registered by another installation.'
        }
    }
    $entries = [Collections.Generic.List[object]]::new()
    if (Test-Path $statePath) {
        $saved = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        if ($saved.clsid -ne $clsid) { throw 'Unexpected registration backup' }
        foreach ($entry in $saved.entries) { $entries.Add($entry) }
    }
    foreach ($path in $paths) {
        if ($entries | Where-Object { $_.path -eq $path }) { continue }
        $key = $user.OpenSubKey($path)
        $hadValue = $false
        $value = $null
        $kind = 'String'
        if ($key) {
            $hadValue = $key.GetValueNames() -contains ''
            if ($hadValue) {
                $value = $key.GetValue('', $null, 'DoNotExpandEnvironmentNames')
                $kind = $key.GetValueKind('').ToString()
            }
            $key.Dispose()
        }
        $entries.Add([pscustomobject]@{ path = $path; hadValue = $hadValue; value = $value; kind = $kind })
    }
    if (-not $PSCmdlet.ShouldProcess($base, 'Install STEP thumbnail provider for the current user and back up thumbnail registrations')) { return }
    New-Item -ItemType Directory -Path $base -Force | Out-Null
    if (-not (Test-Path $version)) {
        New-Item -ItemType Directory -Path $version -Force | Out-Null
        Copy-Item (Join-Path $source '*') $version -Recurse -Force
    }
    $state = [pscustomobject]@{ clsid = $clsid; versionPath = $version; entries = @($entries.ToArray()) }
    $temporary = Join-Path $base ([Guid]::NewGuid().ToString() + '.json')
    $state | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $statePath -Force
    $key = $user.CreateSubKey("Software\Classes\CLSID\$clsid")
    $key.SetValue('', 'STEP Preview thumbnail provider')
    $key.Dispose()
    $key = $user.CreateSubKey("Software\Classes\CLSID\$clsid\InprocServer32")
    $key.SetValue('', (Join-Path $version 'StepThumbnail.dll'))
    $key.SetValue('ThreadingModel', 'Both')
    $key.Dispose()
    foreach ($path in $paths) {
        $key = $user.CreateSubKey($path)
        $key.SetValue('', $clsid)
        $key.Dispose()
    }
    Copy-Item (Join-Path $source 'uninstall.ps1') $base -Force
    Copy-Item (Join-Path $source 'setup.ps1') $base -Force
    $uninstallKey = "Software\Microsoft\Windows\CurrentVersion\Uninstall\StepPreview"
    $key = $user.CreateSubKey($uninstallKey)
    $key.SetValue('DisplayName', 'STEP Preview')
    $key.SetValue('DisplayVersion', '1.0.0')
    $key.SetValue('InstallLocation', $base)
    $key.SetValue('UninstallString', "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$base\setup.ps1`" -Operation Uninstall -Pause")
    $key.SetValue('NoModify', 1, [Microsoft.Win32.RegistryValueKind]::DWord)
    $key.SetValue('NoRepair', 1, [Microsoft.Win32.RegistryValueKind]::DWord)
    $key.Dispose()
    Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class StepPreviewNotify { [DllImport("shell32.dll")] public static extern void SHChangeNotify(uint e, uint f, IntPtr a, IntPtr b); }'
    [StepPreviewNotify]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
    Write-Host "Installed: $version"
    if ($oldDll) {
        Write-Host 'Updated an existing installation. Sign out and sign back in to ensure Windows unloads the previous thumbnail provider.'
    }
    Write-Host 'Open a folder with STEP files, select Medium/Large/Extra large icons and press F5.'
    Write-Host 'If Windows keeps old icons, sign out and sign back in. Explorer has not been restarted.'
} finally {
    $classes.Dispose()
    $user.Dispose()
}
