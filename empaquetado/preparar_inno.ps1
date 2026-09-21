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
# ISCC.exe es la entrada de consola: ProductVersion no identifica el motor.
# En 6.7.3 la versión se consulta mediante Ver en el preprocesador del compilador.
# Compilar verifica también las DLL, recursos y opciones de apariencia necesarias.
$rutaSonda = Join-Path $temporalInno 'ComprobacionInno.iss'
$ejecutableSonda = Join-Path $temporalInno 'ComprobacionInno.exe'
$contenidoSonda = @"
#if DecodeVer(Ver, 3) != "$versionInno"
  #error La version del motor de Inno Setup no coincide con la requerida.
#endif
[Setup]
AppName=Comprobacion del compilador
AppVersion=1.0
DefaultDirName={tmp}\ComprobacionInno
CreateAppDir=no
Uninstallable=no
PrivilegesRequired=lowest
WizardStyle=modern dynamic windows11
OutputBaseFilename=ComprobacionInno
"@
Set-Content -LiteralPath $rutaSonda -Value $contenidoSonda -Encoding utf8
Write-Host "Comprobando Inno Setup $versionInno mediante una compilación real..."
& $compiladorInno "/O$temporalInno" $rutaSonda
$codigoSonda = $LASTEXITCODE
if ($codigoSonda -ne 0) {
    throw "Falló la comprobación del compilador (código $codigoSonda). Revisa su salida anterior."
}
if (-not (Test-Path $ejecutableSonda -PathType Leaf)) {
    throw 'El compilador terminó sin generar el ejecutable de comprobación.'
}
# La sonda solo se compila; nunca se instala ni se incluye en los artefactos.
Remove-Item -LiteralPath $ejecutableSonda
# GITHUB_PATH se incorpora en los pasos posteriores. PATH sirve también al uso local.
$env:PATH = "$destinoInno;$env:PATH"
if ($env:GITHUB_PATH) {
    Add-Content -LiteralPath $env:GITHUB_PATH -Value $destinoInno -Encoding utf8
}
Write-Host "Inno Setup $versionInno comprobado y preparado: $compiladorInno"
