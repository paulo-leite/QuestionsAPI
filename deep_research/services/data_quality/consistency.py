"""Avaliações de consistência entre colunas e fontes relacionadas."""

from dataclasses import dataclass
from datetime import datetime, timezone
import re

import pandas as pd
import pandera.pandas as pa

from deep_research.models import ConsistencyRuleSpec

from .core import AnalysisContext, ParsedTable, is_missing, normalize_name, parse_date, parse_number, round_percentage

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


def _validated_rule_columns(
    table: ParsedTable,
    rule: ConsistencyRuleSpec,
    expected_count: int | None = None,
    minimum_count: int = 1,
) -> list[str]:
    """Valida referências de colunas sem permitir expressões produzidas pelo modelo."""
    if len(rule.columns) < minimum_count:
        raise ValueError(f"{rule.rule_id}: quantidade insuficiente de colunas")
    if expected_count is not None and len(rule.columns) != expected_count:
        raise ValueError(f"{rule.rule_id}: esperava {expected_count} colunas")
    if len(set(rule.columns)) != len(rule.columns):
        raise ValueError(f"{rule.rule_id}: contém colunas repetidas")
    unknown = [column for column in rule.columns if column not in table.headers]
    if unknown:
        raise ValueError(f"{rule.rule_id}: colunas inexistentes: {', '.join(unknown)}")
    return rule.columns


