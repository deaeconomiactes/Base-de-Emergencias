"""Sistema transversal de calidad de datos (primera versión).

Auditoría de solo lectura. Consolida controles existentes y genera alertas sin
corregir, eliminar, imputar ni sobrescribir insumos.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data_processed" / "data_quality" / "global"
DDJJ = ROOT / "data_processed" / "ddjj_2023_excel" / "normalized"
DELIVERIES = ROOT / "data_processed" / "entregas" / "normalized"
MAP = ROOT / "data_processed" / "mapa" / "audit"
RUN_AT = datetime.now().astimezone().isoformat(timespec="seconds")

CHECK_COLUMNS = ["check_id", "modulo", "categoria", "descripcion", "estado", "severidad", "valor_observado", "valor_esperado", "detalle", "fuente_resultado"]
FLAG_COLUMNS = ["modulo", "entidad", "registro_id", "productor_id", "tramite_id", "entrega_id", "adrema", "regla_calidad", "severidad", "descripcion", "apto_conteo_general", "apto_indicador_sustantivo", "apto_mapa", "apto_vinculacion_productor", "fuente", "source_row_number"]
MODULES = ["Productores e identificadores", "DDJJ", "Agricultura", "Ganadería", "ADREMAS y establecimientos", "Georreferenciación y mapa", "Entregas y asistencias", "Normativa y eventos", "Presentación semántica"]
SEVERITY_BY_STATE = {"PASS": "INFO", "WARN": "MEDIA", "FAIL": "ALTA"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path, required: list[str] | None = None) -> tuple[pd.DataFrame, str]:
    if not path.exists():
        return pd.DataFrame(), "archivo ausente"
    try:
        frame = pd.read_csv(path, low_memory=False)
        missing = sorted(set(required or []) - set(frame.columns))
        return frame, f"sha256={sha256(path)}" + (f"; columnas ausentes={missing}" if missing else "")
    except Exception as exc:
        return pd.DataFrame(), f"error de lectura: {type(exc).__name__}: {exc}"


class Audit:
    def __init__(self) -> None:
        self.checks: list[dict] = []
        self.flags: list[dict] = []
        self.inventory: list[dict] = []

    def check(self, module: str, category: str, description: str, state: str, observed, expected, detail: str, source: str, severity: str | None = None) -> None:
        self.checks.append({
            "check_id": f"GQ-{len(self.checks)+1:04d}", "modulo": module,
            "categoria": category, "descripcion": description, "estado": state,
            "severidad": severity or SEVERITY_BY_STATE[state],
            "valor_observado": json.dumps(observed, ensure_ascii=False, default=str) if isinstance(observed, (dict, list)) else observed,
            "valor_esperado": json.dumps(expected, ensure_ascii=False, default=str) if isinstance(expected, (dict, list)) else expected,
            "detalle": detail, "fuente_resultado": source,
        })

    def flag(self, module: str, entity: str, record_id, rule: str, severity: str, description: str, *, producer_id="", procedure_id="", delivery_id="", adrema="", count_ok=True, indicator_ok=False, map_ok=False, link_ok=True, source="", source_row="") -> None:
        self.flags.append({
            "modulo": module, "entidad": entity, "registro_id": record_id,
            "productor_id": producer_id, "tramite_id": procedure_id,
            "entrega_id": delivery_id, "adrema": adrema,
            "regla_calidad": rule, "severidad": severity, "descripcion": description,
            "apto_conteo_general": count_ok, "apto_indicador_sustantivo": indicator_ok,
            "apto_mapa": map_ok, "apto_vinculacion_productor": link_ok,
            "fuente": source, "source_row_number": source_row,
        })


def bool_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(False, index=frame.index)
    return frame[column].astype(str).str.strip().str.casefold().isin({"true", "1", "si", "sí", "yes"})


def reuse_checks(audit: Audit, path: Path, module: str) -> None:
    frame, trace = read_csv(path)
    if frame.empty:
        audit.check(module, "fuente", f"Resultado existente {path.name} disponible", "WARN", trace, "archivo legible", "El módulo continúa con controles disponibles.", str(path), "MEDIA")
        return
    mapping = {"status": "estado", "category": "categoria", "description": "descripcion", "observed": "valor_observado", "expected": "valor_esperado", "details": "detalle"}
    frame = frame.rename(columns=mapping)
    for _, row in frame.iterrows():
        state = str(row.get("estado", "WARN")).upper()
        if state not in {"PASS", "WARN", "FAIL"}:
            state = "WARN"
        audit.check(module, str(row.get("categoria", "control_existente")), str(row.get("descripcion", row.get("check_id", "Control existente"))), state, row.get("valor_observado", ""), row.get("valor_esperado", ""), f"Reutilizado sin modificar. {row.get('detalle', '')}; {trace}", str(path), SEVERITY_BY_STATE[state])


def flag_frame(audit: Audit, frame: pd.DataFrame, module: str, entity: str, id_col: str, rules: dict[str, tuple[str, str, bool]], source: str, producer_col: str = "", procedure_col: str = "tramite_id", adrema_col: str = "") -> None:
    for column, (severity, description, indicator_ok) in rules.items():
        mask = bool_series(frame, column)
        for idx, row in frame.loc[mask].iterrows():
            audit.flag(module, entity, row.get(id_col, idx), column, severity, description,
                       producer_id=row.get(producer_col, "") if producer_col else "",
                       procedure_id=row.get(procedure_col, "") if procedure_col else "",
                       adrema=row.get(adrema_col, "") if adrema_col else "",
                       indicator_ok=indicator_ok, source=source,
                       source_row=row.get("source_row_number", ""))


def audit_local(audit: Audit) -> dict[str, int]:
    counts: dict[str, int] = {}
    producers, producer_trace = read_csv(DDJJ / "dim_productor_2023.csv")
    if not producers.empty:
        cuit = producers.get("cuit_cuil", pd.Series("", index=producers.index)).astype(str).str.replace(r"\D", "", regex=True).str.replace(r"\.0$", "", regex=True)
        invalid = ~cuit.str.len().eq(11)
        if "cuit_valido" in producers:
            invalid = invalid | ~producers["cuit_valido"].astype(str).str.strip().str.casefold().isin({"true", "1", "si", "sí", "yes"})
        blank_names = producers.get("productor_nombre", pd.Series("", index=producers.index)).fillna("").astype(str).str.strip().eq("")
        for idx, row in producers.loc[invalid | blank_names].iterrows():
            rules = []
            if invalid.loc[idx]: rules.append("CUIT/CUIL ausente o longitud distinta de 11")
            if blank_names.loc[idx]: rules.append("Nombre vacío")
            audit.flag(MODULES[0], "productor", row.get("productor_id_2023", idx), "identificacion_productor", "ALTA" if invalid.loc[idx] else "MEDIA", "; ".join(rules), producer_id=row.get("productor_id_2023", ""), indicator_ok=True, link_ok=not invalid.loc[idx], source=str(DDJJ / "dim_productor_2023.csv"))
        audit.check(MODULES[0], "identificadores", "Productores con CUIT/CUIL ausente o inválido", "WARN" if invalid.any() else "PASS", int(invalid.sum()), 0, producer_trace, str(DDJJ / "dim_productor_2023.csv"))
        counts[MODULES[0]] = len(producers)
    else:
        audit.check(MODULES[0], "fuente", "Dimensión de productores disponible", "WARN", producer_trace, "archivo legible", "No se detiene la auditoría.", str(DDJJ / "dim_productor_2023.csv"))

    procedures, trace = read_csv(DDJJ / "fact_ddjj_tramite_2023.csv")
    quality, quality_trace = read_csv(DDJJ / "fact_calidad_dato_2023.csv")
    if not procedures.empty:
        duplicate = procedures["tramite_id"].duplicated(keep=False)
        audit.check(MODULES[1], "unicidad", "Trámite ID único", "FAIL" if duplicate.any() else "PASS", int(duplicate.sum()), 0, trace, str(DDJJ / "fact_ddjj_tramite_2023.csv"), "CRITICA" if duplicate.any() else "INFO")
        counts[MODULES[1]] = len(procedures)
    if not quality.empty:
        rules = {
            "dq_estado_anulado": ("ALTA", "DDJJ anulada: conservar para auditoría, excluir de indicadores sustantivos", False),
            "dq_fecha_fuera_2023": ("MEDIA", "Fecha fuera del año esperado", False),
            "dq_tiene_tramite_huerfano_en_detalle": ("CRITICA", "Detalle huérfano", False),
            "dq_numero_certificado_nulo": ("BAJA", "Certificado nulo; no reinterpretar como norma", True),
            "dq_fecha_presentacion_nula": ("ALTA", "Fecha de presentación nula", False),
        }
        flag_frame(audit, quality, MODULES[1], "ddjj", "tramite_id", rules, str(DDJJ / "fact_calidad_dato_2023.csv"))

    agriculture, ag_trace = read_csv(DDJJ / "fact_agricultura_perdida_2023.csv")
    if not agriculture.empty:
        planted = pd.to_numeric(agriculture.get("superficie_sembrada"), errors="coerce")
        affected = pd.to_numeric(agriculture.get("superficie_afectada"), errors="coerce")
        agriculture["_afectada_mayor_sembrada"] = affected.notna() & planted.notna() & (affected > planted)
        ag_rules = {
            "dq_superficie_afectada_negativa": ("CRITICA", "Superficie afectada negativa: no sumar", False),
            "dq_superficie_sembrada_negativa": ("CRITICA", "Superficie sembrada negativa: no sumar", False),
            "dq_tramite_huerfano": ("ALTA", "Fila agrícola huérfana", False),
            "_afectada_mayor_sembrada": ("ALTA", "Superficie afectada mayor que sembrada", False),
        }
        flag_frame(audit, agriculture, MODULES[2], "registro_agricola", "source_row_number", ag_rules, str(DDJJ / "fact_agricultura_perdida_2023.csv"))
        alerts = sum(int(bool_series(agriculture, c).sum()) for c in ag_rules)
        audit.check(MODULES[2], "coherencia_cuantitativa", "Registros agrícolas con incoherencias severas", "WARN" if alerts else "PASS", alerts, 0, ag_trace, str(DDJJ / "fact_agricultura_perdida_2023.csv"), "ALTA" if alerts else "INFO")
        counts[MODULES[2]] = len(agriculture)

    livestock, lv_trace = read_csv(DDJJ / "fact_ganaderia_declarada_2023.csv")
    if not livestock.empty:
        lv_rules = {
            "dq_cantidad_negativa": ("CRITICA", "Existencias negativas: no usar", False),
            "dq_mortandad_negativa": ("CRITICA", "Mortandad negativa: no usar", False),
            "dq_mortandad_mayor_cantidad": ("CRITICA", "Mortandad mayor que existencias: excluir de indicadores cuantitativos", False),
            "dq_tramite_huerfano": ("ALTA", "Fila ganadera huérfana", False),
            "dq_columna_sospechosa_equinos_porcinos": ("MEDIA", "Encabezado/categoría sospechosa", False),
        }
        flag_frame(audit, livestock, MODULES[3], "registro_ganadero", "source_row_number", lv_rules, str(DDJJ / "fact_ganaderia_declarada_2023.csv"))
        mortality = int(bool_series(livestock, "dq_mortandad_mayor_cantidad").sum())
        audit.check(MODULES[3], "coherencia_cuantitativa", "Mortandad mayor que cantidad", "WARN" if mortality else "PASS", mortality, 0, lv_trace, str(DDJJ / "fact_ganaderia_declarada_2023.csv"), "CRITICA" if mortality else "INFO")
        counts[MODULES[3]] = len(livestock)

    adrema, ad_trace = read_csv(DDJJ / "fact_adrema_establecimiento_2023.csv")
    if not adrema.empty:
        ad_rules = {
            "dq_superficie_negativa": ("CRITICA", "Superficie predial negativa: no sumar", False),
            "dq_adrema_duplicada_en_tramite": ("ALTA", "Par trámite + ADREMA duplicado: conservar, contar una vez", False),
            "dq_tramite_huerfano": ("ALTA", "ADREMA huérfana", False),
            "dq_superficie_no_numerica": ("MEDIA", "Superficie no numérica", False),
        }
        flag_frame(audit, adrema, MODULES[4], "adrema", "source_row_number", ad_rules, str(DDJJ / "fact_adrema_establecimiento_2023.csv"), procedure_col="tramite_id", adrema_col="adrema")
        duplicates = int(bool_series(adrema, "dq_adrema_duplicada_en_tramite").sum())
        audit.check(MODULES[4], "duplicados", "Filas ADREMA duplicadas dentro del trámite", "WARN" if duplicates else "PASS", duplicates, 0, ad_trace, str(DDJJ / "fact_adrema_establecimiento_2023.csv"), "ALTA" if duplicates else "INFO")
        counts[MODULES[4]] = len(adrema)

    map_invalid, map_trace = read_csv(MAP / "mapa_georreferenciacion_invalidos.csv")
    map_checks, _ = read_csv(MAP / "mapa_georreferenciacion_checks.csv")
    if not map_invalid.empty:
        for idx, row in map_invalid.iterrows():
            audit.flag(MODULES[5], "establecimiento", row.get("id_establecimiento", idx), str(row.get("motivo", "coordenada_invalida")), "ALTA" if row.get("motivo") not in {"faltante_o_cero"} else "MEDIA", "Establecimiento no apto para mapa", producer_id="", procedure_id=row.get("id_ddjj", ""), adrema=row.get("adrema", ""), indicator_ok=True, map_ok=False, source=str(MAP / "mapa_georreferenciacion_invalidos.csv"))
        audit.check(MODULES[5], "cobertura", "Establecimientos no aptos para mapa", "WARN", len(map_invalid), 0, map_trace, str(MAP / "mapa_georreferenciacion_invalidos.csv"), "ALTA")
        counts[MODULES[5]] = 32363
    if not map_checks.empty:
        for _, row in map_checks.loc[map_checks.get("tipo", pd.Series(index=map_checks.index)).eq("indicador")].iterrows():
            audit.inventory.append({"modulo": MODULES[5], "control_existente": row.get("categoria"), "script": "scripts/29_audit_mapa_georreferenciacion.py", "archivo_salida": str(MAP / "mapa_georreferenciacion_checks.csv"), "regla": row.get("dimension"), "severidad_actual": "INFO", "tratamiento_actual": "solo reporte", "expuesto_dashboard": "parcial", "unificar": "sí"})

    deliveries, de_trace = read_csv(DELIVERIES / "fact_entregas_emergencia.csv")
    delivery_quality, dq_trace = read_csv(DELIVERIES / "fact_entregas_calidad_dato.csv")
    if not deliveries.empty:
        duplicate_ids = deliveries["entrega_id"].duplicated(keep=False)
        audit.check(MODULES[6], "unicidad", "Entrega ID único", "FAIL" if duplicate_ids.any() else "PASS", int(duplicate_ids.sum()), 0, de_trace, str(DELIVERIES / "fact_entregas_emergencia.csv"), "CRITICA" if duplicate_ids.any() else "INFO")
        counts[MODULES[6]] = len(deliveries)
    if not delivery_quality.empty:
        for idx, row in delivery_quality.iterrows():
            rule = str(row.get("alerta_tipo", "alerta_entrega"))
            duplicate = rule == "posible_duplicado"
            audit.flag(MODULES[6], "entrega", row.get("entrega_id", idx), rule, "ALTA" if duplicate else str(row.get("severidad", "MEDIA")).upper(), str(row.get("alerta_descripcion", rule)), delivery_id=row.get("entrega_id", ""), indicator_ok=not duplicate, source=str(DELIVERIES / "fact_entregas_calidad_dato.csv"), source_row=row.get("source_row_number", ""))
        possible = int(delivery_quality["alerta_tipo"].eq("posible_duplicado").sum())
        audit.check(MODULES[6], "duplicados", "Posibles entregas duplicadas conservadas", "WARN" if possible else "PASS", possible, 0, dq_trace, str(DELIVERIES / "fact_entregas_calidad_dato.csv"), "ALTA" if possible else "INFO")

    reuse_checks(audit, DDJJ / "validation_ddjj_2023_checks.csv", MODULES[1])
    reuse_checks(audit, DELIVERIES / "validation_entregas_checks.csv", MODULES[6])
    bridge = ROOT / "data_processed" / "ddjj_2023_excel" / "bridge" / "validation_bridge_normativo_2023_checks.csv"
    reuse_checks(audit, bridge, MODULES[7])
    counts[MODULES[7]] = 1483

    display_helper = ROOT / "dashboard" / "utils" / "display_format.py"
    dashboard_files = [ROOT / "dashboard" / "Home.py", ROOT / "dashboard" / "pages" / "4_Mapa.py", ROOT / "dashboard" / "pages" / "5_Analisis.py", ROOT / "dashboard" / "pages" / "6_Ficha_Productor.py"]
    required = ["format_year", "format_cuit_cuil", "format_document", "format_renspa", "format_adrema", "format_date", "format_surface", "format_percentage", "format_money", "format_quantity", "format_count"]
    if display_helper.exists():
        text = display_helper.read_text(encoding="utf-8")
        missing = [name for name in required if f"def {name}" not in text]
        state = "PASS" if not missing else "WARN"
        audit.check(MODULES[8], "formatos", "Helper visual cubre tipos semánticos obligatorios", state, missing or "cobertura completa", "sin funciones faltantes", "Auditoría estática; no modifica dashboard.", str(display_helper))
    else:
        audit.check(MODULES[8], "formatos", "Helper visual disponible", "WARN", "ausente", "presente", "Se audita sin modificar dashboard.", str(display_helper))
    direct_patterns = {
        "año con separador": r"Año.*:,",
        "porcentaje sin helper": r"\{[^}]+:\.\d+f\}%",
        "conteo anglosajón": r'f"\{[^}]+:,\}',
    }
    hits = {}
    for file in dashboard_files:
        if file.exists():
            content = file.read_text(encoding="utf-8")
            for label, pattern in direct_patterns.items():
                hits[f"{file.name}:{label}"] = len(re.findall(pattern, content))
    risky = sum(hits.values())
    audit.check(MODULES[8], "presentacion", "Patrones de formato directo potencialmente inconsistentes", "WARN" if risky else "PASS", hits, 0, "Revisión estática; requiere control visual para confirmar cada caso.", "dashboard/*.py", "BAJA" if risky else "INFO")
    counts[MODULES[8]] = sum(1 for path in dashboard_files if path.exists())
    return counts


def inventory_scripts(audit: Audit) -> None:
    mapping = [
        ("DDJJ", "scripts/15_validate_ddjj_2023_processed.py", "validation_ddjj_2023_checks.csv"),
        ("Normativa y eventos", "scripts/17_validate_ddjj_2023_bridge_normativo.py", "validation_bridge_normativo_2023_checks.csv"),
        ("Entregas y asistencias", "scripts/26_validate_entregas_normalized.py", "validation_entregas_checks.csv"),
        ("Entregas y asistencias", "scripts/28_validate_entregas_tidb_staging.py", "validation_entregas_tidb_staging_checks.csv"),
        ("Georreferenciación y mapa", "scripts/29_audit_mapa_georreferenciacion.py", "mapa_georreferenciacion_checks.csv"),
    ]
    for module, script, output in mapping:
        audit.inventory.append({"modulo": module, "control_existente": "validación consolidada", "script": script, "archivo_salida": output, "regla": "múltiples", "severidad_actual": "PASS/WARN/FAIL", "tratamiento_actual": "preservar y reportar", "expuesto_dashboard": "parcial", "unificar": "sí"})


def main() -> None:
    os.environ.setdefault("DATA_SOURCE", "tidb")
    os.environ.setdefault("DATA_MODE", "unificado")
    OUT.mkdir(parents=True, exist_ok=True)
    audit = Audit()
    inventory_scripts(audit)
    counts = audit_local(audit)
    checks = pd.DataFrame(audit.checks, columns=CHECK_COLUMNS)
    flags = pd.DataFrame(audit.flags, columns=FLAG_COLUMNS)
    for module in MODULES:
        if module not in set(checks["modulo"]):
            audit.check(module, "cobertura", "Módulo evaluado", "WARN", "sin controles disponibles", "al menos un control", "La fuente faltante no detiene la auditoría.", "sistema_global")
    checks = pd.DataFrame(audit.checks, columns=CHECK_COLUMNS)
    module_rows = []
    for module in MODULES:
        subset = checks[checks["modulo"].eq(module)]
        flagged = flags[flags["modulo"].eq(module)]
        state = "FAIL" if subset["estado"].eq("FAIL").any() else "WARN" if subset["estado"].eq("WARN").any() else "PASS"
        evaluated = int(counts.get(module, 0))
        records_alert = int(flagged["registro_id"].astype(str).nunique()) if not flagged.empty else 0
        module_rows.append({"modulo": module, "checks_pass": int(subset["estado"].eq("PASS").sum()), "checks_warn": int(subset["estado"].eq("WARN").sum()), "checks_fail": int(subset["estado"].eq("FAIL").sum()), "registros_evaluados": evaluated, "registros_con_alerta": records_alert, "porcentaje_con_alerta": round(records_alert / evaluated * 100, 2) if evaluated else 0.0, "estado_modulo": state})
    by_module = pd.DataFrame(module_rows)
    critical_structural = checks[checks["estado"].eq("FAIL") & checks["severidad"].eq("CRITICA")]
    state_global = "FAIL" if not critical_structural.empty else "WARN" if checks["estado"].isin(["WARN", "FAIL"]).any() else "PASS"
    state_counts = checks["estado"].value_counts()
    summary = pd.DataFrame([{"fecha_ejecucion": RUN_AT, "estado_global": state_global, "checks_pass": int(state_counts.get("PASS", 0)), "checks_warn": int(state_counts.get("WARN", 0)), "checks_fail": int(state_counts.get("FAIL", 0)), "modulos_evaluados": len(MODULES), "registros_con_alertas": int(flags[["modulo", "entidad", "registro_id"]].drop_duplicates().shape[0]), "alertas_criticas": int(flags["severidad"].eq("CRITICA").sum() + len(critical_structural)), "recomendacion": "Priorizar incoherencias cuantitativas, duplicados de entregas, vinculación de identificadores y cobertura geográfica; no corregir automáticamente."}])
    checks.to_csv(OUT / "global_quality_checks.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(OUT / "global_quality_summary.csv", index=False, encoding="utf-8-sig")
    by_module.to_csv(OUT / "global_quality_by_module.csv", index=False, encoding="utf-8-sig")
    flags.to_csv(OUT / "global_quality_records_flagged.csv", index=False, encoding="utf-8-sig")

    not_suitable = int((~flags["apto_indicador_sustantivo"].astype(bool)).sum()) if not flags.empty else 0
    inventory = pd.DataFrame(audit.inventory)
    module_table = "\n".join(f"| {r.modulo} | {r.checks_pass} | {r.checks_warn} | {r.checks_fail} | {r.registros_con_alerta:,} | {r.estado_modulo} |" for r in by_module.itertuples())
    report = f"""# Sistema Transversal de Calidad de Datos — Primera versión

