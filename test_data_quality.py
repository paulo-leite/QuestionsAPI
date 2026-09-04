"""Testes do analisador automático de qualidade de dados."""

import unittest
from unittest.mock import patch

from deep_research.models import ConsistencyRuleSet, ConsistencyRuleSpec
from deep_research.services.data_quality.consistency import check_consistency
from deep_research.services.data_quality.core import AnalysisContext, parse_csv
from deep_research.services.data_quality_service import analyze_csv_quality


CURRENT_CSV = b"""id,name,age,start_date,end_date,status
1,Ana,20,2024-01-03,2024-01-01,ok
2,Bia,,2024-01-01,2024-01-02,ok
3,Caio,25,2024-01-01,2024-01-02,ok
3,Caio,25,2024-01-01,2024-01-02,ok
4,Duda,1000,2024-01-01,2024-01-02,alerta
5,Eva,30,2024-01-01,2024-01-02,ok
6,Fabio,31,2024-01-01,2024-01-02,ok
7,Gabi,32,2024-01-01,2024-01-02,ok
8,Hugo,33,2024-01-01,2024-01-02,ok
9,Iara,34,2024-01-01,2024-01-02,ok
10,Joao,35,2024-01-01,2024-01-02,ok
11,Katia,invalido,2024-01-01,2024-01-02,ok
"""

REFERENCE_CSV = b"""id,name,age,start_date,end_date,status
1,Ana,20,2024-01-01,2024-01-02,ok
2,Bia,21,2024-01-01,2024-01-02,ok
3,Caio,22,2024-01-01,2024-01-02,ok
4,Duda,23,2024-01-01,2024-01-02,ok
5,Eva,24,2024-01-01,2024-01-02,ok
6,Fabio,25,2024-01-01,2024-01-02,ok
7,Gabi,26,2024-01-01,2024-01-02,ok
8,Hugo,27,2024-01-01,2024-01-02,ok
9,Iara,28,2024-01-01,2024-01-02,ok
10,Joao,29,2024-01-01,2024-01-02,ok
"""


