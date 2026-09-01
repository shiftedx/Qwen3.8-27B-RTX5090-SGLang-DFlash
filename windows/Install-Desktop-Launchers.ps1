[CmdletBinding()]
param(
  [string]$Distro = "Ubuntu",
  [string]$Destination = [Environment]::GetFolderPath("Desktop"),
  [switch]$Force
)

function Resolve-WslRepositoryPath {
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)] [string]$RepositoryWindowsPath,
    [Parameter(Mandatory)] [string]$Distro
  )
  if ($RepositoryWindowsPath -match '^\\\\(?:wsl\$|wsl\.localhost)\\(?<uncDistro>[^\\]+)(?<unixPath>\\.*)$') {
    if ($Matches.uncDistro -ine $Distro) { throw "Distro does not match repository UNC path: $($Matches.uncDistro) versus $Distro." }
    return $Matches.unixPath -replace '\\', '/'
  }
  $derived = (& wsl.exe -d $Distro -- wslpath -a ($RepositoryWindowsPath -replace '\\', '/')).Trim()
  if (-not $derived) { throw "Could not derive a WSL path for $RepositoryWindowsPath in distro $Distro." }
  return $derived
}

function New-DesktopLauncherLines {
  [CmdletBinding()]
  param(
    [Parameter(Mandatory)] [string]$Distro,
    [Parameter(Mandatory)] [string]$RepositoryWindowsPath,
    [Parameter(Mandatory)] [string]$RepositoryWslPath,
    [Parameter(Mandatory)] [string]$Name
  )
  return @(
    '@echo off',
    ('set "DISTRO={0}"' -f $Distro),
    ('set "QWEN_WSL_REPO={0}"' -f $RepositoryWslPath),
    ('call "{0}\windows\{1}.cmd" "%DISTRO%"' -f $RepositoryWindowsPath, $Name)
  )
}

if ($MyInvocation.InvocationName -eq '.') { return }

$repoWindows = (Resolve-Path (Join-Path $PSScriptRoot "..")).ProviderPath
$repoWsl = Resolve-WslRepositoryPath -RepositoryWindowsPath $repoWindows -Distro $Distro
New-Item -ItemType Directory -Force -Path $Destination | Out-Null
foreach ($name in "Start-Qwen-Max", "Stop-Qwen-Max") {
  $target = Join-Path $Destination "$name.cmd"
  if ((Test-Path $target) -and -not $Force) { throw "$target exists; pass -Force to replace it." }
  New-DesktopLauncherLines -Distro $Distro -RepositoryWindowsPath $repoWindows -RepositoryWslPath $repoWsl -Name $name | Set-Content -Encoding ascii -Path $target
}
Write-Host "Installed Start/Stop launchers in $Destination for WSL distro $Distro."
