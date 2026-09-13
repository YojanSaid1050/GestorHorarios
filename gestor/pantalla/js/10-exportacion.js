// Sacar el Excel
// ---------------------------------------------------------------------------
// Parte de la pantalla del Gestor de Horarios. Los archivos de esta carpeta se
// cargan en orden y comparten el mismo ámbito, así que juntos son exactamente
// el app.js de antes. Ver frontend/js/LEEME.md.

'use strict';

function recuperarUltimaExportacion() {
    try {
        const ruta = localStorage.getItem(CLAVE_ULTIMA_EXPORTACION);
        if (!ruta) return null;
        ultimaRutaExportada = ruta;
        $('abrir-archivo-exportado')?.classList.remove('hidden');
        return ruta;
    } catch (_) {
        return null;
    }
}

function recordarUltimaExportacion(ruta) {
    if (!ruta) return;
    ultimaRutaExportada = ruta;
    try { localStorage.setItem(CLAVE_ULTIMA_EXPORTACION, ruta); } catch (_) {}
    $('abrir-archivo-exportado')?.classList.remove('hidden');
}

function horarioOficialParaExportar() {
    return horarioActualReferencia
        || alternativasActuales.find(x => x?.oficial)
        || (ultimo?.oficial ? ultimo : null);
}

function actualizarDisponibilidadExportacion() {
    // El botón se quedaba apagado sin decir nada: sin tooltip, sin texto y sin
    // reacción al pulsarlo. El mensaje que sí lo explicaba vivía dentro del
    // modal, al que no se podía llegar justamente porque el botón estaba
    // deshabilitado. Ahora el motivo se escribe en el propio botón.
    const boton = $('exportar');
    if (!boton) return;
    const oficial = horarioOficialParaExportar();
    const listo = !!oficial?.valido && !!oficial?.horario?.length;
    boton.disabled = !listo;
    if (listo) {
        boton.title = 'Exporta a Excel el horario oficial de este mes.';
        return;
    }
    const hayOpciones = (alternativasActuales || []).length > 0;
    boton.title = hayOpciones
        ? 'Todavía no hay horario oficial. En Horario, marca una de las opciones como oficial y podrás exportarla.'
        : 'Este mes todavía no tiene horario. Genéralo en Horario, marca una opción como oficial y podrás exportarla.';
}

async function actualizarRutaExportacion() {
    try {
        const modo = await api('/api/exportacion/modo');
        exportacionDialogoNativo = !!modo.dialogo_nativo;
        if (modo.dialogo_nativo) {
            $('ruta-exportacion').textContent =
                'Al continuar se abrirá la ventana nativa “Guardar como” de Windows para elegir carpeta y nombre.';
            $('descripcion-exportar').textContent = 'Escribe el nombre del archivo. Al continuar se abrirá la ventana de Windows “Guardar como” para elegir la carpeta.';
            $('confirmar-exportacion').textContent = 'Elegir ubicación y guardar';
        } else {
            const info = await api('/api/exportacion/carpeta');
            $('ruta-exportacion').textContent =
                `Modo navegador: se guardará en ${info.ruta}`;
            $('descripcion-exportar').textContent = 'Escribe el nombre del archivo. En modo navegador se guardará directamente en la carpeta indicada abajo.';
            $('confirmar-exportacion').textContent = 'Guardar en la carpeta indicada';
        }
        return exportacionDialogoNativo;
    } catch (e) {
        exportacionDialogoNativo = null;
        $('ruta-exportacion').textContent =
            'La aplicación intentará abrir “Guardar como”. Si no está disponible, usará la carpeta de exportaciones.';
        $('descripcion-exportar').textContent = 'Escribe el nombre del archivo. La aplicación elegirá el método de guardado disponible en este equipo.';
        $('confirmar-exportacion').textContent = 'Continuar con la exportación';
        return null;
    }
}

function abrirModalExportacion() {
    try {
        const oficial = horarioOficialParaExportar();
        // El aviso informativo salía antes de comprobar si hay oficial, así que
        // en el caso de error se veían dos mensajes encadenados diciendo cosas
        // distintas. Primero se mira si se puede, y solo después se informa.
        if (!oficial?.horario?.length) {
            toast(
                'Primero marca una de las cinco opciones como horario oficial.',
                'warning',
                'Falta el horario oficial'
            );
            return;
        }
        if (!oficial?.valido) {
            toast(
                'Corrige los errores de la pestaña Validación y vuelve a generar. Un horario inválido no puede exportarse.',
                'warning',
                'Exportación bloqueada'
            );
            return;
        }

        toast(
            'Se exportará el horario oficial. Elige cuál de los tres libros quieres.',
            'info',
            'Exportar Excel'
        );

        const {anio, mes} = periodo();
        $('nombre-exportacion').value =
            `Programacion_${anio}_${String(mes).padStart(2, '0')}.xlsx`;
        if ($('exportar-libro')) $('exportar-libro').value = 'trabajo';
        configurarLibroExportacion();
        $('modal-exportar').classList.remove('hidden');
        actualizarRutaExportacion();

        setTimeout(() => {
            $('nombre-exportacion').focus();
            $('nombre-exportacion').select();
        }, 0);
    } catch (e) {
        toast(e?.message || String(e), 'error', 'No se pudo abrir Exportar');
    }
}

