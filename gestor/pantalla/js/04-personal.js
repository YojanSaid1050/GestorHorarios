// La plantilla: altas, retiros, parejas y cambios de turno
// ---------------------------------------------------------------------------
// Parte de la pantalla del Gestor de Horarios. Los archivos de esta carpeta se
// cargan en orden y comparten el mismo ámbito, así que juntos son exactamente
// el app.js de antes. Ver frontend/js/LEEME.md.

'use strict';

async function cargarEmpleados() {
    empleadosListado = await api('/api/empleados?incluir_inactivos=true');
    empleados = empleadosListado.filter(e => e.activo);
    $('solicitud-empleado').innerHTML = opts(empleados, 'Seleccionar empleado');
    if ($('requerimiento-empleado')) $('requerimiento-empleado').innerHTML = opts(empleados, 'Seleccionar empleado');
    if ($('modificar-persona')) $('modificar-persona').innerHTML = opts(empleados, 'Seleccionar empleado');
    if ($('manual-persona')) $('manual-persona').innerHTML = opts(empleados, 'Seleccionar empleado');
    if ($('cambio-turno-empleado')) $('cambio-turno-empleado').innerHTML = opts(empleados, 'Seleccionar empleado');
    renderEmpleados();
    camposEmpleado();
    camposSolicitud();
    configurarHorarioRequerimiento();
    camposCambioTurno();
}

// --- Cambio de tipo de turno con fecha de vigencia -------------------------
// Antes solo se podía decir «esta persona es rotativa», y eso valía para todo
// el periodo: al ponerle el lunes de referencia el 21 de septiembre también
// rotaba hacia atrás. Aquí el cambio tiene fecha, y los días anteriores
// conservan la configuración con la que ya se programaron.

function camposCambioTurno() {
    const tipo = $('cambio-turno-tipo')?.value;
    if (!tipo) return;
    $('g-cambio-turno-inicio')?.classList.toggle('hidden', tipo !== 'rotativo');
    $('g-cambio-turno-fijo')?.classList.toggle('hidden', tipo !== 'fijo');
    const persona = empleados.find(x => Number(x.id) === Number($('cambio-turno-empleado')?.value));
    const conPareja = !!persona?.pareja_id && tipo !== 'administrativo';
    $('g-cambio-turno-pareja')?.classList.toggle('hidden', !conPareja);
    const ayuda = $('cambio-turno-fecha-ayuda');
    const fecha = $('cambio-turno-fecha')?.value;
    if (ayuda && fecha) {
        const d = new Date(`${fecha}T00:00:00`);
        ayuda.textContent = d.getDay() === 1
            ? 'Es lunes: el cambio empieza exactamente ese día.'
            : 'El reparto AM/PM se decide una vez por semana, así que este cambio empezará el lunes siguiente a la fecha elegida.';
    }
}

async function guardarCambioTurno(evento) {
    evento.preventDefault();
    const alerta = $('cambio-turno-alerta');
    const mostrar = (texto) => {
        if (!alerta) return;
        alerta.textContent = texto;
        alerta.classList.toggle('hidden', !texto);
    };
    mostrar('');
    const id = Number($('cambio-turno-empleado')?.value);
    const fecha = $('cambio-turno-fecha')?.value;
    if (!id) return mostrar('Elige a la persona que cambia de turno.');
    if (!fecha) return mostrar('Indica desde qué día rige el cambio.');
    const tipo = $('cambio-turno-tipo').value;
    const cuerpo = {
        vigente_desde: fecha,
        tipo_turno: tipo,
        turno_fijo: tipo === 'fijo' ? $('cambio-turno-fijo').value : null,
        inicio_rotacion: tipo === 'rotativo' ? $('cambio-turno-inicio').value : null,
        aplicar_a_pareja: $('cambio-turno-pareja')?.value !== 'no',
        motivo: $('cambio-turno-motivo')?.value?.trim() || null,
    };
    try {
        const fechaOriginal = $('cambio-turno-fecha-original')?.value || '';
        const editando = !!fechaOriginal;
        const ruta = editando
            ? `/api/empleados/${id}/cambio-turno/${fechaOriginal}`
            : `/api/empleados/${id}/cambio-turno`;
        const r = await api(ruta, {method: editando ? 'PUT' : 'POST', body: JSON.stringify(cuerpo)});
        toast(r.mensaje, 'ok', editando ? 'Cambio de turno corregido' : 'Cambio de turno guardado');
        limpiarEdicionCambioTurno();
        await cargarEmpleados();
        try { await cargarCambiosTurno(); } catch (_) {}
        await cargarEstadoPeriodo().catch(() => {});
        actualizarAccionGenerar();
    } catch (error) {
        mostrar(error?.message || 'No se pudo guardar el cambio de turno.');
    }
}

