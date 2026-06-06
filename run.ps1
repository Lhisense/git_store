$ErrorActionPreference = "Stop"

python app.py

if ($LASTEXITCODE -ne 0) {
    throw "app.py exited with code $LASTEXITCODE"
}

& "$PSScriptRoot\build.ps1"
