"""Modelos usados nas rotas, pesquisa e auditoria de dados."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from .config import MAX_RESEARCH_ROUNDS


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    file_type: str
    pages: int | None = None
    rows: int | None = None
    chunks: int
    chunking_method: str
    max_tokens_per_chunk: int
    minimum_chunk_tokens: int
    average_chunk_tokens: int
    maximum_chunk_tokens: int
    average_chunk_characters: int


class QuestionRequest(BaseModel):
    document_id: str
    question: str = Field(min_length=3)


class Source(BaseModel):
    page: int | None = None
    row_start: int | None = None
    row_end: int | None = None
    excerpt: str

    def location_label(self) -> str:
        """Formata a localização da evidência em um PDF ou CSV."""
        if self.row_start is not None:
            end = self.row_end or self.row_start
            return (
                f"linha {self.row_start}"
                if self.row_start == end
                else f"linhas {self.row_start}-{end}"
            )
        return f"página {self.page}"


class QuestionResponse(BaseModel):
    answer: str
    sources: list[Source]


class ResearchRequest(BaseModel):
    document_id: str
    question: str = Field(min_length=3)
    depth: int = Field(default=2, ge=1, le=MAX_RESEARCH_ROUNDS)


class DocumentSearchItem(BaseModel):
    query: str
    reason: str


class DocumentSearchPlan(BaseModel):
    searches: list[DocumentSearchItem]


class ResearchFinding(BaseModel):
    subquestion: str
    answer: str
    sources: list[Source]
    evidence_count: int
    error: str | None = None


class ResearchReview(BaseModel):
    unsupported_subquestions: list[str]
    conflicting_subquestions: list[str]
    follow_up_questions: list[str]


class SufficiencyResult(BaseModel):
    is_sufficient: bool
    reason: str
    missing_information: list[str] = Field(default_factory=list, max_length=4)


class ResearchResponse(BaseModel):
    answer: str
    findings: list[ResearchFinding]
    review: ResearchReview
    sources: list[Source]
    rounds_completed: int
    sufficiency_check: SufficiencyResult


class ReportData(BaseModel):
    short_summary: str
    markdown_report: str
    follow_up_questions: list[str]


class TriageResult(BaseModel):
    needs_clarification: bool
    reason: str


class ClarificationQuestions(BaseModel):
    questions: list[str] = Field(min_length=1, max_length=3)


class ClarificationAnswer(BaseModel):
    answer: str = Field(min_length=1)


class GuardrailResult(BaseModel):
    """Decisão produzida pelo agente de proteção de entradas textuais."""

    allowed: bool
    reason: str
    violations: list[str] = Field(default_factory=list, max_length=5)


class ResearchState(BaseModel):
    session_id: str
    document_id: str
    original_query: str
    depth: int
    status: str = "pending"
    clarification_questions: list[str] = Field(default_factory=list)
    clarification_responses: list[str] = Field(default_factory=list)
    report_data: ReportData | None = None
    findings: list[ResearchFinding] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
    rounds_completed: int = 0
    sufficiency_check: SufficiencyResult | None = None

    def answer_question(self, answer: str) -> bool:
        """Registra a resposta e indica se ainda existem perguntas pendentes."""
        self.clarification_responses.append(answer)
        return len(self.clarification_responses) < len(self.clarification_questions)


class DataQualityTopValue(BaseModel):
    value: str
    count: int
    percentage: float


class DataQualityColumnProfile(BaseModel):
    name: str
    inferred_type: str
    type_confidence: float
    non_missing_count: int
    missing_count: int
    missing_percentage: float
    distinct_count: int
    distinct_percentage: float
    minimum: float | str | None = None
    maximum: float | str | None = None
    mean: float | None = None
    median: float | None = None
    standard_deviation: float | None = None
    outlier_count: int = 0
    top_values: list[DataQualityTopValue] = Field(default_factory=list)


class DataQualityFinding(BaseModel):
    finding_id: str
    dimension: str
    severity: Literal["baixa", "media", "alta"]
    confidence: float = Field(ge=0, le=1)
    scope: str
    title: str
    description: str
    evidence: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    recommendation: str
    limitations: str | None = None


class DataQualityDimensionResult(BaseModel):
    dimension: str
    status: Literal["aprovada", "atencao", "critica", "nao_avaliada"]
    findings_count: int
    high_severity_count: int
    summary: str


class DataQualityDatasetSummary(BaseModel):
    rows: int
    columns: int
    cells: int
    missing_cells: int
    missing_percentage: float
    exact_duplicate_rows: int


class DataQualityReport(BaseModel):
    analysis_version: str
    validation_engines: list[str]
    filename: str
    reference_filename: str | None = None
    dataset: DataQualityDatasetSummary
    dimensions: list[DataQualityDimensionResult]
    columns: list[DataQualityColumnProfile]
    findings: list[DataQualityFinding]
    findings_by_severity: dict[str, int]
    limitations: list[str]


class DocumentUploadResponse(UploadResponse):
    """Resultado do upload, incluindo a auditoria automática para CSVs."""

    data_quality: DataQualityReport | None = None
