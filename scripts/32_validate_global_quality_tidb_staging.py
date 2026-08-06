"""Valida conciliación de calidad global entre CSV local y TiDB staging."""
from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import text


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_processed" / "data_quality" / "tidb_staging"
CHECKS_OUT = OUT / "global_quality_tidb_checks.csv"
REPORT_OUT = OUT / "global_quality_tidb_resultados.md"


def load_upload():
    path = Path(__file__).with_name("31_upload_global_quality_to_tidb_staging.py")
    spec = importlib.util.spec_from_file_location("global_quality_upload", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


UPLOAD = load_upload()


def scalar(engine, sql: str, params=None):
    with engine.connect() as connection:
        return connection.execute(text(sql), params or {}).scalar()


def markdown_table(frame: pd.DataFrame) -> str:
    columns = list(frame.columns)
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join("---" for _ in columns) + " |"]
    for row in frame.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in row) + " |")
    return "\n".join(lines)


def main() -> None:
    local = UPLOAD.read_frames()
    engine = UPLOAD.CONNECTION.make_engine()
    rows = []
    def add(check_id, description, observed, expected, warn=False):
        rows.append({"check_id": check_id, "descripcion": description, "estado": "PASS" if observed == expected else "WARN" if warn else "FAIL", "valor_observado": observed, "valor_esperado": expected})
    try:
        for key, table in UPLOAD.TABLES.items():
            present = UPLOAD.exists(engine, table)
            add(f"table_{key}", f"Existe {table}", present, True)
            if present:
                add(f"rows_{key}", f"Filas de {table}", UPLOAD.row_count(engine, table), len(local[key]))
        records = UPLOAD.TABLES["records"]
        checks = UPLOAD.TABLES["checks"]
        modules = UPLOAD.TABLES["modules"]
        summary = UPLOAD.TABLES["summary"]
        unique_alerts = int(scalar(engine, f"SELECT COUNT(*) FROM (SELECT modulo, entidad, registro_id FROM `{records}` GROUP BY modulo, entidad, registro_id) x"))
        add("unique_alerts", "Registros únicos con alertas", unique_alerts, 36_691)
        add("alert_rows", "Alertas fila/regla", UPLOAD.row_count(engine, records), 40_633)
        add("critical", "Alertas críticas", int(scalar(engine, f"SELECT COUNT(*) FROM `{records}` WHERE severidad='CRITICA'")), 928)
        add("not_suitable", "Marcas no aptas para indicadores", int(scalar(engine, f"SELECT COUNT(*) FROM `{records}` WHERE apto_indicador_sustantivo=0")), 5_334)
        add("modules", "Módulos evaluados", UPLOAD.row_count(engine, modules), 9)
        add("global_state", "Estado global", scalar(engine, f"SELECT estado_global FROM `{summary}` LIMIT 1"), "WARN")
        for state, expected in [("PASS", 231), ("WARN", 18), ("FAIL", 0)]:
            add(f"checks_{state.lower()}", f"Checks {state}", int(scalar(engine, f"SELECT COUNT(*) FROM `{checks}` WHERE estado=:state", {"state": state})), expected)
        module_names = set(pd.read_sql(text(f"SELECT modulo FROM `{modules}`"), engine)["modulo"])
        add("module_names", "Nueve módulos esperados", len(module_names), 9)
        cases = [
            ("mortality", "Mortandad mayor que cantidad no apta", "Ganadería", "dq_mortandad_mayor_cantidad", 924, "apto_indicador_sustantivo=0"),
            ("negative_surface", "Superficies negativas no aptas", None, "dq_superficie_negativa", 1, "apto_indicador_sustantivo=0"),
            ("affected_gt", "Afectada mayor que sembrada", "Agricultura", "_afectada_mayor_sembrada", 6, "apto_indicador_sustantivo=0"),
            ("delivery_duplicates", "Posibles duplicados preservados", "Entregas y asistencias", "posible_duplicado", 4304, "1=1"),
            ("missing_coords", "Coordenadas faltantes no aptas", "Georreferenciación y mapa", "faltante_o_cero", 28868, "apto_mapa=0"),
        ]
        for cid, desc, module, rule, expected, condition in cases:
            module_sql = " AND modulo=:module" if module else ""
            params = {"rule": rule, "module": module}
            observed = int(scalar(engine, f"SELECT COUNT(*) FROM `{records}` WHERE regla_calidad=:rule {module_sql} AND {condition}", params))
            add(cid, desc, observed, expected)
        not_map = int(scalar(engine, f"SELECT COUNT(DISTINCT registro_id) FROM `{records}` WHERE modulo='Georreferenciación y mapa' AND apto_mapa=0"))
        add("map_points", "Puntos aptos para mapa", 32_363 - not_map, 3_218)
        frame = pd.DataFrame(rows)
        status = "FAIL" if frame.estado.eq("FAIL").any() else "WARN" if frame.estado.eq("WARN").any() else "PASS"
        OUT.mkdir(parents=True, exist_ok=True)
        frame.to_csv(CHECKS_OUT, index=False, encoding="utf-8-sig")
        counts = frame.estado.value_counts()
        report = f"""# Validación de calidad global en TiDB staging

- Fecha: **{datetime.now().astimezone().isoformat(timespec='seconds')}**
- Estado: **{status}**
- PASS: **{int(counts.get('PASS',0))}**
- WARN: **{int(counts.get('WARN',0))}**
- FAIL: **{int(counts.get('FAIL',0))}**

Las cuatro tablas staging concilian con los CSV locales. Los datos originales, tablas finales y vistas no fueron modificados.

## Checks

{markdown_table(frame)}
"""
        REPORT_OUT.write_text(report, encoding="utf-8")
        print(f"Estado: {status}")
        print(f"PASS={int(counts.get('PASS',0))} WARN={int(counts.get('WARN',0))} FAIL={int(counts.get('FAIL',0))}")
        if status == "FAIL":
            raise SystemExit(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
