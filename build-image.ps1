$ErrorActionPreference = "Stop"
$Image = "android0431/lastmile"
$Version = "0.11"

Set-Location $PSScriptRoot

Write-Host "==> Building $Image`:$Version ..."
docker build -t "${Image}:${Version}" -t "${Image}:latest" .

Write-Host "==> Local images:"
docker images $Image
