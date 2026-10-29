[CmdletBinding()]
param(
    [ValidateSet('Install', 'Uninstall')][string]$Operation = 'Install',
    [switch]$Pause,
    [string]$LogDirectory = (Join-Path ([IO.Path]::GetTempPath()) 'StepPreview-SetupLogs')
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$exitCode = 1
$transcriptStarted = $false
$logPath = $null
$installing = $Operation -eq 'Install'
$title = if ($installing) { 'Установка STEP Preview' } else { 'Удаление STEP Preview' }

Write-Host ''
Write-Host ('=' * 64) -ForegroundColor Cyan
Write-Host $title -ForegroundColor Cyan
Write-Host ('=' * 64) -ForegroundColor Cyan
try {
    try {
        New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
        $name = '{0}-{1}-{2}.log' -f $Operation, (Get-Date -Format 'yyyyMMdd-HHmmss'), ([Guid]::NewGuid().ToString('N').Substring(0, 8))
        $logPath = Join-Path $LogDirectory $name
        Start-Transcript -LiteralPath $logPath -Force | Out-Null
        $transcriptStarted = $true
    } catch {
        $logPath = $null
        Write-Host ('Не удалось начать запись журнала: ' + $_.Exception.Message) -ForegroundColor Yellow
    }

    $scriptName = if ($installing) { 'install.ps1' } else { 'uninstall.ps1' }
    $scriptPath = Join-Path $PSScriptRoot $scriptName
    if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
        throw "Не найден $scriptName. Распакуйте архив целиком и повторите запуск."
    }
    $global:LASTEXITCODE = 0
    & $scriptPath
    if ($LASTEXITCODE -ne 0) { throw "Команда завершилась с кодом $LASTEXITCODE." }
    $exitCode = 0
    Write-Host ''
    Write-Host ('=' * 64) -ForegroundColor Green
    $success = if ($installing) { 'УСТАНОВКА УСПЕШНО ЗАВЕРШЕНА' } else { 'УДАЛЕНИЕ УСПЕШНО ЗАВЕРШЕНО' }
    Write-Host $success -ForegroundColor Green
    if ($installing) {
        Write-Host 'После обновления выйдите из учётной записи Windows и войдите снова,'
        Write-Host 'чтобы Windows выгрузила предыдущую версию обработчика.'
    }
    Write-Host ('=' * 64) -ForegroundColor Green
} catch {
    Write-Host ''
    Write-Host ('=' * 64) -ForegroundColor Red
    $failure = if ($installing) { 'ОШИБКА УСТАНОВКИ' } else { 'ОШИБКА УДАЛЕНИЯ' }
    Write-Host $failure -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($_.ScriptStackTrace) { Write-Host $_.ScriptStackTrace }
    Write-Host 'Сохраните сообщение об ошибке или журнал для диагностики.'
    Write-Host ('=' * 64) -ForegroundColor Red
} finally {
    if ($logPath) { Write-Host "Журнал: $logPath" }
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null }
        catch { Write-Host ('Не удалось завершить журнал: ' + $_.Exception.Message) -ForegroundColor Yellow }
    }
    if ($Pause) {
        try { [void](Read-Host 'Нажмите Enter, чтобы закрыть окно') }
        catch { }
    }
}
exit $exitCode
