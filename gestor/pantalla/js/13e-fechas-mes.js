// 13e-fechas-mes.js · Ver LEEME.md para el contrato de carga.
'use strict';

const MESES_ES=['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
// `crearSelectorFecha` se retiró en R12: los tres desplegables de día, mes y
// año quedaron sustituidos por el calendario propio (ver `activarCalendarios`).

function crearSelectorMes(input) {
    if (!input || input.dataset.selectorCreado==='1') return;
    input.dataset.selectorCreado='1'; input.classList.add('native-date-hidden');
    const wrap=document.createElement('div'); wrap.className='date-select-group month-only';
    const sm=document.createElement('select'), sy=document.createElement('select');
    sm.className='date-month'; sy.className='date-year';

    // La programación empieza en agosto de 2026 y no existe nada antes. En vez
    // de dejar elegir enero y corregirlo después con un aviso —que es lo que
    // hacía antes—, los meses anteriores al mínimo sencillamente no se ofrecen.
    const minimo = () => String(input.min || PERIODO_MINIMO || '2026-08');
    const anioMinimo = () => Number(minimo().slice(0, 4));
    const mesMinimo = () => Number(minimo().slice(5, 7));

    const actual=new Date().getFullYear(), hasta=Math.max(2036,actual+10);
    const primerAnio=anioMinimo();
    sy.innerHTML=Array.from({length:hasta-primerAnio+1},(_,i)=>primerAnio+i)
        .map(y=>`<option value="${y}">${y}</option>`).join('');

    function pintarMeses(){
        const anio=Number(sy.value)||primerAnio;
        const desde=anio===anioMinimo() ? mesMinimo() : 1;
        const previo=Number(sm.value)||desde;
        sm.innerHTML=MESES_ES
            .map((m,i)=>({m, n:i+1}))
            .filter(x=>x.n>=desde)
            .map(x=>`<option value="${x.n}">${x.m}</option>`).join('');
        sm.value=String(previo>=desde ? previo : desde);
    }

    function cargar(){
        const m=/^(\d{4})-(\d{2})$/.exec(input.value||'');
        if(m){ sy.value=String(Number(m[1])); pintarMeses(); sm.value=String(Number(m[2])); }
        else { pintarMeses(); }
    }
    function actualizar(){
        pintarMeses();
        let valor=`${sy.value}-${String(sm.value).padStart(2,'0')}`;
        if (valor < minimo()) valor=minimo();
        input.value=valor; cargar(); input.dispatchEvent(new Event('change',{bubbles:true}));
    }
    sm.onchange=actualizar; sy.onchange=actualizar; wrap.append(sm,sy); input.insertAdjacentElement('afterend',wrap); cargar(); input._syncSelectorMes=cargar;
}
function inicializarSelectoresFecha(){
    // Las fechas de día completo ya no usan tres desplegables: las lleva el
    // calendario propio, que muestra el mes entero y evita elegir un día que
    // no existe. Los períodos (mes y año) sí conservan sus desplegables,
    // porque ahí no se elige un día.
    document.querySelectorAll('input[type="month"]').forEach(crearSelectorMes);
}
function sincronizarSelectoresFecha(){
    document.querySelectorAll('input.native-date-hidden').forEach(x=>{ x._syncSelectorMes?.(); });
    document.querySelectorAll('input[type="date"]').forEach(x=>{ x._syncCalendario?.(); });
}
