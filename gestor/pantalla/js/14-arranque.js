// Recordar la contraseña, la carga inicial, la guía y el calendario
// ---------------------------------------------------------------------------
// Parte de la pantalla del Gestor de Horarios. Los archivos de esta carpeta se
// cargan en orden y comparten el mismo ámbito, así que juntos son exactamente
// el app.js de antes. Ver frontend/js/LEEME.md.

'use strict';

// ---------------------------------------------------------------------------
// Recordar la contraseña en este equipo
// ---------------------------------------------------------------------------
// Es una comodidad opcional para un ordenador de uso personal: la contraseña se
// guarda en este navegador y solo para la cuenta marcada. Permanece al cerrar
// sesión o la aplicación; se borra únicamente al desmarcar la casilla.
const CLAVE_RECORDADAS = 'gestorhorarios_claves_recordadas';

function clavesRecordadas() {
    try { return JSON.parse(localStorage.getItem(CLAVE_RECORDADAS) || '{}'); }
    catch (_) { return {}; }
}

function apiClaveNativa() {
    return window.pywebview?.api || null;
}

async function esperarApiClaveNativa(intentos = 20) {
    for (let i = 0; i < intentos; i += 1) {
        const apiNativa = apiClaveNativa();
        if (apiNativa?.load && apiNativa?.save && apiNativa?.forget) return apiNativa;
        await new Promise(resolve => setTimeout(resolve, 25));
    }
    return null;
}

async function guardarClaveRecordada(usuario, password) {
    const recordar = !!$('login-recordar')?.checked;
    try {
        const guardadas = clavesRecordadas();
        if (recordar) guardadas[usuario] = password;
        else delete guardadas[usuario];
        localStorage.setItem(CLAVE_RECORDADAS, JSON.stringify(guardadas));
    } catch (_) { /* si el navegador no deja guardar, simplemente no se recuerda */ }
    const apiNativa = await esperarApiClaveNativa();
    if (!apiNativa) return;
    const resultado = recordar
        ? await apiNativa.save(usuario, password)
        : await apiNativa.forget(usuario);
    // No poder recordar la contraseña no es motivo para no dejar entrar. Antes
    // esto lanzaba un error dentro del propio inicio de sesión: si el equipo no
    // podía guardarla —un perfil sin permisos, un disco lleno— la persona veía
    // «No se pudo entrar» con la contraseña correcta y se quedaba fuera.
    // Entra igual, y se le avisa de lo único que ha fallado, que es el recuerdo.
    if (recordar && resultado && resultado.ok === false) {
        return {recordada: false, motivo: String(resultado.error || 'este equipo no pudo guardarla')};
    }
    return {recordada: recordar};
}

async function rellenarClaveRecordada() {
    const usuario = $('login-usuario')?.value;
    const campo = $('login-password');
    const casilla = $('login-recordar');
    if (!usuario || !campo || !casilla) return;
    // Si la persona ya escribió, no se le toca lo escrito.
    //
    // Esto llega hasta el final con dos `await` por medio —la lista de cuentas y
    // la caja de claves del sistema, que tarda hasta ocho intentos—, así que la
    // línea de abajo se ejecutaba **medio segundo después de abrirse la
    // pantalla**. Quien escribía deprisa veía su contraseña desaparecer sola del
    // cuadro y, al pulsar Entrar, «Escribe tu contraseña» con la contraseña
    // recién escrita. Aparecía como intermitente, que es la peor forma de
    // aparecer: la segunda vez ya no pasaba y nadie lo podía reproducir.
    if (campo.dataset.escrito === '1') return;
    let guardada = '';
    const apiNativa = await esperarApiClaveNativa(8);
    if (apiNativa) {
        try {
            const resultado = await apiNativa.load(usuario);
            if (resultado?.ok && resultado.recordada) guardada = resultado.password || '';
        } catch (_) {}
    }
    if (!guardada) guardada = clavesRecordadas()[usuario] || '';
    campo.value = guardada || '';
    casilla.checked = !!guardada;
}

