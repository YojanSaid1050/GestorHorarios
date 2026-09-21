// La barra de título del propio programa, y los bordes para redimensionar
// ---------------------------------------------------------------------------
// Parte de la pantalla del Gestor de Horarios. Los archivos de esta carpeta se
// cargan en orden y comparten el mismo ámbito, así que juntos son exactamente
// el app.js de antes. Ver frontend/js/LEEME.md.
//
// De qué va esto
// --------------
// La ventana del programa se puede abrir de dos maneras: con el marco gris de
// Windows, o sin marco y con la barra de título pintada aquí, con los colores de
// la aplicación. Lo segundo se ve mejor y es lo que viene puesto de fábrica.
//
// Quitar el marco tiene un precio, y es todo lo que Windows hacía gratis:
//
//   * mover la ventana. Lo devuelve pywebview: arrastra lo que lleve la clase
//     `pywebview-drag-region`, que en esta pantalla es solo la zona del título;
//   * minimizar, maximizar y cerrar. Son los tres botones de aquí, que llaman a
//     Python a través de `window.pywebview.api`;
//   * el doble clic en la barra para maximizar;
//   * y **redimensionar arrastrando un borde**, que es lo que más cuesta: un
//     formulario sin marco pierde el borde que se agarra con el ratón. Se
//     devuelve con ocho tiradores invisibles alrededor de la pantalla.
//
// Lo único que no se recupera es el ajuste a los lados de Windows (arrastrar la
// ventana contra un borde para que ocupe media pantalla). Quien lo use a diario
// puede volver a la barra de Windows desde Configuración → Barra de la ventana.
//
// Nada de esto se enciende en un navegador: sin `window.pywebview` no hay
// ventana que mover y la barra se queda escondida.

'use strict';

//: El mínimo lo decide Python (`gestor/servicios/marco.py`) y aquí se repite
//: para que el arrastre no se pase de largo y la ventana no dé un salto al
//: corregirlo. Si alguna vez dejan de coincidir, gana Python.
const ANCHO_MINIMO_VENTANA = 1100;
const ALTO_MINIMO_VENTANA = 700;

let barraDeVentanaPuesta = false;
let estiradoEnVuelo = false;
let estiradoPendiente = null;
let esperaBotonMaximizar = 0;

function apiDeLaVentana() {
    return (typeof window.pywebview === 'object' && window.pywebview) ? window.pywebview.api : null;
}

// ------------------------------------------------------ encender la barra

// Se pregunta a la **ventana**, no al servidor, y a propósito: esta barra tiene
// que funcionar en la pantalla de acceso, antes de que haya sesión, y todo lo
// que está bajo /api/configuracion/ pide sesión. Preguntando por ahí, una
// ventana sin marco se abriría sin barra y sin forma de moverla ni de cerrarla
// hasta después de entrar.
async function encenderBarraDeVentana() {
    if (barraDeVentanaPuesta) return;
    const apiVentana = apiDeLaVentana();
    if (!apiVentana || typeof apiVentana.barra_propia !== 'function') return;
    let propia = false;
    try {
        propia = await conTopeDeEspera(() => apiVentana.barra_propia(), 3);
    } catch (e) {
        console.warn('[ventana] no se pudo saber con qué barra se abrió:', e);
        return;
    }
    if (!propia) return;
    barraDeVentanaPuesta = true;
    $('barra-ventana')?.classList.remove('hidden');
    // Lo lee el CSS para dejar hueco a la barra al saltar a una tarjeta: sin
    // esto, «ir a» una tarjeta la dejaba con el título medio tapado por la
    // barra, que es lo que hace toda página con una cabecera pegada arriba.
    document.body.classList.add('con-barra-propia');
    conectarBotonesDeLaVentana(apiVentana);
    conectarTiradoresDeLaVentana(apiVentana);
    seguirElTituloDeLaVentana();
    await sincronizarBotonMaximizar(apiVentana);
}

