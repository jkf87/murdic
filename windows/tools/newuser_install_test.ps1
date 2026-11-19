<#
  Install test in a fresh local account (run as administrator; no interactive login needed).
  Creates a temporary user and, as that user (scheduled task, password logon):
  installs dist\murdic-setup.exe silently, runs the installed CLI (first-run model download
  + transcription), runs the tray app until its engine is ready (first-run cuBLAS download
  on NVIDIA PCs), uninstalls. Then deletes the user and its profile.

  powershell -ExecutionPolicy Bypass -File windows\tools\newuser_install_test.ps1
#>
param([string]$Setup = "dist\murdic-setup.exe", [string]$Wav = "build\sample.wav", [int]$Timeout = 1500)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Setup = (Resolve-Path (Join-Path $Repo $Setup)).Path
$Wav = (Resolve-Path (Join-Path $Repo $Wav)).Path
$Out = Join-Path $Repo "build\newuser"
Remove-Item -Recurse -Force $Out -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force $Out | Out-Null
$Name = "murdictest"
$Plain = [Convert]::ToBase64String((1..18 | ForEach-Object { Get-Random -Maximum 256 }) -as [byte[]]) + "a1!"
$Secure = ConvertTo-SecureString $Plain -AsPlainText -Force

# Runs as the test user.
$Inner = @'
param($Setup, $Wav, $Out, $Timeout)
$ErrorActionPreference = "Continue"
$Elevated = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$R = [ordered]@{ user = $env:USERNAME; elevated = $Elevated; fresh_profile = $env:USERPROFILE
                 python_on_path = [bool](Get-Command python -ErrorAction SilentlyContinue) }
# Behave like a PC without Python: drop every Python folder from PATH.
$env:PATH = ($env:PATH -split ";" | Where-Object { $_ -and $_ -notmatch "python" }) -join ";"
$env:PYTHONHOME = $null; $env:PYTHONPATH = $null
$R.python_on_path_after_strip = [bool](Get-Command python -ErrorAction SilentlyContinue)
$App = Join-Path $env:LOCALAPPDATA "Programs\murdic"
$t = Get-Date
$p = Start-Process $Setup "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG=`"$Out\install.log`"" -PassThru -Wait
$R.install_exit = $p.ExitCode; $R.install_s = [math]::Round(((Get-Date) - $t).TotalSeconds, 1)
$R.installed_mb = [math]::Round((Get-ChildItem $App -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 1)
$R.start_menu_shortcut = Test-Path (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\머딕 (murdic).lnk")
$R.autostart_registered = [bool](Get-ItemProperty HKCU:\Software\Microsoft\Windows\CurrentVersion\Run -Name murdic -ErrorAction SilentlyContinue)
$t = Get-Date
$p = Start-Process (Join-Path $App "murdic-cli.exe") "--device cpu wav `"$Wav`" --json" -PassThru -Wait `
    -RedirectStandardOutput "$Out\cli.out" -RedirectStandardError "$Out\cli.err" -NoNewWindow
