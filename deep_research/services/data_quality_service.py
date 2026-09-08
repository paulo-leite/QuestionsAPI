"""Orquestra a auditoria automática e explicável de qualidade para CSVs."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from time import perf_counter
from typing import TypeVar

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

# Herda nível e handlers do Uvicorn para emitir cada etapa INFO em tempo real.
logger = logging.getLogger("uvicorn.error.deep_research.data_quality")

StepResult = TypeVar("StepResult")


def _run_dimension_step(
    step: str,
    context: AnalysisContext,
    operation: Callable[[], StepResult],
) -> StepResult:
    """Executa e registra uma etapa sem incluir valores potencialmente sensíveis."""
    findings_before = len(context.findings)
    dimensions_before = context.evaluated_dimensions.copy()
    started_at = perf_counter()
    logger.info("Qualidade de dados: etapa iniciada [etapa=%s].", step)
    try:
        result = operation()
    except Exception:
        logger.exception(
            "Qualidade de dados: etapa falhou [etapa=%s duracao_ms=%.2f].",
            step,
            (perf_counter() - started_at) * 1000,
        )
        raise

    logger.info(
        "Qualidade de dados: etapa concluída "
        "[etapa=%s duracao_ms=%.2f novos_achados=%d novas_dimensoes=%s].",
        step,
        (perf_counter() - started_at) * 1000,
        len(context.findings) - findings_before,
        sorted(context.evaluated_dimensions - dimensions_before),
    )
    return result


def analyze_csv_quality(
    content: bytes,
    filename: str,
    reference_content: bytes | None = None,
    reference_filename: str | None = None,
) -> DataQualityReport:
    """Analisa qualidade objetiva, estatística e temporal de um CSV."""
    analysis_started_at = perf_counter()
    logger.info(
        "Qualidade de dados: análise iniciada "
        "[arquivo=%r possui_referencia=%s].",
        filename,
        reference_content is not None,
    )
    table = parse_csv(content)
    reference = parse_csv(reference_content) if reference_content is not None else None
    context = AnalysisContext(
        findings=[],
        evaluated_dimensions=set(),
        total_rows=len(table.rows),
    )

    _run_dimension_step(
        "validade_estrutural",
        context,
        lambda: check_structural_rows(table, context),
    )
    profiling = _run_dimension_step(
        "perfil_e_completude",
        context,
        lambda: profile_columns(table, context),
    )
    profiles = profiling.profiles
    _run_dimension_step(
        "validade_de_formatos",
        context,
        lambda: check_formats(table, profiles, context),
    )
    _run_dimension_step(
        "atipicidade_univariada",
        context,
        lambda: check_univariate(table, profiles, context),
    )
    _run_dimension_step(
        "atipicidade_multivariada",
        context,
        lambda: check_multivariate(table, profiles, context),
    )
    _run_dimension_step(
        "categorias_raras",
        context,
        lambda: check_rare_categories(table, profiles, context),
    )
    _run_dimension_step(
        "similaridade_de_categorias",
        context,
        lambda: check_category_similarity(table, profiles, context),
    )
    agent_rules = []
    agent_limitations: list[str] = []
    try:
        agent_rules = _run_dimension_step(
            "proposta_de_regras_de_consistencia",
            context,
            lambda: propose_consistency_rules(table, profiles, filename).rules,
        )
    except Exception as error:
        agent_limitations.append(
            "O agente de consistência não pôde propor regras; "
            f"as verificações determinísticas continuaram ({type(error).__name__})."
        )
        logger.warning(
            "Qualidade de dados: análise continuará sem regras propostas pelo agente "
            "[tipo_erro=%s].",
            type(error).__name__,
        )
    rejected_rules = _run_dimension_step(
        "consistencia",
        context,
        lambda: check_consistency(table, context, agent_rules),
    )
    if rejected_rules:
        agent_limitations.append(
            f"O executor rejeitou {len(rejected_rules)} regra(s) proposta(s) por não atenderem ao contrato seguro."
        )
        logger.warning(
            "Qualidade de dados: regras de consistência rejeitadas "
            "[quantidade=%d].",
            len(rejected_rules),
        )
    duplicate_count = _run_dimension_step(
        "duplicidade_exata",
        context,
        lambda: check_exact_duplicates(table, context),
    )
    _run_dimension_step(
        "duplicidade_aproximada",
        context,
        lambda: check_approximate_duplicates(table, profiles, context),
    )
    if reference is not None:
        _run_dimension_step(
            "consistencia_entre_fontes",
            context,
            lambda: check_cross_source_consistency(table, reference, context),
        )
        _run_dimension_step(
            "comportamento_temporal",
            context,
            lambda: check_drift(table, reference, profiles, context),
        )
    else:
        logger.info(
            "Qualidade de dados: etapas dependentes de referência ignoradas "
            "[etapas=%s].",
            ["consistencia_entre_fontes", "comportamento_temporal"],
        )

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
    dimensions = build_dimension_results(context)
    for dimension in dimensions:
        logger.info(
            "Qualidade de dados: dimensão consolidada "
            "[dimensao=%s status=%s achados=%d alta_severidade=%d].",
            dimension.dimension,
            dimension.status,
            dimension.findings_count,
            dimension.high_severity_count,
        )

    report = DataQualityReport(
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
        dimensions=dimensions,
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
    logger.info(
        "Qualidade de dados: análise concluída "
        "[arquivo=%r duracao_ms=%.2f linhas=%d colunas=%d achados=%d].",
        filename,
        (perf_counter() - analysis_started_at) * 1000,
        len(table.rows),
        len(table.headers),
        len(context.findings),
    )
    return report