def _complete_frame(dataframe: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    selected = dataframe.loc[:, columns]
    return selected.loc[selected.map(lambda value: not is_missing(str(value))).all(axis=1)]


def _numeric_frame(dataframe: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    complete = _complete_frame(dataframe, columns)
    numeric = pd.DataFrame(index=complete.index)
    locale_pattern = r"[+-]?\d{1,3}(?:\.\d{3})*,\d+|[+-]?\d+,\d+"
    portuguese_locale = any(
        complete[column].map(lambda value: str(value).strip()).str.fullmatch(
            locale_pattern
        ).any()
        for column in columns
    )
    for column in columns:
        values = complete[column].map(lambda value: str(value).strip())
        # Uma vírgula decimal em qualquer valor é evidência forte de que pontos
        # das colunas comparadas representam separadores de milhar (ex.: 7.000).
        if portuguese_locale:
            numeric[column] = values.map(
                lambda value: parse_number(value.replace(".", "").replace(",", "."))
            )
        else:
            numeric[column] = values.map(parse_number)
    return numeric.dropna()


def _add_agent_finding(
    context: AnalysisContext,
    rule: ConsistencyRuleSpec,
    *,
    title: str,
    description: str,
    evidence: list[str],
    metrics: dict,
) -> None:
    context.add_finding(
        dimension="consistencia",
        severity=rule.severity,
        confidence=rule.confidence,
        scope=f"colunas:{','.join(rule.columns)}",
        title=title,
        description=description,
        evidence=evidence,
        metrics={
            "validation_engine": "agent_rule_executor",
            "agent_generated": True,
            "rule": rule.rule_id,
            "rule_type": rule.rule_type,
            "rationale": rule.rationale,
            **metrics,
        },
        recommendation="Revisar os registros sinalizados e confirmar a regra com o responsável pela fonte.",
        limitations=rule.limitation,
    )


def _execute_ordered_values(
    table: ParsedTable,
    dataframe: pd.DataFrame,
    context: AnalysisContext,
    rule: ConsistencyRuleSpec,
) -> None:
    columns = _validated_rule_columns(table, rule, minimum_count=2)
    if rule.operator not in {"<=", ">=", "<", ">", "=="}:
        raise ValueError(f"{rule.rule_id}: operador obrigatório ou não permitido")
    numeric = _numeric_frame(dataframe, columns)
    if numeric.empty:
        return
    comparisons = {
        "<=": lambda left, right: left.le(right),
        ">=": lambda left, right: left.ge(right),
        "<": lambda left, right: left.lt(right),
        ">": lambda left, right: left.gt(right),
        "==": lambda left, right: left.eq(right),
    }
    valid = pd.Series(True, index=numeric.index)
    compare = comparisons[rule.operator]
    for left, right in zip(columns, columns[1:]):
        valid &= compare(numeric[left], numeric[right])
    context.evaluated_dimensions.add("consistencia")
    if valid.all():
        return
    failed = numeric.loc[~valid]
    _add_agent_finding(
        context, rule,
        title="Ordem numérica inconsistente",
        description=f"Existem {len(failed)} registros que não respeitam {' {} '.format(rule.operator).join(columns)}.",
        evidence=[
            f"linha {index}: " + "; ".join(f"{column}={row[column]:g}" for column in columns)
            for index, row in failed.head(10).iterrows()
        ],
        metrics={
            "operator": rule.operator, "comparable_rows": len(numeric),
            "inconsistent_rows": len(failed),
            "inconsistency_percentage": round_percentage(len(failed), len(numeric)),
        },
    )


def _execute_non_negative(
    table: ParsedTable,
    dataframe: pd.DataFrame,
    context: AnalysisContext,
    rule: ConsistencyRuleSpec,
) -> None:
    columns = _validated_rule_columns(table, rule)
    numeric = _numeric_frame(dataframe, columns)
    if numeric.empty:
        return
    invalid = numeric.lt(0).any(axis=1)
    context.evaluated_dimensions.add("consistencia")
    if not invalid.any():
        return
    failed = numeric.loc[invalid]
    _add_agent_finding(
        context, rule,
        title="Valor negativo incompatível com a regra de domínio",
        description=f"Existem {len(failed)} registros com valores negativos.",
        evidence=[
            f"linha {index}: " + "; ".join(f"{column}={row[column]:g}" for column in columns)
            for index, row in failed.head(10).iterrows()
        ],
        metrics={"comparable_rows": len(numeric), "inconsistent_rows": len(failed)},
    )


def _execute_unique_key(
    table: ParsedTable,
    dataframe: pd.DataFrame,
    context: AnalysisContext,
    rule: ConsistencyRuleSpec,
) -> None:
    columns = _validated_rule_columns(table, rule)
    usable = _complete_frame(dataframe, columns)
    if usable.empty:
        return
    duplicated = usable.duplicated(columns, keep=False)
    context.evaluated_dimensions.add("consistencia")
    if not duplicated.any():
        return
    failed = usable.loc[duplicated]
    grouped = failed.groupby(columns, sort=False, dropna=False)
    evidence = []
    for key, group in list(grouped)[:10]:
        values = key if isinstance(key, tuple) else (key,)
        label = "; ".join(f"{column}={value}" for column, value in zip(columns, values))
        evidence.append(f"{label}; linhas={','.join(str(index) for index in group.index)}")
    _add_agent_finding(
        context, rule,
        title="Chave de negócio repetida",
        description=f"Foram encontradas {grouped.ngroups} chaves repetidas.",
        evidence=evidence,
        metrics={"evaluated_rows": len(usable), "duplicate_rows": len(failed), "duplicate_keys": grouped.ngroups},
    )


def _execute_column_mapping(
    table: ParsedTable,
    dataframe: pd.DataFrame,
    context: AnalysisContext,
    rule: ConsistencyRuleSpec,
) -> None:
    key, attribute = _validated_rule_columns(table, rule, expected_count=2)
    usable = _complete_frame(dataframe, [key, attribute])
    if usable.empty:
        return
    grouped = usable.groupby(key, sort=False)[attribute].agg(
        lambda values: frozenset(str(value) for value in values)
    )
    context.evaluated_dimensions.add("consistencia")
    conflicts = grouped[grouped.map(len) > 1]
    if conflicts.empty:
        return
    _add_agent_finding(
        context, rule,
        title="Atributo instável para a mesma chave",
        description=f"Foram encontradas {len(conflicts)} chaves associadas a valores divergentes.",
        evidence=[f"{key}={value}: " + " | ".join(sorted(values)) for value, values in conflicts.head(10).items()],
        metrics={"compared_entities": len(grouped), "conflicting_entities": len(conflicts)},
    )


def _period_month(value: object) -> int | None:
    candidate = normalize_name(str(value))
    match = re.match(r"^(\d{1,2})(?:_|$)", candidate)
    if match and 1 <= int(match.group(1)) <= 12:
        return int(match.group(1))
    names = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
             "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12}
    return names.get(candidate[:3])


def _execute_date_matches_period(
    table: ParsedTable,
    dataframe: pd.DataFrame,
    context: AnalysisContext,
    rule: ConsistencyRuleSpec,
) -> None:
    date_column, period_column = _validated_rule_columns(table, rule, expected_count=2)
    usable = _complete_frame(dataframe, [date_column, period_column])
    dates = usable[date_column].map(lambda value: parse_date(str(value)))
    months = usable[period_column].map(_period_month)
    comparable = usable.loc[dates.notna() & months.notna()]
    if comparable.empty:
        return
    invalid = dates.loc[comparable.index].map(lambda value: value.month).ne(months.loc[comparable.index])
    context.evaluated_dimensions.add("consistencia")
    if not invalid.any():
        return
    failed = comparable.loc[invalid]
    _add_agent_finding(
        context, rule,
        title="Data incompatível com o período informado",
        description=f"Existem {len(failed)} registros cujo mês não corresponde à data.",
        evidence=[f"linha {index}: {date_column}={row[date_column]}; {period_column}={row[period_column]}" for index, row in failed.head(10).iterrows()],
        metrics={"comparable_rows": len(comparable), "inconsistent_rows": len(failed)},
    )


def _execute_conditional_equality(
    table: ParsedTable,
    dataframe: pd.DataFrame,
    context: AnalysisContext,
    rule: ConsistencyRuleSpec,
) -> None:
    condition_column, result_column = _validated_rule_columns(table, rule, expected_count=2)
    if rule.condition_value is None or rule.expected_value is None:
        raise ValueError(f"{rule.rule_id}: valores da condição são obrigatórios")
    usable = _complete_frame(dataframe, [condition_column, result_column])
    condition = usable[condition_column].map(normalize_name).eq(normalize_name(rule.condition_value))
    applicable = usable.loc[condition]
    if applicable.empty:
        return
    invalid = applicable[result_column].map(normalize_name).ne(normalize_name(rule.expected_value))
    context.evaluated_dimensions.add("consistencia")
    if not invalid.any():
        return
    failed = applicable.loc[invalid]
    _add_agent_finding(
        context, rule,
        title="Regra condicional inconsistente",
        description=f"Existem {len(failed)} registros que não atendem à consequência esperada.",
        evidence=[f"linha {index}: {condition_column}={row[condition_column]}; {result_column}={row[result_column]}" for index, row in failed.head(10).iterrows()],
        metrics={"applicable_rows": len(applicable), "inconsistent_rows": len(failed)},
    )


def _execute_identifier_format(
    table: ParsedTable,
    dataframe: pd.DataFrame,
    context: AnalysisContext,
    rule: ConsistencyRuleSpec,
) -> None:
    column = _validated_rule_columns(table, rule, expected_count=1)[0]
    if rule.identifier_format not in {"digits_only", "not_scientific_notation"}:
        raise ValueError(f"{rule.rule_id}: formato de identificador obrigatório")
    usable = _complete_frame(dataframe, [column])[column]
    if usable.empty:
        return
    if rule.identifier_format == "digits_only":
        invalid = ~usable.map(lambda value: str(value).strip().isdigit())
    else:
        scientific = re.compile(r"^[+-]?\d+(?:[.,]\d+)?e[+-]?\d+$", re.IGNORECASE)
        invalid = usable.map(lambda value: bool(scientific.fullmatch(str(value).strip())))
    context.evaluated_dimensions.add("consistencia")
    if not invalid.any():
        return
    failed = usable.loc[invalid]
    _add_agent_finding(
        context, rule,
        title="Representação insegura de identificador",
        description=f"Existem {len(failed)} identificadores incompatíveis com o formato esperado.",
        evidence=[f"linha {index}: {column}={value}" for index, value in failed.head(10).items()],
        metrics={"evaluated_rows": len(usable), "inconsistent_rows": len(failed), "identifier_format": rule.identifier_format},
    )


RULE_EXECUTORS = {
    "ordered_values": _execute_ordered_values,
    "non_negative": _execute_non_negative,
    "unique_key": _execute_unique_key,
    "column_mapping": _execute_column_mapping,
    "date_matches_period": _execute_date_matches_period,
    "conditional_equality": _execute_conditional_equality,
    "identifier_format": _execute_identifier_format,
}


def check_consistency(
    table: ParsedTable,
    context: AnalysisContext,
    proposed_rules: list[ConsistencyRuleSpec] | None = None,
) -> list[str]:
    """Executa regras internas e regras estruturadas propostas pelo agente."""
    dataframe = _table_frame(table)
    _check_date_order(table, dataframe, context)
    _check_numeric_ranges(table, dataframe, context)
    _check_stable_attributes(table, dataframe, context)
    rejected: list[str] = []
    for rule in proposed_rules or []:
        try:
            RULE_EXECUTORS[rule.rule_type](table, dataframe, context, rule)
        except (KeyError, TypeError, ValueError) as error:
            rejected.append(str(error))
    return rejected


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
