[CmdletBinding()]
param(
  [ValidateNotNullOrEmpty()] [string]$Distro = 'Ubuntu',
  [ValidateSet(1234)] [int]$Port = 1234
)

$ErrorActionPreference = 'Stop'
$FirewallRuleName = 'QwenSGLangLAN1234'
$StateDirectory = Join-Path $env:ProgramData 'QwenSGLang'
$StateFile = Join-Path $StateDirectory "lan-$Port.json"

function ConvertTo-UsableIPv4 {
  param([Parameter(Mandatory)] [string]$Value)
  $address = $null
  if (-not [System.Net.IPAddress]::TryParse($Value, [ref]$address) -or
      $address.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork -or
      [System.Net.IPAddress]::IsLoopback($address) -or
      $address.Equals([System.Net.IPAddress]::Any)) {
    throw "Invalid IPv4 address: $Value"
  }
  return $address.IPAddressToString
}

function Get-WslIPv4 {
  param([Parameter(Mandatory)] [string]$Distro)
  $output = & wsl.exe -d $Distro -- ip -4 -o addr show dev eth0 scope global 2>&1
  if ($LASTEXITCODE -ne 0) { throw "Could not query IPv4 for WSL distro $Distro`: $output" }
  $match = [regex]::Match(($output -join ' '), '\binet\s+(?<address>(?:\d{1,3}\.){3}\d{1,3})/')
  if (-not $match.Success) { throw "No eth0 IPv4 address found for WSL distro $Distro." }
  return ConvertTo-UsableIPv4 $match.Groups['address'].Value
}

function Get-WindowsLanIPv4 {
  $candidate = Get-NetIPConfiguration |
    Where-Object { $_.NetAdapter.Status -eq 'Up' -and $_.IPv4DefaultGateway } |
    ForEach-Object { $_.IPv4Address } |
    Where-Object { $_.IPAddress -and $_.IPAddress -notlike '169.254.*' } |
    Select-Object -First 1
  if (-not $candidate) { throw 'No active Windows LAN IPv4 address with a default gateway was found.' }
  return ConvertTo-UsableIPv4 $candidate.IPAddress
}

function Test-Administrator {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = [Security.Principal.WindowsPrincipal]::new($identity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Remove-QwenPortProxy {
  param([Parameter(Mandatory)] [string]$ListenAddress)
  & netsh.exe interface portproxy delete v4tov4 "listenport=$Port" "listenaddress=$ListenAddress" protocol=tcp 2>$null | Out-Null
}

$wslAddress = Get-WslIPv4 -Distro $Distro
$lanAddress = Get-WindowsLanIPv4

if (-not (Test-Administrator)) {
  $powershell = Join-Path $PSHOME 'powershell.exe'
  if (-not (Test-Path $powershell)) { $powershell = 'powershell.exe' }
  $arguments = @(
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$PSCommandPath`"",
    '-Distro', "`"$Distro`"", '-Port', $Port
  )
  $elevated = Start-Process -FilePath $powershell -Verb RunAs -Wait -PassThru -ArgumentList $arguments
  exit $elevated.ExitCode
}

New-Item -ItemType Directory -Force -Path $StateDirectory | Out-Null
$previous = if (Test-Path $StateFile) { Get-Content -Raw $StateFile | ConvertFrom-Json } else { $null }
if ($previous -and $previous.FirewallRuleName -eq $FirewallRuleName -and $previous.Port -eq $Port) {
  try { Remove-QwenPortProxy -ListenAddress (ConvertTo-UsableIPv4 ([string]$previous.ListenAddress)) } catch { Write-Warning $_ }
}
Remove-QwenPortProxy -ListenAddress $lanAddress

& netsh.exe interface portproxy add v4tov4 "listenport=$Port" "listenaddress=$lanAddress" "connectport=$Port" "connectaddress=$wslAddress" protocol=tcp | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to add TCP $Port port proxy from $lanAddress to $wslAddress." }

$existingRule = Get-NetFirewallRule -Name $FirewallRuleName -ErrorAction SilentlyContinue
if ($existingRule) { $existingRule | Remove-NetFirewallRule }
New-NetFirewallRule -Name $FirewallRuleName -DisplayName "Qwen SGLang LAN TCP $Port" `
  -Enabled True -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port `
  -LocalAddress $lanAddress -RemoteAddress LocalSubnet -Profile Private | Out-Null

$rule = Get-NetFirewallRule -Name $FirewallRuleName
$portFilter = $rule | Get-NetFirewallPortFilter
$addressFilter = $rule | Get-NetFirewallAddressFilter
if ($rule.Profile -notmatch 'Private' -or $portFilter.LocalPort -notcontains [string]$Port -or
    $addressFilter.RemoteAddress -notcontains 'LocalSubnet') {
  throw "Firewall verification failed for $FirewallRuleName."
}

$proxyOutput = & netsh.exe interface portproxy show v4tov4
$proxyPattern = ('{0}\s+{1}\s+{2}\s+{1}' -f [regex]::Escape($lanAddress), $Port, [regex]::Escape($wslAddress))
if (($proxyOutput -join "`n") -notmatch $proxyPattern) { throw 'Port-proxy verification failed.' }

[pscustomobject]@{
  Distro = $Distro
  Port = $Port
  ListenAddress = $lanAddress
  ConnectAddress = $wslAddress
  FirewallRuleName = $FirewallRuleName
} | ConvertTo-Json | Set-Content -Encoding UTF8 -Path $StateFile

Write-Host "Qwen LAN forwarding enabled: http://$lanAddress`:$Port/v1"
Write-Host "Local endpoint preserved: http://127.0.0.1`:$Port/v1"
Write-Host 'Firewall scope: Private profile, LocalSubnet only.'
