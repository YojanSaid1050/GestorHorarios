// Colores del horario, paletas, claro y oscuro
// ---------------------------------------------------------------------------
// Parte de la pantalla del Gestor de Horarios. Los archivos de esta carpeta se
// cargan en orden y comparten el mismo ámbito, así que juntos son exactamente
// el app.js de antes. Ver frontend/js/LEEME.md.

'use strict';


function nombreColorConfiguracion(key) {
    const input = $(COLOR_INPUTS[key]);
    const label = input?.closest('label');
    if (!label) return 'este elemento';
    const texto = [...label.childNodes].find(n => n.nodeType === Node.TEXT_NODE && n.textContent.trim());
    return texto ? texto.textContent.trim() : 'este elemento';
}

function inicializarRestauracionIndividualColores() {
    Object.entries(COLOR_INPUTS).forEach(([key, id]) => {
        const input = $(id);
        const label = input?.closest('label');
        if (!input || !label || label.querySelector('.color-reset-one')) return;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'color-reset-one';
        btn.textContent = 'Usar original';
        btn.title = `Restaurar solo ${nombreColorConfiguracion(key).toLowerCase()}`;
        btn.onclick = async ev => {
            ev.preventDefault();
            ev.stopPropagation();
            try {
                const data = await api(`/api/configuracion/colores-excel/${encodeURIComponent(key)}`, {method:'DELETE'});
                aplicarColoresFormulario(data.colores || {});
                toast(`${nombreColorConfiguracion(key)} volvió a su color original.`, 'success', 'Color restaurado');
            } catch (e) {
                toast(e.message, 'error', 'No se pudo restaurar el color');
            }
        };
        label.appendChild(btn);
    });
}

