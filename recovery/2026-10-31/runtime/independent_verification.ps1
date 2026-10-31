param(
    [Parameter(Mandatory=$true)][ValidateSet('smoke','failure','verify')][string]$Mode,
    [Parameter(Mandatory=$true)][string]$RunDirectory,
    [ValidateRange(1,60)][int]$SmokeSeconds = 20
)
$ErrorActionPreference = 'Stop'
$taskPython = 'D:\Projects\AShareQiheng\.venv\Scripts\python.exe'
$taskWorkspace = 'C:\Users\Lenovo\.codex\worktrees\formal-final-stage-d\AShareQiheng'
$taskRunner = 'D:\Projects\AShareQiheng\.tmp\grouped_regression.py'
[void][System.IO.Directory]::CreateDirectory($RunDirectory)
$taskStatusPath = Join-Path $RunDirectory 'status.json'
if (Test-Path -LiteralPath $taskStatusPath) { throw 'Run directory already used; refusing to overwrite evidence.' }
$taskState = [ordered]@{
    mode=$Mode; phase='started'; pid=$PID;
    user=[System.Security.Principal.WindowsIdentity]::GetCurrent().Name;
    started_utc=[DateTime]::UtcNow.ToString('o'); exit_code=$null
}
$taskState | ConvertTo-Json | Set-Content -LiteralPath $taskStatusPath -Encoding UTF8
$taskExit = 1
try {
    Set-Location -LiteralPath $taskWorkspace
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:TMPDIR = 'D:\Projects\AShareQiheng\.tmp'
    $env:TEMP = $env:TMPDIR
    $env:TMP = $env:TMPDIR
    if ($Mode -eq 'verify') {
        $taskArguments = @('-u','-X','faulthandler',$taskRunner,'--all')
    } else {
        $taskProbeExit = if ($Mode -eq 'failure') { 7 } else { 0 }
        $taskCode = "import os,time; print('PROBE_STARTED',os.getpid(),os.getppid(),flush=True); time.sleep($SmokeSeconds); print('PROBE_FINISHED',flush=True); raise SystemExit($taskProbeExit)"
        $taskArguments = @('-u','-c',$taskCode)
    }
    # Native stderr is evidence, not a PowerShell exception. Preserve native exit.
    $ErrorActionPreference = 'Continue'
    & $taskPython @taskArguments 2>&1 | Out-File -LiteralPath (Join-Path $RunDirectory 'output.log') -Encoding UTF8
    $taskExit = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
} catch {
    $_ | Out-String | Add-Content -LiteralPath (Join-Path $RunDirectory 'wrapper-error.log')
    $taskExit = 1
} finally {
    $taskState.phase = 'finished'
    $taskState.exit_code = $taskExit
    $taskState['finished_utc'] = [DateTime]::UtcNow.ToString('o')
    $taskState | ConvertTo-Json | Set-Content -LiteralPath $taskStatusPath -Encoding UTF8
}
exit $taskExit
