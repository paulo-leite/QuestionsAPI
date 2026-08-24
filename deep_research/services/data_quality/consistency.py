"""Avaliações de consistência entre colunas e fontes relacionadas."""

from dataclasses import dataclass
from datetime import datetime, timezone
import re

import pandas as pd
import pandera.pandas as pa

from .core import AnalysisContext, ParsedTable, is_missing, normalize_name, parse_number, round_percentage

DATE_MARKER_PAIRS = (("inicio", "fim"), ("inicial", "final"), ("start", "end"), ("from", "to"))
RANGE_MARKER_PAIRS = (("min", "max"), ("minimum", "maximum"), ("minimo", "maximo"), ("lower", "upper"))
KEY_MARKERS = {"id", "codigo", "code", "key", "chave", "identifier"}
ATTRIBUTE_MARKERS = {"nome", "name", "descricao", "description", "razao", "denominacao"}


@dataclass(frozen=True)
class _DateValue:
    value: datetime | None
    status: str
    aware: bool = False


def _table_frame(table: ParsedTable) -> pd.DataFrame:
    """Converte a tabela uma vez, preservando o número original de cada linha."""
    return pd.DataFrame(
        [
            {
                header: row.values[index]
                for index, header in enumerate(table.headers)
            }
            for row in table.rows
        ],
        index=pd.Index([row.number for row in table.rows], name="row_number"),
    )


def _pandera_failed_rows(
    dataframe: pd.DataFrame,
    predicate: object,
    check_name: str,
) -> set[int]:
    """Executa um check relacional e devolve os índices das linhas reprovadas."""
    schema = pa.DataFrameSchema(
        checks=pa.Check(predicate, name=check_name),
        strict=False,
        coerce=False,
    )
    try:
        schema.validate(dataframe, lazy=True)
        return set()
    except pa.errors.SchemaErrors as error:
        cases = error.failure_cases
    relevant = cases[cases["check"] == check_name]
    return {
        int(row_index)
        for row_index in relevant["index"].dropna().tolist()
    }


def _tokens(header: str) -> list[str]:
    """Divide um cabeçalho normalizado em tokens semânticos completos."""
    return [token for token in normalize_name(header).split("_") if token]


def _paired_columns(headers: tuple[str, ...], markers: tuple[tuple[str, str], ...]) -> list[tuple[int, int]]:
    """Infere pares de colunas substituindo tokens relacionais equivalentes."""
    tokenized = [_tokens(header) for header in headers]
    pairs: set[tuple[int, int]] = set()
    for left_index, tokens in enumerate(tokenized):
        for left_marker, right_marker in markers:
            if left_marker not in tokens:
                continue
            expected = tokens.copy()
            expected[expected.index(left_marker)] = right_marker
            if expected in tokenized:
                pairs.add((left_index, tokenized.index(expected)))
    return sorted(pairs)


def _parse_consistency_date(raw: str) -> _DateValue:
    """Classifica e converte uma data sem resolver formatos deliberadamente ambíguos."""
    candidate = raw.strip()
    if not candidate:
        return _DateValue(None, "missing")
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        aware = parsed.tzinfo is not None
        if aware:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return _DateValue(parsed, "valid", aware)
    except ValueError:
        pass
    slash_match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", candidate)
    if slash_match:
        first, second = int(slash_match.group(1)), int(slash_match.group(2))
        if first <= 12 and second <= 12:
            return _DateValue(None, "ambiguous")
        try:
            return _DateValue(datetime.strptime(candidate, "%d/%m/%Y"), "valid")
        except ValueError:
            return _DateValue(None, "invalid")
    for date_format in ("%d-%m-%Y", "%Y/%m/%d"):
        try:
            return _DateValue(datetime.strptime(candidate, date_format), "valid")
        except ValueError:
            continue
    return _DateValue(None, "invalid")