$('login-password')?.addEventListener('input', ev => {
    // Lo marca la persona al teclear. Al cambiar de cuenta se borra la marca:
    // ahí sí queremos la contraseña recordada de la cuenta nueva.
    ev.target.dataset.escrito = ev.target.value ? '1' : '';
});
$('login-usuario')?.addEventListener('change', () => {
    const campo = $('login-password');
    if (campo) campo.dataset.escrito = '';
    void rellenarClaveRecordada();
});
$('login-recordar')?.addEventListener('change', async ev => {
    if (ev.target.checked) return;
    const usuario = $('login-usuario')?.value;
    if (!usuario) return;
    try {
        const guardadas = clavesRecordadas();
        delete guardadas[usuario];
        localStorage.setItem(CLAVE_RECORDADAS, JSON.stringify(guardadas));
    } catch (_) {}
    const apiNativa = await esperarApiClaveNativa(8);
    try { await apiNativa?.forget(usuario); } catch (_) {}
});

$('cerrar-sesion')?.addEventListener('click', async () => {
    try { await api('/api/auth/logout',{method:'POST'}); } catch(_) {}
    // «Recordar» pertenece al equipo, no a la sesión. Salir invalida el token,
    // pero conserva la comodidad elegida para la próxima apertura.
    bloquearSesion();
    location.reload();
});

$('cambiar-clave-propia')?.addEventListener('click', async () => {
    const actual=$('clave-actual').value, nueva=$('clave-nueva').value;
    if (!actual || !nueva) { toast('Escribe tu contraseña actual y la nueva contraseña.','warning','Faltan datos'); return; }
    try {
        const r=await api('/api/auth/password',{method:'PUT',body:JSON.stringify({actual,nueva})});
        toast(r.mensaje,'success','Contraseña actualizada');
        // Si esta cuenta estaba marcada para recordar, sustituye la clave vieja
        // inmediatamente; de lo contrario el siguiente acceso se rellenaría
        // con una contraseña que ya no sirve.
        const usuario = sesionUsuario?.usuario;
        if (usuario && clavesRecordadas()[usuario]) {
            const guardadas = clavesRecordadas();
            guardadas[usuario] = nueva;
            localStorage.setItem(CLAVE_RECORDADAS, JSON.stringify(guardadas));
            const apiNativa = await esperarApiClaveNativa();
            const resultado = await apiNativa?.save(usuario, nueva);
            if (resultado && resultado.ok === false) {
                throw new Error('La contraseña cambió, pero Windows no pudo actualizar la copia recordada.');
            }
        }
        localStorage.removeItem('gestorhorarios_session');
        setTimeout(()=>location.reload(),700);
    } catch(e){ toast(e.message,'error','No se pudo cambiar la contraseña'); }
});

async function ejecutarCargaInicial(nombre, tarea) {
    try {
        await tarea();
        return null;
    } catch (error) {
        console.error(`Error cargando ${nombre}:`, error);
        return `${nombre}: ${error.message}`;
    }
}

