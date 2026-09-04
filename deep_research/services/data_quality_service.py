"""Orquestra a auditoria automática e explicável de qualidade para CSVs."""

from __future__ import annotations

import os

# Evita telemetria em auditorias locais e no processo da API.
os.environ.setdefault("DO_NOT_TRACK", "1")

from deep_research.agents.consistency_agent import propose_consistency_rules
from deep_research.models import DataQualityDatasetSummary, DataQualityReport

from .data_quality.categorical import check_category_similarity, check_rare_categories
from .data_quality.consistency import check_consistency, check_cross_source_consistency
from .data_quality.core import AnalysisContext, is_missing, parse_csv, round_percentage
from .data_quality.dimensions import build_dimension_results
from .data_quality.drift import check_drift
from .data_quality.duplicates import check_approximate_duplicates, check_exact_duplicates
from .data_quality.outliers import check_multivariate, check_univariate
from .data_quality.profiling import profile_columns
from .data_quality.validity import check_formats, check_structural_rows


def analyze_csv_quality(
    content: bytes,
    filename: str,
    reference_content: bytes | None = None,
    reference_filename: str | None = None,
) -> DataQualityReport:
    """Analisa qualidade objetiva, estatística e temporal de um CSV."""
    table = parse_csv(content)
    reference = parse_csv(reference_content) if reference_content is not None else None
    context = AnalysisContext(
        findings=[],
        evaluated_dimensions=set(),
        total_rows=len(table.rows),
    )

    check_structural_rows(table, context)
    profiling = profile_columns(table, context)
    profiles = profiling.profiles
    check_formats(table, profiles, context)
    check_univariate(table, profiles, context)
    check_multivariate(table, profiles, context)
    check_rare_categories(table, profiles, context)
    check_category_similarity(table, profiles, context)
    agent_rules = []
    agent_limitations: list[str] = []
    try:
        agent_rules = propose_consistency_rules(table, profiles, filename).rules
    except Exception as error:
        agent_limitations.append(
            "O agente de consistência não pôde propor regras; "
            f"as verificações determinísticas continuaram ({type(error).__name__})."
        )
    rejected_rules = check_consistency(table, context, agent_rules)
    if rejected_rules:
        agent_limitations.append(
            f"O executor rejeitou {len(rejected_rules)} regra(s) proposta(s) por não atenderem ao contrato seguro."
        )
    duplicate_count = check_exact_duplicates(table, context)
    check_approximate_duplicates(table, profiles, context)
    if reference is not None:
        check_cross_source_consistency(table, reference, context)
        check_drift(table, reference, profiles, context)

    total_cells = len(table.rows) * len(table.headers)
    missing_cells = sum(is_missing(value) for row in table.rows for value in row.values)
    context.findings.sort(
        key=lambda finding: (
            {"alta": 0, "media": 1, "baixa": 2}[finding.severity],
            finding.finding_id,
        )
    )
    findings_by_severity = {
        severity: sum(finding.severity == severity for finding in context.findings)
        for severity in ("alta", "media", "baixa")
    }
    return DataQualityReport(
        analysis_version="1.6.0",
        validation_engines=list(dict.fromkeys([
            profiling.engine,
            "pandera",
            "scikit-learn",
            "rapidfuzz",
            "splink",
            *(["evidently"] if reference is not None else []),
            *(["llm-rule-proposal", "agent-rule-executor"] if agent_rules else []),
            "native",
        ])),
        filename=filename,
        reference_filename=reference_filename,
        dataset=DataQualityDatasetSummary(
            rows=len(table.rows),
            columns=len(table.headers),
            cells=total_cells,
            missing_cells=missing_cells,
            missing_percentage=round_percentage(missing_cells, total_cells),
            exact_duplicate_rows=duplicate_count,
        ),
        dimensions=build_dimension_results(context),
        columns=profiles,
        findings=context.findings,
        findings_by_severity=findings_by_severity,
        limitations=[
            "A análise automática não comprova acurácia ou veracidade sem fonte externa confiável.",
            "Ausência, tipo, categorias e relações de datas são inferidos; um contrato de domínio aumenta a precisão.",
            "Valores atípicos e mudanças de distribuição são sinais para investigação, não erros comprovados.",
            "Os pares indicados pelo Splink são candidatos determinísticos e devem ser revisados antes da consolidação.",
            "Consistência entre fontes exige configuração específica de domínio.",
            *agent_limitations,
        ],
    )