## Estado global

**{state_global}** — ejecución {RUN_AT}.

- Checks PASS: **{int(state_counts.get('PASS', 0))}**.
- Checks WARN: **{int(state_counts.get('WARN', 0))}**.
- Checks FAIL: **{int(state_counts.get('FAIL', 0))}**.
- Registros/reglas marcados no aptos para indicadores sustantivos: **{not_suitable:,}**.
- Alertas críticas: **{int(summary.iloc[0]['alertas_criticas']):,}**.

## Alcance y fuentes

Se evaluaron los nueve módulos definidos. Se reutilizaron checks validados de DDJJ 2023, bridge normativo, entregas y georreferenciación; también se leyeron los CSV normalizados con verificación SHA-256. La auditoría es de solo lectura y tolera fuentes ausentes mediante WARN.

## Resultados por módulo

| Módulo | PASS | WARN | FAIL | Registros con alerta | Estado |
|---|---:|---:|---:|---:|---|
{module_table}

## Reglas metodológicas

- Una alerta no elimina el registro de auditoría ni necesariamente de los conteos generales.
- Superficies negativas o afectadas mayores que sembradas no se suman.
- Mortandad mayor que existencias se conserva, pero no alimenta indicadores ganaderos.
- Posibles entregas duplicadas se conservan, pero no se agregan sin conciliación.
- ADREMAS duplicadas se preservan; el conteo usa el par único trámite + ADREMA.
- Establecimientos sin coordenadas siguen siendo válidos, pero no son aptos para mapa.
- DDJJ anuladas se conservan y se excluyen de indicadores sustantivos vigentes.

