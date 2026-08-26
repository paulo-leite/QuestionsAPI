"""Perfilamento agregado de colunas com Evidently e fallback nativo."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import statistics
from typing import Protocol
import warnings

import pandas as pd
from evidently import DataDefinition, Dataset, Report
from evidently.presets import DataSummaryPreset

from deep_research.models import DataQualityColumnProfile, DataQualityTopValue

from .core import (
    AnalysisContext,
    ParsedTable,
    TYPE_CONFIDENCE_THRESHOLD,
    is_missing,
    parse_date,
    parse_number,
    round_percentage,
    value_kind,
)


@dataclass(frozen=True)
class ProfilingResult:
    """Perfis calculados e motor que efetivamente produziu as métricas."""

    profiles: list[DataQualityColumnProfile]
    engine: str


class DatasetProfiler(Protocol):
    """Contrato interno para motores capazes de perfilar uma tabela."""

    def profile(self, table: ParsedTable) -> list[DataQualityColumnProfile]:
        """Produz um perfil estável para cada coluna da tabela."""
        ...


class NativeDatasetProfiler:
    """Calcula métricas exatas e preserva as convenções locais de parsing."""

    def profile(self, table: ParsedTable) -> list[DataQualityColumnProfile]:
        """Produz perfis exatos usando somente estruturas e estatísticas nativas."""
        return [self._profile_column(table, index) for index in range(len(table.headers))]

    @staticmethod
    def _profile_column(table: ParsedTable, index: int) -> DataQualityColumnProfile:
        """Calcula o perfil nativo de uma única coluna."""
        name = table.headers[index]
        values = [row.values[index] for row in table.rows]
        present = [value for value in values if not is_missing(value)]
        missing_count = len(values) - len(present)
        value_counts = Counter(present)

        kinds = Counter(value_kind(value) for value in present)
        inferred_type, type_confidence = "vazia", 0.0
        if present:
            dominant_kind, dominant_count = kinds.most_common(1)[0]
            type_confidence = dominant_count / len(present)
            inferred_type = (
                dominant_kind
                if type_confidence >= TYPE_CONFIDENCE_THRESHOLD
                else "mista"
            )

        numeric_values: list[float] = []
        if inferred_type == "numerico":
            numeric_values = [
                parsed
                for value in present
                if (parsed := parse_number(value)) is not None
            ]
        profile = DataQualityColumnProfile(
            name=name,
            inferred_type=inferred_type,
            type_confidence=round(type_confidence, 3),
            non_missing_count=len(present),
            missing_count=missing_count,
            missing_percentage=round_percentage(missing_count, len(values)),
            distinct_count=len(value_counts),
            distinct_percentage=round_percentage(len(value_counts), len(present)),
            top_values=[
                DataQualityTopValue(
                    value=value,
                    count=count,
                    percentage=round_percentage(count, len(present)),
                )
                for value, count in value_counts.most_common(5)
            ],
        )
        if numeric_values:
            profile.minimum = round(min(numeric_values), 6)
            profile.maximum = round(max(numeric_values), 6)
            profile.mean = round(statistics.fmean(numeric_values), 6)
            profile.median = round(statistics.median(numeric_values), 6)
            profile.standard_deviation = round(
                statistics.pstdev(numeric_values), 6
            )
        elif inferred_type == "data":
            dates = [
                parsed
                for value in present
                if (parsed := parse_date(value)) is not None
            ]
            if dates:
                profile.minimum = min(dates).isoformat()
                profile.maximum = max(dates).isoformat()
        return profile


class EvidentlyDatasetProfiler:
    """Adapta o DataSummaryPreset ao contrato de perfil público da aplicação."""

    def __init__(self, native_profiler: DatasetProfiler | None = None) -> None:
        """Inicializa o adaptador com o provedor das semânticas locais."""
        self._native_profiler = native_profiler or NativeDatasetProfiler()

    def profile(self, table: ParsedTable) -> list[DataQualityColumnProfile]:
        """Combina tipos locais com métricas agregadas calculadas pelo Evidently."""
        profiles = self._native_profiler.profile(table)
        dataset = self._build_dataset(table, profiles)
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=r"Starting with pandas version 4\.0",
                category=DeprecationWarning,
                module=r"evidently\..*",
            )
            payload = Report([DataSummaryPreset()]).run(dataset, None).dict()
        metrics = self._index_metrics(payload.get("metrics", []))
        for profile in profiles:
            self._apply_metrics(profile, metrics)
        return profiles

    @staticmethod
    def _build_dataset(
        table: ParsedTable,
        profiles: list[DataQualityColumnProfile],
    ) -> Dataset:
        """Normaliza valores e declara explicitamente os tipos usados no relatório."""
        indexes = {name: index for index, name in enumerate(table.headers)}
        data: dict[str, list[object | None]] = {}
        numerical: list[str] = []
        categorical: list[str] = []
        text: list[str] = []
        datetimes: list[str] = []
        unknown: list[str] = []
        for profile in profiles:
            name = profile.name
            raw_values = [row.values[indexes[name]] for row in table.rows]
            if profile.inferred_type == "numerico":
                data[name] = [
                    None if is_missing(value) else parse_number(value)
                    for value in raw_values
                ]
                numerical.append(name)
            elif profile.inferred_type == "data":
                data[name] = [
                    None if is_missing(value) else parse_date(value)
                    for value in raw_values
                ]
                datetimes.append(name)
            elif profile.inferred_type in {"texto", "booleano"}:
                data[name] = [
                    None if is_missing(value) else value
                    for value in raw_values
                ]
                if profile.distinct_percentage <= 50:
                    categorical.append(name)
                else:
                    text.append(name)
            else:
                data[name] = [
                    None if is_missing(value) else value
                    for value in raw_values
                ]
                unknown.append(name)
        frame = pd.DataFrame(data)
        definition = DataDefinition(
            numerical_columns=numerical,
            categorical_columns=categorical,
            text_columns=text,
            datetime_columns=datetimes,
            unknown_columns=unknown,
        )
        return Dataset.from_pandas(frame, data_definition=definition)

    @staticmethod
    def _index_metrics(metrics: list[dict]) -> dict[tuple[str, str | None, float | None], object]:
        """Indexa valores do snapshot por tipo, coluna e quantil."""
        indexed: dict[tuple[str, str | None, float | None], object] = {}
        for metric in metrics:
            config = metric.get("config", {})
            metric_type = str(config.get("type", "")).rsplit(":", 1)[-1]
            column = config.get("column")
            quantile = config.get("quantile")
            indexed[(metric_type, str(column) if column is not None else None, quantile)] = metric.get("value")
        return indexed

    @staticmethod
    def _apply_metrics(
        profile: DataQualityColumnProfile,
        metrics: dict[tuple[str, str | None, float | None], object],
    ) -> None:
        """Aplica métricas disponíveis sem alterar semânticas não equivalentes."""
        name = profile.name
        missing = metrics.get(("MissingValueCount", name, None))
        if isinstance(missing, dict):
            total_count = profile.non_missing_count + profile.missing_count
            count = int(float(missing.get("count", profile.missing_count)))
            profile.missing_count = count
            profile.non_missing_count = total_count - count
            profile.missing_percentage = round(float(missing.get("share", 0)) * 100, 2)

        if profile.inferred_type == "numerico":
            numeric_fields = {
                "minimum": "MinValue",
                "maximum": "MaxValue",
                "mean": "MeanValue",
            }
            for field_name, metric_type in numeric_fields.items():
                value = metrics.get((metric_type, name, None))
                if isinstance(value, (int, float)):
                    setattr(profile, field_name, round(float(value), 6))
            median = metrics.get(("QuantileValue", name, 0.5))
            if isinstance(median, (int, float)):
                profile.median = round(float(median), 6)

        categories = metrics.get(("UniqueValueCount", name, None))
        if isinstance(categories, dict):
            raw_counts = categories.get("counts", {})
            if isinstance(raw_counts, dict):
                counts = Counter(
                    {
                        str(value): int(float(count))
                        for value, count in raw_counts.items()
                        if float(count) > 0 and not is_missing(str(value))
                    }
                )
                profile.distinct_count = len(counts)
                profile.distinct_percentage = round_percentage(
                    len(counts), profile.non_missing_count
                )
                profile.top_values = [
                    DataQualityTopValue(
                        value=value,
                        count=count,
                        percentage=round_percentage(count, profile.non_missing_count),
                    )
                    for value, count in sorted(
                        counts.items(),
                        key=lambda item: (-item[1], item[0]),
                    )[:5]
                ]


def _check_completeness(
    table: ParsedTable,
    profiles: list[DataQualityColumnProfile],
    context: AnalysisContext,
    engine: str,
) -> None:
    """Converte métricas de ausência em achados com evidências por linha."""
    context.evaluated_dimensions.add("completude")
    indexes = {name: index for index, name in enumerate(table.headers)}
    for profile in profiles:
        if not profile.missing_count:
            continue
        missing_rows = [
            row.number
            for row in table.rows
            if is_missing(row.values[indexes[profile.name]])
        ]
        rate = profile.missing_count / len(table.rows)
        severity = "alta" if rate >= 0.50 else "media" if rate >= 0.10 else "baixa"
        context.add_finding(
            dimension="completude",
            severity=severity,
            confidence=1.0,
            scope=f"coluna:{profile.name}",
            title=f"Valores ausentes em {profile.name}",
            description=f"A coluna possui {profile.missing_count} valores ausentes em {len(table.rows)} registros.",
            evidence=[f"linha {row}" for row in missing_rows],
            metrics={
                "validation_engine": engine,
                "missing_count": profile.missing_count,
                "missing_percentage": profile.missing_percentage,
            },
            recommendation="Confirmar se o campo é obrigatório para o uso pretendido e, se for, corrigir a origem ou aplicar bloqueio na ingestão.",
            limitations="A análise trata vazio, null, none, n/a, na e nan como ausência; a obrigatoriedade depende do domínio.",
        )


def profile_columns(
    table: ParsedTable,
    context: AnalysisContext,
    profiler: DatasetProfiler | None = None,
) -> ProfilingResult:
    """Perfila o dataset uma vez e usa o motor nativo se o Evidently falhar."""
    selected = profiler or EvidentlyDatasetProfiler()
    engine = "evidently" if isinstance(selected, EvidentlyDatasetProfiler) else "native"
    try:
        profiles = selected.profile(table)
    except Exception as error:
        if profiler is not None:
            raise
        warnings.warn(
            f"Falha no perfilamento Evidently; usando fallback nativo: {error}",
            RuntimeWarning,
            stacklevel=2,
        )
        profiles = NativeDatasetProfiler().profile(table)
        engine = "native"
    _check_completeness(table, profiles, context, engine)
    return ProfilingResult(profiles=profiles, engine=engine)