function seguirElTituloDeLaVentana() {
    const destino = $('barra-ventana-titulo');
    const titulo = document.querySelector('title');
    if (!destino || !titulo) return;
    const copiar = () => { destino.textContent = document.title; };
    copiar();
    // El nombre y la versión llegan del servidor un momento después de arrancar,
    // así que se vigila el <title> en vez de copiarlo una vez y quedarse con el
    // que trae el archivo.
    new MutationObserver(copiar).observe(titulo, {childList: true, characterData: true, subtree: true});
}

// ------------------------------------------------------------ los botones

function conectarBotonesDeLaVentana(apiVentana) {
    const minimizar = $('ventana-minimizar');
    if (minimizar) minimizar.onclick = () => { apiVentana.minimizar?.(); };
    const maximizar = $('ventana-maximizar');
    if (maximizar) maximizar.onclick = () => alternarMaximizada(apiVentana);
    const cerrar = $('ventana-cerrar');
    if (cerrar) cerrar.onclick = () => { apiVentana.cerrar?.(); };
    // El doble clic en la barra maximiza, como en cualquier ventana de Windows.
    $('barra-ventana-arrastre')?.addEventListener('dblclick', () => alternarMaximizada(apiVentana));
    // Windows también maximiza por su cuenta, con Win+flecha arriba. El botón
    // tiene que enseñar el icono que toca en ese caso también, y lo único que
    // llega hasta aquí de ese gesto es el cambio de tamaño.
    window.addEventListener('resize', () => {
        clearTimeout(esperaBotonMaximizar);
        esperaBotonMaximizar = setTimeout(() => sincronizarBotonMaximizar(apiVentana), 160);
    });
}

async function alternarMaximizada(apiVentana) {
    try {
        await apiVentana.maximizar_o_restaurar();
    } catch (e) {
        console.warn('[ventana] no se pudo maximizar ni restaurar:', e);
    }
    await sincronizarBotonMaximizar(apiVentana);
}

async function sincronizarBotonMaximizar(apiVentana) {
    let maximizada = false;
    try {
        maximizada = await apiVentana.esta_maximizada();
    } catch (_) { /* se queda como estaba */ }
    $('barra-ventana')?.classList.toggle('maximizada', !!maximizada);
    // Maximizada no hay bordes que estirar, y dejar los tiradores puestos
    // permitiría agrandar una ventana que ya ocupa la pantalla entera.
    $('tiradores-ventana')?.classList.toggle('quieta', !!maximizada);
    const boton = $('ventana-maximizar');
    if (!boton) return;
    boton.title = maximizada ? 'Restaurar' : 'Maximizar';
    boton.setAttribute('aria-label', maximizada
        ? 'Restaurar el tamaño anterior de la ventana'
        : 'Maximizar la ventana');
}

// --------------------------------------------- estirar desde los bordes

function conectarTiradoresDeLaVentana(apiVentana) {
    const tiradores = $('tiradores-ventana');
    if (!tiradores) return;
    if (typeof apiVentana.redimensionar !== 'function') {
        // Mejor ningún tirador que ocho bandas que no hacen nada y encima se
        // comen los clics del borde de la pantalla.
        console.warn('[ventana] esta versión no sabe redimensionar; sin tiradores');
        return;
    }
    tiradores.classList.remove('hidden');
    tiradores.querySelectorAll('[data-borde]').forEach(tirador => {
        tirador.addEventListener('pointerdown', ev => empezarAEstirar(ev, tirador, apiVentana));
    });
}

