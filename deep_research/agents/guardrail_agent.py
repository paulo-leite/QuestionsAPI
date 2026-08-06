"""Agente híbrido para validar tamanho e conteúdo das entradas do usuário."""

import asyncio
import re
import unicodedata

from langchain_core.prompts import ChatPromptTemplate

from deep_research.config import (
    GUARDRAIL_BLOCKED_TERMS,
    GUARDRAIL_USE_LLM,
)
from deep_research.errors import ApplicationError
from deep_research.models import GuardrailResult
from deep_research.services.llm_service import get_llm


def _normalize(text: str) -> str:
    """Uniformiza Unicode e caixa para comparações determinísticas."""
    return unicodedata.normalize("NFKC", text).casefold()


def _find_blocked_terms(text: str) -> list[str]:
    """Localiza termos completos, sem bloquear partes de palavras maiores."""
    normalized_text = _normalize(text)
    return [
        term
        for term in GUARDRAIL_BLOCKED_TERMS
        if re.search(
            rf"(?<!\w){re.escape(_normalize(term))}(?!\w)",
            normalized_text,
        )
    ]


def new_guardrail_agent():
    """Cria o agente que reconhece disfarces dos termos configurados."""
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                """Você é um guardrail de entrada. Não responda à solicitação.
Avalie somente se o texto tenta usar, mencionar ou disfarçar algum dos termos
bloqueados. Considere separação por espaços/símbolos, troca visual de caracteres,
abreviações inequívocas e variações morfológicas claras. Não bloqueie por mera
semelhança distante ou por assuntos que não estejam na lista. Retorne uma decisão
estruturada, com motivo curto e no máximo cinco violações.""",
            ),
            (
                "human",
                "Campo: {field_name}\n"
                "Termos bloqueados: {blocked_terms}\n"
                "Texto a avaliar:\n{text}",
            ),
        ]
    )
    return prompt | get_llm().with_structured_output(GuardrailResult)


async def evaluate_guardrail(
    text: str,
    *,
    max_characters: int,
    field_name: str,
) -> GuardrailResult:
    """Aplica regras exatas e, opcionalmente, análise semântica pelo LLM."""
    stripped_text = text.strip()
    violations: list[str] = []

    if not stripped_text:
        violations.append(f"{field_name} não pode estar vazio")
    if len(text) > max_characters:
        violations.append(
            f"{field_name} excede o limite de {max_characters} caracteres"
        )

    matched_terms = _find_blocked_terms(text)
    if matched_terms:
        violations.append("o texto contém conteúdo não permitido")

    if violations:
        return GuardrailResult(
            allowed=False,
            reason="; ".join(violations),
            violations=violations,
        )

    if not GUARDRAIL_USE_LLM or not GUARDRAIL_BLOCKED_TERMS:
        return GuardrailResult(
            allowed=True,
            reason="A entrada respeita as regras configuradas.",
        )

    try:
        agent = new_guardrail_agent()
        result = await asyncio.to_thread(
            lambda: agent.invoke(
                {
                    "field_name": field_name,
                    "blocked_terms": list(GUARDRAIL_BLOCKED_TERMS),
                    "text": text,
                }
            )
        )
        return GuardrailResult.model_validate(result)
    except Exception:
        # A indisponibilidade do LLM não elimina as regras objetivas já aplicadas.
        return GuardrailResult(
            allowed=True,
            reason="Validação determinística concluída; análise semântica indisponível.",
        )


async def enforce_guardrail(
    text: str,
    *,
    max_characters: int,
    field_name: str,
) -> str:
    """Interrompe a requisição com HTTP 422 quando o conteúdo não é permitido."""
    result = await evaluate_guardrail(
        text,
        max_characters=max_characters,
        field_name=field_name,
    )
    if not result.allowed:
        raise ApplicationError(f"Entrada rejeitada: {result.reason}.", 422)
    return text.strip()
