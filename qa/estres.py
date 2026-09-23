"""Estrés reproducible por HTTP real, siempre sobre datos temporales de QA.

Guarda cada respuesta de generación y un acta JSON. Un escenario que no termina
es un fallo, aunque no llegue a ejecutar su auditor. No usa datos de trabajo.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sqlite3
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path
from threading import Barrier

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from pruebas.auditor import auditar  # noqa: E402
from qa.encadenado import reglas_vigentes_en  # noqa: E402
from qa.reglas import revisar_mes  # noqa: E402
from qa.servidor import Servidor, entrar_como_admin  # noqa: E402


def mapa(horario):
    return {(f["empleado_id"], d["fecha"]): d["turno"] for f in horario for d in f["dias"]}


class Prueba:
    def __init__(self, salida):
        self.salida = salida
        self.informe = {"generaciones": [], "escenarios": [], "fallos": [], "lecturas": {}}
        self.s = None
        self.h = None

    def pedir(self, ruta, metodo="GET", cuerpo=None):
        estado, resultado = self.s.pedir(ruta, metodo, cuerpo, self.h)
        if estado != 200:
            raise AssertionError(f"{metodo} {ruta}: {estado}; {resultado}")
        return resultado

    def generar(self, anio, mes, etiqueta):
        inicio = time.monotonic()
        r = self.pedir("/api/horarios/generar", "POST", {"anio": anio, "mes": mes})
        numero = len(self.informe["generaciones"]) + 1
        destino = self.salida / f"horarios-{numero:03}.json.gz"
        temporal = destino.with_suffix(".tmp")
        temporal.write_bytes(gzip.compress(json.dumps(r, ensure_ascii=False).encode("utf-8")))
        temporal.replace(destino)
        reglas = reglas_vigentes_en(self.s, self.h, anio, mes)
        inicio_mes = date(anio, mes, 1)
        inicio_periodo = (inicio_mes - timedelta(days=inicio_mes.weekday())).isoformat()
        historial = self.pedir("/api/configuracion/reglas-operacion")["historial"]
        vigentes = [r for r in historial if r["vigente_desde"] <= inicio_periodo]
        tope = max(vigentes, key=lambda r: r["vigente_desde"])["max_dias_consecutivos"]
        ficha = {
            "escenario": etiqueta,
            "anio": anio,
            "mes": mes,
            "segundos": round(time.monotonic() - inicio, 3),
            "alternativas": [],
            "reglas_cobertura": reglas,
            "tope_configurado": tope,
        }
        for a in r["alternativas"]:
            fallos = auditar(a["horario"], reglas)
            propios = [x for x in fallos if "(heredado)" not in x[0]]
            normas = revisar_mes(a["horario"], reglas, tope)
            for norma in normas:
                propios.extend((norma.clave, f) for f in norma.fallos)
            if a["reglas"]["maximo_dias_consecutivos"] != tope:
                propios.append(("configuración", "el mes no usó el máximo vigente en su período"))
            ficha["alternativas"].append(
                {
                    "id": a["horario_id"],
                    "valida_motor": a["valido"],
                    "incumplimientos": propios,
                    "historicos": [x for x in fallos if "(heredado)" in x[0]],
                    "normas": [
                        {
                            "nombre": n.clave,
                            "revisados": n.revisados,
                            "exentos": len(n.exentos),
                            "fallos": n.fallos,
                        }
                        for n in normas
                    ],
                }
            )
            if propios and a["valido"]:
                self.informe["fallos"].append(
                    {"escenario": etiqueta, "alternativa": a["horario_id"], "fallos": propios}
                )
        self.informe["generaciones"].append(ficha)
        validas = [a for a in r["alternativas"] if a["valido"]]
        assert validas, f"{etiqueta}: no hay opciones válidas: {r['alternativas'][0]['errores']}"
        elegida = validas[0]
        self.pedir(f"/api/horarios/{elegida['horario_id']}/oficial", "PATCH")
        self.pedir(
            f"/api/operacion/publicacion/{elegida['horario_id']}",
            "POST",
            {"confirmar_excepciones": True},
        )
        print(
            f"{etiqueta}: {anio}-{mes:02} · {len(r['alternativas'])} opciones · "
            f"{ficha['segundos']} s",
            flush=True,
        )
        return elegida

    def bases(self):
        return [self.pedir(f"/api/horarios/oficial/2026/{mes}") for mes in (8, 9)]

    def integridad(self):
        with sqlite3.connect(self.s.carpeta / "horarios.db") as c:
            assert c.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            assert not c.execute("PRAGMA foreign_key_check").fetchall()

    def ejecutar(self, nombre, funcion):
        inicio = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="gestor-estres-") as carpeta:
            try:
                with Servidor(Path(carpeta) / "datos") as self.s:
                    self.h = entrar_como_admin(self.s)
                    antes = self.bases()
                    funcion()
                    assert self.bases() == antes, "se modificaron las bases históricas"
                    self.integridad()
                estado = "correcto"
            except Exception as error:  # noqa: BLE001
                estado = "fallo"
                self.informe["fallos"].append({"escenario": nombre, "error": str(error)})
                print(f"FALLA {nombre}: {error}", flush=True)
        self.informe["escenarios"].append(
            {"nombre": nombre, "estado": estado, "segundos": round(time.monotonic() - inicio, 3)}
        )
        self.guardar()

    def guardar(self):
        self.informe["alternativas_total"] = sum(
            len(x["alternativas"]) for x in self.informe["generaciones"]
        )
        (self.salida / "resultado.json").write_text(
            json.dumps(self.informe, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def encadenar(self, meses):
        anterior = None
        for i in range(meses):
            absoluto = 2026 * 12 + 9 + i
            anio, cero = divmod(absoluto, 12)
            actual = self.generar(anio, cero + 1, "cadena")
            if anterior:
                antes, despues = mapa(anterior["horario"]), mapa(actual["horario"])
                assert all(antes[k] == despues[k] for k in antes.keys() & despues.keys()), (
                    "se rompió la continuidad"
                )
            anterior = actual

    def combinado(self, indice):
        original = self.generar(2026, 10, f"mezcla-{indice}-antes")
        antes = mapa(original["horario"])
        nueva = self.pedir(
            "/api/empleados",
            "POST",
            {
                "nombre": f"Persona QA {indice}",
                "area": "gestion_social",
                "tipo_turno": "fijo",
                "turno_fijo": "AM",
                "vigente_desde": "2026-10-05",
            },
        )["id"]
        tipo, codigo = [("vacaciones", "VAC"), ("permiso", "PER"), ("incapacidad", "INC")][
            indice % 3
        ]
        dia = f"2026-10-{13 + indice % 3:02}"
        solicitud = self.pedir(
            "/api/solicitudes",
            "POST",
            {"empleado_id": nueva, "tipo": tipo, "fecha_inicio": dia, "fecha_fin": dia},
        )
        self.pedir(f"/api/solicitudes/{solicitud['id']}/aprobar", "PATCH")
        self.pedir(
            "/api/requerimientos",
            "POST",
            {
                "empleado_id": nueva,
                "tipo": "asignacion_administrativa",
                "horario_administrativo": "ADM-GS",
                "fechas": ["2026-10-20"],
            },
        )
        self.pedir(
            f"/api/empleados/{nueva}/cambio-turno",
            "POST",
            {
                "vigente_desde": "2026-11-09",
                "tipo_turno": "rotativo",
                "inicio_rotacion": "PM",
                "fecha_ancla_rotacion": "2026-11-09",
            },
        )
        self.pedir(
            "/api/configuracion/reglas-operacion",
            "PUT",
            {
                "vigente_desde": "2026-11-02",
                "max_dias_consecutivos": 10 + indice % 3,
                "nota": "Escenario temporal de estrés",
            },
        )
        oficial = self.pedir("/api/horarios/oficial/2026/10")
        assert mapa(oficial["horario"]["datos"]["horario"]) == antes, (
            "una novedad reescribió el oficial"
        )
        assert self.pedir("/api/operacion/periodo/2026/10")["desactualizado"]
        actual = self.generar(2026, 10, f"mezcla-{indice}-despues")
        nuevo = mapa(actual["horario"])
        assert nuevo[nueva, dia] == codigo, "no se aplicó la solicitud aprobada"
        assert nuevo[nueva, "2026-10-20"] == "ADM-GS", "no se aplicó la asignación"
        assert all(t == "NV" for (p, f), t in nuevo.items() if p == nueva and f < "2026-10-05"), (
            "alta retroactiva"
        )
        fila, celda = next(
            (f, d)
            for f in actual["horario"]
            if f["area"] == "gestion_social" and f["empleado_id"] != nueva
            for d in f["dias"]
            if d["turno"] in ("AM", "PM") and not d.get("heredado") and d.get("mes_propio")
        )
        parcial = self.pedir(
            "/api/horarios/reprogramar-parcial",
            "POST",
            {
                "anio": 2026,
                "mes": 10,
                "horario_id": actual["horario_id"],
                "solo_este_dia": True,
                "ajustes_manuales": [
                    {"empleado_id": fila["empleado_id"], "fecha": celda["fecha"], "turno": "D"}
                ],
            },
        )
        assert parcial["diagnostico_ajustes_manuales"][0]["estado"] == "aplicado"
        ajuste = (fila["empleado_id"], celda["fecha"])
        assert mapa(parcial["alternativas"][0]["horario"])[ajuste] == "D"
        regenerada = self.generar(2026, 10, f"mezcla-{indice}-manual-persistente")
        assert mapa(regenerada["horario"])[ajuste] == "D", "se perdió el ajuste manual"
        noviembre = self.generar(2026, 11, f"mezcla-{indice}-rotacion")
        ficha = next(f for f in noviembre["horario"] if f["empleado_id"] == nueva)
        assert any(d["fecha"] >= "2026-11-09" and d["turno"] == "PM" for d in ficha["dias"])

    def concurrencia(self, cantidad):
        self.generar(2026, 10, "concurrencia")
        rutas = [
            "/api/salud",
            "/api/empleados",
            "/api/solicitudes",
            "/api/horarios/oficial/2026/10",
        ]

        def leer(i):
            inicio = time.monotonic()
            estado, _ = self.s.pedir(rutas[i % len(rutas)], cabeceras=self.h)
            return estado, time.monotonic() - inicio

        with ThreadPoolExecutor(max_workers=8) as pool:
            respuestas = list(pool.map(leer, range(cantidad)))
        tiempos = sorted(t for _, t in respuestas)
        self.informe["lecturas"] = {
            "peticiones": cantidad,
            "trabajadores": 8,
            "errores": sum(e != 200 for e, _ in respuestas),
            "p95_segundos": round(tiempos[int((cantidad - 1) * 0.95)], 4),
            "max_segundos": round(max(tiempos), 4),
        }
        assert all(e == 200 for e, _ in respuestas), "lecturas concurrentes fallidas"
        persona = next(p for p in self.pedir("/api/empleados") if not p.get("pareja_id"))
        for i in range(12):
            dia = f"2027-02-{i + 1:02}"
            ids = [
                self.pedir(
                    "/api/solicitudes",
                    "POST",
                    {
                        "empleado_id": persona["id"],
                        "tipo": tipo,
                        "fecha_inicio": dia,
                        "fecha_fin": dia,
                    },
                )["id"]
                for tipo in ("vacaciones", "incapacidad")
            ]
            barrera = Barrier(2)

            def aprobar(identificador, barrera=barrera):
                barrera.wait(timeout=10)
                return self.s.pedir(
                    f"/api/solicitudes/{identificador}/aprobar", "PATCH", cabeceras=self.h
                )[0]

            with ThreadPoolExecutor(max_workers=2) as pool:
                estados = list(pool.map(aprobar, ids))
            assert estados.count(200) == 1 and all(e < 500 for e in estados), estados
            aprobadas = [
                s
                for s in self.pedir("/api/solicitudes")
                if s["id"] in ids and s["estado"] == "aprobada"
            ]
            assert len(aprobadas) == 1, "dos solicitudes incompatibles quedaron aprobadas"
        self.informe["carreras_aprobacion"] = 12


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meses", type=int, default=24)
    parser.add_argument("--escenarios", type=int, default=6)
    parser.add_argument("--lecturas", type=int, default=400)
    parser.add_argument("--salida", type=Path, default=RAIZ / "dist/diagnostico/estres")
    args = parser.parse_args()
    if args.meses < 1 or args.escenarios < 1 or args.lecturas < 1:
        parser.error("Todos los recuentos deben ser positivos.")
    args.salida.mkdir(parents=True, exist_ok=True)
    prueba = Prueba(args.salida)
    prueba.ejecutar("meses encadenados", lambda: prueba.encadenar(args.meses))
    for i in range(args.escenarios):
        prueba.ejecutar(f"combinado-{i}", lambda i=i: prueba.combinado(i))
    prueba.ejecutar("concurrencia", lambda: prueba.concurrencia(args.lecturas))
    print(
        json.dumps(
            {
                "alternativas": prueba.informe["alternativas_total"],
                "fallos": len(prueba.informe["fallos"]),
                "lecturas": prueba.informe["lecturas"],
            },
            ensure_ascii=False,
        )
    )
    return 1 if prueba.informe["fallos"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
