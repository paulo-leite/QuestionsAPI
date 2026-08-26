"""Avaliação multivariada de atipicidade."""

import statistics

from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer

from deep_research.models import DataQualityColumnProfile

from .core import AnalysisContext, ParsedTable, looks_like_identifier, parse_number, percentile

MIN_MULTIVARIATE_ROWS = 20
MIN_MULTIVARIATE_COLUMNS = 2
MAX_MULTIVARIATE_COLUMNS = 20
MULTIVARIATE_N_ESTIMATORS = 200
MULTIVARIATE_RANDOM_STATES = (42, 137, 997)
MIN_ANOMALY_VOTE_RATIO = 2 / 3
MIN_OUTLIER_VALUES = 8


def check_univariate(
    table: ParsedTable,
    profiles: list[DataQualityColumnProfile],
    context: AnalysisContext,
) -> None:
    """Detecta valores numéricos fora de 1,5 IQR e atualiza os perfis."""
    indexes = {name: index for index, name in enumerate(table.headers)}
    for profile in profiles:
        if profile.inferred_type != "numerico":
            continue
        numeric_rows = [
            (row.number, parsed)
            for row in table.rows
            if (parsed := parse_number(row.values[indexes[profile.name]])) is not None
        ]
        numeric_values = [value for _, value in numeric_rows]
        if len(numeric_values) < MIN_OUTLIER_VALUES or len(set(numeric_values)) < 4:
            continue
        context.evaluated_dimensions.add("atipicidade")
        sorted_values = sorted(numeric_values)
        q1, q3 = percentile(sorted_values, 0.25), percentile(sorted_values, 0.75)
        iqr = q3 - q1
        if iqr <= 0:
            continue
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outlier_rows = [
            (row, value)
            for row, value in numeric_rows
            if value < lower or value > upper
        ]
        profile.outlier_count = len(outlier_rows)
        if not outlier_rows:
            continue
        context.add_finding(
            dimension="atipicidade", severity="baixa", confidence=0.85,
            scope=f"coluna:{profile.name}", title=f"Valores atípicos em {profile.name}",
            description=f"Foram sinalizados {len(outlier_rows)} valores fora dos limites calculados pelo intervalo interquartil.",
            evidence=[f"linha {row}: {value:g}" for row, value in outlier_rows],
            metrics={"method": "IQR_1.5", "lower_bound": round(lower, 6), "upper_bound": round(upper, 6), "outlier_count": len(outlier_rows)},
            recommendation="Revisar os registros no contexto do domínio antes de corrigir ou remover valores.",
            limitations="Valor atípico não é necessariamente erro; sazonalidade e segmentos não são considerados neste teste.",
        )


