# Instalar la versión requerida desde la publicación oficial, sin Chocolatey.
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$versionInno = '6.7.3'
$urlInno = 'https://github.com/jrsoftware/issrc/releases/download/is-6_7_3/innosetup-6.7.3.exe'
$temporalInno = Join-Path ([System.IO.Path]::GetTempPath()) ('gestor-inno-' + [guid]::NewGuid())
$destinoInno = Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6'
$descargaInno = Join-Path $temporalInno "innosetup-$versionInno.exe"
$registroInno = Join-Path $temporalInno 'instalacion.log'
New-Item -ItemType Directory -Path $temporalInno -Force | Out-Null

Write-Host "Descargando Inno Setup $versionInno desde su publicación oficial..."
Invoke-WebRequest -Uri $urlInno -OutFile $descargaInno
$firmaInno = Get-AuthenticodeSignature -FilePath $descargaInno
if ($firmaInno.Status -ne 'Valid' -or
    $firmaInno.SignerCertificate.Subject -notmatch 'CN=Pyrsys B\.V\.(?:,|$)') {
    throw "La firma de Inno Setup no es válida o no corresponde a Pyrsys B.V.: $($firmaInno.Status)"
}

$argumentosInno = @(
    '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/CURRENTUSER',
    ('/DIR="{0}"' -f $destinoInno), ('/LOG="{0}"' -f $registroInno)
)
$procesoInno = Start-Process -FilePath $descargaInno -ArgumentList $argumentosInno -Wait -PassThru
if ($procesoInno.ExitCode -notin @(0, 3010)) {
    if (Test-Path $registroInno) { Get-Content $registroInno -Tail 60 }
    throw "No se pudo instalar Inno Setup. Código: $($procesoInno.ExitCode)"
}

$compiladorInno = Join-Path $destinoInno 'ISCC.exe'
if (-not (Test-Path $compiladorInno -PathType Leaf)) {
    throw "La instalación no dejó el compilador esperado: $compiladorInno"
}
$versionInstalada = (Get-Item $compiladorInno).VersionInfo.ProductVersion
if ($versionInstalada -notmatch '^6\.7\.3(?:\.|$)') {
    throw "Se esperaba Inno Setup $versionInno, pero ISCC indica $versionInstalada"
}
# GITHUB_PATH se incorpora en los pasos posteriores. PATH sirve también al uso local.
$env:PATH = "$destinoInno;$env:PATH"
if ($env:GITHUB_PATH) {
    Add-Content -LiteralPath $env:GITHUB_PATH -Value $destinoInno -Encoding utf8
}
Write-Host "Inno Setup $versionInstalada preparado: $compiladorInno"