function limpiarEdicionCambioTurno() {
    if ($('cambio-turno-fecha-original')) $('cambio-turno-fecha-original').value = '';
    if ($('cambio-turno-empleado')) $('cambio-turno-empleado').disabled = false;
    if ($('cambio-turno-motivo')) $('cambio-turno-motivo').value = '';
    if ($('guardar-cambio-turno')) $('guardar-cambio-turno').textContent = 'Guardar cambio de turno';
    $('cancelar-edicion-cambio-turno')?.classList.add('hidden');
    $('cambio-turno-alerta')?.classList.add('hidden');
}

$('cancelar-edicion-cambio-turno')?.addEventListener('click', limpiarEdicionCambioTurno);

// La misma tabla muestra el personal activo o el retirado, según el
// interruptor de la cabecera. Antes el retirado aparecía en una segunda tabla
// debajo, y en pantallas normales quedaba fuera de la vista.
let vistaPersonal = 'activos';

const COLUMNAS_PERSONAL = {
    activos: ['Nombre','Área','Tipo','Turno base','Lunes de referencia','Descanso','Pareja','Estado','Acciones'],
    retirados: ['Nombre','Área','Tipo','Último día vigente','Estado','Acciones'],
};

function filaPersonalActivo(e) {
    const estado = e.es_nuevo
        ? '<span class="badge badge-new">Nuevo · pendiente de asignación</span>'
        : e.auto_asignado
            ? '<span class="badge badge-auto">Base autoasignada</span>'
            : '<span class="badge badge-ok">Configurado</span>';
    return `<tr>
        <td>${esc(e.nombre)}</td>
        <td>${area(e.area)}</td>
        <td>${tipo(e.tipo_turno)}</td>
        <td>${esc(e.turno_base_mostrado || '')}</td>
        <td>${esc(e.fecha_ancla_rotacion || '—')}</td>
        <td>${esc(e.descanso_mostrado || 'Variable')}</td>
        <td>${esc(e.nombre_pareja || '—')}</td>
        <td>${estado}</td>
        <td class="table-actions">
            <button onclick="editarEmpleado(${e.id})">Editar</button>
            <button onclick="eliminarEmpleado(${e.id})" class="secondary">Retirar</button>
            <button onclick="eliminarEmpleadoDefinitivo(${e.id})" class="danger-soft">Eliminar</button>
        </td>
    </tr>`;
}

function filaPersonalRetirado(e) {
    return `<tr class="employee-inactive">
        <td>${esc(e.nombre)}</td>
        <td>${area(e.area)}</td>
        <td>${tipo(e.tipo_turno)}</td>
        <td>${esc(e.desactivado_en ? String(e.desactivado_en).slice(0,10) : '—')}</td>
        <td><span class="badge badge-inactive">Retirado</span></td>
        <td class="table-actions">
            <button onclick="reactivarEmpleado(${e.id})" class="secondary">Reactivar</button>
            <button onclick="eliminarEmpleadoDefinitivo(${e.id})" class="danger-soft">Eliminar</button>
        </td>
    </tr>`;
}

