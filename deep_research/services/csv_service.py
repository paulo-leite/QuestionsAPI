"""Leitura e fragmentação manual de CSVs preservando números das linhas."""

import csv
from io import StringIO

from langchain_core.documents import Document

from deep_research.errors import ApplicationError


def _decode_csv(content: bytes) -> str:
    """Decodifica CSVs UTF-8 e arquivos comuns exportados pelo Excel."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ApplicationError(
        "Não foi possível decodificar o CSV. Use UTF-8 ou Windows-1252.", 400
    )


def _get_dialect(text: str) -> csv.Dialect:
    """Detecta o delimitador e usa vírgula quando a amostra é ambígua."""
    try:
        return csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def _normalize_headers(values: list[str]) -> list[str]:
    """Gera nomes utilizáveis para colunas vazias ou repetidas."""
    headers: list[str] = []
    occurrences: dict[str, int] = {}
    for index, value in enumerate(values, start=1):
        base = value.strip() or f"coluna_{index}"
        occurrences[base] = occurrences.get(base, 0) + 1
        suffix = occurrences[base]
        headers.append(base if suffix == 1 else f"{base}_{suffix}")
    return headers


def _format_row(headers: list[str], values: list[str], row_number: int) -> str:
    """Transforma uma linha tabular em texto explícito para busca semântica."""
    padded = values + [""] * max(len(headers) - len(values), 0)
    cells = [
        f"{header}: {value.strip()}"
        for header, value in zip(headers, padded)
    ]
    if len(values) > len(headers):
        cells.extend(
            f"coluna_extra_{index}: {value.strip()}"
            for index, value in enumerate(values[len(headers):], start=1)
        )
    return f"Linha {row_number}\n" + "\n".join(cells)


def _new_document(
    text: str,
    filename: str,
    row_start: int,
    row_end: int,
) -> Document:
    """Cria um chunk com metadados para citar as linhas de origem."""
    return Document(
        page_content=text,
        metadata={
            "source": filename,
            "file_type": "csv",
            "row_start": row_start,
            "row_end": row_end,
            "chunking": "csv_rows",
        },
    )


def create_csv_chunks(content: bytes, filename: str) -> tuple[list[Document], int]:
    """Lê o CSV e cria exatamente um chunk para cada linha de dados."""
    text = _decode_csv(content)
    if not text.strip() or "\x00" in text:
        raise ApplicationError("O CSV está vazio ou possui conteúdo inválido.", 422)

    try:
        rows = list(csv.reader(StringIO(text), dialect=_get_dialect(text)))
    except csv.Error as exc:
        raise ApplicationError(
            "Não foi possível interpretar o arquivo CSV.", 400
        ) from exc

    if not rows or not any(cell.strip() for cell in rows[0]):
        raise ApplicationError("O CSV deve possuir uma linha de cabeçalho.", 422)

    headers = _normalize_headers(rows[0])
    data_rows = [
        (number, values)
        for number, values in enumerate(rows[1:], start=2)
        if any(cell.strip() for cell in values)
    ]
    if not data_rows:
        raise ApplicationError(
            "O CSV não possui linhas de dados utilizáveis.", 422
        )

    chunks = [
        _new_document(
            _format_row(headers, values, row_number),
            filename,
            row_number,
            row_number,
        )
        for row_number, values in data_rows
    ]
    return chunks, len(data_rows)
