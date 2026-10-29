[CmdletBinding()]
param([switch]$SkipTests)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Push-Location $root
try {
    $tools = Join-Path $root '.tools'
    $output = Join-Path $root 'artifacts\StepPreview-x64'
    New-Item -ItemType Directory -Force "$tools\tmp", $output | Out-Null
    $env:TEMP = "$tools\tmp"
    $env:TMP = $env:TEMP
    $env:ZIG_GLOBAL_CACHE_DIR = "$tools\zig-global-cache"
    $env:ZIG_LOCAL_CACHE_DIR = "$tools\zig-local-cache"
    $zig = "$tools\build-tools\ziglang\zig.exe"
    if (-not (Test-Path $zig)) { $zig = "$tools\python-packages\ziglang\zig.exe" }
    if (-not (Test-Path $zig)) {
        & python -m pip --isolated install --index-url https://pypi.org/simple --target "$tools\build-tools" --no-deps ziglang==0.14.1
        if ($LASTEXITCODE) { throw 'Compiler download failed' }
        $zig = "$tools\build-tools\ziglang\zig.exe"
    }
    if (-not (Test-Path "$tools\runtime-packages\OCP")) {
        & python -m pip --isolated install --index-url https://pypi.org/simple --target "$tools\runtime-packages" --no-deps -r renderer/requirements.txt
        if ($LASTEXITCODE) { throw 'Dependency download failed' }
    }
    $pythonZip = "$tools\python-3.14.4-embed-amd64.zip"
    if (-not (Test-Path $pythonZip)) {
        Invoke-WebRequest 'https://www.python.org/ftp/python/3.14.4/python-3.14.4-embed-amd64.zip' -OutFile $pythonZip
    }
    $expectedHash = 'CDA80A9B1E75C0F1B4F9872CA1B417F0D19BCE32FACC811AEA9180E70FAD5FB9'
    if ((Get-FileHash $pythonZip -Algorithm SHA256).Hash -ne $expectedHash) { throw 'Python archive SHA256 mismatch' }
    & $zig cc -target x86_64-windows-gnu -std=c11 -O2 -Wall -Wextra -Werror -shared src/provider.c src/worker.c src/provider.def -o "$output\StepThumbnail.dll" -lole32 -luuid -lgdi32
    if ($LASTEXITCODE) { throw 'Native build failed' }
    & $zig cc -target x86_64-windows-gnu -std=c11 -O3 -Wall -Wextra -Werror -shared src/raster.c -o "$output\StepRaster.dll"
    if ($LASTEXITCODE) { throw 'Rasterizer build failed' }
    Expand-Archive -LiteralPath $pythonZip -DestinationPath "$output\runtime" -Force
    @('python314.zip', '.', 'Lib\site-packages') | Set-Content "$output\runtime\python314._pth" -Encoding ASCII
    New-Item -ItemType Directory -Force "$output\runtime\Lib\site-packages" | Out-Null
    Copy-Item "$tools\runtime-packages\*" "$output\runtime\Lib\site-packages" -Recurse -Force
    Copy-Item renderer/render_step.py $output -Force
    Copy-Item scripts/install.ps1, scripts/uninstall.ps1, scripts/setup.ps1, scripts/Install.cmd, scripts/Uninstall.cmd, README.md, AUTHORS.md, THIRD_PARTY.md, LICENSE, CONTRIBUTING.md, SECURITY.md $output -Force
    New-Item -ItemType Directory -Force "$output\docs\images" | Out-Null
    Copy-Item docs/images/part.png, docs/images/assembly.png "$output\docs\images" -Force
    Copy-Item licenses $output -Recurse -Force
    $manifest = @(Get-ChildItem -LiteralPath $output -Recurse -File | Where-Object { $_.Name -ne 'package-manifest.json' } | Sort-Object FullName | ForEach-Object {
        [pscustomobject]@{ path = $_.FullName.Substring($output.Length + 1); sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash }
    })
    $manifest | ConvertTo-Json -Depth 3 | Set-Content "$output\package-manifest.json" -Encoding UTF8
    if (-not $SkipTests) {
        $testBridge = Join-Path $root 'artifacts\test-worker'
        New-Item -ItemType Directory -Force "$testBridge\runtime" | Out-Null
        & $zig cc -target x86_64-windows-gnu -std=c11 -O2 -Wall -Wextra -Werror -DSTEP_TIMEOUT_MS=1500 -DSTEP_IDLE_MS=700 -DSTEP_MAX_REQUESTS=3 -shared src/provider.c src/worker.c src/provider.def -o "$testBridge\StepThumbnail.dll" -lole32 -luuid -lgdi32
        if ($LASTEXITCODE) { throw 'Test bridge build failed' }
        & $zig cc -target x86_64-windows-gnu -std=c11 -O2 -Wall -Wextra -Werror tests/fake_worker.c -o "$testBridge\runtime\python.exe"
        if ($LASTEXITCODE) { throw 'Test worker build failed' }
        & "$output\runtime\python.exe" -I -B tests/test_worker_lifecycle.py $testBridge
        if ($LASTEXITCODE) { throw 'Worker lifecycle tests failed; package has not been archived' }
        & "$output\runtime\python.exe" -I -B tests/test_renderer.py $output
        if ($LASTEXITCODE) { throw 'Tests failed; package has not been archived' }
    }
    $archive = Join-Path $root 'artifacts\StepPreview-1.0.0-x64.zip'
    Compress-Archive -Path "$output\*" -DestinationPath $archive -Force
    $archiveHash = Get-FileHash -LiteralPath $archive -Algorithm SHA256
    ($archiveHash.Hash.ToLowerInvariant() + '  ' + [IO.Path]::GetFileName($archive)) | Set-Content ($archive + '.sha256') -Encoding ASCII
    $archiveHash | Format-List
    Write-Host "Built: $output"
} finally {
    Pop-Location
}