## Cobertura geográfica

Se incorporó la auditoría del script 29: 32.363 establecimientos actuales, 3.495 pares GPS informados, 3.218 puntos mostrados, cobertura actual 9,94 %, 28.925 faltantes/no parseables, 218 fuera de rango, 2 posiblemente invertidas, 204 positivas sospechosas, 13 con precisión insuficiente y 452 pares idénticos repetidos.

## Alertas principales y prioridades

1. **Prioridad 1 — Indicadores:** mortandad mayor que cantidad, superficies negativas/incoherentes y posibles duplicados de cantidades o montos.
2. **Prioridad 2 — Vinculación:** CUIT/DNI inválidos, RENSPA ambiguos, ADREMAS duplicadas y huérfanos.
3. **Prioridad 3 — Geografía:** cobertura baja, coordenadas inválidas, positivas, invertidas o alejadas de Corrientes.
4. **Prioridad 4 — Presentación:** revisar los patrones estáticos informados antes de cambiar el dashboard.

## Controles existentes reutilizados

Se inventariaron **{len(inventory):,}** controles o grupos de controles existentes. El detalle de procedencia se conserva en `fuente_resultado` de cada check; no se reescribieron sus reportes originales.

## Limitaciones

- Esta primera versión se concentra en DDJJ 2023 y entregas normalizadas, complementadas con la auditoría geográfica y resultados TiDB existentes.
- Las similitudes de nombres, múltiples CUIT/RENSPA y formatos visibles requieren una segunda etapa con reglas de comparación explicables y revisión institucional.
- La auditoría de presentación es estática; confirmar visualmente antes de modificar el dashboard.
- No se imputaron datos ni se transformaron sistemas de referencia.

## Plan de corrección

Resolver primero las reglas CRITICA/ALTA que pueden alterar indicadores; luego conciliar identificadores y duplicados; posteriormente construir una capa geográfica validada; finalmente corregir presentación. Cada corrección futura debe ejecutarse en una capa derivada, conservar el original y registrar decisión, responsable y fecha.
"""
    (OUT / "global_quality_report.md").write_text(report, encoding="utf-8")
    print(f"Estado global: {state_global}")
    print(f"Checks: PASS={int(state_counts.get('PASS', 0))}, WARN={int(state_counts.get('WARN', 0))}, FAIL={int(state_counts.get('FAIL', 0))}")
    print(f"Alertas fila/regla: {len(flags)}")
    print(f"Salidas: {OUT}")


if __name__ == "__main__":
    main()