function empezarAEstirar(ev, tirador, apiVentana) {
    if (ev.button !== 0) return;
    ev.preventDefault();
    const borde = tirador.dataset.borde || 'se';
    // Sin capturar el puntero, el estirado se corta en cuanto el ratón sale de
    // la ventana, que es exactamente lo que pasa al agrandarla.
    try { tirador.setPointerCapture(ev.pointerId); } catch (_) { /* da igual */ }

    // `outerWidth` es la ventana entera; `innerWidth` se queda corto por la
    // barra de desplazamiento y haría que la ventana adelgazara sola al primer
    // arrastre. Se usa el otro solo si el primero no contesta nada creíble.
    const anchoInicial = window.outerWidth > 200 ? window.outerWidth : window.innerWidth;
    const altoInicial = window.outerHeight > 200 ? window.outerHeight : window.innerHeight;
    const desdeX = ev.screenX;
    const desdeY = ev.screenY;

    const mover = e => {
        const dx = e.screenX - desdeX;
        const dy = e.screenY - desdeY;
        let ancho = anchoInicial;
        let alto = altoInicial;
        if (borde.includes('e')) ancho = anchoInicial + dx;
        if (borde.includes('o')) ancho = anchoInicial - dx;
        if (borde.includes('s')) alto = altoInicial + dy;
        if (borde.includes('n')) alto = altoInicial - dy;
        estiradoPendiente = {
            ancho: Math.max(Math.round(ancho), ANCHO_MINIMO_VENTANA),
            alto: Math.max(Math.round(alto), ALTO_MINIMO_VENTANA),
        };
        enviarEstirado(apiVentana, borde);
    };

    const soltar = () => {
        tirador.removeEventListener('pointermove', mover);
        tirador.removeEventListener('pointerup', soltar);
        tirador.removeEventListener('pointercancel', soltar);
        // Lo que quede pendiente **no** se tira: es el último tamaño, el que la
        // persona vio al soltar el ratón. Descartándolo, la ventana se quedaba
        // un paso por detrás de donde se dejó.
        enviarEstirado(apiVentana, borde);
    };

    tirador.addEventListener('pointermove', mover);
    tirador.addEventListener('pointerup', soltar);
    tirador.addEventListener('pointercancel', soltar);
}

// Un solo viaje a Python a la vez, con el último tamaño pedido.
//
// El ratón manda decenas de movimientos por segundo y cada llamada a la ventana
// cruza el puente de pywebview. Encolándolas todas, la ventana se quedaba
// persiguiendo al ratón varios cientos de milisegundos por detrás. Así se pide
// solo el tamaño que vale, que es el último.
async function enviarEstirado(apiVentana, borde) {
    if (estiradoEnVuelo) return;
    estiradoEnVuelo = true;
    try {
        while (estiradoPendiente) {
            const {ancho, alto} = estiradoPendiente;
            estiradoPendiente = null;
            await apiVentana.redimensionar(ancho, alto, borde);
        }
    } catch (e) {
        estiradoPendiente = null;
        console.warn('[ventana] no se pudo redimensionar:', e);
    } finally {
        estiradoEnVuelo = false;
    }
}

// ------------------------------------ el interruptor de Configuración

function pintarBarraElegida(propia) {
    document.querySelectorAll('[data-barra-opcion]').forEach(b => {
        const activo = (b.dataset.barraOpcion === 'propia') === !!propia;
        b.classList.toggle('active', activo);
        b.setAttribute('aria-pressed', String(activo));
    });
}

async function cargarBarraVentana() {
    const data = await api('/api/configuracion/barra-ventana');
    pintarBarraElegida(data.propia);
    const nota = $('barra-ventana-nota');
    if (nota && data.aviso) nota.textContent = data.aviso;
}

function conectarSelectorDeBarra() {
    document.querySelectorAll('[data-barra-opcion]').forEach(boton => {
        boton.onclick = async () => {
            const propia = boton.dataset.barraOpcion === 'propia';
            try {
                const data = await api('/api/configuracion/barra-ventana', {
                    method: 'PUT', body: JSON.stringify({propia}),
                });
                pintarBarraElegida(data.propia);
                const nota = $('barra-ventana-nota');
                if (nota) nota.textContent = data.mensaje;
                toast(data.mensaje, 'success', 'Ventana actualizada');
            } catch (e) {
                toast(e.message, 'error', 'No se pudo cambiar la barra de la ventana');
            }
        };
    });
}

// La barra no espera al arranque de la aplicación: se enciende en cuanto
// pywebview contesta, que es antes de la pantalla de acceso. El interruptor de
// Configuración sí va con el resto (`14-arranque.js`), porque necesita sesión.
conectarSelectorDeBarra();
if (apiDeLaVentana()) {
    encenderBarraDeVentana();
} else {
    window.addEventListener('pywebviewready', () => { encenderBarraDeVentana(); });
}