def _check_date_order(
    table: ParsedTable,
    dataframe: pd.DataFrame,
    context: AnalysisContext,
) -> None:
    """Valida com Pandera se datas iniciais não são posteriores às finais."""
    for start_index, end_index in _paired_columns(table.headers, DATE_MARKER_PAIRS):
        counts = {"comparable": 0, "missing": 0, "invalid": 0, "ambiguous": 0, "timezone_mismatch": 0}
        comparable_records: list[dict[str, datetime]] = []
        comparable_indexes: list[int] = []
        for row in table.rows:
            start = _parse_consistency_date(row.values[start_index])
            end = _parse_consistency_date(row.values[end_index])
            statuses = {start.status, end.status}
            if "missing" in statuses:
                counts["missing"] += 1
            elif "ambiguous" in statuses:
                counts["ambiguous"] += 1
            elif "invalid" in statuses:
                counts["invalid"] += 1
            elif start.aware != end.aware:
                counts["timezone_mismatch"] += 1
            else:
                counts["comparable"] += 1
                if start.value is not None and end.value is not None:
                    comparable_indexes.append(row.number)
                    comparable_records.append({"start": start.value, "end": end.value})
        if not counts["comparable"]:
            continue
        context.evaluated_dimensions.add("consistencia")
        comparable_frame = pd.DataFrame(
            comparable_records,
            index=pd.Index(comparable_indexes, name="row_number"),
        )
        failed_rows = _pandera_failed_rows(
            comparable_frame,
            lambda frame: frame["start"] <= frame["end"],
            "date_start_not_after_end",
        )
        if failed_rows:
            start_name, end_name = table.headers[start_index], table.headers[end_index]
            conflicts = [
                f"linha {row_number}: {dataframe.at[row_number, start_name]} > "
                f"{dataframe.at[row_number, end_name]}"
                for row_number in sorted(failed_rows)
            ]
            context.add_finding(
                dimension="consistencia", severity="alta", confidence=0.98,
                scope=f"colunas:{start_name},{end_name}", title="Ordem cronológica inconsistente",
                description=f"Existem {len(conflicts)} registros em que a data inicial é posterior à final.",
                evidence=conflicts,
                metrics={
                    "validation_engine": "pandera", "rule": "date_start_not_after_end", "comparable_rows": counts["comparable"],
                    "inconsistent_rows": len(conflicts), "skipped_missing_rows": counts["missing"],
                    "skipped_invalid_rows": counts["invalid"], "skipped_ambiguous_rows": counts["ambiguous"],
                    "skipped_timezone_mismatch_rows": counts["timezone_mismatch"],
                    "inconsistency_percentage": round_percentage(len(conflicts), counts["comparable"]),
                },
                recommendation="Corrigir a origem ou a associação entre os campos de início e fim.",
                limitations="O pareamento das colunas foi inferido a partir de seus nomes.",
            )


def _check_numeric_ranges(
    table: ParsedTable,
    dataframe: pd.DataFrame,
    context: AnalysisContext,
) -> None:
    """Valida com Pandera se limites inferiores não excedem os superiores."""
    for lower_index, upper_index in _paired_columns(table.headers, RANGE_MARKER_PAIRS):
        comparable_records: list[dict[str, float]] = []
        comparable_indexes: list[int] = []
        for row in table.rows:
            lower, upper = parse_number(row.values[lower_index]), parse_number(row.values[upper_index])
            if lower is None or upper is None:
                continue
            comparable_indexes.append(row.number)
            comparable_records.append({"lower": lower, "upper": upper})
        comparable = len(comparable_records)
        if not comparable:
            continue
        context.evaluated_dimensions.add("consistencia")
        comparable_frame = pd.DataFrame(
            comparable_records,
            index=pd.Index(comparable_indexes, name="row_number"),
        )
        failed_rows = _pandera_failed_rows(
            comparable_frame,
            lambda frame: frame["lower"] <= frame["upper"],
            "numeric_lower_not_greater_than_upper",
        )
        if failed_rows:
            lower_name, upper_name = table.headers[lower_index], table.headers[upper_index]
            conflicts = [
                f"linha {row_number}: "
                f"{parse_number(str(dataframe.at[row_number, lower_name])):g} > "
                f"{parse_number(str(dataframe.at[row_number, upper_name])):g}"
                for row_number in sorted(failed_rows)
            ]
            context.add_finding(
                dimension="consistencia", severity="alta", confidence=0.98,
                scope=f"colunas:{lower_name},{upper_name}", title="Intervalo numérico inconsistente",
                description=f"Existem {len(conflicts)} registros cujo limite mínimo é maior que o máximo.",
                evidence=conflicts,
                metrics={"validation_engine": "pandera", "rule": "numeric_lower_not_greater_than_upper", "comparable_rows": comparable, "inconsistent_rows": len(conflicts), "inconsistency_percentage": round_percentage(len(conflicts), comparable)},
                recommendation="Corrigir os limites numéricos contraditórios na origem.",
                limitations="O pareamento dos limites foi inferido a partir dos nomes das colunas.",
            )


def _entity_pairs(headers: tuple[str, ...]) -> list[tuple[int, int, str]]:
    """Infere pares chave–atributo que compartilham o mesmo nome de entidade."""
    tokenized = [_tokens(header) for header in headers]
    pairs: list[tuple[int, int, str]] = []
    for key_index, key_tokens in enumerate(tokenized):
        key_entities = [token for token in key_tokens if token not in KEY_MARKERS]
        if len(key_entities) != 1 or not set(key_tokens) & KEY_MARKERS:
            continue
        entity = key_entities[0]
        for attribute_index, attribute_tokens in enumerate(tokenized):
            if attribute_index == key_index or entity not in attribute_tokens:
                continue
            if set(attribute_tokens) & ATTRIBUTE_MARKERS:
                pairs.append((key_index, attribute_index, entity))
    return pairs


