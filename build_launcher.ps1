$ErrorActionPreference = "Stop"
$source = Join-Path $PSScriptRoot "StockScreenerLauncher.cs"
$output = Join-Path $PSScriptRoot "StockScreener.exe"
$compilerCandidates = @(
    (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
    (Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe")
)
$compiler = $compilerCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $compiler) {
    $command = Get-Command csc.exe -ErrorAction SilentlyContinue
    if ($command) { $compiler = $command.Source }
}
if (-not $compiler) { throw "C# compiler csc.exe was not found. Install the .NET Framework developer tools." }
& $compiler /nologo "/out:$output" $source
if ($LASTEXITCODE -ne 0) { throw "Launcher compilation failed with exit code $LASTEXITCODE." }
Write-Host "Created $output"
