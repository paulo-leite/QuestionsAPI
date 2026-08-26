"""Avaliações da qualidade de valores categóricos."""

from collections import Counter

from rapidfuzz import fuzz, utils

from deep_research.models import DataQualityColumnProfile

from .core import AnalysisContext, ParsedTable, is_missing

RAPIDFUZZ_SIMILARITY_THRESHOLD = 90.0
MAX_RAPIDFUZZ_CATEGORIES = 50


def check_rare_categories(
    table: ParsedTable,
    profiles: list[DataQualityColumnProfile],
    context: AnalysisContext,
) -> None:
    """Sinaliza categorias textuais com uma única ocorrência."""
    indexes = {name: index for index, name in enumerate(table.headers)}
    for profile in profiles:
        if profile.inferred_type != "texto":
            continue
        values = [
            row.values[indexes[profile.name]]
            for row in table.rows
            if not is_missing(row.values[indexes[profile.name]])
        ]
        distinct = profile.distinct_count
        if not (len(values) >= 20 >= distinct >= 2):
            continue
        context.evaluated_dimensions.add("qualidade_categorica")
        rare = [
            (value, count)
            for value, count in Counter(values).items()
            if count == 1
        ]
        if not rare:
            continue
        context.add_finding(
            dimension="qualidade_categorica", severity="baixa", confidence=0.65,
            scope=f"coluna:{profile.name}", title=f"Categorias raras em {profile.name}",
            description=f"Foram encontradas {len(rare)} categorias com uma única ocorrência.",
            evidence=[f"{value}: {count} ocorrência" for value, count in rare],
            metrics={"rare_category_count": len(rare), "distinct_count": distinct},
            recommendation="Comparar as categorias com o vocabulário autorizado e verificar grafias equivalentes.",
            limitations="Raridade não comprova invalidade; o teste não possui vocabulário de domínio.",
        )


def check_category_similarity(table: ParsedTable, profiles: list[DataQualityColumnProfile], context: AnalysisContext) -> None:
    """Encontra categorias distintas com grafias potencialmente equivalentes."""
    indexes = {name: index for index, name in enumerate(table.headers)}
    for profile in profiles:
        if profile.inferred_type != "texto" or profile.distinct_count < 2 or profile.distinct_count > MAX_RAPIDFUZZ_CATEGORIES or profile.distinct_percentage > 50:
            continue
        context.evaluated_dimensions.add("qualidade_categorica")
        values = sorted({row.values[indexes[profile.name]] for row in table.rows if not is_missing(row.values[indexes[profile.name]])})
        similar_pairs: list[tuple[str, str, float]] = []
        for left_index, left in enumerate(values):
            if len(left.strip()) < 3:
                continue
            for right in values[left_index + 1:]:
                if len(right.strip()) < 3:
                    continue
                score = float(fuzz.WRatio(left, right, processor=utils.default_process))
                if score >= RAPIDFUZZ_SIMILARITY_THRESHOLD:
                    similar_pairs.append((left, right, score))
        if not similar_pairs:
            continue
        similar_pairs.sort(key=lambda item: item[2], reverse=True)
        context.add_finding(
            dimension="qualidade_categorica", severity="baixa", confidence=0.80,
            scope=f"coluna:{profile.name}", title=f"Categorias com grafias semelhantes em {profile.name}",
            description=f"O RapidFuzz encontrou {len(similar_pairs)} pares de categorias distintas com alta similaridade textual.",
            evidence=[f"{left} ↔ {right}: {score:.1f}%" for left, right, score in similar_pairs],
            metrics={"validation_engine": "rapidfuzz", "scorer": "WRatio", "similarity_threshold": RAPIDFUZZ_SIMILARITY_THRESHOLD, "candidate_pair_count": len(similar_pairs)},
            recommendation="Comparar os pares com o vocabulário autorizado antes de normalizar ou consolidar categorias.",
            limitations="Similaridade textual não comprova equivalência semântica; siglas e termos legítimos podem ser parecidos.",
        )
