// Límites de espera y lectura inicial; sin dependencia de la pantalla.
'use strict';

async function conTopeDeEspera(tarea, segundos) {
    let reloj;
    try {
        return await Promise.race([
            Promise.resolve().then(tarea),
            new Promise((_, fallar) => {
                reloj = setTimeout(() => fallar(new Error(
                    `no contestó en ${segundos} segundos`)), segundos * 1000);
            }),
        ]);
    } finally {
        clearTimeout(reloj);
    }
}

// Lecturas del acceso: el límite incluye cabeceras y cuerpo, y cancela la red.
async function leerAlArrancar(url, milisegundos = 8000) {
    const control = new AbortController();
    const reloj = setTimeout(() => control.abort(), milisegundos);
    try {
        const respuesta = await fetch(url, {signal: control.signal, cache: 'no-store'});
        if (!respuesta.ok) throw new Error(`No se pudo leer ${url}: HTTP ${respuesta.status}`);
        return await respuesta.json();
    } finally {
        clearTimeout(reloj);
    }
}
