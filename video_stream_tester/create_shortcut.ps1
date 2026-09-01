$ErrorActionPreference = 'Stop'

$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$pythonw = 'D:\moxingxunlian\pythonw.exe'

if (-not (Test-Path -LiteralPath $pythonw)) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        $pythonw = $python.Source -replace 'python\.exe$', 'pythonw.exe'
    }
}
if (-not (Test-Path -LiteralPath $pythonw)) {
    throw 'pythonw.exe not found'
}

# Chinese name: video stream test tool.
$linkName = -join @(
    [char]0x89C6, [char]0x9891, [char]0x6D41,
    [char]0x6D4B, [char]0x8BD5, [char]0x5DE5, [char]0x5177
)
$mainPath = Join-Path $PSScriptRoot 'main.py'
$linkPath = Join-Path $desktop ($linkName + '.lnk')

$sc = $ws.CreateShortcut($linkPath)
$sc.TargetPath = $pythonw
$sc.Arguments = '"' + $mainPath + '"'
$sc.WorkingDirectory = $PSScriptRoot
$sc.WindowStyle = 1
$sc.Description = 'DOFBOT Independent MJPEG Video Stream Tester'
$sc.IconLocation = $pythonw + ',0'
$sc.Save()

if (-not (Test-Path -LiteralPath $linkPath)) {
    throw "Shortcut was not created: $linkPath"
}

Write-Host 'Shortcut created successfully:' $linkPath
Write-Host 'Program:' $mainPath