$R.cli_exit = $p.ExitCode; $R.cli_first_run_s = [math]::Round(((Get-Date) - $t).TotalSeconds, 1)
$R.cli_result = (Get-Content "$Out\cli.out" -Encoding utf8 | Where-Object { $_ -like "{*" }) -join ""
$R.model_files = (Get-ChildItem (Join-Path $env:LOCALAPPDATA "murdic\models\faster-whisper-small") | ForEach-Object Name) -join ", "
$t = Get-Date
$app = Start-Process (Join-Path $App "murdic.exe") -PassThru
$Log = Join-Path $env:APPDATA "murdic\murdic.log"
$R.app_ready = $false
while (((Get-Date) - $t).TotalSeconds -lt $Timeout) {
    Start-Sleep -Seconds 2
    if ((Test-Path $Log) -and (Select-String -Path $Log -Pattern "키를 누른 채 말하세요" -Quiet)) { $R.app_ready = $true; break }
    if ($app.HasExited) { break }
}
$R.app_first_run_s = [math]::Round(((Get-Date) - $t).TotalSeconds, 1)
if (Test-Path $Log) { Copy-Item $Log "$Out\app.log" -Force }
$R.app_engine = (Select-String -Path $Log -Pattern "Whisper small ready on (\S+)" | Select-Object -Last 1).Matches.Groups[1].Value
$R.gpu_files = (Get-ChildItem (Join-Path $env:LOCALAPPDATA "murdic\cuda") -ErrorAction SilentlyContinue | ForEach-Object Name) -join ", "
Stop-Process -Id $app.Id -Force -ErrorAction SilentlyContinue
Start-Sleep 2
$p = Start-Process (Join-Path $App "unins000.exe") "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART" -PassThru -Wait
$R.uninstall_exit = $p.ExitCode
# unins000.exe relaunches itself from %TEMP% and returns at once: wait for the real removal.
$t = Get-Date
while ((Test-Path (Join-Path $App "unins000.exe")) -and ((Get-Date) - $t).TotalSeconds -lt 120) { Start-Sleep -Milliseconds 500 }
$R.app_removed = -not (Test-Path (Join-Path $App "murdic.exe"))
$R.downloads_removed = -not (Test-Path (Join-Path $env:LOCALAPPDATA "murdic"))
$R.settings_kept = Test-Path (Join-Path $env:APPDATA "murdic\hints.txt")
$R.autostart_removed = -not (Get-ItemProperty HKCU:\Software\Microsoft\Windows\CurrentVersion\Run -Name murdic -ErrorAction SilentlyContinue)
$R | ConvertTo-Json | Out-File "$Out\inner.json" -Encoding utf8
'@
$InnerPath = Join-Path $Out "inner.ps1"
[IO.File]::WriteAllText($InnerPath, $Inner, (New-Object Text.UTF8Encoding $true))
$Report = [ordered]@{ setup = $Setup; setup_mb = [math]::Round((Get-Item $Setup).Length / 1MB, 1) }
$Task = "murdic-newuser-test"
try {
    if (Get-LocalUser $Name -ErrorAction SilentlyContinue) { Remove-LocalUser $Name }
    New-LocalUser $Name -Password $Secure -Description "murdic install test (temporary)" | Out-Null
    Add-LocalGroupMember -Group (Get-LocalGroup -SID "S-1-5-32-545") -Member $Name
    # Task Scheduler needs "log on as a batch job", which only Administrators have by default.
    # The task still runs with a filtered, non-elevated token (RunLevel Limited).
    Add-LocalGroupMember -Group (Get-LocalGroup -SID "S-1-5-32-544") -Member $Name
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument ("-NoProfile -ExecutionPolicy Bypass -File `"$InnerPath`" " +
        "-Setup `"$Setup`" -Wav `"$Wav`" -Out `"$Out`" -Timeout $Timeout")
    $principal = New-ScheduledTaskPrincipal -UserId "$env:COMPUTERNAME\$Name" -LogonType Password -RunLevel Limited
    $task = New-ScheduledTask -Action $action -Principal $principal `
        -Settings (New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 1))
    Register-ScheduledTask -TaskName $Task -InputObject $task -User "$env:COMPUTERNAME\$Name" -Password $Plain -Force | Out-Null
    $t = Get-Date
    Start-ScheduledTask -TaskName $Task
    do {
        Start-Sleep -Seconds 3
        $info = Get-ScheduledTaskInfo -TaskName $Task
        $finished = (Test-Path "$Out\inner.json") -or
            ((Get-ScheduledTask -TaskName $Task).State -ne "Running" -and $info.LastTaskResult -ne 267011 -and $info.LastTaskResult -ne 267009)
    } until ($finished -or ((Get-Date) - $t).TotalSeconds -gt $Timeout + 900)
    $Report.task_result = (Get-ScheduledTaskInfo -TaskName $Task).LastTaskResult
    $Report.total_s = [math]::Round(((Get-Date) - $t).TotalSeconds, 1)
    if (Test-Path "$Out\inner.json") { $Report.inner = Get-Content "$Out\inner.json" -Raw -Encoding utf8 | ConvertFrom-Json }
}
finally {
    Unregister-ScheduledTask -TaskName $Task -Confirm:$false -ErrorAction SilentlyContinue
    Get-CimInstance Win32_UserProfile | Where-Object { $_.LocalPath -like "*\$Name" } | Remove-CimInstance -ErrorAction SilentlyContinue
    Remove-LocalUser $Name -ErrorAction SilentlyContinue
    $Report.user_removed = -not (Get-LocalUser $Name -ErrorAction SilentlyContinue)
    $Report.profile_removed = -not (Test-Path "C:\Users\$Name")
    $Report | ConvertTo-Json -Depth 4 | Out-File "$Out\report.json" -Encoding utf8
    $Report | ConvertTo-Json -Depth 4
}