function renderEmpleados() {
    const activos = empleadosListado.filter(e => e.activo);
    const retirados = empleadosListado.filter(e => !e.activo);
    if (vistaPersonal === 'retirados' && !retirados.length) vistaPersonal = 'activos';
    const mostrandoRetirados = vistaPersonal === 'retirados';
    const filas = mostrandoRetirados ? retirados : activos;

    const cabecera = $('cabecera-tabla-personal');
    if (cabecera) {
        cabecera.innerHTML = `<tr>${COLUMNAS_PERSONAL[vistaPersonal].map(x => `<th>${esc(x)}</th>`).join('')}</tr>`;
    }
    const columnas = COLUMNAS_PERSONAL[vistaPersonal].length;
    const vacio = mostrandoRetirados ? 'No hay personal retirado.' : 'Sin personal activo.';
    $('tabla-empleados').querySelector('tbody').innerHTML =
        filas.map(mostrandoRetirados ? filaPersonalRetirado : filaPersonalActivo).join('')
        || `<tr><td colspan="${columnas}">${vacio}</td></tr>`;

    const titulo = $('titulo-tabla-personal');
    if (titulo) titulo.textContent = mostrandoRetirados ? 'Personal retirado' : 'Personal activo';
    const ayuda = $('ayuda-tabla-personal');
    if (ayuda) {
        ayuda.innerHTML = mostrandoRetirados
            ? 'Se conserva el historial de quien salió de la empresa. Puedes <strong>Reactivar</strong> a una persona si vuelve a vincularse.'
            : 'Usa <strong>Retirar</strong> cuando una persona realmente salió de la empresa y <strong>Eliminar</strong> solo para corregir un registro creado por error.';
    }
    document.querySelectorAll('[data-vista-personal]').forEach(boton => {
        const suya = boton.dataset.vistaPersonal;
        const activa = suya === vistaPersonal;
        boton.classList.toggle('on', activa);
        boton.setAttribute('aria-pressed', activa ? 'true' : 'false');
        const cuantos = suya === 'retirados' ? retirados.length : activos.length;
        boton.textContent = `${suya === 'retirados' ? 'Retirados' : 'Activos'} (${cuantos})`;
        boton.disabled = suya === 'retirados' && retirados.length === 0;
    });
}

document.querySelectorAll('[data-vista-personal]').forEach(boton => {
    boton.addEventListener('click', () => {
        vistaPersonal = boton.dataset.vistaPersonal;
        renderEmpleados();
    });
});

function candidatosPareja() {
    const id = +$('empleado-id').value || 0;
    const a = $('empleado-area').value;
    const t = $('empleado-tipo').value;
    const nuevo = $('empleado-nuevo').checked;

    if (nuevo || a === 'comunicaciones' || t === 'administrativo') return [];

    return empleados.filter(e =>
        e.id !== id &&
        e.area === a &&
        e.tipo_turno === t &&
        (!e.pareja_id || e.pareja_id === id) &&
        (t !== 'fijo' || e.turno_fijo !== $('empleado-turno').value) &&
        (t !== 'rotativo' || (
            e.inicio_rotacion !== $('empleado-inicio').value &&
            e.fecha_ancla_rotacion === $('empleado-ancla').value
        ))
    );
}

function camposEmpleado() {
    const t = $('empleado-tipo').value;
    const a = $('empleado-area').value;
    const nuevo = t === 'rotativo' && $('empleado-nuevo').checked;

    $('g-nuevo').classList.toggle('hidden', t !== 'rotativo');
    $('g-turno').classList.toggle('hidden', t !== 'fijo');
    $('g-inicio').classList.toggle('hidden', t !== 'rotativo' || nuevo);
    $('g-ancla').classList.toggle('hidden', t !== 'rotativo' || nuevo);
    $('g-descanso').classList.toggle('hidden', t === 'administrativo');
    $('g-exento').classList.toggle('hidden', t === 'administrativo');
    $('g-pareja').classList.toggle('hidden', t === 'administrativo' || a === 'comunicaciones' || nuevo);
    $('g-orden').classList.toggle('hidden', a !== 'comunicaciones' || nuevo);

    const current = $('empleado-pareja').value;
    $('empleado-pareja').innerHTML = opts(candidatosPareja(), 'Sin pareja');
    if ([...$('empleado-pareja').options].some(o => o.value === current)) {
        $('empleado-pareja').value = current;
    }
    actualizarPasosVisibles();
}