class DataQualityAnalysisTest(unittest.TestCase):
    def setUp(self) -> None:
        self.consistency_agent_patcher = patch(
            "deep_research.services.data_quality_service.propose_consistency_rules"
        )
        self.propose_consistency_rules = self.consistency_agent_patcher.start()
        self.propose_consistency_rules.return_value = ConsistencyRuleSet()

    def tearDown(self) -> None:
        self.consistency_agent_patcher.stop()

    def test_detects_objective_and_statistical_problems(self) -> None:
        report = analyze_csv_quality(CURRENT_CSV, "current.csv")

        self.assertEqual(report.dataset.rows, 12)
        self.assertEqual(report.dataset.exact_duplicate_rows, 1)
        dimensions = {finding.dimension for finding in report.findings}
        self.assertIn("completude", dimensions)
        self.assertIn("validade", dimensions)
        self.assertIn("consistencia", dimensions)
        self.assertIn("atipicidade", dimensions)
        self.assertIn("duplicidade", dimensions)
        accuracy = next(
            item for item in report.dimensions
            if item.dimension == "acuracia_veracidade"
        )
        self.assertEqual(accuracy.status, "nao_avaliada")
        validity = next(
            finding for finding in report.findings
            if finding.dimension == "validade"
            and finding.scope == "coluna:age"
        )
        self.assertEqual(validity.metrics["validation_engine"], "pandera")
        self.assertIn("linha 13: invalido", validity.evidence)

    def test_compares_current_data_with_reference(self) -> None:
        report = analyze_csv_quality(
            CURRENT_CSV,
            "current.csv",
            reference_content=REFERENCE_CSV,
            reference_filename="reference.csv",
        )

        temporal = [
            finding for finding in report.findings
            if finding.dimension == "comportamento_temporal"
        ]
        self.assertTrue(temporal)
        self.assertEqual(report.reference_filename, "reference.csv")
        self.assertIn("evidently", report.validation_engines)

    def test_preserves_dimensions_instead_of_overall_score(self) -> None:
        report = analyze_csv_quality(CURRENT_CSV, "current.csv")
        payload = report.model_dump()

        self.assertNotIn("score", payload)
        self.assertEqual(len(report.dimensions), 8)
        self.assertIn("pandera", report.validation_engines)

    def test_evidently_manages_column_profile_metrics(self) -> None:
        content = b"""amount,category
1,a
2,a
null,
4,b
4,b
"""

        report = analyze_csv_quality(content, "profiles.csv")
        profiles = {profile.name: profile for profile in report.columns}
        amount = profiles["amount"]
        category = profiles["category"]

        self.assertIn("evidently", report.validation_engines)
        self.assertEqual(amount.missing_count, 1)
        self.assertEqual(amount.non_missing_count, 4)
        self.assertEqual(amount.minimum, 1.0)
        self.assertEqual(amount.maximum, 4.0)
        self.assertEqual(amount.mean, 2.75)
        self.assertEqual(amount.median, 3.0)
        self.assertAlmostEqual(amount.standard_deviation, 1.299038)
        self.assertEqual(category.distinct_count, 2)
        self.assertEqual(
            [(value.value, value.count) for value in category.top_values],
            [("a", 2), ("b", 2)],
        )
        completeness = next(
            finding for finding in report.findings
            if finding.dimension == "completude"
            and finding.scope == "coluna:amount"
        )
        self.assertEqual(completeness.metrics["validation_engine"], "evidently")

    @patch(
        "deep_research.services.data_quality.profiling.Report.run",
        side_effect=RuntimeError("indisponível"),
    )
    def test_profile_falls_back_to_native_engine(self, _run) -> None:
        content = b"amount,category\n1,a\n2,b\n"

        with patch(
            "deep_research.services.data_quality.profiling.warnings.warn"
        ) as warn:
            report = analyze_csv_quality(content, "fallback.csv")

        warn.assert_called_once()
        self.assertIn("native", report.validation_engines)
        self.assertNotIn("evidently", report.validation_engines)
        amount = next(profile for profile in report.columns if profile.name == "amount")
        self.assertEqual(amount.mean, 1.5)

    def test_does_not_compare_mixed_timezone_dates(self) -> None:
        content = (
            b"start_date,end_date\n"
            b"2024-01-02T00:00:00Z,2024-01-01T21:00:00\n"
        )

        report = analyze_csv_quality(content, "dates.csv")

        consistency = next(
            item for item in report.dimensions
            if item.dimension == "consistencia"
        )
        self.assertEqual(consistency.status, "nao_avaliada")
        self.assertFalse(
            any(finding.dimension == "consistencia" for finding in report.findings)
        )

    def test_consistency_requires_comparable_dates(self) -> None:
        content = b"start_date,end_date\nfoo,bar\nbaz,qux\n"

        report = analyze_csv_quality(content, "invalid-dates.csv")
        consistency = next(
            item for item in report.dimensions
            if item.dimension == "consistencia"
        )

        self.assertEqual(consistency.status, "nao_avaliada")

    def test_consistency_normalizes_explicit_timezones(self) -> None:
        content = (
            b"start_date,end_date\n"
            b"2025-01-01T12:00:00Z,2025-01-01T09:00:00-03:00\n"
        )

        report = analyze_csv_quality(content, "aware-dates.csv")
        consistency = next(
            item for item in report.dimensions
            if item.dimension == "consistencia"
        )

        self.assertEqual(consistency.status, "aprovada")
        self.assertFalse(
            any(finding.dimension == "consistencia" for finding in report.findings)
        )

    def test_consistency_pairs_only_complete_name_tokens(self) -> None:
        content = b"fromage,toage\n2025-02-01,2025-01-01\n"

        report = analyze_csv_quality(content, "unrelated-columns.csv")
        consistency = next(
            item for item in report.dimensions
            if item.dimension == "consistencia"
        )

        self.assertEqual(consistency.status, "nao_avaliada")

    def test_consistency_reports_auditable_metrics(self) -> None:
        content = b"""start_date,end_date
2025-02-01,2025-01-01
2025-01-01,2025-02-01
,2025-02-01
data-invalida,2025-02-01
01/02/2025,02/03/2025
2025-01-01T00:00:00Z,2025-02-01T00:00:00
"""

        report = analyze_csv_quality(content, "date-metrics.csv")
        finding = next(
            finding for finding in report.findings
            if finding.dimension == "consistencia"
        )

        self.assertEqual(finding.metrics["comparable_rows"], 2)
        self.assertEqual(finding.metrics["inconsistent_rows"], 1)
        self.assertEqual(finding.metrics["skipped_missing_rows"], 1)
        self.assertEqual(finding.metrics["skipped_invalid_rows"], 1)
        self.assertEqual(finding.metrics["skipped_ambiguous_rows"], 1)
        self.assertEqual(finding.metrics["skipped_timezone_mismatch_rows"], 1)
        self.assertEqual(finding.metrics["inconsistency_percentage"], 50.0)
        self.assertEqual(finding.confidence_percentage, 98.0)
        self.assertEqual(finding.coverage_percentage, 33.33)
        self.assertIn(
            "validação determinística com pandera",
            finding.confidence_basis,
        )
        self.assertIn(
            "regra auditável: date_start_not_after_end",
            finding.confidence_basis,
        )
        self.assertIsNone(finding.veracity_confidence)
        self.assertEqual(
            finding.model_dump()["confidence_percentage"],
            98.0,
        )

    def test_consistency_detects_numeric_range_contradiction(self) -> None:
        content = b"""product_id,price_min,price_max
1,10,20
2,30,25
3,,40
"""

        report = analyze_csv_quality(content, "ranges.csv")
        finding = next(
            finding for finding in report.findings
            if finding.metrics.get("rule")
            == "numeric_lower_not_greater_than_upper"
        )

        self.assertEqual(finding.metrics["comparable_rows"], 2)
        self.assertEqual(finding.metrics["inconsistent_rows"], 1)
        self.assertIn("linha 3: 30 > 25", finding.evidence)

    def test_consistency_detects_conflict_between_related_records(self) -> None:
        content = b"""customer_id,customer_name,status
1,Ana,active
1,Ana Maria,inactive
2,Bia,active
2,Bia,inactive
"""

        report = analyze_csv_quality(content, "related.csv")
        finding = next(
            finding for finding in report.findings
            if finding.metrics.get("rule") == "stable_attribute_per_entity"
        )

        self.assertEqual(finding.metrics["key_column"], "customer_id")
        self.assertEqual(finding.metrics["attribute_column"], "customer_name")
        self.assertEqual(finding.metrics["entity"], "customer")
        self.assertEqual(
            finding.metrics["association_method"],
            "semantic_name_inference",
        )
        self.assertEqual(finding.metrics["compared_entities"], 2)
        self.assertEqual(finding.metrics["conflicting_entities"], 1)
        self.assertIn("customer_id=1", finding.evidence[0])

    def test_consistency_detects_conflict_between_sources(self) -> None:
        current = b"""customer_id,customer_name
1,Ana Maria
2,Bia
"""
        reference = b"""customer_id,customer_name
1,Ana Silva
2,Bia
"""

        report = analyze_csv_quality(
            current,
            "current.csv",
            reference_content=reference,
            reference_filename="reference.csv",
        )
        finding = next(
            finding for finding in report.findings
            if finding.metrics.get("rule") == "stable_attribute_across_sources"
        )

        self.assertEqual(finding.scope, "fontes:customer_id,customer_name")
        self.assertEqual(finding.metrics["entity"], "customer")
        self.assertEqual(finding.metrics["compared_entities"], 2)
        self.assertEqual(finding.metrics["conflicting_entities"], 1)
        self.assertIn("customer_id=1", finding.evidence[0])

    def test_consistency_rejects_attributes_from_another_entity(self) -> None:
        content = b"""codigo_unidade_gestora,nome_proponente
304050,CAVALCANTI E MENDES ADVOGADOS ASSOCIADOS
304050,CLAIR E LEITAO CONTABILIDADE PUBLICA LTDA
304050,ELTON JEAN SERAFIM FERREIRA
"""

        report = analyze_csv_quality(content, "invalid-association.csv")

        self.assertFalse(
            any(
                finding.metrics.get("rule") == "stable_attribute_per_entity"
                for finding in report.findings
            )
        )

    def test_consistency_accepts_attributes_from_the_same_entity(self) -> None:
        content = b"""codigo_proponente,nome_proponente
10,Empresa Alfa
10,Empresa Alfa Ltda
20,Empresa Beta
20,Empresa Beta
"""

        report = analyze_csv_quality(content, "valid-association.csv")
        finding = next(
            finding for finding in report.findings
            if finding.metrics.get("rule") == "stable_attribute_per_entity"
        )

        self.assertEqual(finding.metrics["entity"], "proponente")
        self.assertEqual(finding.metrics["key_column"], "codigo_proponente")
        self.assertEqual(finding.metrics["attribute_column"], "nome_proponente")

    def test_pandera_collects_failures_from_multiple_columns(self) -> None:
        content = b"""flag,event_date
true,2026-01-01
false,2026-01-02
sim,2026-01-03
nao,2026-01-04
invalido,data-invalida
"""

        report = analyze_csv_quality(content, "typed.csv")
        pandera_findings = [
            finding for finding in report.findings
            if finding.metrics.get("validation_engine") == "pandera"
        ]

        self.assertEqual(len(pandera_findings), 2)
        self.assertEqual(
            {finding.scope for finding in pandera_findings},
            {"coluna:flag", "coluna:event_date"},
        )

    def test_evidently_detects_numeric_and_categorical_drift(self) -> None:
        reference_rows = ["number,category"] + [
            f"{number},{'a' if number < 80 else 'b'}"
            for number in range(100)
        ]
        current_rows = ["number,category"] + [
            f"{number},{'a' if number < 110 else 'c'}"
            for number in range(100, 200)
        ]

        report = analyze_csv_quality(
            ("\n".join(current_rows) + "\n").encode(),
            "current.csv",
            reference_content=("\n".join(reference_rows) + "\n").encode(),
            reference_filename="reference.csv",
        )
        evidently_findings = [
            finding for finding in report.findings
            if finding.metrics.get("validation_engine") == "evidently"
        ]

        self.assertEqual(
            {finding.scope for finding in evidently_findings},
            {"coluna:number", "coluna:category"},
        )
        self.assertTrue(
            all(
                finding.metrics["test_status"] == "FAIL"
                for finding in evidently_findings
            )
        )

    def test_sklearn_detects_multivariate_anomalies(self) -> None:
        rows = ["measure_a,measure_b"] + [
            f"{100 + index % 4},{200 + index % 5}" for index in range(39)
        ] + ["10000,-9000"]

        report = analyze_csv_quality(
            ("\n".join(rows) + "\n").encode(),
            "multivariate.csv",
        )
        findings = [
            finding for finding in report.findings
            if finding.metrics.get("validation_engine") == "scikit-learn"
        ]

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].metrics["model"], "IsolationForest")
        self.assertIn("linha 41", " ".join(findings[0].evidence))
        self.assertEqual(findings[0].metrics["imputation_strategy"], "median")
        self.assertEqual(findings[0].metrics["ensemble_size"], 3)
        self.assertIn("desvio_robusto", findings[0].evidence[0])

    def test_sklearn_ignores_identifiers_and_constant_columns(self) -> None:
        rows = ["customer_id,constant,measure_a,measure_b"] + [
            f"{10_000 + index},7,{100 + index % 4},{200 + index % 5}"
            for index in range(39)
        ] + ["999999,7,10000,-9000"]

        report = analyze_csv_quality(
            ("\n".join(rows) + "\n").encode(),
            "multivariate-with-id.csv",
        )
        finding = next(
            finding for finding in report.findings
            if finding.metrics.get("validation_engine") == "scikit-learn"
        )

        self.assertEqual(
            finding.metrics["feature_columns"],
            ["measure_a", "measure_b"],
        )
        self.assertIn("linha 41", " ".join(finding.evidence))

    def test_sklearn_imputes_missing_values_and_is_deterministic(self) -> None:
        rows = ["measure_a,measure_b"] + [
            f"{100 + index % 4},{'' if index == 5 else 200 + index % 5}"
            for index in range(39)
        ] + ["10000,-9000"]
        content = ("\n".join(rows) + "\n").encode()

        first = analyze_csv_quality(content, "missing.csv")
        second = analyze_csv_quality(content, "missing.csv")
        first_finding = next(
            finding for finding in first.findings
            if finding.metrics.get("validation_engine") == "scikit-learn"
        )
        second_finding = next(
            finding for finding in second.findings
            if finding.metrics.get("validation_engine") == "scikit-learn"
        )

        self.assertEqual(first_finding.evidence, second_finding.evidence)
        self.assertEqual(first_finding.metrics, second_finding.metrics)

    def test_rapidfuzz_detects_similar_categories(self) -> None:
        categories = ["Sao Paulo"] * 9 + ["Rio de Janeiro"] * 10 + ["Sao Pauloo"]
        rows = ["city"] + categories

        report = analyze_csv_quality(
            ("\n".join(rows) + "\n").encode(),
            "categories.csv",
        )
        finding = next(
            finding for finding in report.findings
            if finding.metrics.get("validation_engine") == "rapidfuzz"
        )

        self.assertEqual(finding.scope, "coluna:city")
        self.assertIn("Sao Paulo", finding.evidence[0])
        self.assertIn("Sao Pauloo", finding.evidence[0])

    def test_splink_detects_approximate_duplicate_candidates(self) -> None:
        rows = ["customer_name,city"]
        rows.extend(
            [
                "Ana Maria Silva,Sao Paulo",
                "Ana Maria Silba,Sao Paulo",
            ]
        )
        rows.extend(
            f"Cliente Numero {index:02d},{'Sao Paulo' if index % 2 else 'Recife'}"
            for index in range(3, 21)
        )

        report = analyze_csv_quality(
            ("\n".join(rows) + "\n").encode(),
            "customers.csv",
        )
        finding = next(
            finding for finding in report.findings
            if finding.metrics.get("validation_engine") == "splink"
        )

        self.assertEqual(finding.dimension, "duplicidade")
        self.assertGreater(finding.metrics["candidate_pair_count"], 0)
        self.assertEqual(
            finding.metrics["linkage_method"],
            "deterministic_fuzzy_blocking",
        )


    def test_agent_rules_are_executed_without_dynamic_code(self) -> None:
        table = parse_csv(
            b"valor_pago,valor_liquidado,valor_empenhado,cpf_cnpj,mes,data_empenho\n"
            b"120,100,110,9.12E+12,02/fev,2026-01-10\n"
            b"10,20,30,12345678901,01/jan,2026-01-11\n"
        )
        context = AnalysisContext(findings=[], evaluated_dimensions=set())
        rules = [
            ConsistencyRuleSpec(
                rule_id="ordem_fases", rule_type="ordered_values",
                columns=["valor_pago", "valor_liquidado", "valor_empenhado"],
                operator="<=", severity="alta", confidence=0.99,
                rationale="As fases acumuladas devem ser crescentes.",
            ),
            ConsistencyRuleSpec(
                rule_id="documento_sem_notacao_cientifica",
                rule_type="identifier_format", columns=["cpf_cnpj"],
                identifier_format="not_scientific_notation", severity="alta",
                confidence=0.99, rationale="Notação científica pode remover dígitos.",
            ),
            ConsistencyRuleSpec(
                rule_id="mes_da_data", rule_type="date_matches_period",
                columns=["data_empenho", "mes"],
                rationale="O mês deve corresponder à data.",
            ),
        ]

        rejected = check_consistency(table, context, rules)

        self.assertEqual(rejected, [])
        self.assertEqual(
            {finding.metrics["rule"] for finding in context.findings},
            {"ordem_fases", "documento_sem_notacao_cientifica", "mes_da_data"},
        )
        self.assertTrue(all(
            finding.metrics["agent_generated"] for finding in context.findings
        ))

    def test_agent_rule_with_unknown_column_is_rejected(self) -> None:
        table = parse_csv(b"id,nome\n1,Ana\n")
        context = AnalysisContext(findings=[], evaluated_dimensions=set())
        rule = ConsistencyRuleSpec(
            rule_id="coluna_inventada", rule_type="unique_key",
            columns=["nao_existe"],
            rationale="Regra inválida para testar o contrato.",
        )

        rejected = check_consistency(table, context, [rule])

        self.assertEqual(len(rejected), 1)
        self.assertIn("colunas inexistentes", rejected[0])
        self.assertEqual(context.findings, [])

    def test_agent_numeric_rule_infers_portuguese_monetary_format(self) -> None:
        table = parse_csv(
            "valor_pago;valor_liquidado;valor_empenhado\n"
            "6.765,94;6.765,94;7.000\n".encode()
        )
        context = AnalysisContext(findings=[], evaluated_dimensions=set())
        rule = ConsistencyRuleSpec(
            rule_id="ordem_monetaria", rule_type="ordered_values",
            columns=["valor_pago", "valor_liquidado", "valor_empenhado"],
            operator="<=", rationale="Fases acumuladas da despesa.",
        )

        rejected = check_consistency(table, context, [rule])

        self.assertEqual(rejected, [])
        self.assertEqual(context.findings, [])
        self.assertIn("consistencia", context.evaluated_dimensions)

    @patch("deep_research.services.data_quality_service.propose_consistency_rules")
    def test_analysis_automatically_activates_consistency_agent(self, propose) -> None:
        propose.return_value = ConsistencyRuleSet(rules=[
            ConsistencyRuleSpec(
                rule_id="codigo_nome_estavel", rule_type="column_mapping",
                columns=["codigo", "nome"],
                rationale="Um código deve preservar o mesmo nome.",
            )
        ])

        report = analyze_csv_quality(
            b"codigo,nome\n1,Ana\n1,Ana Maria\n2,Bia\n", "cadastro.csv",
        )

        propose.assert_called_once()
        self.assertIn("llm-rule-proposal", report.validation_engines)
        self.assertTrue(any(
            finding.metrics.get("rule") == "codigo_nome_estavel"
            for finding in report.findings
        ))

    @patch(
        "deep_research.services.data_quality_service.propose_consistency_rules",
        side_effect=RuntimeError("modelo indisponível"),
    )
    def test_agent_failure_preserves_deterministic_analysis(self, _propose) -> None:
        report = analyze_csv_quality(
            b"start_date,end_date\n2026-02-01,2026-01-01\n", "datas.csv",
        )

        self.assertTrue(any(
            finding.metrics.get("rule") == "date_start_not_after_end"
            for finding in report.findings
        ))
        self.assertTrue(any(
            "agente de consistência" in item for item in report.limitations
        ))


if __name__ == "__main__":
    unittest.main()
