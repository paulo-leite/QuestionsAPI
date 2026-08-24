"""Avaliações de validade estrutural e de formato."""

import pandas as pd
import pandera.pandas as pa
from pandera.api.checks import Check

from deep_research.models import DataQualityColumnProfile

from .core import AnalysisContext, ParsedTable, TYPE_CONFIDENCE_THRESHOLD, is_missing, parse_date, parse_number, value_kind

PANDERA_CHECK_NAMES = {"numerico": "formato_numerico", "data": "formato_data", "booleano": "formato_booleano"}


def _value_is_valid(value: str | None, inferred_type: str) -> bool:
    """Valida uma célula não ausente de acordo com o tipo inferido."""
    if value is None:
        return True
    if inferred_type == "numerico":
        return parse_number(value) is not None
    if inferred_type == "data":
        return parse_date(value) is not None
    if inferred_type == "booleano":
        return value_kind(value) == "booleano"
    return True


def check_formats(table: ParsedTable, profiles: list[DataQualityColumnProfile], context: AnalysisContext) -> None:
    """Executa validações lazy do Pandera e converte falhas em achados."""
    context.evaluated_dimensions.add("validade")
    profile_by_name = {profile.name: profile for profile in profiles}
    schema_columns: dict[str, pa.Column] = {}
    for profile in profiles:
        inferred_type = profile.inferred_type
        if inferred_type not in PANDERA_CHECK_NAMES or profile.type_confidence < TYPE_CONFIDENCE_THRESHOLD or profile.non_missing_count < 3:
            continue
        schema_columns[profile.name] = pa.Column(
            str, nullable=True,
            checks=Check(lambda value, expected=inferred_type: _value_is_valid(value, expected), element_wise=True, name=PANDERA_CHECK_NAMES[inferred_type]),
        )
    if not schema_columns:
        return

    dataframe = pd.DataFrame(
        [{header: None if is_missing(row.values[index]) else row.values[index] for index, header in enumerate(table.headers)} for row in table.rows],
        index=[row.number for row in table.rows],
    )
    schema = pa.DataFrameSchema(schema_columns, strict=False, coerce=False)
    try:
        schema.validate(dataframe, lazy=True)
        return
    except pa.errors.SchemaErrors as error:
        failure_cases = error.failure_cases

    relevant = failure_cases[failure_cases["check"].isin(set(PANDERA_CHECK_NAMES.values()))]
    for column_name, cases in relevant.groupby("column", sort=False):
        profile = profile_by_name[str(column_name)]
        evidence = [f"linha {case.get('index')}: {case.get('failure_case')}" for case in cases.to_dict("records")]
        context.add_finding(
            dimension="validade", severity="media", confidence=profile.type_confidence,
            scope=f"coluna:{column_name}", title=f"Tipos incompatíveis em {column_name}",
            description=f"O Pandera validou a coluna como predominantemente {profile.inferred_type}, mas encontrou {len(cases)} valores com formato incompatível.",
            evidence=evidence,
            metrics={"validation_engine": "pandera", "inferred_type": profile.inferred_type, "type_confidence": profile.type_confidence, "incompatible_count": len(cases), "pandera_check": PANDERA_CHECK_NAMES[profile.inferred_type]},
            recommendation="Validar os valores contra o contrato da coluna e corrigir formatos divergentes.",
            limitations="O esquema foi inferido a partir dos próprios dados; um contrato fornecido pelo domínio aumenta a precisão.",
        )


def check_structural_rows(table: ParsedTable, context: AnalysisContext) -> None:
    """Registra linhas cuja quantidade de campos difere do cabeçalho."""
    if not table.width_mismatches:
        return
    context.evaluated_dimensions.add("validade")
    context.add_finding(
        dimension="validade", severity="alta", confidence=1.0, scope="dataset",
        title="Linhas com quantidade inesperada de colunas",
        description=f"Foram encontradas {len(table.width_mismatches)} linhas cuja largura difere do cabeçalho.",
        evidence=[f"linha {row}: {width} valores; esperado {len(table.headers)}" for row, width in table.width_mismatches],
        metrics={"mismatched_rows": len(table.width_mismatches)},
        recommendation="Verificar delimitadores, aspas e campos ausentes ou excedentes no arquivo de origem.",
    )
