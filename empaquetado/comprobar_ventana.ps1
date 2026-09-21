# Comprobar el ejecutable recién creado y dejar el diagnóstico en los artefactos.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$raizProyecto = Split-Path $PSScriptRoot -Parent
$ejecutable = Join-Path $raizProyecto 'dist\GestorHorarios\GestorHorarios.exe'
$diagnostico = Join-Path $raizProyecto 'dist\diagnostico\ventana'
New-Item -ItemType Directory -Path $diagnostico -Force | Out-Null
if (-not (Test-Path $ejecutable -PathType Leaf)) {
    throw "No existe el ejecutable que debe probarse: $ejecutable"
}
$informe = Join-Path $diagnostico 'comprobacion-ventana.json'
# Un informe de otra ejecución no puede acreditar la prueba actual.
if (Test-Path $informe -PathType Leaf) { Remove-Item -LiteralPath $informe }
$datosAnteriores = $env:GESTOR_DATOS
try {
    # El padre solo deja aquí el informe. El hijo usa datos temporales propios.
    $env:GESTOR_DATOS = $diagnostico
    $proceso = Start-Process -FilePath $ejecutable -ArgumentList '--comprobar-ventana' -PassThru
    if (-not $proceso.WaitForExit(100000)) {
        $proceso.Kill($true)
        $proceso.WaitForExit()
        throw 'La comprobación nativa no terminó en 100 segundos.'
    }
    if (-not (Test-Path $informe -PathType Leaf)) {
        throw "La ventana no dejó un informe. Código de salida: $($proceso.ExitCode)"
    }
    $contenido = Get-Content -LiteralPath $informe -Raw
    Write-Host $contenido
    $resultado = $contenido | ConvertFrom-Json
    if ($proceso.ExitCode -ne 0 -or $resultado.ok -ne $true) {
        throw "Falló la ventana real. Código: $($proceso.ExitCode). Consulta el diagnóstico."
    }
} finally {
    $env:GESTOR_DATOS = $datosAnteriores
}
