<#
  Install test in a fresh local account (run as administrator; no interactive login needed).
  Creates a temporary user, installs dist\murdic-setup.exe silently as that user, runs the
  installed CLI (first-run model download + transcription), runs the tray app until the
  engine is ready (first-run GPU download on NVIDIA PCs), uninstalls, then deletes the user.

  powershell -ExecutionPolicy Bypass -File windows\tools\newuser_install_test.ps1
#>
param([string]$Setup = "dist\murdic-setup.exe", [string]$Wav = "build\sample.wav", [int]$AppTimeout = 900)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Setup = (Resolve-Path (Join-Path $Repo $Setup)).Path
$Wav = (Resolve-Path (Join-Path $Repo $Wav)).Path
$Out = Join-Path $Repo "build\newuser"
New-Item -ItemType Directory -Force $Out | Out-Null
$Name = "murdictest"
$Plain = [Convert]::ToBase64String((1..18 | ForEach-Object { Get-Random -Maximum 256 }) -as [byte[]]) + "a1!"
$Secure = ConvertTo-SecureString $Plain -AsPlainText -Force
$Cred = New-Object System.Management.Automation.PSCredential("$env:COMPUTERNAME\$Name", $Secure)
$Report = [ordered]@{ setup = $Setup; setup_mb = [math]::Round((Get-Item $Setup).Length / 1MB, 1) }

function Invoke-AsUser($File, $Arguments, $Log) {
    $p = Start-Process -FilePath $File -ArgumentList $Arguments -Credential $Cred -LoadUserProfile -PassThru `
        -WorkingDirectory $Out -RedirectStandardOutput "$Log.out" -RedirectStandardError "$Log.err" -Wait
    return $p.ExitCode
}

try {
    if (Get-LocalUser $Name -ErrorAction SilentlyContinue) { Remove-LocalUser $Name }
    New-LocalUser $Name -Password $Secure -Description "murdic install test (temporary)" | Out-Null
    Add-LocalGroupMember -Group (Get-LocalGroup -SID "S-1-5-32-545") -Member $Name

    $t = Get-Date
    $Report.install_exit = Invoke-AsUser $Setup "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /LOG=`"$Out\install.log`"" "$Out\setup"
    $Report.install_s = [math]::Round(((Get-Date) - $t).TotalSeconds, 1)
    $Home_ = (Get-CimInstance Win32_UserProfile | Where-Object { $_.LocalPath -like "*\$Name*" } | Select-Object -First 1).LocalPath
    $App = Join-Path $Home_ "AppData\Local\Programs\murdic"
    $Report.installed_files = (Get-ChildItem $App -Recurse -File | Measure-Object).Count
    $Report.installed_mb = [math]::Round((Get-ChildItem $App -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 1)
    $Report.start_menu = Test-Path (Join-Path $Home_ "AppData\Roaming\Microsoft\Windows\Start Menu\Programs\머딕 (murdic).lnk")

    $t = Get-Date
    $Report.cli_exit = Invoke-AsUser (Join-Path $App "murdic-cli.exe") "--device cpu wav `"$Wav`" --json" "$Out\cli"
    $Report.cli_s = [math]::Round(((Get-Date) - $t).TotalSeconds, 1)
    $Report.cli_result = (Get-Content "$Out\cli.out" -Encoding utf8 | Where-Object { $_ -like "{*" }) -join ""

    # Tray app: first run fetches cuBLAS on NVIDIA PCs, then loads the engine.
    $t = Get-Date
    $app = Start-Process -FilePath (Join-Path $App "murdic.exe") -Credential $Cred -LoadUserProfile -PassThru -WorkingDirectory $Out
    $Log = Join-Path $Home_ "AppData\Roaming\murdic\murdic.log"
    $ready = $false
    while (((Get-Date) - $t).TotalSeconds -lt $AppTimeout) {
        Start-Sleep -Seconds 2
        if ((Test-Path $Log) -and (Select-String -Path $Log -Pattern "키를 누른 채 말하세요|Engine failed" -Quiet)) { $ready = $true; break }
        if ($app.HasExited) { break }
    }
    $Report.app_ready = $ready
    $Report.app_s = [math]::Round(((Get-Date) - $t).TotalSeconds, 1)
    if (Test-Path $Log) { Copy-Item $Log "$Out\app.log" -Force }
    Get-Process murdic -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$App*" } | Stop-Process -Force
    $Report.gpu_files = (Get-ChildItem (Join-Path $Home_ "AppData\Local\murdic\cuda") -ErrorAction SilentlyContinue | ForEach-Object Name) -join ", "

    Start-Sleep 2
    $Report.uninstall_exit = Invoke-AsUser (Join-Path $App "unins000.exe") "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART" "$Out\uninstall"
    Start-Sleep 3
    $Report.app_removed = -not (Test-Path (Join-Path $App "murdic.exe"))
    $Report.downloads_removed = -not (Test-Path (Join-Path $Home_ "AppData\Local\murdic"))
    $Report.settings_kept = Test-Path (Join-Path $Home_ "AppData\Roaming\murdic\settings.json")
}
finally {
    Get-CimInstance Win32_UserProfile | Where-Object { $_.LocalPath -like "*\$Name" } | Remove-CimInstance -ErrorAction SilentlyContinue
    Remove-LocalUser $Name -ErrorAction SilentlyContinue
    $Report.user_removed = -not (Get-LocalUser $Name -ErrorAction SilentlyContinue)
    $Report | ConvertTo-Json | Out-File "$Out\report.json" -Encoding utf8
    $Report | ConvertTo-Json
}
