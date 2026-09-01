$ErrorActionPreference = 'Stop'

$ws = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')

# Prefer the known Python environment, then fall back to the current Python.
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

# Build the Chinese shortcut name from Unicode code points. This keeps
# Windows PowerShell 5 code-page detection from corrupting the file name.
$linkName = -join @(
    [char]0x673A, [char]0x68B0, [char]0x81C2,
    [char]0x76D1, [char]0x63A7, [char]0x002D,
    [char]0x65E0, [char]0x89C6, [char]0x9891, [char]0x7248
)

$mainPath = Join-Path $PSScriptRoot 'main.py'
if (-not (Test-Path -LiteralPath $mainPath)) {
    throw "main.py not found: $mainPath"
}

$linkPath = Join-Path $desktop ($linkName + '.lnk')
$sc = $ws.CreateShortcut($linkPath)
$sc.TargetPath = $pythonw
$sc.Arguments = '"' + $mainPath + '"'
$sc.WorkingDirectory = $PSScriptRoot
$sc.WindowStyle = 1
$sc.Description = 'DOFBOT PRO Arm Monitor - No Video Stream'
$sc.IconLocation = $pythonw + ',0'
$sc.Save()

if (-not (Test-Path -LiteralPath $linkPath)) {
    throw "Shortcut was not created: $linkPath"
}

Write-Host 'Shortcut created successfully:' $linkPath
Write-Host 'Target:' $pythonw
Write-Host 'Program:' $mainPath