window.editarEmpleado = id => {
    const e = empleados.find(x => x.id === id);
    if (!e) return;

    $('empleado-id').value = e.id;
    $('empleado-nombre').value = e.nombre;
    $('empleado-area').value = e.area;
    $('empleado-tipo').value = e.tipo_turno;
    $('empleado-turno').value = e.turno_fijo || 'AM';
    $('empleado-nuevo').checked = !!e.es_nuevo;
    $('empleado-inicio').value = e.inicio_rotacion || 'AM';
    $('empleado-ancla').value = e.fecha_ancla_rotacion || '';
    $('empleado-descanso').value = e.descanso_fijo ?? '';
    $('empleado-orden').value = e.orden_rotacion || 0;
    $('empleado-exento').checked = !!e.exento_especiales;
    pintarCoberturaDias(e.cobertura_dias ?? null);
    if ($('empleado-vigente-desde')) $('empleado-vigente-desde').value = e.vigente_desde || $('periodo').value + '-01';
    camposEmpleado();
    $('empleado-pareja').value = e.pareja_id || '';
    sincronizarSelectoresFecha();
    abrirEditorFormulario('form-empleado', `Editar ${e.nombre}`, 'Los cambios se aplicarán desde la fecha indicada. Al guardar volverás a la misma posición de la lista.');
};

let empleadoRetiroPendiente = null;

function cerrarRetiroEmpleado() {
    $('modal-retirar-empleado')?.classList.add('hidden');
    empleadoRetiroPendiente = null;
}

window.eliminarEmpleado = id => {
    const persona = empleadosListado.find(x => x.id === id && x.activo);
    if (!persona) return;
    empleadoRetiroPendiente = persona;
    const modal = $('modal-retirar-empleado');
    const fecha = $('retirar-empleado-fecha');
    const vigente = String(persona.vigente_desde || INICIO_OPERACION_ISO).slice(0,10);
    const hoy = ymd(new Date());
    fecha.min = vigente;
    fecha.value = hoy >= vigente ? hoy : vigente;
    $('retirar-empleado-motivo').value = 'renuncia';
    $('retirar-empleado-mensaje').textContent = `Retirar a ${persona.nombre} sin borrar sus horarios ni su historial.`;
    modal?.classList.remove('hidden');
    fecha.focus();
};

$('cancelar-retirar-empleado')?.addEventListener('click', cerrarRetiroEmpleado);
$('cerrar-retirar-empleado')?.addEventListener('click', cerrarRetiroEmpleado);
$('modal-retirar-empleado')?.addEventListener('click', ev => {
    if (ev.target === $('modal-retirar-empleado')) cerrarRetiroEmpleado();
});
$('confirmar-retirar-empleado')?.addEventListener('click', async () => {
    const persona = empleadoRetiroPendiente;
    if (!persona) return;
    const fecha = $('retirar-empleado-fecha')?.value;
    const motivo = $('retirar-empleado-motivo')?.value || 'otro';
    if (!fecha) {
        toast('Indica el último día vigente del colaborador.', 'warning', 'Fecha requerida');
        return;
    }
    const btn = $('confirmar-retirar-empleado');
    ponerBotonOcupado(btn, true, 'Retirando…');
    try {
        const data = await api(`/api/empleados/${persona.id}/retirar`, {
            method: 'POST',
            body: JSON.stringify({fecha_retiro: fecha, motivo}),
        });
        cerrarRetiroEmpleado();
        await cargarEmpleados();
        await cargarEstadoPeriodo().catch(()=>{});
        actualizarAccionGenerar();
        toast(data.mensaje || 'El colaborador fue retirado y su historial se conservó.', 'success', 'Personal actualizado');
    } catch (e) {
        toast(e.message, 'error', 'No se pudo retirar');
    } finally {
        ponerBotonOcupado(btn, false);
    }
});

