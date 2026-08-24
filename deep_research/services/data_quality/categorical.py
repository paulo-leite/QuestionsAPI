"""Avaliações da qualidade de valores categóricos."""

from rapidfuzz import fuzz, utils

from deep_research.models import DataQualityColumnProfile

from .core import AnalysisContext, ParsedTable, is_missing

RAPIDFUZZ_SIMILARITY_THRESHOLD = 90.0
MAX_RAPIDFUZZ_CATEGORIES = 50


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
