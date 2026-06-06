param(
    [string]$PythonSelector = "-3.8"
)

$ErrorActionPreference = "Stop"

function Invoke-Python {
    param(
        [string[]]$Command,
        [string[]]$Arguments
    )

    $exe = $Command[0]
    if ($Command.Length -gt 1) {
        $prefix = $Command[1..($Command.Length - 1)]
        & $exe @prefix @Arguments
        return
    }

    & $exe @Arguments
}

function Resolve-PythonCommand {
    param(
        [string]$Selector
    )

    $localPython38x86 = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python38-32\python.exe'
    if (Test-Path -LiteralPath $localPython38x86) {
        return @($localPython38x86)
    }

    $localPython38 = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python38\python.exe'
    if (Test-Path -LiteralPath $localPython38) {
        return @($localPython38)
    }

    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        try {
            & py $Selector -c "import sys; print(sys.version)"
            if ($LASTEXITCODE -eq 0) {
                return @("py", $Selector)
            }
        } catch {
        }
    }

    if ($Selector -eq "-3.8") {
        $python38 = Get-Command python3.8 -ErrorAction SilentlyContinue
        if ($python38) {
            return @($python38.Source)
        }
    }

    throw "Python 3.8 was not found. Win7 packaging must use Python 3.8 x64. Install it first and make sure 'py -3.8' or 'python3.8' works."
}

$pythonCommand = Resolve-PythonCommand -Selector $PythonSelector

Write-Host ("Using Python command: " + ($pythonCommand -join " ")) -ForegroundColor Cyan

Invoke-Python -Command $pythonCommand -Arguments @("-m", "PyInstaller", "--version") | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is not installed in the selected Python 3.8 environment. Run: py -3.8 -m pip install pyinstaller==5.13.2"
}

Invoke-Python -Command $pythonCommand -Arguments @(
    "-m",
    "PyInstaller",
    "--noconfirm",
    "--clean",
    "--onefile",
    "--windowed",
    "--name",
    "TrainDataManager",
    "app.py"
)

if ($LASTEXITCODE -ne 0) {
    throw "Build failed."
}
