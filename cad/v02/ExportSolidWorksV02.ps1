param([string]$Output = "", [switch]$ResumeVerified)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$cad = Split-Path -Parent $here
$root = Split-Path -Parent $cad
$source = Join-Path $root "model\V02"
$csc = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$exe = Join-Path $cad "ExportSolidWorksV02.exe"
& $csc /nologo /target:exe "/out:$exe" "/reference:$(Join-Path $cad 'SolidWorks.Interop.sldworks.dll')" "/reference:$(Join-Path $cad 'SolidWorks.Interop.swconst.dll')" "/reference:System.Web.Extensions.dll" (Join-Path $here "ExportSolidWorksV02.cs")
if ($LASTEXITCODE -ne 0) { throw "Native exporter compilation failed" }
if ($ResumeVerified) {
    if (-not $Output) { $Output = Join-Path $source "native" }
    & $exe $source $Output "--resume-verified"
} elseif ($Output) { & $exe $source $Output } else { & $exe $source }
if ($LASTEXITCODE -ne 0) { throw "Native conversion failed; inspect solidworks_validation.json" }