// Tres libros, no cinco archivos sueltos.
//
// El de trabajo es el que se edita: lleva el horario por semanas completas y,
// al lado, la misma tabla recortada al mes, que toma sus turnos de la primera.
// Se cambia un turno en «Semanas completas» y la hoja del mes lo recoge sola,
// con su color y sus horas. Los otros dos se reparten y se consultan: una
// semana suelta y el libro completo con comentarios y hojas de apoyo. En esos
// dos las horas siguen calculándose; el resto de controles no aparece, porque
// son de quien programa, no de quien lee.
const AYUDA_LIBRO = {
    trabajo: 'Dos hojas: se cambia un turno en «Semanas completas» y la hoja «Solo el mes» lo recoge sola, con su color y sus horas.',
    completo: 'El horario del período con los comentarios de cada día, más las hojas de Parámetros, Resumen mensual e Instructivo. Para consultar, no para editar.',
    semana: 'Una sola semana, de lunes a domingo, con las horas calculadas. Es el que se imprime y se reparte.',
};

function configurarLibroExportacion() {
    const libro = $('exportar-libro')?.value || 'trabajo';
    const ayuda = $('ayuda-exportar-libro');
    if (ayuda) ayuda.textContent = AYUDA_LIBRO[libro] || '';

    const grupo = $('g-exportar-semana');
    const select = $('exportar-semana');
    if (!grupo || !select) return;
    grupo.classList.toggle('hidden', libro !== 'semana');
    if (libro !== 'semana') return;

    const dias = horarioOficialParaExportar()?.horario?.[0]?.dias || [];
    const semanas = [...new Set(dias.map(d => d.lunes_semana).filter(Boolean))].sort();
    const anterior = select.value;
    select.innerHTML = semanas.map(lunes => {
        const visibles = dias.filter(d => d.lunes_semana === lunes);
        return `<option value="${esc(lunes)}">${fechaBonita(visibles[0]?.fecha || lunes)} a ${fechaBonita(visibles.at(-1)?.fecha || lunes)}</option>`;
    }).join('');
    if ([...select.options].some(o => o.value === anterior)) select.value = anterior;
}
$('exportar-libro')?.addEventListener('change', configurarLibroExportacion);

function completarExportacionEnCarpeta(data) {
    recordarUltimaExportacion(data.ruta);
    $('abrir-exportaciones').classList.remove('hidden');
    if (ultimaRutaExportada) $('abrir-archivo-exportado')?.classList.remove('hidden');
    cerrarModalExportacion();
    toast(
        `${data.nombre} se guardó correctamente en ${data.carpeta}.`,
        'success',
        'Excel exportado'
    );
}

function cerrarModalExportacion() {
    $('modal-exportar').classList.add('hidden');
}

async function esperarResultadoExportacion(requestId) {
    let avisoDialogoMostrado = false;

    // Hasta 10 minutos. Mientras el usuario tenga “Guardar como” abierto,
    // el estado seguirá en dialogo sin bloquear la interfaz.
    for (let i = 0; i < 2400; i += 1) {
        const estado = await api(`/api/exportacion/estado/${requestId}`);

        if (estado.estado === 'dialogo' && !avisoDialogoMostrado) {
            avisoDialogoMostrado = true;
            toast(
                'Se abrió la ventana de Windows. Elige la carpeta, ajusta el nombre si quieres y pulsa Guardar.',
                'info',
                'Guardar como'
            );
        }

        if (estado.estado === 'completado') {
            return estado;
        }

        if (estado.estado === 'cancelado') {
            return estado;
        }

        if (estado.estado === 'error') {
            throw new Error(estado.mensaje || 'No se pudo exportar el Excel.');
        }

        await esperar(250);
    }

    throw new Error('La exportación tardó demasiado tiempo. Intenta nuevamente.');
}

$('exportar').onclick = abrirModalExportacion;
$('cerrar-modal-exportar').onclick = cerrarModalExportacion;
$('cancelar-exportacion').onclick = cerrarModalExportacion;
$('modal-exportar').onclick = ev => {
    if (ev.target === $('modal-exportar')) cerrarModalExportacion();
};

