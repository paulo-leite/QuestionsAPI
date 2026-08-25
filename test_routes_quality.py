"""Testes da integração da qualidade de dados com o upload principal."""

import unittest
from io import BytesIO
from unittest.mock import patch

from fastapi import UploadFile

from deep_research.errors import ApplicationError
from deep_research.models import UploadResponse
from deep_research.routes import upload_document


class DocumentUploadQualityTest(unittest.TestCase):
    @staticmethod
    def _csv_upload_response() -> UploadResponse:
        """Cria a resposta simulada usada pelos testes de upload de CSV."""
        return UploadResponse(
            document_id="doc-1",
            filename="dados.csv",
            file_type="csv",
            rows=3,
            chunks=3,
            chunking_method="csv_rows",
            max_tokens_per_chunk=512,
            minimum_chunk_tokens=4,
            average_chunk_tokens=5,
            maximum_chunk_tokens=6,
            average_chunk_characters=20,
        )

    @patch("deep_research.routes.prepare_document")
    def test_csv_upload_runs_quality_analysis_before_returning(self, prepare) -> None:
        prepare.return_value = UploadResponse(
            document_id="doc-1",
            filename="dados.csv",
            file_type="csv",
            rows=3,
            chunks=3,
            chunking_method="csv_rows",
            max_tokens_per_chunk=512,
            minimum_chunk_tokens=4,
            average_chunk_tokens=5,
            maximum_chunk_tokens=6,
            average_chunk_characters=20,
        )
        file = UploadFile(
            filename="dados.csv",
            file=BytesIO(b"id,nome\n1,Ana\n2,Bia\n2,Bia\n"),
        )

        response = upload_document(file)

        self.assertEqual(response.document_id, "doc-1")
        self.assertIsNotNone(response.data_quality)
        self.assertEqual(response.data_quality.dataset.exact_duplicate_rows, 1)
        prepare.assert_called_once()

    @patch("deep_research.routes.prepare_document")
    def test_pdf_upload_does_not_run_tabular_analysis(self, prepare) -> None:
        prepare.return_value = UploadResponse(
            document_id="doc-2",
            filename="documento.pdf",
            file_type="pdf",
            pages=1,
            chunks=1,
            chunking_method="docling_hybrid",
            max_tokens_per_chunk=512,
            minimum_chunk_tokens=10,
            average_chunk_tokens=10,
            maximum_chunk_tokens=10,
            average_chunk_characters=40,
        )
        file = UploadFile(filename="documento.pdf", file=BytesIO(b"%PDF-test"))

        response = upload_document(file)

        self.assertIsNone(response.data_quality)
        prepare.assert_called_once()

    @patch("deep_research.routes.prepare_document")
    def test_invalid_csv_is_not_indexed(self, prepare) -> None:
        file = UploadFile(filename="vazio.csv", file=BytesIO(b""))

        with self.assertRaises(ApplicationError):
            upload_document(file)

        prepare.assert_not_called()

    @patch("deep_research.routes.prepare_document")
    def test_csv_upload_accepts_optional_reference(self, prepare) -> None:
        prepare.return_value = self._csv_upload_response()
        file = UploadFile(
            filename="dados.csv",
            file=BytesIO(b"customer_id,customer_name\n1,Ana\n2,Bia\n"),
        )
        reference = UploadFile(
            filename="referencia.csv",
            file=BytesIO(b"customer_id,customer_name\n1,Ana Maria\n2,Bia\n"),
        )

        response = upload_document(file, reference)

        self.assertIsNotNone(response.data_quality)
        self.assertEqual(
            response.data_quality.reference_filename,
            "referencia.csv",
        )
        self.assertIn("evidently", response.data_quality.validation_engines)
        self.assertTrue(
            any(
                finding.metrics.get("rule")
                == "stable_attribute_across_sources"
                for finding in response.data_quality.findings
            )
        )
        prepare.assert_called_once()

    @patch("deep_research.routes.prepare_document")
    def test_csv_upload_rejects_non_csv_reference(self, prepare) -> None:
        file = UploadFile(
            filename="dados.csv",
            file=BytesIO(b"id,nome\n1,Ana\n"),
        )
        reference = UploadFile(
            filename="referencia.pdf",
            file=BytesIO(b"%PDF-test"),
        )

        with self.assertRaises(ApplicationError) as raised:
            upload_document(file, reference)

        self.assertEqual(raised.exception.status_code, 415)
        prepare.assert_not_called()

    @patch("deep_research.routes.prepare_document")
    def test_pdf_upload_rejects_reference(self, prepare) -> None:
        file = UploadFile(filename="documento.pdf", file=BytesIO(b"%PDF-test"))
        reference = UploadFile(
            filename="referencia.csv",
            file=BytesIO(b"id,nome\n1,Ana\n"),
        )

        with self.assertRaises(ApplicationError) as raised:
            upload_document(file, reference)

        self.assertEqual(raised.exception.status_code, 422)
        prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