window.eliminarEmpleadoDefinitivo = async id => {
    const persona = empleadosListado.find(x => x.id === id);
    if (!persona) return;
    const ok = await confirmarUI({
        titulo: 'Eliminar registro de personal',
        mensaje: `¿${persona.nombre} fue creado por error y debe eliminarse definitivamente?`,
        detalle: 'Esta acción solo se permitirá si la persona NO aparece en un horario oficial/publicado y no tiene solicitudes, asignaciones ni cambios manuales. Si la persona sí trabajó, usa Retirar para conservar el historial.',
        aceptar: 'Eliminar definitivamente',
        peligro: true,
    });
    if (!ok) return;
    try {
        const data = await api(`/api/empleados/${id}/definitivo`, {method: 'DELETE'});
        await cargarEmpleados();
        await cargarEstadoPeriodo().catch(()=>{});
        actualizarAccionGenerar();
        toast(data.mensaje || 'El registro fue eliminado definitivamente.', 'success', 'Registro eliminado');
    } catch (e) {
        toast(e.message, 'error', 'No se puede eliminar');
    }
};

window.reactivarEmpleado = async id => {
    const persona = empleadosListado.find(x => x.id === id);
    const ok = await confirmarUI({
        titulo: 'Reactivar empleado',
        mensaje: `¿Quieres reactivar a ${persona?.nombre || 'este empleado'}?`,
        detalle: 'Volverá a estar disponible para nuevas programaciones sin perder sus horarios, solicitudes ni historial anteriores.',
        aceptar: 'Reactivar empleado',
        peligro: false,
    });
    if (!ok) return;
    try {
        await api(`/api/empleados/${id}/reactivar`, {method: 'POST'});
        await cargarEmpleados();
        await cargarEstadoPeriodo().catch(()=>{});
        actualizarAccionGenerar();
        toast('El empleado volvió a estar disponible para la programación.', 'success', 'Empleado reactivado');
    } catch (e) {
        toast(e.message, 'error', 'No se pudo reactivar');
    }
};

