"""Avaliações temporais e de drift em relação a um CSV de referência."""

from typing import TypeAlias
import warnings

import pandas as pd
from evidently import Report
from evidently.presets import DataDriftPreset

from deep_research.models import DataQualityColumnProfile

from .core import AnalysisContext, ParsedTable, is_missing, parse_number

ColumnData: TypeAlias = list[float | None] | list[str | None]


def _build_frames(current: ParsedTable, reference: ParsedTable, profiles: list[DataQualityColumnProfile]) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    """Prepara colunas numéricas e categóricas comparáveis para o Evidently."""
    current_indexes = {name: index for index, name in enumerate(current.headers)}
    reference_indexes = {name: index for index, name in enumerate(reference.headers)}
    current_data: dict[str, ColumnData] = {}
    reference_data: dict[str, ColumnData] = {}
    column_types: dict[str, str] = {}
    for profile in profiles:
        name = profile.name
        if name not in reference_indexes:
            continue
        current_values = [row.values[current_indexes[name]] for row in current.rows]
        reference_values = [row.values[reference_indexes[name]] for row in reference.rows]
        if profile.inferred_type == "numerico":
            current_numbers = [None if is_missing(value) else parse_number(value) for value in current_values]
            reference_numbers = [None if is_missing(value) else parse_number(value) for value in reference_values]
            if sum(value is not None for value in current_numbers) < 5 or sum(value is not None for value in reference_numbers) < 5:
                continue
            current_data[name], reference_data[name], column_types[name] = current_numbers, reference_numbers, "numerico"
            continue
        if profile.inferred_type not in {"texto", "booleano"}:
            continue
        current_categories = [None if is_missing(value) else value for value in current_values]
        reference_categories = [None if is_missing(value) else value for value in reference_values]
        combined_categories = {value for value in current_categories if value is not None} | {value for value in reference_categories if value is not None}
        if len(combined_categories) < 2 or len(combined_categories) > 50 or sum(value is not None for value in current_categories) < 5 or sum(value is not None for value in reference_categories) < 5:
            continue
        current_data[name], reference_data[name], column_types[name] = current_categories, reference_categories, "categorico"
    return pd.DataFrame(current_data), pd.DataFrame(reference_data), column_types


def _check_distribution(current: ParsedTable, reference: ParsedTable, profiles: list[DataQualityColumnProfile], context: AnalysisContext) -> None:
    """Executa o preset de drift e converte testes reprovados em achados."""
    current_frame, reference_frame, column_types = _build_frames(current, reference, profiles)
    if not column_types:
        return
    report = Report([DataDriftPreset(columns=list(column_types))], include_tests=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        snapshot = report.run(current_frame, reference_frame)
    payload = snapshot.dict()
    metrics_by_id = {metric.get("id"): metric for metric in payload.get("metrics", []) if isinstance(metric, dict)}
    current_indexes = {name: index for index, name in enumerate(current.headers)}
    reference_indexes = {name: index for index, name in enumerate(reference.headers)}
    for test in payload.get("tests", []):
        if not isinstance(test, dict) or test.get("status") != "FAIL":
            continue
        metric_config = test.get("metric_config", {})
        params = metric_config.get("params", {})
        if not str(params.get("type", "")).endswith("ValueDrift"):
            continue
        column = str(params.get("column", ""))
        if column not in column_types:
            continue
        metric = metrics_by_id.get(metric_config.get("metric_id"), {})
        score = metric.get("value") if isinstance(metric, dict) else None
        method, threshold = str(params.get("method", "desconhecido")), params.get("threshold")
        evidence: list[str] = []
        if column_types[column] == "categorico":
            current_values = {row.values[current_indexes[column]] for row in current.rows if not is_missing(row.values[current_indexes[column]])}
            reference_values = {row.values[reference_indexes[column]] for row in reference.rows if not is_missing(row.values[reference_indexes[column]])}
            evidence = [f"nova categoria: {value}" for value in sorted(current_values - reference_values)]
        context.add_finding(
            dimension="comportamento_temporal", severity="media", confidence=0.85,
            scope=f"coluna:{column}", title=f"Drift de distribuição em {column}",
            description=f"O Evidently classificou a distribuição da coluna como diferente da referência usando o método {method}.",
            evidence=evidence,
            metrics={"validation_engine": "evidently", "column_type": column_types[column], "drift_method": method, "drift_score": score, "drift_threshold": threshold, "test_status": test.get("status")},
            recommendation="Investigar mudança de população, processo, unidade ou coleta antes de classificar os dados como incorretos.",
            limitations="Drift indica diferença estatística, não erro. O resultado depende do tamanho, representatividade e comparabilidade das amostras.",
        )


def check_drift(current: ParsedTable, reference: ParsedTable, current_profiles: list[DataQualityColumnProfile], context: AnalysisContext) -> None:
    """Combina mudanças objetivas com drift estatístico do Evidently."""
    context.evaluated_dimensions.add("comportamento_temporal")
    reference_indexes = {name: index for index, name in enumerate(reference.headers)}
    for current_index, name in enumerate(current.headers):
        if name not in reference_indexes:
            context.add_finding(
                dimension="comportamento_temporal", severity="media", confidence=1.0,
                scope=f"coluna:{name}", title=f"Nova coluna no conjunto atual: {name}",
                description="A coluna não existe no arquivo de referência.",
                recommendation="Confirmar se a mudança de esquema foi planejada e atualizar o contrato.",
            )
            continue
        reference_index = reference_indexes[name]
        current_values = [row.values[current_index] for row in current.rows]
        reference_values = [row.values[reference_index] for row in reference.rows]
        current_missing = sum(is_missing(value) for value in current_values) / len(current_values)
        reference_missing = sum(is_missing(value) for value in reference_values) / len(reference_values)
        missing_delta = current_missing - reference_missing
        if abs(missing_delta) >= 0.10:
            context.add_finding(
                dimension="comportamento_temporal", severity="media" if abs(missing_delta) < 0.30 else "alta", confidence=0.95,
                scope=f"coluna:{name}", title=f"Mudança na ausência de valores em {name}",
                description="A taxa de ausência mudou pelo menos 10 pontos percentuais em relação à referência.",
                metrics={"current_missing_percentage": round(current_missing * 100, 2), "reference_missing_percentage": round(reference_missing * 100, 2), "delta_percentage_points": round(missing_delta * 100, 2)},
                recommendation="Verificar alterações na coleta, origem ou regra de preenchimento.",
                limitations="A referência é considerada comparável; sazonalidade não é ajustada automaticamente.",
            )
    for name in sorted(set(reference.headers) - set(current.headers)):
        context.add_finding(
            dimension="comportamento_temporal", severity="alta", confidence=1.0,
            scope=f"coluna:{name}", title=f"Coluna ausente no conjunto atual: {name}",
            description="Uma coluna existente na referência não aparece no arquivo atual.",
            recommendation="Confirmar se a remoção foi planejada e avaliar consumidores afetados.",
        )
    _check_distribution(current, reference, current_profiles, context)
