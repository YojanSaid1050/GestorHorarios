// Las pestañas, los contadores y los formularios por pasos
// ---------------------------------------------------------------------------
// Parte de la pantalla del Gestor de Horarios. Los archivos de esta carpeta se
// cargan en orden y comparten el mismo ámbito, así que juntos son exactamente
// el app.js de antes. Ver frontend/js/LEEME.md.

'use strict';

// ---------------------------------------------------------------------------
// Configuración, por grupos
// ---------------------------------------------------------------------------
// Configuración eran once apartados uno detrás de otro en una misma página:
// noventa y nueve botones seguidos, y para llegar a los festivos había que
// pasar por delante de la copia de seguridad y del restablecimiento de fábrica.
// No es que estuviera mal explicado —es que se veía todo a la vez.
//
// Ahora se agrupan por lo que la persona ha venido a hacer, y solo se enseña un
// grupo cada vez. El índice lateral sigue funcionando igual: al pulsar un
// apartado se abre su grupo y se baja hasta él.

const GRUPOS_CONFIG = [
    {
        id: 'reglas',
        nombre: 'Reglas del horario',
        ayuda: 'Lo que la aplicación tiene en cuenta al armar cada mes.',
        tarjetas: ['tarjeta-regla-racha', 'tarjeta-reglas-cobertura', 'cfg-festivos'],
    },
    {
        id: 'apariencia',
        nombre: 'Apariencia',
        ayuda: 'Cómo se ve la aplicación y con qué colores sale el Excel.',
        tarjetas: ['cfg-ventana', 'cfg-modo', 'cfg-apariencia', 'cfg-colores'],
    },
    {
        id: 'cuenta',
        nombre: 'Cuentas',
        ayuda: 'Tu contraseña y quién más puede entrar a trabajar con la programación.',
        tarjetas: ['cfg-usuarios'],
    },
    {
        id: 'datos',
        nombre: 'Datos y copias',
        ayuda: 'Dónde se guarda todo, cómo hacer una copia y cómo volver atrás.',
        tarjetas: ['cfg-actualizaciones', 'cfg-archivos', 'cfg-copias', 'cfg-reiniciar', 'cfg-fabrica'],
    },
];

let grupoConfigActivo = 'reglas';

function organizarConfiguracion() {
    const seccion = document.getElementById('configuracion');
    if (!seccion || seccion.dataset.agrupada === '1') return;

    const barra = document.createElement('div');
    barra.className = 'cfg-grupos';
    barra.setAttribute('role', 'tablist');
    barra.innerHTML = GRUPOS_CONFIG.map(g => `
        <button type="button" class="cfg-grupo-boton" data-grupo="${g.id}" role="tab">
            <strong>${esc(g.nombre)}</strong><span>${esc(g.ayuda)}</span>
        </button>`).join('');
    seccion.prepend(barra);

    GRUPOS_CONFIG.forEach(g => {
        const caja = document.createElement('div');
        caja.className = 'cfg-grupo';
        caja.dataset.grupo = g.id;
        seccion.appendChild(caja);
        g.tarjetas.forEach(id => {
            const tarjeta = document.getElementById(id);
            if (tarjeta) caja.appendChild(tarjeta);
        });
    });

    barra.querySelectorAll('[data-grupo]').forEach(b => {
        b.onclick = () => mostrarGrupoConfig(b.dataset.grupo);
    });
    seccion.dataset.agrupada = '1';
    mostrarGrupoConfig(grupoConfigActivo);
}

function mostrarGrupoConfig(id) {
    grupoConfigActivo = id;
    document.querySelectorAll('.cfg-grupo').forEach(c => {
        c.classList.toggle('hidden', c.dataset.grupo !== id);
    });
    document.querySelectorAll('.cfg-grupo-boton').forEach(b => {
        const activo = b.dataset.grupo === id;
        b.classList.toggle('active', activo);
        b.setAttribute('aria-selected', activo ? 'true' : 'false');
    });
    requestAnimationFrame(marcarSubmenuConfigPorPosicion);
}

function grupoDeTarjeta(idTarjeta) {
    return (GRUPOS_CONFIG.find(g => g.tarjetas.includes(idTarjeta)) || {}).id;
}

// El índice lateral también sigue el desplazamiento. Antes solo recordaba el
// último botón pulsado: si la persona bajaba desde Reparto hasta Festivos, el
// menú seguía afirmando que estaba en Reparto. Se toma como actual la tarjeta
// visible más cercana al inicio útil de la ventana.
let rafSubmenuConfig = 0;
function marcarSubmenuConfigPorPosicion() {
    rafSubmenuConfig = 0;
    if (!document.getElementById('configuracion')?.classList.contains('active')) return;
    const candidatos = [...document.querySelectorAll('[data-ir-config]')]
        .map(boton => ({boton, tarjeta: document.getElementById(boton.dataset.irConfig)}))
        .filter(x => x.tarjeta && !x.tarjeta.closest('.cfg-grupo')?.classList.contains('hidden'));
    if (!candidatos.length) return;
    const ancla = Math.min(190, Math.max(96, window.innerHeight * .18));
    const visibles = candidatos.filter(x => {
        const r = x.tarjeta.getBoundingClientRect();
        return r.bottom > ancla && r.top < window.innerHeight;
    });
    const universo = visibles.length ? visibles : candidatos;
    const actual = universo.reduce((mejor, x) => {
        const distancia = Math.abs(x.tarjeta.getBoundingClientRect().top - ancla);
        return !mejor || distancia < mejor.distancia ? {x, distancia} : mejor;
    }, null)?.x;
    document.querySelectorAll('[data-ir-config]').forEach(b =>
        b.classList.toggle('active', b === actual?.boton));
}