$('form-empleado').onsubmit = async ev => {
    ev.preventDefault();
    const t = $('empleado-tipo').value;
    const nuevo = t === 'rotativo' && $('empleado-nuevo').checked;
    const extrasEmpleado = [
        {id:'empleado-turno', nombre:'Turno fijo', ok: t !== 'fijo' || !!$('empleado-turno')?.value},
        {id:'empleado-inicio', nombre:'Turno inicial', ok: t !== 'rotativo' || nuevo || !!$('empleado-inicio')?.value},
        {id:'empleado-ancla', nombre:'Lunes de referencia', ok: t !== 'rotativo' || nuevo || !!$('empleado-ancla')?.value},
        {id:'empleado-vigente-desde', nombre:'Vigente desde', ok: !!$('empleado-vigente-desde')?.value},
    ];
    if (mostrarFaltantesFormulario($('form-empleado'), extrasEmpleado)) return;

    const id = $('empleado-id').value;
    const a = $('empleado-area').value;

    const d = {
        nombre: $('empleado-nombre').value.trim(),
        cargo: 'GUÍA SOCIAL',
        area: a,
        tipo_turno: t,
        turno_fijo: t === 'fijo' ? $('empleado-turno').value : null,
        descanso_fijo: t === 'administrativo' || $('empleado-descanso').value === '' ? null : +$('empleado-descanso').value,
        pareja_id: !nuevo && t !== 'administrativo' && a !== 'comunicaciones' && $('empleado-pareja').value ? +$('empleado-pareja').value : null,
        inicio_rotacion: t === 'rotativo' && !nuevo ? $('empleado-inicio').value : null,
        fecha_ancla_rotacion: t === 'rotativo' && !nuevo ? $('empleado-ancla').value : null,
        orden_rotacion: +$('empleado-orden').value || 0,
        exento_especiales: t === 'administrativo' ? true : $('empleado-exento').checked,
        cobertura_dias: leerCoberturaDias(),
        es_nuevo: nuevo,
        auto_asignado: false,
        activo: true,
        vigente_desde: $('empleado-vigente-desde')?.value || ($('periodo').value + '-01'),
    };

    try {
        await api(id ? '/api/empleados/' + id : '/api/empleados', {
            method: id ? 'PUT' : 'POST',
            body: JSON.stringify(d),
        });
        // Guardar un empleado termina la edición. El formulario vuelve a su
        // sitio original y la lista se refresca sin dejar un modal abierto.
        cerrarEditorFormulario();
        limpiarErroresFormulario($('form-empleado'));
        $('form-empleado').reset();
        pintarCoberturaDias(null);
        $('empleado-id').value = '';
        $('empleado-nuevo').checked = false;
        if ($('empleado-vigente-desde')) $('empleado-vigente-desde').value = `${$('periodo').value}-01`;
        await cargarEmpleados();
        await cargarEstadoPeriodo().catch(()=>{});
        actualizarAccionGenerar();
        toast(
            nuevo ? 'La base de rotación se asignará al generar su primer horario.' : 'Los datos del empleado fueron guardados.',
            'success',
            nuevo ? 'Empleado nuevo guardado' : 'Personal guardado'
        );
    } catch (e) {
        mostrarAlertaFormulario($('form-empleado'), e.message, 'No se pudo guardar');
        toast(e.message, 'error', 'No se pudo guardar');
    }
};

$('cancelar-empleado').onclick = () => {
    cerrarEditorFormulario();
    limpiarErroresFormulario($('form-empleado'));
    $('form-empleado').reset();
    pintarCoberturaDias(null);
    $('empleado-id').value = '';
    $('empleado-nuevo').checked = false;
    if ($('empleado-vigente-desde')) $('empleado-vigente-desde').value = `${$('periodo').value}-01`;
    camposEmpleado();
};

['empleado-area','empleado-tipo','empleado-turno','empleado-inicio','empleado-ancla','empleado-nuevo']
    .forEach(id => $(id).onchange = camposEmpleado);

// Días en que una persona cuenta para el mínimo de su área. `null` —lo normal—
// significa todos. Una lista 0..6 significa solo esos. Ver
// `backend/cobertura_personal.py`, que es donde está explicado el porqué.
function leerCoberturaDias() {
    const soloAlgunos = $('empleado-cobertura-algunos')?.checked;
    if (!soloAlgunos) return null;
    return [...document.querySelectorAll('#empleado-cobertura-dias input[data-dia]')]
        .filter(c => c.checked)
        .map(c => Number(c.dataset.dia));
}

function pintarCoberturaDias(dias) {
    const soloAlgunos = Array.isArray(dias);
    const todos = $('empleado-cobertura-todos');
    const algunos = $('empleado-cobertura-algunos');
    if (todos) todos.checked = !soloAlgunos;
    if (algunos) algunos.checked = soloAlgunos;
    document.querySelectorAll('#empleado-cobertura-dias input[data-dia]').forEach(c => {
        c.checked = soloAlgunos && dias.includes(Number(c.dataset.dia));
    });
    actualizarVisibilidadCoberturaDias();
}

function actualizarVisibilidadCoberturaDias() {
    const caja = $('empleado-cobertura-dias');
    if (caja) caja.classList.toggle('hidden', !$('empleado-cobertura-algunos')?.checked);
}

document.querySelectorAll('input[name="empleado-cobertura"]').forEach(r => {
    r.addEventListener('change', actualizarVisibilidadCoberturaDias);
});