def _grouped_values(
    dataframe: pd.DataFrame,
    key_column: str,
    attribute_column: str,
) -> pd.Series:
    """Agrupa os valores presentes de um atributo por chave de entidade."""
    usable = dataframe[[key_column, attribute_column]].loc[
        lambda frame: (
            ~frame[key_column].map(is_missing)
            & ~frame[attribute_column].map(is_missing)
        )
    ]
    return usable.groupby(key_column, sort=False)[attribute_column].agg(
        lambda values: frozenset(str(value) for value in values)
    )


def _check_stable_attributes(
    table: ParsedTable,
    dataframe: pd.DataFrame,
    context: AnalysisContext,
) -> None:
    """Detecta com agrupamentos Pandas atributos divergentes para a mesma entidade."""
    for key_index, attribute_index, entity in _entity_pairs(table.headers):
        key_name, attribute_name = table.headers[key_index], table.headers[attribute_index]
        usable = dataframe[[key_name, attribute_name]].loc[
            lambda frame: (
                ~frame[key_name].map(is_missing)
                & ~frame[attribute_name].map(is_missing)
            )
        ]
        occurrence_counts = usable.groupby(key_name, sort=False).size()
        compared_keys = occurrence_counts[occurrence_counts >= 2].index
        if compared_keys.empty:
            continue
        context.evaluated_dimensions.add("consistencia")
        grouped = _grouped_values(usable, key_name, attribute_name)
        compared = grouped[grouped.index.isin(compared_keys)]
        conflicts = compared[compared.map(len) > 1]
        if conflicts.empty:
            continue
        context.add_finding(
            dimension="consistencia", severity="media", confidence=0.90,
            scope=f"colunas:{key_name},{attribute_name}", title=f"Atributo instável por {entity}",
            description=f"Foram encontradas {len(conflicts)} entidades associadas a valores divergentes em {attribute_name}.",
            evidence=[f"{key_name}={key}: " + " | ".join(sorted(values)) for key, values in conflicts.items()],
            metrics={"validation_engine": "pandas", "rule": "stable_attribute_per_entity", "key_column": key_name, "attribute_column": attribute_name, "entity": entity, "association_method": "semantic_name_inference", "compared_entities": len(compared), "conflicting_entities": len(conflicts)},
            recommendation="Validar qual valor representa corretamente cada entidade e corrigir a fonte.",
            limitations="A associação entre chave e atributo foi inferida semanticamente pelos nomes das colunas.",
        )


def check_consistency(table: ParsedTable, context: AnalysisContext) -> None:
    """Executa todas as regras internas da dimensão de consistência."""
    dataframe = _table_frame(table)
    _check_date_order(table, dataframe, context)
    _check_numeric_ranges(table, dataframe, context)
    _check_stable_attributes(table, dataframe, context)


def check_cross_source_consistency(current: ParsedTable, reference: ParsedTable, context: AnalysisContext) -> None:
    """Compara atributos por chave entre os conjuntos atual e de referência."""
    current_frame = _table_frame(current)
    reference_frame = _table_frame(reference)
    reference_indexes = {name: index for index, name in enumerate(reference.headers)}
    for key_index, attribute_index, entity in _entity_pairs(current.headers):
        key_name, attribute_name = current.headers[key_index], current.headers[attribute_index]
        if key_name not in reference_indexes or attribute_name not in reference_indexes:
            continue
        current_values = _grouped_values(current_frame, key_name, attribute_name)
        reference_values = _grouped_values(reference_frame, key_name, attribute_name)
        shared_keys = current_values.index.intersection(reference_values.index, sort=False)
        if shared_keys.empty:
            continue
        context.evaluated_dimensions.add("consistencia")
        comparison = pd.DataFrame(
            {
                "current": current_values.loc[shared_keys],
                "reference": reference_values.loc[shared_keys],
            }
        )
        conflicts = comparison[
            comparison["current"] != comparison["reference"]
        ]
        if conflicts.empty:
            continue
        context.add_finding(
            dimension="consistencia", severity="media", confidence=0.95,
            scope=f"fontes:{key_name},{attribute_name}", title=f"Atributo divergente entre fontes para {entity}",
            description=f"Foram encontradas {len(conflicts)} entidades com valores diferentes entre o arquivo atual e a referência.",
            evidence=[f"{key_name}={key}: atual={' | '.join(sorted(row['current']))}; referência={' | '.join(sorted(row['reference']))}" for key, row in conflicts.iterrows()],
            metrics={"validation_engine": "pandas", "rule": "stable_attribute_across_sources", "key_column": key_name, "attribute_column": attribute_name, "entity": entity, "association_method": "semantic_name_inference", "compared_entities": len(shared_keys), "conflicting_entities": len(conflicts)},
            recommendation="Conciliar os valores com a fonte autoritativa antes da consolidação.",
            limitations="A comparabilidade das fontes e a associação semântica das colunas são presumidas.",
        )