window.addEventListener('scroll', () => {
    if (rafSubmenuConfig) return;
    rafSubmenuConfig = requestAnimationFrame(marcarSubmenuConfigPorPosicion);
}, {passive:true});
window.addEventListener('resize', marcarSubmenuConfigPorPosicion, {passive:true});

// ---------------------------------------------------------------------------
// Los formularios largos, leídos por pasos
// ---------------------------------------------------------------------------
// Registrar una solicitud o una asignación es una rejilla de hasta doce campos
// que aparecen y desaparecen según el tipo. Están bien puestos, pero se leen
// todos de golpe y no dicen por dónde empezar.
//
// Aquí se les pone encima una línea de separación con un título —quién, cuándo,
// detalles— delante del primer campo de cada tramo. No se mueve ningún campo:
// solo se marca dónde empieza cada parte. Y un tramo cuyos campos estén todos
// ocultos para ese tipo desaparece también, para no dejar títulos vacíos.

const PASOS_FORMULARIO = {
    'form-solicitud': [
        {campo: 'solicitud-empleado', titulo: 'Quién y qué', ayuda: 'La persona y el tipo de novedad.'},
        {campo: 'solicitud-modo-fechas-general', titulo: 'Cuándo', ayuda: 'Los días que abarca, dentro del mes que estás programando.'},
        {campo: 'g-fecha-inicio', titulo: 'Cuándo', ayuda: 'Los días que abarca, dentro del mes que estás programando.'},
        {campo: 'solicitud-observacion', titulo: 'Para dejar constancia', ayuda: 'Opcional, pero es lo que se lee dentro de tres meses.'},
    ],
    'form-requerimiento': [
        {campo: 'g-requerimiento-alcance', titulo: 'A quién', ayuda: 'Una persona, un área entera o todo el personal.'},
        {campo: 'requerimiento-tipo', titulo: 'Qué se le pone', ayuda: 'El tipo de asignación y el horario que le corresponde.'},
        {campo: 'requerimiento-modo-fechas', titulo: 'Cuándo', ayuda: 'Los días que abarca, dentro del mes que estás programando.'},
        {campo: 'requerimiento-descripcion', titulo: 'Para dejar constancia', ayuda: 'Qué es y por qué, para quien lo lea dentro de tres meses.'},
    ],
    'form-empleado': [
        {campo: 'empleado-nombre', titulo: 'Quién es', ayuda: 'Nombre y área en la que trabaja.'},
        {campo: 'empleado-tipo', titulo: 'Cómo trabaja', ayuda: 'Su turno, su descanso y su pareja, si la tiene.'},
        {campo: 'empleado-vigente-desde', titulo: 'Desde cuándo', ayuda: 'Los meses anteriores conservan lo que ya tenían.'},
    ],
};

function prepararPasosDeFormulario() {
    Object.entries(PASOS_FORMULARIO).forEach(([idForm, pasos]) => {
        const form = document.getElementById(idForm);
        if (!form || form.dataset.pasosListos === '1') return;
        let anterior = '';
        pasos.forEach(paso => {
            const campo = document.getElementById(paso.campo);
            if (!campo) return;
            // El tramo se marca sobre el bloque que envuelve al campo, que es
            // hijo directo del formulario: ahí es donde encaja la separación.
            let bloque = campo;
            while (bloque && bloque.parentElement !== form) bloque = bloque.parentElement;
            if (!bloque || bloque.previousElementSibling?.classList?.contains('form-paso')) return;
            if (paso.titulo === anterior) return;
            anterior = paso.titulo;
            const cabecera = document.createElement('div');
            cabecera.className = 'form-paso';
            cabecera.dataset.paso = paso.titulo;
            cabecera.innerHTML = `<strong>${esc(paso.titulo)}</strong><span>${esc(paso.ayuda)}</span>`;
            form.insertBefore(cabecera, bloque);
        });
        form.dataset.pasosListos = '1';
    });
    actualizarPasosVisibles();
}

// Un tramo sin ningún campo visible sobra: se esconde con ellos.
function actualizarPasosVisibles() {
    document.querySelectorAll('.form-paso').forEach(cabecera => {
        let hermano = cabecera.nextElementSibling;
        let hayAlgo = false;
        while (hermano && !hermano.classList.contains('form-paso')) {
            const oculto = hermano.classList.contains('hidden')
                || getComputedStyle(hermano).display === 'none';
            if (!oculto && !hermano.classList.contains('actions')) { hayAlgo = true; break; }
            hermano = hermano.nextElementSibling;
        }
        cabecera.classList.toggle('hidden', !hayAlgo);
    });
}

