"""Avaliações de duplicidade exata e aproximada."""

import pandas as pd
from rapidfuzz import fuzz, utils
from splink import DuckDBAPI, Linker, SettingsCreator

from deep_research.models import DataQualityColumnProfile

from .core import AnalysisContext, ParsedTable, is_missing, looks_like_identifier

MIN_SPLINK_ROWS = 20
MAX_SPLINK_ROWS = 2_000
SPLINK_SIMILARITY_THRESHOLD = 0.92
MAX_SPLINK_RULES = 6


def check_exact_duplicates(table: ParsedTable, context: AnalysisContext) -> int:
    """Detecta linhas idênticas e devolve o total excedente à primeira ocorrência."""
    context.evaluated_dimensions.add("duplicidade")
    groups: dict[tuple[str, ...], list[int]] = {}
    for row in table.rows:
        groups.setdefault(row.values, []).append(row.number)
    duplicate_groups = [rows for rows in groups.values() if len(rows) > 1]
    duplicate_count = sum(len(rows) - 1 for rows in duplicate_groups)
    if duplicate_count:
        context.add_finding(
            dimension="duplicidade", severity="media", confidence=1.0, scope="dataset",
            title="Linhas exatamente duplicadas",
            description=f"Foram encontradas {duplicate_count} linhas duplicadas além da primeira ocorrência.",
            evidence=["linhas " + ", ".join(map(str, rows)) for rows in duplicate_groups],
            metrics={"duplicate_rows": duplicate_count, "duplicate_groups": len(duplicate_groups)},
            recommendation="Confirmar a chave de negócio e remover ou consolidar duplicatas na origem.",
            limitations="O teste detecta apenas linhas idênticas; duplicidade aproximada requer resolução de entidades.",
        )
    return duplicate_count


def check_approximate_duplicates(table: ParsedTable, profiles: list[DataQualityColumnProfile], context: AnalysisContext) -> None:
    """Gera pares candidatos por bloqueio exato e comparação textual fuzzy."""
    row_count = len(table.rows)
    if row_count < MIN_SPLINK_ROWS or row_count > MAX_SPLINK_ROWS:
        return
    fuzzy_profiles = sorted(
        [profile for profile in profiles if profile.inferred_type == "texto" and profile.distinct_count >= 3 and profile.distinct_percentage >= 30 and not looks_like_identifier(profile.name)],
        key=lambda profile: profile.distinct_percentage, reverse=True,
    )[:3]
    anchor_profiles = sorted(
        [profile for profile in profiles if profile.inferred_type not in {"vazia", "mista"} and profile.missing_percentage <= 30 and 0.05 <= profile.distinct_count / row_count <= 0.80],
        key=lambda profile: abs(profile.distinct_count / row_count - 0.25),
    )[:4]
    if not fuzzy_profiles or not anchor_profiles:
        return

    selected_names = list(dict.fromkeys([profile.name for profile in fuzzy_profiles] + [profile.name for profile in anchor_profiles]))
    internal_names = {name: f"field_{index}" for index, name in enumerate(selected_names)}
    table_indexes = {name: index for index, name in enumerate(table.headers)}
    dataframe = pd.DataFrame([
        {"unique_id": row.number, **{internal_names[name]: None if is_missing(row.values[table_indexes[name]]) else utils.default_process(row.values[table_indexes[name]]) for name in selected_names}}
        for row in table.rows
    ])

    rules: list[str] = []
    rule_metadata: list[tuple[str, str]] = []
    for fuzzy_profile in fuzzy_profiles:
        for anchor_profile in anchor_profiles:
            if fuzzy_profile.name == anchor_profile.name:
                continue
            fuzzy_field, anchor_field = internal_names[fuzzy_profile.name], internal_names[anchor_profile.name]
            rules.append(f"l.{anchor_field} = r.{anchor_field} and jaro_winkler_similarity(l.{fuzzy_field}, r.{fuzzy_field}) >= {SPLINK_SIMILARITY_THRESHOLD}")
            rule_metadata.append((fuzzy_profile.name, anchor_profile.name))
            if len(rules) >= MAX_SPLINK_RULES:
                break
        if len(rules) >= MAX_SPLINK_RULES:
            break
    if not rules:
        return

    settings = SettingsCreator(link_type="dedupe_only", blocking_rules_to_generate_predictions=rules, retain_matching_columns=True)  # type: ignore[arg-type]
    linker = Linker(dataframe, settings, db_api=DuckDBAPI(), set_up_basic_logging=False)  # type: ignore[arg-type]
    predictions = linker.inference.deterministic_link().as_pandas_dataframe()
    if predictions.empty:
        return

    rows_by_number = {row.number: row for row in table.rows}
    candidates: list[tuple[int, int, str, str, float]] = []
    seen_pairs: set[tuple[int, int]] = set()
    for prediction in predictions.to_dict("records"):
        left_row, right_row = int(prediction["unique_id_l"]), int(prediction["unique_id_r"])
        pair = (min(left_row, right_row), max(left_row, right_row))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        if rows_by_number[left_row].values == rows_by_number[right_row].values:
            continue
        match_key = int(prediction.get("match_key", 0))
        if match_key >= len(rule_metadata):
            continue
        fuzzy_name, anchor_name = rule_metadata[match_key]
        similarity = float(fuzz.WRatio(rows_by_number[left_row].values[table_indexes[fuzzy_name]], rows_by_number[right_row].values[table_indexes[fuzzy_name]], processor=utils.default_process))
        candidates.append((left_row, right_row, fuzzy_name, anchor_name, similarity))
    if not candidates:
        return
    context.add_finding(
        dimension="duplicidade", severity="baixa", confidence=0.75, scope="dataset",
        title="Possíveis duplicatas aproximadas",
        description=f"O Splink encontrou {len(candidates)} pares de registros candidatos a representar a mesma entidade.",
        evidence=[f"linhas {left} e {right}: {fuzzy_name} semelhante ({similarity:.1f}%), {anchor_name} igual" for left, right, fuzzy_name, anchor_name, similarity in candidates],
        metrics={"validation_engine": "splink", "linkage_method": "deterministic_fuzzy_blocking", "jaro_winkler_threshold": SPLINK_SIMILARITY_THRESHOLD, "candidate_pair_count": len(candidates), "blocking_rule_count": len(rules), "maximum_rows": MAX_SPLINK_ROWS},
        recommendation="Revisar os pares e calibrar regras com exemplos rotulados antes de consolidar ou excluir registros.",
        limitations="Os pares são candidatos, não probabilidades calibradas. O bloqueio exige um campo de apoio igual e pode deixar passar duplicatas com múltiplos erros.",
    )
