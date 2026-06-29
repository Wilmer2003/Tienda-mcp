"""
metrics.py
==========
Coleccion de metricas cuantitativas para reportar (Criterio 5 de la rubrica).

Registra:
- latencia por turno y por agente,
- tasa de exito,
- estimacion de tokens (aprox 1 token = 4 caracteres, suficiente para reportar
  ordenes de magnitud en la exposicion).

Genera un reporte JSON y una tabla en Markdown.
"""
from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TurnoMetricas:
    n: int
    usuario: str
    mensaje: str
    agente: str
    intent: str
    latencia_ms: float
    exito: bool
    tools_invocadas: list[str] = field(default_factory=list)
    tokens_estimados: int = 0


class Metrics:
    def __init__(self) -> None:
        self.turnos: list[TurnoMetricas] = []

    def registrar(self, **kwargs: Any) -> TurnoMetricas:
        t = TurnoMetricas(n=len(self.turnos) + 1, **kwargs)
        self.turnos.append(t)
        return t

    @staticmethod
    def estimar_tokens(*textos: str) -> int:
        total = sum(len(t or "") for t in textos)
        return max(1, total // 4)

    def resumen(self) -> dict[str, Any]:
        if not self.turnos:
            return {"turnos": 0}
        exitosos = [t for t in self.turnos if t.exito]
        latencias = [t.latencia_ms for t in self.turnos]
        tokens = [t.tokens_estimados for t in self.turnos]
        por_agente: dict[str, list[float]] = {}
        for t in self.turnos:
            por_agente.setdefault(t.agente, []).append(t.latencia_ms)
        return {
            "turnos": len(self.turnos),
            "tasa_exito_pct": round(100 * len(exitosos) / len(self.turnos), 1),
            "latencia_ms": {
                "avg": round(statistics.mean(latencias), 2),
                "p50": round(statistics.median(latencias), 2),
                "p95": round(sorted(latencias)[int(0.95 * (len(latencias) - 1))], 2),
                "max": round(max(latencias), 2),
            },
            "tokens_estimados_total": sum(tokens),
            "latencia_avg_por_agente_ms": {
                ag: round(statistics.mean(v), 2) for ag, v in por_agente.items()
            },
        }

    def guardar_markdown(self, path: Path) -> None:
        r = self.resumen()
        if r.get("turnos", 0) == 0:
            path.write_text("# Metricas\n\n(sin turnos registrados)\n",
                            encoding="utf-8")
            return

        lat = r["latencia_ms"]
        contenido = f"""# Metricas del sistema multi-agente

Reporte generado tras correr los escenarios de prueba.

## Resumen global

- Turnos atendidos: **{r['turnos']}**
- Tasa de exito: **{r['tasa_exito_pct']}%**
- Latencia (ms): avg **{lat['avg']}** · p50 **{lat['p50']}** · p95 **{lat['p95']}** · max **{lat['max']}**
- Tokens estimados totales: **{r['tokens_estimados_total']}**

## Latencia promedio por agente (ms)

| Agente | Latencia avg |
|---|---|
"""
        for ag, v in r["latencia_avg_por_agente_ms"].items():
            contenido += f"| {ag} | {v} |\n"

        contenido += "\n## Detalle por turno\n\n"
        contenido += "| # | Usuario | Mensaje | Agente | Intent | Tools | Lat. ms | Exito |\n"
        contenido += "|---|---|---|---|---|---|---|---|\n"
        for t in self.turnos:
            msg_corto = (t.mensaje[:50] + "...") if len(t.mensaje) > 50 else t.mensaje
            tools = ", ".join(t.tools_invocadas) or "-"
            contenido += (f"| {t.n} | {t.usuario} | {msg_corto} | {t.agente} "
                          f"| {t.intent} | {tools} | {t.latencia_ms:.1f} "
                          f"| {'OK' if t.exito else 'FAIL'} |\n")

        path.write_text(contenido, encoding="utf-8")

    def guardar_json(self, path: Path) -> None:
        data = {
            "resumen": self.resumen(),
            "turnos": [t.__dict__ for t in self.turnos],
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                   default=str), encoding="utf-8")
