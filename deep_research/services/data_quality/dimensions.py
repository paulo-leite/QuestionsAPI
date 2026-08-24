"""Consolidação do status das dimensões avaliadas."""

from typing import Literal

from deep_research.models import DataQualityDimensionResult

from .core import AnalysisContext

DIMENSIONS = (
    "completude", "validade", "consistencia", "atipicidade",
    "qualidade_categorica", "comportamento_temporal", "duplicidade",
    "acuracia_veracidade",
)


def build_dimension_results(context: AnalysisContext) -> list[DataQualityDimensionResult]:
    """Consolida achados e cobertura nos quatro estados possíveis de cada dimensão."""
    results: list[DataQualityDimensionResult] = []
    for dimension in DIMENSIONS:
        status: Literal["aprovada", "atencao", "critica", "nao_avaliada"]
        findings = [finding for finding in context.findings if finding.dimension == dimension]
        high_count = sum(finding.severity == "alta" for finding in findings)
        if dimension not in context.evaluated_dimensions:
            status = "nao_avaliada"
            if dimension == "acuracia_veracidade":
                summary = "Exige fonte externa confiável ou validação explícita do domínio."
            elif dimension == "comportamento_temporal":
                summary = "Envie um CSV de referência para avaliar mudanças de comportamento."
            else:
                summary = "Não havia dados ou relações suficientes para aplicar o teste automático."
        elif high_count:
            status, summary = "critica", f"Foram encontrados {len(findings)} achados, incluindo {high_count} de alta severidade."
        elif findings:
            status, summary = "atencao", f"Foram encontrados {len(findings)} achados que requerem revisão."
        else:
            status, summary = "aprovada", "Nenhum problema foi detectado pelos testes executados nesta dimensão."
        results.append(DataQualityDimensionResult(
            dimension=dimension, status=status, findings_count=len(findings),
            high_severity_count=high_count, summary=summary,
        ))
    return results