// Texto legible sobre un color cualquiera del horario.
//
// Los colores del horario los elige la persona que usa la aplicación, así que
// el color de la letra no puede estar escrito a mano en el CSS: una paleta
// oscura dejaba la cabecera del último viernes con letra oscura sobre fondo
// oscuro, ilegible. Se calcula el contraste real contra blanco y contra el
// tinte oscuro de la marca y gana el que mejor se lee.
function textoSobre(hex) {
    const n = String(hex || '').replace('#', '');
    if (n.length !== 6) return '#ffffff';
    const canal = i => {
        const v = parseInt(n.slice(i * 2, i * 2 + 2), 16) / 255;
        return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    const L = 0.2126 * canal(0) + 0.7152 * canal(1) + 0.0722 * canal(2);
    const conBlanco = 1.05 / (L + 0.05);
    const conOscuro = (L + 0.05) / 0.0916;   // luminancia de #231D2B
    return conBlanco >= conOscuro ? '#ffffff' : '#231d2b';
}

function aplicarColoresHorario(colores) {
    const root = document.documentElement;
    const get = key => '#' + String(colores[key] || 'FFFFFF').replace('#','').toUpperCase();
    const poner = (nombre, key) => {
        const valor = get(key);
        root.style.setProperty(`--schedule-${nombre}`, valor);
        root.style.setProperty(`--schedule-${nombre}-text`, textoSobre(valor));
    };
    poner('header', 'header');
    poner('saturday', 'saturday_header');
    poner('sunday', 'sunday_header');
    poner('holiday', 'holiday_header');
    poner('admin-friday', 'admin_friday_header');
    poner('admin-friday-cell', 'admin_friday_cell');
    poner('otro-mes', 'otro_mes_header');
    poner('otro-mes-cell', 'otro_mes_cell');
    ['AM','PM','D','ADM-GS','ADM-AC','VAC','INC','PER','CAP'].forEach(key => {
        poner(key.replace(/[^A-Z]/g,'_'), key);
    });
}

function aplicarColoresFormulario(colores) {
    // Refresca los selectores de color y su código hexadecimal con lo que
    // acaba de devolver el servidor. Sin esto, aplicar una paleta la guardaba
    // bien pero la pantalla seguía mostrando los colores anteriores: parecía
    // que la paleta «se desconfiguraba» al seleccionarla.
    if (!colores) return;
    document.querySelectorAll('[data-color-key]').forEach(input => {
        const key = input.dataset.colorKey;
        const valor = colores[key];
        if (!valor) return;
        const hex = '#' + String(valor).replace('#', '').toUpperCase();
        input.value = hex;
        const code = document.querySelector(`[data-color-code="${key}"]`);
        if (code) code.textContent = hex;
    });
    // Y la vista del horario, para que el cambio se vea sin recargar.
    aplicarColoresHorario(colores);
}

if ($('tema-app')) $('tema-app').onchange = () => { const tema = temaSeleccionado(); if (tema) aplicarTemaApp(tema); };

if ($('guardar-tema-app')) $('guardar-tema-app').onclick = async () => {
    const tema = temaSeleccionado();
    if (!tema) return toast('Selecciona un color para la aplicación.', 'warning', 'Falta el color');
    try {
        const data = await api('/api/configuracion/tema-app', {method:'PUT', body:JSON.stringify({tema:tema.id})});
        aplicarTemaApp(data.tema);
        toast(data.mensaje, 'success', 'Color de la aplicación actualizado');
        await ofrecerPaletaAJuego(data.tema);
    } catch (e) { toast(e.message, 'error', 'No se pudo guardar el color'); }
};

// Los colores del horario son los del Excel, y esos no se cambian solos: lo
// que sale impreso no puede moverse porque alguien haya elegido otro color de
// aplicación. Pero dejarlos morados junto a una interfaz azul tampoco tiene
// sentido, así que se ofrece y decide la persona.
async function ofrecerPaletaAJuego(tema) {
    if (!tema?.id) return;
    const paletaId = tema.id === 'morado' ? 'actual' : `tema_${tema.id}`;
    let paletas = [];
    try {
        paletas = (await api('/api/configuracion/colores-excel')).paletas || [];
    } catch (_) { return; }
    const aJuego = paletas.find(p => p.id === paletaId);
    if (!aJuego) return;

    const ok = await confirmarUI({
        titulo: 'Poner el horario a juego',
        mensaje: `¿Quieres que los colores del horario vayan a juego con ${String(tema.nombre).toLowerCase()}?`,
        detalle: 'Cambia los encabezados del horario que ves en pantalla y los del Excel: cabecera, sábado, domingo, festivo y viernes administrativo. Los turnos no se tocan —AM sigue en blanco, PM en lila y ADM-GS en verde— porque son los que la operación lee de un vistazo.',
        aceptar: 'Sí, a juego',
        cancelar: 'Dejar los de ahora',
        peligro: false,
    });
    if (!ok) return;
    try {
        const r = await api('/api/configuracion/colores-excel/paleta', {
            method: 'POST', body: JSON.stringify({paleta: paletaId}),
        });
        aplicarColoresFormulario(r.colores || {});
        await cargarConfiguracionExcel();
        if (typeof renderHorario === 'function' && ultimo) renderHorario(ultimo);
        toast('Los encabezados del horario y del Excel van a juego con el color de la aplicación.',
              'success', 'Horario a juego');
    } catch (e) {
        toast(e.message, 'error', 'No se pudo aplicar la paleta a juego');
    }
}

if ($('restablecer-tema-app')) $('restablecer-tema-app').onclick = async () => {
    try {
        const data = await api('/api/configuracion/tema-app', {method:'DELETE'});
        if ($('tema-app')) $('tema-app').value = data.tema.id;
        aplicarTemaApp(data.tema);
        toast(data.mensaje, 'success', 'Color restablecido');
    } catch (e) { toast(e.message, 'error', 'No se pudo restablecer el color'); }
};


function periodoEsIgualOPosterior(valor, corte) {
    return String(valor || '') >= String(corte || '');
}

function limpiarProgramacionVisible() {
    ultimo = null;
    alternativasActuales = [];
    respuestaGeneracion = null;
    renderHorario({horario: []});
    renderAlternativas(null);
    $('panel-validacion').innerHTML = '<div class="info-box">Genera un horario para ver la revisión.</div>';
    const tabValidacion = document.querySelector('[data-tab="validacion"]');
    if (tabValidacion) {
        tabValidacion.dataset.count = '0';
        tabValidacion.dataset.errores = '0';
    }
    actualizarContadoresMenu();
    $('exportar').disabled = true;
    $('abrir-exportaciones').classList.add('hidden');
    $('abrir-archivo-exportado')?.classList.add('hidden');
}

function inicializarPeriodoReinicio() {
    const anioSel = $('reiniciar-anio');
    const mesSel = $('reiniciar-mes');
    const hidden = $('reiniciar-periodo');
    if (!anioSel || !mesSel || !hidden) return;

    const MESES = [
        'Enero','Febrero','Marzo','Abril','Mayo','Junio',
        'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'
    ];
    const actual = new Date().getFullYear();
    const fin = Math.max(actual + 8, 2035);
    anioSel.innerHTML = Array.from({length: fin - 2026 + 1}, (_, i) => 2026 + i)
        .map(y => `<option value="${y}">${y}</option>`).join('');
    anioSel.value = '2026';

    const sincronizar = () => {
        hidden.value = `${anioSel.value}-${String(Number(mesSel.value)).padStart(2, '0')}`;
    };

    const actualizarMeses = () => {
        const anio = Number(anioSel.value);
        const valorAnterior = Number(mesSel.value) || 10;
        // Agosto y septiembre de 2026 son las dos programaciones base y no se
        // reinician. En 2026 solo se puede reiniciar desde octubre; a partir
        // de 2027 vuelven a estar disponibles los doce meses del año.
        const primerMes = anio === 2026 ? 10 : 1;
        const permitidos = Array.from({length: 13 - primerMes}, (_, i) => primerMes + i);
        mesSel.innerHTML = permitidos
            .map(m => `<option value="${m}">${MESES[m - 1]}</option>`).join('');
        mesSel.value = String(permitidos.includes(valorAnterior) ? valorAnterior : primerMes);
        sincronizar();
    };

    anioSel.onchange = actualizarMeses;
    mesSel.onchange = sincronizar;
    actualizarMeses();
}

$('reiniciar-programacion').onclick = async () => {
    const valor = $('reiniciar-periodo').value;
    const match = /^(\d{4})-(\d{2})$/.exec(valor || '');
    if (!match) {
        toast('Selecciona el mes desde el que deseas reiniciar la programación.', 'warning', 'Falta el periodo');
        return;
    }
    const anio = Number(match[1]);
    const mes = Number(match[2]);
    if (valor < '2026-10') {
        toast('Agosto y septiembre de 2026 son las programaciones base y no se reinician. Selecciona octubre de 2026 o un mes posterior.', 'warning', 'Periodo protegido');
        return;
    }

    const ok = await confirmarUI({
        titulo: 'Reiniciar programación',
        mensaje: `¿Eliminar todas las programaciones guardadas desde ${valor} en adelante?`,
        detalle: 'Se eliminarán las opciones y los horarios oficiales desde ese mes en adelante. Se conservan las dos programaciones base —agosto y septiembre de 2026—, el personal, las parejas, las solicitudes, los colores y los festivos ajustados.',
        aceptar: 'Reiniciar programación',
        peligro: true,
    });
    if (!ok) return;
    const claveUsuario = await pedirClaveUsuario('Reiniciar programación');
    if (!claveUsuario) return;

    try {
        setEstado('Reiniciando programación…', 'working');
        const data = await api('/api/configuracion/reiniciar-programacion', {
            method: 'POST',
            headers: {'X-User-Password': claveUsuario},
            body: JSON.stringify({mes, anio}),
        });
        if (periodoEsIgualOPosterior($('periodo').value, valor)) {
            limpiarProgramacionVisible();
            await cargarOpcionesPeriodo().catch(()=>{});
            await cargarEstadoPeriodo().catch(()=>{});
            await cargarSemanasBloqueo().catch(()=>{});
        }
        setEstado('Programación reiniciada', 'success', 1600);
        toast(`${data.registros_eliminados} registro(s) eliminados en ${data.periodos_afectados} periodo(s).`, 'success', 'Programación reiniciada');
    } catch (e) {
        setEstado('No se pudo reiniciar', 'error', 2200);
        toast(e.message, 'error', 'No se pudo reiniciar');
    }
};

$('reiniciar-fabrica').onclick = async () => {
    const ok = await confirmarUI({
        titulo: 'Restablecer aplicación de fábrica',
        mensaje: '¿Quieres borrar todos los datos creados durante las pruebas?',
        detalle: 'Se restaurará el personal inicial y quedarán únicamente los horarios oficiales/publicados de agosto y septiembre de 2026. Se eliminarán solicitudes, asignaciones, horarios posteriores, semanas cerradas, festivos ajustados, historial, personal agregado y personalizaciones. También se repondrán las cuentas y las contraseñas iniciales: se cerrará tu sesión y tendrás que volver a entrar con la contraseña de fábrica, así que asegúrate de tenerla a mano. Antes de hacerlo se creará una copia de seguridad automática.',
        aceptar: 'Sí, restablecer de fábrica',
        peligro: true,
    });
    if (!ok) return;
    const claveAdmin = await pedirClaveAdmin('Restablecer aplicación de fábrica');
    if (!claveAdmin) return;
    try {
        setEstado('Restableciendo la aplicación…', 'working');
        const data = await api('/api/configuracion/reiniciar-fabrica', {method: 'POST', headers:{'X-Admin-Password':claveAdmin}});
        toast(data.mensaje, 'success', 'Aplicación restablecida');
        setEstado('Estado inicial restaurado. Vuelve a iniciar sesión con la contraseña de fábrica.', 'success');
        setTimeout(() => window.location.reload(), 900);
    } catch (e) {
        setEstado('', '');
        toast(e.message, 'error', 'No se pudo restablecer');
    }
};


function leerColoresFormulario() {
    const out = {};
    Object.entries(COLOR_INPUTS).forEach(([key, id]) => { out[key] = $(id).value; });
    return out;
}

async function cargarConfiguracionExcel() {
    const data = await api('/api/configuracion/colores-excel');
    aplicarColoresFormulario(data.colores || {});
    inicializarRestauracionIndividualColores();
    renderPaletas(data.paletas || []);
}

// Una paleta es un punto de partida: la aplica de golpe y deja todos los
// colores igual de editables que antes.
// Las paletas se muestran como fichas pequeñas en dos grupos: las pensadas
// para el horario y las que van a juego con el color elegido para la
// aplicación. Cada ficha enseña seis muestras reales; la explicación aparece
// al pasar el ratón, para que la fila no ocupe media pantalla.
const CLAVES_MUESTRA = ['header', 'AM', 'PM', 'D', 'ADM-GS', 'ADM-AC', 'otro_mes_cell'];
const GRUPOS_PALETAS = [
    // La combinación propia va primero: es la que alguien construyó a mano y
    // la que va a querer recuperar después de probar otras.
    ['propia', 'Tu combinación'],
    ['horario', 'Para el horario y el Excel'],
    ['tema', 'A juego con el color de la aplicación'],
];

function fichaPaleta(p) {
    const muestras = CLAVES_MUESTRA
        .map(k => `<i style="background:#${esc(p.colores[k] || 'CCCCCC')}"></i>`).join('');
    const nombre = String(p.nombre || '').replace(/^A juego · /, '');
    return `<button type="button" class="paleta" data-paleta="${esc(p.id)}"
        title="${esc(p.nombre)} · ${esc(p.descripcion)}" aria-label="${esc(p.nombre)}: ${esc(p.descripcion)}">
        <span class="paleta-muestras">${muestras}</span>
        <span class="paleta-nombre">${esc(nombre)}</span>
    </button>`;
}

function renderPaletas(paletas) {
    const cont = $('lista-paletas');
    if (!cont) return;
    const lista = paletas || [];
    // Sin paletas la caja quedaba abierta y completamente vacía, que es lo que
    // ve alguien si el servidor no las devuelve. Se dice qué pasa en vez de no
    // enseñar nada.
    if (!lista.length) {
        cont.innerHTML = '<p class="muted">No hay paletas disponibles ahora mismo. '
            + 'Los colores de abajo se pueden ajustar uno a uno igualmente.</p>';
        return;
    }
    cont.innerHTML = GRUPOS_PALETAS.map(([familia, titulo]) => {
        const grupo = lista.filter(p => (p.familia || 'horario') === familia);
        if (!grupo.length) return '';
        return `<div class="paletas-grupo">
            <span class="paletas-titulo">${esc(titulo)}</span>
            <div class="paletas-lista">${grupo.map(fichaPaleta).join('')}</div>
        </div>`;
    }).join('');
    cont.querySelectorAll('[data-paleta]').forEach(boton => {
        boton.onclick = () => aplicarPaleta(boton.dataset.paleta, boton);
    });
}

async function aplicarPaleta(id, boton) {
    ponerBotonOcupado(boton, true, 'Aplicando…');
    try {
        const r = await api('/api/configuracion/colores-excel/paleta', {
            method: 'POST', body: JSON.stringify({paleta: id}),
        });
        aplicarColoresFormulario(r.colores || {});
        aplicarColoresHorario(r.colores || {});
        if (r.paletas) renderPaletas(r.paletas);
        else { try { await cargarConfiguracionExcel(); } catch (_) {} }
        if (typeof renderHorario === 'function' && ultimo) renderHorario(ultimo);
        toast(r.mensaje, 'success', 'Paleta aplicada');
    } catch (e) {
        toast(e.message, 'error', 'No se pudo aplicar la paleta');
    } finally {
        ponerBotonOcupado(boton, false);
    }
}

async function cargarRutasAplicacion() {
    try {
        const r = await api('/api/configuracion/rutas');
        $('rutas-aplicacion').innerHTML = [
            ['Carpeta de instalación', r.instalacion],
            ['Datos persistentes', r.datos],
            ['Base de datos · personal, solicitudes y horarios oficiales', r.base_datos],
            ['Exportaciones de respaldo', r.exportaciones_seguras],
        ].map(([titulo, ruta]) => `<div class="path-item"><strong>${esc(titulo)}</strong><code>${esc(ruta)}</code></div>`).join('');
    } catch (e) {
        $('rutas-aplicacion').textContent = 'No se pudieron consultar las rutas: ' + e.message;
    }
}

let festivosConfigurados = [];

async function cargarFestivosConfiguracion() {
    const anio = Number($('festivos-anio').value || new Date().getFullYear());
    const data = await api(`/api/configuracion/festivos/${anio}`);
    festivosConfigurados = data.festivos || [];
    const tbody = $('tabla-festivos').querySelector('tbody');
    tbody.innerHTML = festivosConfigurados.map(f => `
        <tr>
            <td>${esc(f.nombre)}</td>
            <td>${fechaBonita(f.fecha_original)}</td>
            <td><input class="holiday-date-input" type="date" id="festivo-fecha-${f.fecha_original}" value="${esc(f.fecha_efectiva)}" aria-label="Fecha en que se celebrará ${esc(f.nombre)}" title="Fecha en que se celebrará ${esc(f.nombre)}"></td>
            <td>${f.modificado ? '<span class="badge holiday-modified">Modificado</span>' : '<span class="badge holiday-default">Calculado</span>'}</td>
            <td><div class="holiday-actions">
                <button type="button" onclick="guardarFestivo('${f.fecha_original}')">Guardar fecha</button>
                ${f.modificado ? `<button type="button" class="secondary" onclick="restaurarFestivo('${f.fecha_original}')">Restaurar</button>` : ''}
            </div></td>
        </tr>`).join('') || '<tr><td colspan="5">No se encontraron festivos para ese año.</td></tr>';
    // Estas fechas se pintan después de arrancar, así que no las alcanzó el
    // recorrido inicial: eran los únicos campos de fecha de toda la aplicación
    // que se quedaban con el selector nativo del navegador, sin el calendario
    // propio y —lo que importa— sin la fecha mínima. Se podía trasladar un
    // festivo a un día anterior al primer mes que la aplicación maneja.
    // `12-reparto-areas.js` ya hacía estas dos llamadas con su contenido
    // dinámico; aquí faltaban.
    aplicarFechaMinimaDocumento(tbody);
    activarCalendarios(tbody);
}

window.guardarFestivo = async fechaOriginal => {
    const nueva = $(`festivo-fecha-${fechaOriginal}`)?.value;
    if (!nueva) return toast('Selecciona la nueva fecha efectiva.', 'warning', 'Falta la fecha');
    try {
        const data = await api('/api/configuracion/festivos', {
            method: 'PUT',
            body: JSON.stringify({fecha_original: fechaOriginal, fecha_nueva: nueva}),
        });
        await cargarFestivosConfiguracion();
        toast(`${data.festivo.nombre}: ${fechaBonita(fechaOriginal)} → ${fechaBonita(nueva)}. Regenera los meses afectados.`, 'success', 'Festivo actualizado');
    } catch (e) {
        toast(e.message, 'error', 'No se pudo cambiar el festivo');
    }
};

window.restaurarFestivo = async fechaOriginal => {
    const ok = await confirmarUI({
        titulo: 'Restaurar fecha del festivo',
        mensaje: `¿Volver el festivo del ${fechaBonita(fechaOriginal)} a su fecha calculada?`,
        detalle: 'Los horarios oficiales existentes no cambian automáticamente. Regenera desde el mes afectado si deseas aplicar la restauración.',
        aceptar: 'Restaurar fecha',
        peligro: false,
    });
    if (!ok) return;
    try {
        await api(`/api/configuracion/festivos/${fechaOriginal}`, {method: 'DELETE'});
        await cargarFestivosConfiguracion();
        toast('El festivo volvió a su fecha calculada.', 'success', 'Festivo restaurado');
    } catch (e) {
        toast(e.message, 'error', 'No se pudo restaurar');
    }
};

$('cargar-festivos').onclick = () => cargarFestivosConfiguracion().catch(e => toast(e.message, 'error', 'No se pudieron cargar festivos'));
$('festivos-anio').onchange = () => cargarFestivosConfiguracion().catch(e => toast(e.message, 'error', 'No se pudieron cargar festivos'));

Object.entries(COLOR_INPUTS).forEach(([key, id]) => {
    $(id).oninput = () => {
        const code = document.querySelector(`[data-color-code="${key}"]`);
        if (code) code.textContent = $(id).value.toUpperCase();
        aplicarColoresHorario(leerColoresFormulario());
    };
});

$('guardar-colores').onclick = async () => {
    try {
        const data = await api('/api/configuracion/colores-excel', {
            method: 'PUT',
            body: JSON.stringify(leerColoresFormulario()),
        });
        aplicarColoresFormulario(data.colores);
        toast('La paleta se aplicó al horario en pantalla y a los próximos Excel.', 'success', 'Colores guardados');
    } catch (e) {
        toast(e.message, 'error', 'No se pudieron guardar los colores');
    }
};

$('restablecer-colores').onclick = async () => {
    const ok = await confirmarUI({
        titulo: 'Restaurar colores originales',
        mensaje: '¿Quieres restaurar todos los colores originales del horario y del Excel?',
        detalle: 'Cambia la apariencia del horario en pantalla y de futuras exportaciones. No modifica turnos, personal ni solicitudes.',
        aceptar: 'Restaurar todos',
        peligro: false,
    });
    if (!ok) return;
    try {
        const data = await api('/api/configuracion/colores-excel', {method: 'DELETE'});
        aplicarColoresFormulario(data.colores);
        toast(data.mensaje, 'success', 'Colores restaurados');
    } catch (e) {
        toast(e.message, 'error', 'No se pudieron restablecer los colores');
    }
};





// ================================================================
// V11.8 · color predeterminado de la aplicación
// ================================================================
let temasAppDisponibles = [];

// --- Modo claro y modo oscuro --------------------------------------------
//
// Tres opciones: claro, oscuro y el del sistema, que es la de partida. Lo que
// se guarda es la elección, no el resultado: quien deja «el del sistema» y
// cambia Windows a oscuro por la tarde ve la aplicación cambiar con él.
//
// Los tonos de la marca no pueden vivir en la hoja de estilos, porque la
// aplicación los escribe como estilo en línea al elegir un color, y el estilo
// en línea gana siempre. Así que se calculan aquí, para el modo que esté
// puesto: el mismo morado da un lila claro cuando hace de texto sobre fondo
// oscuro y un morado hondo cuando hace de panel.
const MODOS_APP = ['claro', 'oscuro', 'sistema'];
let modoElegido = 'sistema';
let temaAplicado = null;

function consultaOscuro() {
    return window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
}

function modoEfectivo() {
    if (modoElegido === 'claro' || modoElegido === 'oscuro') return modoElegido;
    return consultaOscuro()?.matches ? 'oscuro' : 'claro';
}

function aplicarModoApp(modo) {
    modoElegido = MODOS_APP.includes(modo) ? modo : 'sistema';
    document.documentElement.dataset.modo = modoEfectivo();
    document.documentElement.dataset.modoElegido = modoElegido;
    if (temaAplicado) aplicarTemaApp(temaAplicado);
    document.querySelectorAll('[data-modo-opcion]').forEach(b => {
        b.classList.toggle('active', b.dataset.modoOpcion === modoElegido);
        b.setAttribute('aria-pressed', String(b.dataset.modoOpcion === modoElegido));
    });
}

consultaOscuro()?.addEventListener('change', () => {
    if (modoElegido === 'sistema') aplicarModoApp('sistema');
});

function _rgb(hex) {
    const v = String(hex || '').replace('#', '');
    return [0, 2, 4].map(i => parseInt(v.slice(i, i + 2), 16) || 0);
}

// proporcion=0 devuelve el primero; 1, el segundo.
function mezclarColor(hex, hacia, proporcion) {
    const a = _rgb(hex), b = _rgb(hacia);
    return '#' + a.map((x, i) => Math.round(x + (b[i] - x) * proporcion)
        .toString(16).padStart(2, '0')).join('');
}

const NEGRO_APP = '#141119';
const BLANCO = '#ffffff';

// Cuánta luz tiene un color, con la fórmula que decide de verdad si un texto se
// lee sobre un fondo. No es una apreciación: es la misma cuenta que usan las
// pautas de accesibilidad.
function _luz(hex) {
    return _rgb(hex).map(v => {
        const x = v / 255;
        return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
    }).reduce((a, v, i) => a + v * [0.2126, 0.7152, 0.0722][i], 0);
}

function _contraste(a, b) {
    const la = _luz(a), lb = _luz(b);
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

// Aclara —o apaga— un color hasta que se lea sobre el fondo indicado.
//
// Hace falta porque no todos los temas parten del mismo sitio. Un morado medio
// aclarado un 18 % ya se lee sobre una tarjeta oscura; el azul marino de
// CABLEMOVIL, no: sigue siendo casi tan oscuro como el fondo, y los títulos de
// los formularios quedaban en 2,1 de contraste, prácticamente invisibles.
// En vez de elegir un porcentaje a ojo por tema, se sube hasta que la cuenta
// dice que se lee.
function tonoLegible(color, fondo, objetivo = 4.6) {
    const hacia = _luz(fondo) > 0.4 ? NEGRO_APP : BLANCO;
    let salida = color;
    for (let paso = 0; paso <= 20 && _contraste(salida, fondo) < objetivo; paso++) {
        salida = mezclarColor(color, hacia, paso * 0.05);
    }
    return salida;
}

function tonoDeRelleno(color, superficie, conLetra = 4.5, conFondo = 3.0) {
    /* El color con el que se rellena un botón o una pestaña activa.
       Tiene que cumplir dos cosas a la vez, y por eso se busca en vez de
       calcularse de una fórmula:

       · que la **letra blanca de encima se lea** —si no, el botón dice algo que
         nadie distingue—;
       · que el botón **se vea recortado contra la tarjeta** que hay detrás —si
         no, se lee la etiqueta pero no se ve que sea un botón—.

       En claro las dos se cumplen con el color de marca tal cual. En oscuro no:
       el morado puro contrasta 9,9 con el blanco pero solo 1,76 con la
       superficie oscura, y aclarado hasta despegarse de ella baja a 3,5 con el
       blanco. La ventana que cumple las dos existe, es estrecha y cae en un
       sitio distinto según el color elegido, así que se busca. */
    let mejor = null;
    for (let paso = 0; paso <= 20; paso++) {
        const tono = mezclarColor(color, BLANCO, paso * 0.05);
        const letra = _contraste(tono, BLANCO);
        const fondo = _contraste(tono, superficie);
        if (letra >= conLetra && fondo >= conFondo) return tono;
        if (fondo >= conFondo && (!mejor || letra > mejor.letra)) mejor = {tono, letra};
    }
    // Si no hay ningún tono que cumpla las dos cosas, manda la letra: un botón
    // algo parecido a su tarjeta se sigue usando; una etiqueta que no se lee, no.
    return mejor ? mejor.tono : tonoLegible(color, BLANCO, conLetra);
}


function tonosDeMarca(tema, modo) {
    const solido = '#' + String(tema.primary).replace('#', '');
    const hondo = '#' + String(tema.dark).replace('#', '');
    // El gris de los botones secundarios no es un gris cualquiera: lleva el
    // matiz del color elegido. Antes estaba fijo en un gris amoratado, así que
    // con el tema azul o el rosado desentonaba en cada pantalla.
    // El gris de los botones secundarios lleva el matiz del color elegido, pero
    // con naranja o rosado salía tan claro que el texto blanco encima se quedaba
    // en 4,4 de contraste. Se apaga hasta que la letra se lee.
    const secundarioCrudo = mezclarColor(mezclarColor(solido, '#7c7580', 0.72),
                                         modo === 'oscuro' ? NEGRO_APP : BLANCO,
                                         modo === 'oscuro' ? 0.08 : 0.02);
    const secundario = modo === 'oscuro'
        ? secundarioCrudo
        : tonoLegible(secundarioCrudo, BLANCO, 4.8);
    if (modo !== 'oscuro') {
        return {
            // En claro el color de marca sirve para las dos cosas: contrasta
            // 9,9 con el blanco de encima y de sobra con las tarjetas claras.
            '--purple-tinta': solido,
            '--bg': '#f5f3f8',
            '--surface': '#ffffff',
            '--surface-2': '#f7f5f8',
            '--surface-3': '#f1eef4',
            '--border': '#ded8e5',
            '--secundario': secundario,
            '--brand': solido, '--brand-deep': hondo,
            '--login-start': hondo, '--login-end': solido,
            '--purple': solido, '--purple-dark': hondo,
            '--purple-mid': '#' + String(tema.mid).replace('#', ''),
            '--purple-light': '#' + String(tema.light).replace('#', ''),
            '--purple-pale': '#' + String(tema.pale).replace('#', ''),
            '--theme-focus': '#' + String(tema.focus).replace('#', ''),
            '--theme-border': '#' + String(tema.border).replace('#', ''),
            '--theme-soft-border': '#' + String(tema.soft_border).replace('#', ''),
            '--theme-card-border': '#' + String(tema.soft_border).replace('#', ''),
        };
    }
    // En oscuro se invierte el papel de cada tono: los que eran fondos claros
    // pasan a ser fondos hondos, y los que eran tinta oscura, tinta clara.
    const superficie = mezclarColor(solido, NEGRO_APP, 0.86);
    return {
        // Las superficies también llevan el matiz elegido. Así el tema azul
        // no cae sobre tarjetas negras-moradas ni el rosado sobre grises sin
        // relación: siguen siendo oscuras, pero pertenecen a la misma paleta.
        '--bg': mezclarColor(solido, '#0d0b10', 0.91),
        '--surface': superficie,
        '--surface-2': mezclarColor(solido, NEGRO_APP, 0.78),
        '--surface-3': mezclarColor(solido, NEGRO_APP, 0.69),
        '--border': mezclarColor(solido, NEGRO_APP, 0.58),
        '--secundario': secundario,
        '--brand': solido,
        '--brand-deep': hondo,
        '--login-start': mezclarColor(hondo, NEGRO_APP, 0.28),
        '--login-end': mezclarColor(solido, NEGRO_APP, 0.58),
        // Estos tres hacen de tinta sobre las tarjetas oscuras, así que se
        // aclaran hasta que se leen de verdad, sea cual sea el color de partida.
        // Aquí los dos tonos se separan, y es la razón de que exista
        // `--purple-tinta`. Un solo color no puede hacer de relleno con letra
        // blanca encima y de tinta sobre una tarjeta oscura: lo que sirve para
        // uno es justo lo que estorba al otro. Con un solo tono, «Guardar» y la
        // pestaña activa se quedaban en 3,5 de contraste.
        '--purple': tonoDeRelleno(solido, superficie),
        '--purple-tinta': tonoLegible(mezclarColor(solido, BLANCO, 0.18), superficie),
        '--purple-dark': tonoLegible(mezclarColor(solido, BLANCO, 0.58), superficie),
        '--purple-mid': tonoLegible(mezclarColor(solido, BLANCO, 0.38), superficie, 4.0),
        '--purple-light': mezclarColor(solido, NEGRO_APP, 0.58),
        '--purple-pale': mezclarColor(solido, NEGRO_APP, 0.84),
        '--theme-focus': mezclarColor(solido, BLANCO, 0.42),
        '--theme-border': mezclarColor(solido, NEGRO_APP, 0.66),
        '--theme-soft-border': mezclarColor(solido, NEGRO_APP, 0.74),
        '--theme-card-border': mezclarColor(solido, NEGRO_APP, 0.78),
    };
}

function aplicarTemaApp(tema) {
    if (!tema) return;
    temaAplicado = tema;
    const root = document.documentElement;
    const vars = tonosDeMarca(tema, modoEfectivo());
    Object.entries(vars).forEach(([key, value]) => {
        if (value) root.style.setProperty(key, '#' + String(value).replace('#',''));
    });
    document.body.dataset.appTheme = tema.id || 'morado';
    const esCable = tema.id === 'cablemovil';
    const filtrosIcono = {
        morado:'none', azul:'hue-rotate(315deg) saturate(.95)', rojo:'hue-rotate(105deg) saturate(1.15)',
        verde:'hue-rotate(205deg) saturate(.85)', turquesa:'hue-rotate(245deg) saturate(.9)',
        naranja:'hue-rotate(135deg) saturate(1.05)', rosado:'hue-rotate(65deg) saturate(.8)'
    };
    root.style.setProperty('--app-icon-filter', esCable ? 'none' : (filtrosIcono[tema.id] || 'none'));
    const aplicarMarca = (img, contexto) => {
        if (!img) return;
        let recurso = '/GestorHorarios.png';
        if (esCable) {
            const asset = contexto === 'login' ? (tema.login_asset || 'CABLEMOVIL_logo.png') : (tema.brand_asset || 'CABLEMOVIL_header.png');
            recurso = '/' + String(asset).replace(/^\/+/, '');
        }
        img.src = recurso;
        img.alt = esCable ? 'CABLEMOVIL' : 'Gestor de Horarios';
        img.dataset.brandType = esCable ? `cablemovil-${contexto}` : 'gestor';
    };
    aplicarMarca($('brand-logo'), 'header');
    aplicarMarca($('login-logo'), 'login');
    renderTemaPreview(tema);
}

function renderTemaPreview(tema) {
    const cont = $('tema-preview');
    if (!cont || !tema) return;
    cont.innerHTML = [tema.primary, tema.mid, tema.light].map(c =>
        `<span class="theme-preview-swatch" style="background:#${esc(String(c).replace('#',''))}"></span>`
    ).join('') + `<span class="theme-preview-name">${esc(tema.nombre || tema.id || 'Tema')}</span>`;
}


// ---------------------------------------------------------------------------
// Versión y actualizaciones
// ---------------------------------------------------------------------------
// El servidor sabía comprobar, descargar e instalar una versión nueva desde el
// primer día, con sus rutas y sus pruebas. Lo que no existía era el sitio desde
// donde pedirlo: ni un botón en ninguna pantalla. Desde fuera eso se ve como
// que la aplicación no se actualiza, y con razón, porque no había forma de
// decírselo. Esta tarjeta es la mitad que faltaba.
//
// Los tres pasos no se encadenan solos a propósito: que el programa se
// reemplace a sí mismo mientras alguien está armando el horario de un mes sería
// la peor sorpresa posible.

let novedadDescargada = null;

function pintarNovedad(datos) {
    const caja = $('version-novedad');
    const bDescargar = $('descargar-actualizacion');
    const bInstalar = $('instalar-actualizacion');
    if (!caja) return;

    $('version-instalada').textContent = datos.version_instalada || '—';
    bInstalar.classList.toggle('hidden', !novedadDescargada);
    // Los avisos de la consulta anterior se quitan antes de pintar los de esta.
    // Sin esto se van amontonando uno debajo de otro cada vez que alguien pulsa
    // «Comprobar», y a la cuarta vez la pantalla enseña el mismo aviso cuatro
    // veces, que se lee como cuatro problemas distintos.
    document.querySelectorAll('.aviso-actualizacion').forEach(x => x.remove());

    if (datos.hay_novedad) {
        caja.className = 'form-alert';
        caja.innerHTML = `<strong>Hay una versión nueva: ${esc(datos.version_publicada)}.</strong>`
            + (datos.notas ? `<br>${esc(String(datos.notas).slice(0, 400))}` : '');
        bDescargar.classList.remove('hidden');
    } else {
        caja.className = 'form-alert';
        caja.textContent = datos.motivo || 'Tienes la última versión publicada.';
        bDescargar.classList.add('hidden');
    }
    // Los avisos se quedan **escritos en la caja**, además del mensaje que pasa.
    // El aviso de que el permiso va a caducar aparece justo cuando todo va bien
    // —«tienes la última versión»—, que es cuando nadie está mirando la pantalla:
    // un mensaje que se va solo a los cinco segundos no lo lee nadie, y el día
    // que caduque las actualizaciones dejan de llegar sin que salte nada.
    (datos.avisos || []).forEach(a => {
        const linea = document.createElement('div');
        linea.className = 'form-alert aviso-actualizacion';
        linea.style.marginTop = '8px';
        linea.textContent = a;
        caja.after(linea);
        toast(a, 'warning', 'Actualizaciones');
    });
}

async function comprobarActualizacion(forzar) {
    const boton = $('comprobar-actualizacion');
    if (!boton) return;
    boton.disabled = true;
    try {
        const datos = await api(`/api/actualizaciones?forzar=${forzar ? 'true' : 'false'}`);
        $('version-estado').textContent = new Date().toLocaleString();
        pintarNovedad(datos);
    } catch (e) {
        // Sin internet la aplicación funciona igual: comprobar es una comodidad,
        // no un requisito, y por eso esto avisa en vez de alarmar.
        $('version-estado').textContent = 'No se pudo comprobar.';
        const caja = $('version-novedad');
        if (caja) {
            caja.className = 'form-alert';
            caja.textContent = `No se pudo comprobar si hay versión nueva: ${e.message}`;
        }
    } finally {
        boton.disabled = false;
    }
}

if ($('comprobar-actualizacion')) {
    $('comprobar-actualizacion').onclick = () => comprobarActualizacion(true);

    $('descargar-actualizacion').onclick = async () => {
        const claveAdmin = await pedirClaveAdmin('Descargar la versión nueva');
        if (!claveAdmin) return;
        const boton = $('descargar-actualizacion');
        boton.disabled = true;
        try {
            setEstado('Descargando la versión nueva…', 'working');
            const datos = await api('/api/actualizaciones/descargar', {
                method: 'POST', headers: {'X-Admin-Password': claveAdmin},
            });
            novedadDescargada = datos.ruta;
            $('instalar-actualizacion').classList.remove('hidden');
            setEstado('Versión descargada', 'success', 2000);
            toast(datos.mensaje, 'success', `Versión ${datos.version} descargada`);
        } catch (e) {
            setEstado('No se pudo descargar', 'error', 2200);
            toast(e.message, 'error', 'No se pudo descargar');
        } finally {
            boton.disabled = false;
        }
    };

    $('instalar-actualizacion').onclick = async () => {
        if (!novedadDescargada) return;
        const ok = await confirmarUI({
            titulo: 'Instalar la versión nueva',
            mensaje: '¿Instalar ahora la versión descargada?',
            detalle: 'La aplicación se cerrará para que el instalador pueda reemplazar el '
                   + 'programa, y después podrás volver a abrirla. Tus datos no se tocan: '
                   + 'están en una carpeta aparte y el instalador guarda además una copia '
                   + 'de la base antes de empezar. Guarda lo que tengas a medias.',
            aceptar: 'Instalar y cerrar',
            peligro: true,
        });
        if (!ok) return;
        const claveAdmin = await pedirClaveAdmin('Instalar la versión nueva');
        if (!claveAdmin) return;
        try {
            const datos = await api(
                `/api/actualizaciones/instalar?ruta=${encodeURIComponent(novedadDescargada)}`,
                {method: 'POST', headers: {'X-Admin-Password': claveAdmin}});
            toast(datos.mensaje, datos.ok ? 'success' : 'warning', 'Instalando');
            setEstado(datos.mensaje, datos.ok ? 'success' : 'warning');
        } catch (e) {
            toast(e.message, 'error', 'No se pudo instalar');
        }
    };
}
