"""Perfilamento de colunas e avaliações univariadas de completude."""

from collections import Counter
import statistics
from typing import Literal

from deep_research.models import DataQualityColumnProfile, DataQualityTopValue

from .core import (
    AnalysisContext, ParsedTable, TYPE_CONFIDENCE_THRESHOLD, is_missing,
    parse_date, parse_number, percentile, round_percentage, value_kind,
)

MIN_OUTLIER_VALUES = 8


def profile_column(table: ParsedTable, index: int, context: AnalysisContext) -> DataQualityColumnProfile:
    """Perfila uma coluna e avalia completude, IQR e categorias raras."""
    name = table.headers[index]
    row_values = [(row.number, row.values[index]) for row in table.rows]
    present = [(row, value) for row, value in row_values if not is_missing(value)]
    missing = [(row, value) for row, value in row_values if is_missing(value)]
    value_counts = Counter(value for _, value in present)

    context.evaluated_dimensions.add("completude")
    if missing:
        rate = len(missing) / len(row_values)
        severity: Literal["baixa", "media", "alta"] = (
            "alta" if rate >= 0.50 else "media" if rate >= 0.10 else "baixa"
        )
        context.add_finding(
            dimension="completude", severity=severity, confidence=1.0,
            scope=f"coluna:{name}", title=f"Valores ausentes em {name}",
            description=f"A coluna possui {len(missing)} valores ausentes em {len(row_values)} registros.",
            evidence=[f"linha {row}" for row, _ in missing],
            metrics={"missing_count": len(missing), "missing_percentage": round(rate * 100, 2)},
            recommendation="Confirmar se o campo é obrigatório para o uso pretendido e, se for, corrigir a origem ou aplicar bloqueio na ingestão.",
            limitations="A análise trata vazio, null, none, n/a, na e nan como ausência; a obrigatoriedade depende do domínio.",
        )

    kinds = Counter(value_kind(value) for _, value in present)
    inferred_type, type_confidence = "vazia", 0.0
    if present:
        dominant_kind, dominant_count = kinds.most_common(1)[0]
        type_confidence = dominant_count / len(present)
        inferred_type = dominant_kind if type_confidence >= TYPE_CONFIDENCE_THRESHOLD else "mista"

    numeric_rows: list[tuple[int, float]] = []
    if inferred_type == "numerico":
        numeric_rows = [(row, parsed) for row, value in present if (parsed := parse_number(value)) is not None]
    numeric_values = [value for _, value in numeric_rows]
    outlier_rows: list[tuple[int, float]] = []
    if len(numeric_values) >= MIN_OUTLIER_VALUES and len(set(numeric_values)) >= 4:
        context.evaluated_dimensions.add("atipicidade")
        sorted_values = sorted(numeric_values)
        q1, q3 = percentile(sorted_values, 0.25), percentile(sorted_values, 0.75)
        iqr = q3 - q1
        if iqr > 0:
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            outlier_rows = [(row, value) for row, value in numeric_rows if value < lower or value > upper]
            if outlier_rows:
                context.add_finding(
                    dimension="atipicidade", severity="baixa", confidence=0.85,
                    scope=f"coluna:{name}", title=f"Valores atípicos em {name}",
                    description=f"Foram sinalizados {len(outlier_rows)} valores fora dos limites calculados pelo intervalo interquartil.",
                    evidence=[f"linha {row}: {value:g}" for row, value in outlier_rows],
                    metrics={"method": "IQR_1.5", "lower_bound": round(lower, 6), "upper_bound": round(upper, 6), "outlier_count": len(outlier_rows)},
                    recommendation="Revisar os registros no contexto do domínio antes de corrigir ou remover valores.",
                    limitations="Valor atípico não é necessariamente erro; sazonalidade e segmentos não são considerados neste teste.",
                )

    if present and inferred_type == "texto":
        distinct = len(value_counts)
        if len(present) >= 20 >= distinct >= 2:
            context.evaluated_dimensions.add("qualidade_categorica")
            rare = [(value, count) for value, count in value_counts.items() if count == 1]
            if rare:
                context.add_finding(
                    dimension="qualidade_categorica", severity="baixa", confidence=0.65,
                    scope=f"coluna:{name}", title=f"Categorias raras em {name}",
                    description=f"Foram encontradas {len(rare)} categorias com uma única ocorrência.",
                    evidence=[f"{value}: {count} ocorrência" for value, count in rare],
                    metrics={"rare_category_count": len(rare), "distinct_count": distinct},
                    recommendation="Comparar as categorias com o vocabulário autorizado e verificar grafias equivalentes.",
                    limitations="Raridade não comprova invalidade; o teste não possui vocabulário de domínio.",
                )

    profile = DataQualityColumnProfile(
        name=name, inferred_type=inferred_type, type_confidence=round(type_confidence, 3),
        non_missing_count=len(present), missing_count=len(missing),
        missing_percentage=round_percentage(len(missing), len(row_values)),
        distinct_count=len(value_counts), distinct_percentage=round_percentage(len(value_counts), len(present)),
        outlier_count=len(outlier_rows),
        top_values=[DataQualityTopValue(value=value, count=count, percentage=round_percentage(count, len(present))) for value, count in value_counts.most_common(5)],
    )
    if numeric_values:
        profile.minimum, profile.maximum = round(min(numeric_values), 6), round(max(numeric_values), 6)
        profile.mean, profile.median = round(statistics.fmean(numeric_values), 6), round(statistics.median(numeric_values), 6)
        profile.standard_deviation = round(statistics.pstdev(numeric_values), 6)
    elif inferred_type == "data":
        valid_dates = [parsed_date for _, value in present if (parsed_date := parse_date(value)) is not None]
        if valid_dates:
            profile.minimum, profile.maximum = min(valid_dates).isoformat(), max(valid_dates).isoformat()
    return profile
