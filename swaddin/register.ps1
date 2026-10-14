# Registers (or -Unregister removes) the CurveMill SolidWorks add-in. Run as Administrator.
# regasm's ComRegisterFunction writes the SolidWorks\Addins keys; this script also writes
# the SOFTWARE\CurveMill launch keys the add-in reads (dev = the venv's pythonw + -m curvemill;
# the v4.0 installer will write the packaged exe here instead).
param([switch]$Unregister)

$ErrorActionPreference = "Stop"
$dll    = Join-Path $PSScriptRoot "bin\Release\CurveMillAddin.dll"
$regasm = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe"

if (-not (([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator))) {
    throw "Run this from an elevated PowerShell (Administrator)."
}

if ($Unregister) {
    & $regasm $dll /unregister
    Remove-Item "HKLM:\SOFTWARE\CurveMill" -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "Unregistered." -ForegroundColor Green
    return
}

if (-not (Test-Path $dll)) { throw "Build first: MSBuild CurveMillAddin.csproj /p:Configuration=Release" }

& $regasm $dll /codebase   # /codebase because the DLL lives outside the GAC
if ($LASTEXITCODE -ne 0) { throw "regasm failed (exit $LASTEXITCODE) - the add-in was NOT registered. See the error above." }

New-Item -Path "HKLM:\SOFTWARE\CurveMill" -Force | Out-Null
Set-ItemProperty "HKLM:\SOFTWARE\CurveMill" -Name "ExePath"  -Value "C:\Users\ibrah\VS-projects\DXF-CNC-Optimizer\.venv\Scripts\pythonw.exe"
Set-ItemProperty "HKLM:\SOFTWARE\CurveMill" -Name "BaseArgs" -Value "-m curvemill"

Write-Host "Registered. Restart SolidWorks; enable 'CurveMill' under Tools > Add-Ins if not auto-loaded." -ForegroundColor Green
