// Arranque: se ejecuta después de registrar todos los módulos.
async function ejecutarCargaInicial(nombre, tarea) {
    try {
        await tarea();
        return null;
    } catch (error) {
        console.error(`Error cargando ${nombre}:`, error);
        return `${nombre}: ${error.message}`;
    }
}

// Nada de lo que pasa antes de entrar puede dejar la pantalla muerta.
//
// El arranque hacía `await cargarModoApp()` a pelo. Esa función no lanza —tiene
// su propio `catch`— pero si el servidor no contesta, el `await` no vuelve
// nunca: `fetch` no tiene tope de espera. Y entonces lo que viene después
// tampoco se ejecuta, incluido cargar las cuentas. Lo que se ve es la pantalla
// de acceso pintada, el desplegable diciendo «Cargando cuentas…» para siempre y
// ni un mensaje. Desde fuera parece que el programa se colgó.
//
// El modo, el tema y la lista de cuentas son comodidades. Entrar no lo es.

async function antesDeEntrar(nombre, tarea, segundos = 8) {
    try {
        await conTopeDeEspera(tarea, segundos);
        return true;
    } catch (error) {
        console.error(`No se pudo cargar ${nombre} antes de entrar:`, error);
        return false;
    }
}

//: Si la lista de cuentas no llegó, se ponen las de siempre y se dice por qué.
//: Es preferible a un desplegable vacío que no deja ni intentarlo.
function cuentasDeRespaldo(motivo) {
    const select = $('login-usuario');
    if (select && (!select.options.length || !select.options[0].value)) {
        select.innerHTML = '<option value="katerine">Katerine Manzanares</option>'
                         + '<option value="admin">Administrador</option>';
    }
    avisoAcceso('El programa tardó en responder',
                `${motivo} Puedes intentar entrar igualmente; si falla, cierra y `
                + 'vuelve a abrir.');
}

(async function init() {
    tabs();
    // El modo y el tema se cargan antes del login para que la pantalla de
    // acceso conserve la apariencia elegida en la sesión anterior y no se vea
    // un destello en claro antes de ponerse oscura. Con tope: si el servidor no
    // contesta, se entra con la apariencia por defecto y se sigue.
    conectarSelectorDeModo();
    // La apariencia no es una dependencia de las cuentas ni del acceso.
    void antesDeEntrar('claro u oscuro', cargarModoApp);
    void antesDeEntrar('la apariencia', cargarTemaApp);
    recuperarUltimaExportacion();
    if (!await antesDeEntrar('las cuentas', cargarCuentasLogin)) {
        cuentasDeRespaldo('No se pudo leer la lista de cuentas.');
    }
    await esperarInicioSesion();
    const n = new Date();
    const periodoHoy=`${n.getFullYear()}-${String(n.getMonth()+1).padStart(2,'0')}`;
    $('periodo').value = periodoHoy < PERIODO_MINIMO ? PERIODO_MINIMO : periodoHoy;
    $('solicitud-semana-periodo').value = $('periodo').value;
    $('solicitud-turno-periodo').value = $('periodo').value;
    $('solicitud-rango-semana-periodo').value = $('periodo').value;
    inicializarPeriodoReinicio();
    inicializarSelectoresFecha();
    if ($('manual-fecha')) $('manual-fecha').value = $('periodo').value === periodoHoy ? ymd(n) : `${$('periodo').value}-01`;
    sincronizarSelectoresFecha();
    actualizarSemanasModificar();
    $('festivos-anio').value = String(n.getFullYear());
    actualizarSemanasSolicitud();
    actualizarSemanasCambioTemporal();
    camposEmpleado();
    camposSolicitud();
    organizarConfiguracion();
    prepararPasosDeFormulario();
    conectarBarrasPeriodo();
    renderBarrasPeriodo();
    actualizarLimitesDeFecha();
    ajustarBarraDeHerramientas(document.querySelector('.tab.active')?.id || 'personal');

    // Cada bloque se carga de forma independiente. Si una sección tiene datos
    // heredados problemáticos, las demás siguen funcionando y el mensaje indica
    // exactamente qué sección falló en lugar de abortar todo el inicio.
    const errores = [];
    for (const [nombre, tarea] of [
        ['apariencia de la aplicación', cargarTemaApp],
        ['claro u oscuro', cargarModoApp],
        ['barra de la ventana', cargarBarraVentana],
        ['personal', cargarEmpleados],
        ['solicitudes', cargarSolicitudes],
        ['asignaciones y ajustes', cargarRequerimientos],
        ['cambios de turno programados', cargarCambiosTurno],
        ['colores del Excel', cargarConfiguracionExcel],
        ['rutas de la aplicación', cargarRutasAplicacion],
        ['festivos', cargarFestivosConfiguracion],
        ['semanas del mes', cargarSemanasBloqueo],
        ['horarios del período', cargarOpcionesPeriodo],
        ['estado del período', cargarEstadoPeriodo],
        ['reglas activas', cargarReglasActivas],
        ['máximo de jornadas seguidas', cargarReglaRacha],
        ['reparto de turnos por área', cargarReglasCobertura],
        ['seguridad', cargarUsuariosSeguridad],
    ]) {
        const error = await ejecutarCargaInicial(nombre, tarea);
        if (error) errores.push(error);
    }

    if ($('manual-persona') && !$('manual-persona').value && empleados.length) $('manual-persona').value=String(empleados[0].id);
    configurarModoManual();
    // La guía de primeros pasos se muestra al terminar de cargar, cuando ya se
    // ve la aplicación completa y no la pantalla de acceso.
    if (typeof mostrarGuia === 'function') mostrarGuia();
    aplicarFechaMinimaDocumento();
    activarCalendarios();
    conectarOjosDeClave();
    aplicarEdicion();

    if (errores.length) {
        toast(
            errores.join(' · '),
            'error',
            'Inicio parcial'
        );
    }
})().catch(e => toast(e.message, 'error', 'Error al iniciar'));


window.addEventListener('pywebviewready', () => { document.body.dataset.desktop = '1'; });

$('periodo').addEventListener('change', async () => {
    if ($('periodo').value < PERIODO_MINIMO) {
        $('periodo').value=PERIODO_MINIMO;
        sincronizarSelectoresFecha();
        toast('La programación comienza en agosto de 2026.', 'info', 'Período ajustado');
    }
    if ($('manual-fecha')) $('manual-fecha').value=`${$('periodo').value}-01`;
    if (!$('empleado-id')?.value && $('empleado-vigente-desde')) $('empleado-vigente-desde').value = `${$('periodo').value}-01`;
    sincronizarSelectoresFecha();
    semanasEstadoActual = [];
    limpiarProgramacionVisible();
    renderBarrasPeriodo();
    renderSolicitudes();
    renderRequerimientos();
    actualizarLimitesDeFecha();
    await cargarSemanasBloqueo().catch(()=>{ actualizarSemanasModificar(); renderEditorManual(); });
    await cargarOpcionesPeriodo().catch(()=>{});
    await cargarEstadoPeriodo().catch(()=>{});
    await cargarResumenPublicacion().catch(()=>{});
});


document.addEventListener('reset', () => setTimeout(sincronizarSelectoresFecha, 0));