(async function init() {
    tabs();
    // El modo y el tema se cargan antes del login para que la pantalla de
    // acceso conserve la apariencia elegida en la sesión anterior y no se vea
    // un destello en claro antes de ponerse oscura.
    conectarSelectorDeModo();
    await cargarModoApp();
    try { await cargarTemaApp(); } catch (_) {}
    recuperarUltimaExportacion();
    await cargarCuentasLogin();
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

// ---------------------------------------------------------------------------
// Primeros pasos
// ---------------------------------------------------------------------------
// Quien abre la aplicación por primera vez encuentra ocho pestañas y ningún
// indicio del orden en que se usan. Esta guía se muestra hasta que la persona
// pide no volver a verla, y siempre se puede recuperar desde la cabecera.
const CLAVE_GUIA = 'gestorhorarios_guia_oculta';

function guiaOculta() {
    try { return localStorage.getItem(CLAVE_GUIA) === '1'; } catch (_) { return false; }
}

function mostrarGuia(forzar = false) {
    const caja = $('guia-inicio');
    if (!caja) return;
    if (!forzar && guiaOculta()) return;
    const check = $('guia-no-mostrar');
    if (check) check.checked = guiaOculta();
    caja.classList.remove('hidden');
    // La guía se muestra plegada: una línea con el título y un botón. Antes
    // ocupaba la pantalla entera en todos los apartados y había que
    // desplazarse para llegar al trabajo. Solo se abre entera cuando se pide
    // desde «¿Cómo empiezo?».
    plegarGuia(forzar);
    if (forzar) caja.scrollIntoView({block: 'nearest', behavior: 'smooth'});
}

function plegarGuia(abierta) {
    const caja = $('guia-inicio');
    const boton = $('guia-desplegar');
    if (!caja) return;
    caja.classList.toggle('abierta', Boolean(abierta));
    if (boton) {
        boton.setAttribute('aria-expanded', abierta ? 'true' : 'false');
        const texto = boton.querySelector('span');
        if (texto) texto.textContent = abierta ? 'Ocultar los pasos' : 'Ver los siete pasos';
    }
}

function ocultarGuia() {
    $('guia-inicio')?.classList.add('hidden');
}

$('guia-cerrar')?.addEventListener('click', ocultarGuia);
$('guia-desplegar')?.addEventListener('click', () => plegarGuia(!$('guia-inicio')?.classList.contains('abierta')));
$('abrir-guia')?.addEventListener('click', () => mostrarGuia(true));
$('guia-no-mostrar')?.addEventListener('change', ev => {
    try {
        if (ev.target.checked) localStorage.setItem(CLAVE_GUIA, '1');
        else localStorage.removeItem(CLAVE_GUIA);
    } catch (_) { /* si el navegador no deja guardar, la guía simplemente reaparece */ }
});
document.querySelectorAll('.guide-step').forEach(boton => {
    boton.addEventListener('click', () => {
        const destino = boton.dataset.ir;
        document.querySelector(`[data-tab="${destino}"]`)?.click();
        window.scrollTo({top: 0, behavior: 'smooth'});
    });
});

// ---------------------------------------------------------------------------
// Calendario propio
// ---------------------------------------------------------------------------
// El calendario nativo del navegador no se puede diseñar: cada sistema lo pinta
// a su manera y en la ventana de escritorio salía con colores que no son los de
// la aplicación. Este lo sustituye por uno propio, con el mismo estilo que el
// resto, y conserva el campo original para que nada del código cambie: se sigue
// leyendo y escribiendo `input.value` en formato AAAA-MM-DD.
const MESES_LARGOS = ['enero','febrero','marzo','abril','mayo','junio','julio',
                      'agosto','septiembre','octubre','noviembre','diciembre'];
const DIAS_CORTOS = ['L','M','X','J','V','S','D'];

let calendarioAbierto = null;

function cerrarCalendario() {
    if (!calendarioAbierto) return;
    calendarioAbierto.caja.remove();
    calendarioAbierto.campo.setAttribute('aria-expanded', 'false');
    calendarioAbierto = null;
}

function fechaLegibleCorta(iso) {
    if (!iso) return '';
    const [a, m, d] = String(iso).split('-').map(Number);
    if (!a || !m || !d) return '';
    return `${String(d).padStart(2,'0')} ${MESES_LARGOS[m-1].slice(0,3)} ${a}`;
}

function limitesDe(input) {
    const min = input.min || INICIO_OPERACION_ISO;
    const max = input.max || '';
    return {min, max};
}

function construirMes(campo, ancla) {
    const {min, max} = limitesDe(campo);
    const anio = ancla.getFullYear(), mes = ancla.getMonth();
    const primero = new Date(anio, mes, 1);
    // La semana empieza en lunes, como el resto de la aplicación.
    const desplazamiento = (primero.getDay() + 6) % 7;
    const dias = new Date(anio, mes + 1, 0).getDate();
    const seleccionado = campo.value || '';
    const hoy = new Date();
    const hoyIso = `${hoy.getFullYear()}-${String(hoy.getMonth()+1).padStart(2,'0')}-${String(hoy.getDate()).padStart(2,'0')}`;

    let celdas = '';
    for (let i = 0; i < desplazamiento; i++) celdas += '<span class="dp-hueco"></span>';
    for (let d = 1; d <= dias; d++) {
        const iso = `${anio}-${String(mes+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
        // Hay campos que solo admiten lunes —la fecha desde la que se cuenta la
        // alternancia AM/PM de un rotativo—. El calendario dejaba elegir
        // cualquier día y el rechazo llegaba al guardar, cuando ya se había
        // rellenado todo el formulario. Se apagan aquí.
        const soloLunes = campo.dataset.soloLunes === '1';
        const esLunes = new Date(anio, mes, d).getDay() === 1;
        const fuera = (min && iso < min) || (max && iso > max) || (soloLunes && !esLunes);
        const clases = ['dp-dia'];
        if (iso === seleccionado) clases.push('sel');
        if (iso === hoyIso) clases.push('hoy');
        const finde = new Date(anio, mes, d).getDay();
        if (finde === 0 || finde === 6) clases.push('finde');
        celdas += fuera
            ? `<span class="dp-dia fuera" aria-disabled="true">${d}</span>`
            : `<button type="button" class="${clases.join(' ')}" data-iso="${iso}" `
              + `aria-label="${d} de ${MESES_LARGOS[mes]} de ${anio}"`
              + `${iso === seleccionado ? ' aria-current="date"' : ''}>${d}</button>`;
    }

    // Las flechas se apagan cuando al otro lado no queda ningún día elegible:
    // así se ve de un vistazo hasta dónde llega lo que se puede elegir, en vez
    // de pasar meses en blanco.
    const primeroDelMes = `${anio}-${String(mes+1).padStart(2,'0')}-01`;
    const ultimoDelMes = `${anio}-${String(mes+1).padStart(2,'0')}-${String(dias).padStart(2,'0')}`;
    const anteriorFuera = !!(min && primeroDelMes <= min);
    const siguienteFuera = !!(max && ultimoDelMes >= max);
    return `
      <div class="dp-cabecera">
        <button type="button" class="dp-nav" data-salto="-1" aria-label="Mes anterior" ${anteriorFuera ? 'disabled' : ''}>‹</button>
        <strong>${MESES_LARGOS[mes][0].toUpperCase()}${MESES_LARGOS[mes].slice(1)} de ${anio}</strong>
        <button type="button" class="dp-nav" data-salto="1" aria-label="Mes siguiente" ${siguienteFuera ? 'disabled' : ''}>›</button>
      </div>
      <div class="dp-semana">${DIAS_CORTOS.map(x => `<span>${x}</span>`).join('')}</div>
      <div class="dp-rejilla">${celdas}</div>
      <div class="dp-pie">
        <button type="button" class="dp-accion" data-accion="hoy">Hoy</button>
        <button type="button" class="dp-accion" data-accion="limpiar">Borrar</button>
      </div>`;
}

function abrirCalendario(campo) {
    if (calendarioAbierto?.campo === campo) { cerrarCalendario(); return; }
    cerrarCalendario();
    const {min} = limitesDe(campo);
    const partida = campo.value || min || INICIO_OPERACION_ISO;
    const [a, m] = partida.split('-').map(Number);
    let ancla = new Date(a, (m || 1) - 1, 1);

    const caja = document.createElement('div');
    caja.className = 'datepicker';
    caja.setAttribute('role', 'dialog');
    caja.setAttribute('aria-label', 'Elegir fecha');
    const pintar = () => { caja.innerHTML = construirMes(campo, ancla); };
    pintar();
    document.body.appendChild(caja);

    const colocar = () => {
        const r = campo.getBoundingClientRect();
        const alto = caja.offsetHeight || 320;
        const abajo = window.innerHeight - r.bottom;
        const arriba = abajo < alto + 12 && r.top > alto + 12;
        caja.style.top = `${(arriba ? r.top - alto - 6 : r.bottom + 6) + window.scrollY}px`;
        caja.style.left = `${Math.max(8, Math.min(r.left + window.scrollX, window.scrollX + window.innerWidth - caja.offsetWidth - 8))}px`;
    };
    colocar();

    caja.addEventListener('click', ev => {
        // Este clic es del calendario y aquí termina. Sin esto, al pulsar las
        // flechas de mes el calendario se redibuja y el clic sigue subiendo
        // hasta el cierre-al-pulsar-fuera; para entonces el botón que se pulsó
        // ya no existe —lo acaba de reemplazar el redibujado—, así que se
        // tomaba por un clic fuera y el calendario se cerraba. Ese era el
        // motivo de que no se pudiera cambiar de mes.
        ev.stopPropagation();
        const salto = ev.target.closest('[data-salto]');
        if (salto) {
            ancla = new Date(ancla.getFullYear(), ancla.getMonth() + Number(salto.dataset.salto), 1);
            pintar(); colocar(); return;
        }
        const accion = ev.target.closest('[data-accion]');
        if (accion) {
            if (accion.dataset.accion === 'limpiar') {
                if (!campo.required) { campo.value = ''; campo.dispatchEvent(new Event('change', {bubbles:true})); }
                cerrarCalendario();
            } else {
                // «Hoy» solo tiene sentido si hoy se puede elegir. Fuera del
                // rango permitido lleva al día más cercano que sí se puede.
                const {min: mn, max: mx} = limitesDe(campo);
                const h = new Date();
                let destino = `${h.getFullYear()}-${String(h.getMonth()+1).padStart(2,'0')}-${String(h.getDate()).padStart(2,'0')}`;
                if (mn && destino < mn) destino = mn;
                if (mx && destino > mx) destino = mx;
                const [da, dm] = destino.split('-').map(Number);
                ancla = new Date(da, dm - 1, 1);
                pintar(); colocar();
            }
            return;
        }
        const dia = ev.target.closest('.dp-dia[data-iso]');
        if (dia) {
            campo.value = dia.dataset.iso;
            campo.dispatchEvent(new Event('input', {bubbles:true}));
            campo.dispatchEvent(new Event('change', {bubbles:true}));
            cerrarCalendario();
            campo.focus();
        }
    });

    calendarioAbierto = {campo, caja, recolocar: colocar};
    campo.setAttribute('aria-expanded', 'true');
}

document.addEventListener('click', ev => {
    if (!calendarioAbierto) return;
    if (calendarioAbierto.caja.contains(ev.target)) return;
    if (ev.target.closest('.date-field')?.contains(calendarioAbierto.campo)) return;
    cerrarCalendario();
});
document.addEventListener('keydown', ev => { if (ev.key === 'Escape' && calendarioAbierto) cerrarCalendario(); });
window.addEventListener('resize', () => calendarioAbierto?.recolocar());
window.addEventListener('scroll', () => calendarioAbierto?.recolocar(), true);

// Convierte los campos de fecha en un control propio. El input original se
// conserva (oculto para el ratón, no para el código) para que toda la
// aplicación siga leyendo `input.value` exactamente igual que antes.
function activarCalendarios(raiz = document) {
    raiz.querySelectorAll('input[type="date"]').forEach(campo => {
        if (campo.dataset.dpListo === '1') return;
        campo.dataset.dpListo = '1';
        const envoltura = document.createElement('div');
        envoltura.className = 'date-field';
        campo.parentNode.insertBefore(envoltura, campo);
        envoltura.appendChild(campo);
        const boton = document.createElement('button');
        boton.type = 'button';
        boton.className = 'date-display';
        boton.innerHTML = `<span class="date-text"></span>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3v3M17 3v3M3.5 9h17M5 5.5h14a1.5 1.5 0 0 1 1.5 1.5v12A1.5 1.5 0 0 1 19 20.5H5A1.5 1.5 0 0 1 3.5 19V7A1.5 1.5 0 0 1 5 5.5Z"/></svg>`;
        envoltura.appendChild(boton);
        const etiqueta = campo.getAttribute('aria-label') || campo.getAttribute('title')
            || campo.closest('label')?.childNodes[0]?.textContent?.trim() || 'fecha';
        boton.setAttribute('aria-label', `Elegir ${etiqueta}`);
        boton.setAttribute('aria-haspopup', 'dialog');
        const refrescar = () => {
            const texto = boton.querySelector('.date-text');
            texto.textContent = fechaLegibleCorta(campo.value) || 'Sin fecha';
            texto.classList.toggle('vacio', !campo.value);
        };
        // El botón tiene que seguir al campo: los formularios habilitan y
        // deshabilitan sus fechas según el tipo de solicitud. Antes el estado
        // se copiaba una sola vez, al crear el control, así que un campo que
        // nacía deshabilitado se quedaba con el botón muerto para siempre: se
        // veía el control nuevo y no se abría nada al pulsarlo.
        const seguirEstado = () => {
            boton.disabled = campo.disabled;
            boton.classList.toggle('desactivado', campo.disabled);
        };
        const sincronizar = () => { refrescar(); seguirEstado(); };
        sincronizar();
        campo.addEventListener('change', refrescar);
        campo.addEventListener('input', refrescar);
        // El resto de la aplicación asigna `input.value` y `input.disabled`
        // directamente, sin lanzar eventos. Se vigila el atributo para no
        // depender de que cada sitio se acuerde de avisar.
        new MutationObserver(seguirEstado).observe(campo, {
            attributes: true, attributeFilter: ['disabled'],
        });
        campo._syncCalendario = sincronizar;
        boton.addEventListener('click', () => { if (!campo.disabled) abrirCalendario(campo); });
    });
}

// Si a la instalación le falta el archivo de una programación base, ese mes
// aparecería vacío y la aplicación ofrecería generarlo, como si nunca hubiera
// existido. Se dice en voz alta: es un problema de la copia instalada, no algo
// que se arregle generando el mes otra vez.
function avisarProblemasDeBase(problemas) {
    if (!Array.isArray(problemas) || !problemas.length) return;
    const meses = problemas.map(p => p.periodo).join(', ');
    const archivos = problemas.map(p => p.archivo).filter(Boolean).join(' y ');
    const carpeta = problemas.map(p => p.carpeta_reposicion).filter(Boolean)[0] || '';
    const comoArreglarlo = archivos && carpeta
        ? `Copia ${archivos} en ${carpeta} y vuelve a abrir la aplicación; o reinstálala con su carpeta «data» completa.`
        : 'Vuelve a instalar la aplicación con su carpeta «data» completa.';
    toast(`Falta la programación base de ${meses}, así que ese mes sale vacío. ${comoArreglarlo} No lo generes de nuevo: se perdería la programación que ya está vigente.`,
          'error', 'Instalación incompleta', 20000);
    console.error('[base] programación base incompleta:', problemas);
}

// El nombre y la versión vienen del servidor, así que la portada, el título de
// la ventana y la pantalla de acceso dicen siempre lo mismo sin repetirlo a
// mano en tres sitios.
async function aplicarEdicion() {
    try {
        const salud = await fetch('/api/salud').then(r => r.json());
        avisarProblemasDeBase(salud?.problemas_base);
        const e = salud?.edicion;
        if (!e) return;
        const nombre = `${e.nombre} ${e.version}`.trim();
        document.title = nombre;
        const marca = $('nombre-edicion');
        if (marca) marca.textContent = nombre;
        // La pantalla de acceso dice qué aplicación es y en qué versión: es lo
        // único que alguien necesita confirmar antes de escribir su clave.
        const titulo = $('login-titulo');
        if (titulo) titulo.textContent = e.nombre || nombre;
        const edicion = $('login-edicion');
        if (edicion) edicion.textContent = `Programación de turnos · ${e.version || ''}`.trim();
        // La tarjeta de actualizaciones enseña la versión instalada desde el
        // primer momento, sin obligar a pulsar «comprobar» para saber qué se
        // tiene puesto. Es la pregunta que hace todo el que llama pidiendo
        // ayuda, y hasta ahora había que ir a buscarla al pie de la ventana.
        const instalada = $('version-instalada');
        if (instalada) instalada.textContent = e.version_motor || e.version || '—';
    } catch (_) { /* sin conexión, se queda la disposición del propio archivo */ }
}