function tabs() {
    document.querySelectorAll('[data-tab]').forEach(button => {
        button.onclick = () => {
            document.querySelectorAll('[data-tab]').forEach(x => x.classList.toggle('active', x === button));
            document.querySelectorAll('.tab').forEach(x => x.classList.toggle('active', x.id === button.dataset.tab));
            // El índice de Configuración solo se despliega cuando se está en ella.
            const enConfig = button.dataset.tab === 'configuracion';
            $('nav-configuracion')?.classList.toggle('abierto', enConfig);
            document.querySelector('[data-tab="configuracion"]')
                ?.setAttribute('aria-expanded', enConfig ? 'true' : 'false');
            if (!enConfig) {
                document.querySelectorAll('[data-ir-config]')
                    .forEach(x => x.classList.remove('active'));
            }
            ajustarBarraDeHerramientas(button.dataset.tab);
            if (button.dataset.tab === 'historial') cargarAuditoria().catch(e => toast(e.message,'error','Historial'));
            if (button.dataset.tab === 'horario') cargarSemanasBloqueo().catch(()=>{});
            // Cada apartado refresca su contador al entrar y al salir: así el
            // número de la barra no se queda con lo que había hace media hora.
            actualizarContadoresMenu();
        };
    });
    // Índice de Configuración: lleva directamente al apartado, sin bajar por
    // los ocho anteriores.
    document.querySelectorAll('[data-ir-config]').forEach(boton => {
        boton.onclick = () => {
            document.querySelector('[data-tab="configuracion"]')?.click();
            document.querySelectorAll('[data-ir-config]')
                .forEach(x => x.classList.toggle('active', x === boton));
            const destino = document.getElementById(boton.dataset.irConfig);
            if (!destino) return;
            const grupo = grupoDeTarjeta(boton.dataset.irConfig);
            if (grupo) mostrarGrupoConfig(grupo);
            requestAnimationFrame(() => destino.scrollIntoView({block: 'start', behavior: 'smooth'}));
            destino.classList.add('destacado');
            setTimeout(() => destino.classList.remove('destacado'), 1400);
        };
    });
}

// --- Contadores de la barra de navegación --------------------------------
// Dicen cuánto trabajo hay esperando en cada apartado sin tener que entrar:
// solicitudes por aprobar, asignaciones activas y conflictos del horario que
// se está viendo. Solo se muestran cuando hay algo; un cero fijo es ruido.

function ponerContadorMenu(tab, valor, alerta = false) {
    const marca = document.getElementById(`nav-count-${tab}`);
    if (!marca) return;
    const n = Number(valor) || 0;
    marca.textContent = n > 99 ? '99+' : String(n);
    marca.classList.toggle('alerta', Boolean(alerta) && n > 0);
    marca.hidden = n <= 0;
    const boton = document.querySelector(`[data-tab="${tab}"]`);
    if (boton) {
        const texto = boton.querySelector('.nav-text')?.textContent || tab;
        boton.setAttribute('aria-label', n > 0 ? `${texto}: ${n} pendiente${n === 1 ? '' : 's'}` : texto);
    }
}

function actualizarContadoresMenu() {
    // Los números del menú son del mes que se está viendo. Antes contaban todo
    // el histórico, así que crecían sin parar y dejaban de significar nada.
    // Solicitudes pendientes de aprobar en este mes.
    ponerContadorMenu('solicitudes',
        (typeof solicitudes !== 'undefined' && Array.isArray(solicitudes))
            // `estado_efectivo`, que es lo que el servidor calcula y lo único
            // que distingue «pendiente» de «vencida», «rechazada» o
            // «cancelada». El campo `rechazada` que se leía aquí no existe en
            // ninguna parte del programa, así que el número rojo contaba
            // también las rechazadas y las canceladas: crecía y no bajaba
            // nunca, y quien lo seguía llegaba a una tabla sin nada pendiente.
            ? solicitudes.filter(x => x.estado_efectivo === 'pendiente' && solicitudDelPeriodo(x)).length : 0);

    // Solo asignaciones pendientes de incorporar. Contar todas las activas
    // mantenía un número aunque el horario ya estuviera actualizado y hacía
    // parecer que siempre quedaba trabajo por hacer.
    ponerContadorMenu('requerimientos', contarCambiosPendientesDe('asignaciones'));

    // Del horario que se está viendo: el número son conflictos y avisos, pero
    // solo se pinta en rojo si hay conflictos, que son los que impiden dar el
    // mes por bueno. Un aviso no debe alarmar.
    const tabV = document.querySelector('[data-tab="validacion"]');
    const total = Number(tabV?.dataset.count || 0);
    const errores = Number(tabV?.dataset.errores || 0);
    ponerContadorMenu('validacion', total, errores > 0);
}

function opts(list, first) {
    return `<option value="">${esc(first)}</option>` + list
        .map(e => `<option value="${e.id}">${esc(e.nombre)}</option>`)
        .join('');
}