def check_multivariate(table: ParsedTable, profiles: list[DataQualityColumnProfile], context: AnalysisContext) -> None:
    """Sinaliza combinações numéricas incomuns com um ensemble de Isolation Forest."""
    if len(table.rows) < MIN_MULTIVARIATE_ROWS:
        return
    numeric_profiles = [
        profile for profile in profiles
        if profile.inferred_type == "numerico"
        and profile.non_missing_count >= MIN_MULTIVARIATE_ROWS // 2
        and profile.distinct_count >= 2
        and (profile.standard_deviation or 0) > 0
        and not looks_like_identifier(profile.name)
    ]
    numeric_profiles.sort(key=lambda profile: (profile.missing_percentage, -profile.distinct_count, profile.name))
    numeric_profiles = numeric_profiles[:MAX_MULTIVARIATE_COLUMNS]
    numeric_profiles.sort(key=lambda profile: table.headers.index(profile.name))
    if len(numeric_profiles) < MIN_MULTIVARIATE_COLUMNS:
        return

    indexes = {name: index for index, name in enumerate(table.headers)}
    matrix = [[parse_number(row.values[indexes[profile.name]]) for profile in numeric_profiles] for row in table.rows]
    imputed = SimpleImputer(strategy="median").fit_transform(matrix)
    labels_by_model: list[list[int]] = []
    scores_by_model: list[list[float]] = []
    for random_state in MULTIVARIATE_RANDOM_STATES:
        model = IsolationForest(
            n_estimators=MULTIVARIATE_N_ESTIMATORS, contamination="auto", max_samples="auto",
            random_state=random_state, n_jobs=1,
        )
        labels_by_model.append(model.fit_predict(imputed).tolist())
        scores_by_model.append(model.decision_function(imputed).tolist())

    robust_centers: list[float] = []
    robust_scales: list[float] = []
    for column_index in range(len(numeric_profiles)):
        present_values: list[float] = []
        for row in matrix:
            value = row[column_index]
            if value is not None:
                present_values.append(value)
        present_values.sort()
        center = statistics.median(present_values)
        scale = 1.4826 * statistics.median(sorted(abs(value - center) for value in present_values))
        if scale == 0:
            scale = (percentile(present_values, 0.75) - percentile(present_values, 0.25)) / 1.349
        if scale == 0:
            scale = statistics.pstdev(present_values)
        robust_centers.append(center)
        robust_scales.append(scale or 1.0)

    model_count = len(MULTIVARIATE_RANDOM_STATES)
    row_diagnostics: list[tuple[int, float, int, str]] = []
    for row_index, row in enumerate(matrix):
        votes = sum(labels[row_index] == -1 for labels in labels_by_model)
        if votes / model_count < MIN_ANOMALY_VOTE_RATIO:
            continue
        mean_score = statistics.fmean(scores[row_index] for scores in scores_by_model)
        deviations = sorted(
            (abs(float(value) - robust_centers[column_index]) / robust_scales[column_index], numeric_profiles[column_index].name, float(value))
            for column_index, value in enumerate(row) if value is not None
        )
        deviations.reverse()
        drivers = ", ".join(f"{name}={value:g} (desvio_robusto={deviation:.2f})" for deviation, name, value in deviations[:2])
        missing_columns = [numeric_profiles[column_index].name for column_index, value in enumerate(row) if value is None]
        if missing_columns:
            drivers += f"; imputadas={','.join(missing_columns)}"
        row_diagnostics.append((table.rows[row_index].number, float(mean_score), votes, drivers))

    flagged = sorted(row_diagnostics, key=lambda item: item[1])
    context.evaluated_dimensions.add("atipicidade")
    if not flagged:
        return
    context.add_finding(
        dimension="atipicidade", severity="baixa", confidence=0.75, scope="dataset",
        title="Combinações numéricas atípicas",
        description=f"O ensemble de Isolation Forest sinalizou {len(flagged)} registros com combinação incomum entre variáveis numéricas e concordância mínima de dois terços dos modelos.",
        evidence=[f"linha {row}: decision_score_medio={score:.6f}; votos={votes}/{model_count}; destaques: {drivers}" for row, score, votes, drivers in flagged],
        metrics={
            "validation_engine": "scikit-learn", "model": "IsolationForest",
            "feature_columns": [profile.name for profile in numeric_profiles], "anomaly_count": len(flagged),
            "evaluated_row_count": len(table.rows), "n_estimators_per_model": MULTIVARIATE_N_ESTIMATORS,
            "ensemble_size": model_count, "random_states": list(MULTIVARIATE_RANDOM_STATES),
            "minimum_vote_ratio": round(MIN_ANOMALY_VOTE_RATIO, 3), "contamination": "auto",
            "imputation_strategy": "median", "decision_threshold": 0.0, "score_interpretation": "menor_mais_atipico",
        },
        recommendation="Revisar os registros no contexto das variáveis combinadas antes de corrigir, excluir ou bloquear os dados.",
        limitations="O escore não é probabilidade de erro e os destaques por desvio robusto são explicações descritivas, não atribuições causais do modelo. Medianas são usadas para valores ausentes; identificadores e colunas constantes são excluídos; segmentos, relações causais e sazonalidade não são considerados.",
    )
