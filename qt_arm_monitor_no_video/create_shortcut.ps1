$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')

# Find pythonw.exe: prefer D:\moxingxunlian, fallback to current python env
$pythonw = "D:\moxingxunlian\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    $pythonw = (Get-Command python -ErrorAction SilentlyContinue).Source -replace 'python\.exe$', 'pythonw.exe'
}
if (-not (Test-Path $pythonw)) {
    Write-Host "ERROR: pythonw.exe not found"
    exit 1
}

$linkName = '机械臂监控-无视频版'
$sc = $ws.CreateShortcut("$desktop\$linkName.lnk")
$sc.TargetPath = $pythonw
$sc.Arguments = '"E:\机械臂jetson主板上全部代码（完整拷贝）\机械臂设计代码\jixiebichengxu\qt_arm_monitor_no_video\main.py"'
$sc.WorkingDirectory = "E:\机械臂jetson主板上全部代码（完整拷贝）\机械臂设计代码\jixiebichengxu\qt_arm_monitor_no_video"
$sc.WindowStyle = 1
$sc.Description = "DOFBOT PRO Arm Monitor - No Video Stream"
$sc.IconLocation = $pythonw
$sc.Save()
Write-Host "Shortcut '$linkName.lnk' created on desktop."
Write-Host "Target: $pythonw"
