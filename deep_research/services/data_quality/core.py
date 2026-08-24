"""Tipos, constantes e conversores compartilhados pelas dimensões."""

from __future__ import annotations

import csv
import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from io import StringIO
from typing import Literal

from deep_research.errors import ApplicationError
from deep_research.models import DataQualityFinding
from deep_research.services.csv_service import _decode_csv, _get_dialect, _normalize_headers

MISSING_MARKERS = {"", "null", "none", "n/a", "na", "nan"}
MAX_EVIDENCE = 10
TYPE_CONFIDENCE_THRESHOLD = 0.80


@dataclass(frozen=True)
class TableRow:
    number: int
    values: tuple[str, ...]


@dataclass(frozen=True)
class ParsedTable:
    headers: tuple[str, ...]
    rows: tuple[TableRow, ...]
    width_mismatches: tuple[tuple[int, int], ...]


@dataclass
class AnalysisContext:
    findings: list[DataQualityFinding]
    evaluated_dimensions: set[str]
    next_finding_number: int = 1

    def add_finding(
        self,
        *,
        dimension: str,
        severity: Literal["baixa", "media", "alta"],
        confidence: float,
        scope: str,
        title: str,
        description: str,
        recommendation: str,
        evidence: list[str] | None = None,
        metrics: dict | None = None,
        limitations: str | None = None,
    ) -> None:
        """Cria um achado numerado, limita evidências e o adiciona ao contexto."""
        finding_id = f"DQ-{self.next_finding_number:04d}"
        self.next_finding_number += 1
        self.findings.append(
            DataQualityFinding(
                finding_id=finding_id,
                dimension=dimension,
                severity=severity,
                confidence=round(confidence, 3),
                scope=scope,
                title=title,
                description=description,
                evidence=(evidence or [])[:MAX_EVIDENCE],
                metrics=metrics or {},
                recommendation=recommendation,
                limitations=limitations,
            )
        )


def round_percentage(numerator: int | float, denominator: int | float) -> float:
    """Calcula um percentual arredondado, tratando denominador zero."""
    if not denominator:
        return 0.0
    return round(100 * numerator / denominator, 2)


def is_missing(value: str) -> bool:
    """Indica se um texto representa ausência segundo os marcadores aceitos."""
    return value.strip().casefold() in MISSING_MARKERS


def parse_csv(content: bytes) -> ParsedTable:
    """Decodifica e normaliza um CSV, preservando números de linha e irregularidades."""
    text = _decode_csv(content)
    if not text.strip() or "\x00" in text:
        raise ApplicationError("O CSV está vazio ou possui conteúdo inválido.", 422)
    try:
        raw_rows = list(csv.reader(StringIO(text), dialect=_get_dialect(text)))
    except csv.Error as exc:
        raise ApplicationError("Não foi possível interpretar o arquivo CSV.", 400) from exc
    if not raw_rows or not any(cell.strip() for cell in raw_rows[0]):
        raise ApplicationError("O CSV deve possuir uma linha de cabeçalho.", 422)

    headers = tuple(_normalize_headers(raw_rows[0]))
    rows: list[TableRow] = []
    mismatches: list[tuple[int, int]] = []
    for number, raw_values in enumerate(raw_rows[1:], start=2):
        if not any(cell.strip() for cell in raw_values):
            continue
        if len(raw_values) != len(headers):
            mismatches.append((number, len(raw_values)))
        normalized = (raw_values + [""] * len(headers))[: len(headers)]
        rows.append(TableRow(number, tuple(value.strip() for value in normalized)))
    if not rows:
        raise ApplicationError("O CSV não possui linhas de dados utilizáveis.", 422)
    return ParsedTable(headers, tuple(rows), tuple(mismatches))


def parse_number(value: str) -> float | None:
    """Converte formatos numéricos usuais em português ou inglês para ponto flutuante."""
    candidate = value.strip().replace(" ", "")
    if not candidate:
        return None
    if re.fullmatch(r"[+-]?\d+", candidate):
        return float(candidate)
    if re.fullmatch(r"[+-]?\d+[.,]\d+", candidate):
        candidate = candidate.replace(",", ".")
    elif re.fullmatch(r"[+-]?\d{1,3}(?:\.\d{3})*,\d+", candidate):
        candidate = candidate.replace(".", "").replace(",", ".")
    try:
        parsed = float(candidate)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def parse_date(value: str) -> datetime | None:
    """Converte formatos de data suportados e normaliza timestamps conscientes para UTC."""
    candidate = value.strip()
    if not candidate:
        return None
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        pass
    for date_format in ("%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(candidate, date_format)
        except ValueError:
            continue
    return None


def value_kind(value: str) -> str:
    """Classifica um valor presente como booleano, numérico, data ou texto."""
    folded = value.strip().casefold()
    if folded in {"true", "false", "sim", "não", "nao", "yes", "no"}:
        return "booleano"
    if parse_number(value) is not None:
        return "numerico"
    if parse_date(value) is not None:
        return "data"
    return "texto"


def percentile(sorted_values: list[float], proportion: float) -> float:
    """Calcula um percentil interpolado sobre valores previamente ordenados."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    position = (len(sorted_values) - 1) * proportion
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return sorted_values[lower] * (1 - fraction) + sorted_values[upper] * fraction


def normalize_name(value: str) -> str:
    """Normaliza um nome para tokens ASCII minúsculos separados por sublinhado."""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.casefold()).strip("_")


def looks_like_identifier(column_name: str) -> bool:
    """Infere pelo nome se uma coluna provavelmente representa um identificador."""
    tokens = set(normalize_name(column_name).split("_"))
    return bool(tokens & {"id", "identifier", "codigo", "code", "key", "chave"})