$('confirmar-exportacion').onclick = async () => {
    const boton = $('confirmar-exportacion');
    const anterior = boton.textContent;

    try {
        const oficial = horarioOficialParaExportar();
        if (!oficial?.horario?.length) {
            throw new Error('Marca primero una alternativa como horario oficial.');
        }
        if (!oficial?.valido) {
            throw new Error('El horario tiene validaciones pendientes. Corrígelas antes de exportar.');
        }

        const {anio, mes} = periodo();
        const nombre = $('nombre-exportacion').value.trim();
        const libro = $('exportar-libro')?.value || 'trabajo';
        const semana_inicio = libro === 'semana' ? ($('exportar-semana')?.value || null) : null;
        if (libro === 'semana' && !semana_inicio) {
            throw new Error('Elige qué semana quieres exportar.');
        }

        boton.disabled = true;
        const dialogoNativo = await actualizarRutaExportacion();
        boton.textContent = dialogoNativo === false ? 'Guardando…' : 'Preparando…';
        $('ruta-exportacion').textContent = dialogoNativo === false
            ? 'Generando el Excel y guardándolo en la carpeta de exportaciones…'
            : 'Generando el Excel y preparando “Guardar como”…';

        toast(
            dialogoNativo === false
                ? 'Generando el archivo en la carpeta segura de exportaciones.'
                : 'Generando el archivo. En unos segundos se abrirá “Guardar como”.',
            'info',
            'Preparando Excel'
        );

        if (dialogoNativo === false) {
            const data = await api(`/api/exportacion/exportar/${anio}/${mes}`, {
                method: 'POST',
                body: JSON.stringify({nombre: nombre || null, horario_id: oficial.horario_id, libro, semana_inicio}),
            });
            completarExportacionEnCarpeta(data);
            return;
        }

        let solicitud;
        try {
            solicitud = await api(`/api/exportacion/dialogo/${anio}/${mes}`, {
                method: 'POST',
                body: JSON.stringify({nombre: nombre || null, horario_id: oficial.horario_id, libro, semana_inicio}),
            });
        } catch (dialogError) {
            // Fallback útil al ejecutar el frontend en un navegador durante desarrollo.
            if (!String(dialogError?.message || '').includes('diálogo nativo')) {
                throw dialogError;
            }

            const data = await api(`/api/exportacion/exportar/${anio}/${mes}`, {
                method: 'POST',
                body: JSON.stringify({nombre: nombre || null, horario_id: oficial.horario_id, libro, semana_inicio}),
            });
            completarExportacionEnCarpeta(data);
            return;
        }

        boton.textContent = 'Esperando ubicación…';
        const resultado = await esperarResultadoExportacion(solicitud.request_id);

        if (resultado.estado === 'cancelado') {
            cerrarModalExportacion();
            toast('No se guardó ningún archivo.', 'info', 'Exportación cancelada');
            return;
        }

        recordarUltimaExportacion(resultado.ruta);
        cerrarModalExportacion();
        // Tras guardar, lo que casi siempre se quiere es abrirlo, no ir a
        // buscarlo a la carpeta.
        if (ultimaRutaExportada) $('abrir-archivo-exportado')?.classList.remove('hidden');

        if (resultado.fallback) {
            $('abrir-exportaciones').classList.remove('hidden');
            toast(
                `La ventana “Guardar como” no pudo completarse en este equipo, pero el Excel sí se creó y quedó guardado en ${resultado.carpeta}.`,
                'warning',
                'Excel guardado automáticamente'
            );
        } else {
            toast(
                `${resultado.nombre} se guardó correctamente en ${resultado.carpeta}.`,
                'success',
                'Excel exportado'
            );
        }
    } catch (e) {
        toast(e?.message || String(e), 'error', 'No se pudo exportar');
    } finally {
        boton.disabled = false;
        boton.textContent = anterior;
    }
};

$('abrir-archivo-exportado').onclick = async () => {
    if (!ultimaRutaExportada) {
        toast('Todavía no has exportado ningún archivo en esta sesión.', 'info', 'Sin archivo reciente');
        return;
    }
    try {
        const data = await api('/api/exportacion/abrir-archivo', {
            method: 'POST', body: JSON.stringify({ruta: ultimaRutaExportada}),
        });
        if (!data.ok) toast(data.mensaje || `Archivo: ${data.ruta}`, 'warning', 'No se pudo abrir');
    } catch (e) {
        toast(e?.message || String(e), 'error', 'No se pudo abrir el archivo');
    }
};

$('abrir-exportaciones').onclick = async () => {
    try {
        const data = await api('/api/exportacion/abrir-carpeta', {method: 'POST'});
        if (!data.ok) {
            toast(data.mensaje || `Carpeta: ${data.ruta}`, 'info', 'Carpeta de exportaciones');
        }
    } catch (e) {
        toast(e?.message || String(e), 'error', 'No se pudo abrir la carpeta');
    }
};

const COLOR_INPUTS = {
    header: 'color-header',
    saturday_header: 'color-saturday',
    sunday_header: 'color-sunday',
    holiday_header: 'color-holiday',
    admin_friday_header: 'color-admin-friday',
    admin_friday_cell: 'color-admin-friday-cell',
    AM: 'color-am',
    PM: 'color-pm',
    D: 'color-d',
    'ADM-GS': 'color-adm-gs',
    'ADM-AC': 'color-adm-ac',
    VAC: 'color-vac',
    INC: 'color-inc',
    PER: 'color-per',
    CAP: 'color-cap',
    otro_mes_header: 'color-otro-mes',
    otro_mes_cell: 'color-otro-mes-cell',
};
