"""Testes da integração da qualidade de dados com o upload principal."""

import unittest
from io import BytesIO
from unittest.mock import patch

from fastapi import UploadFile

from deep_research.errors import ApplicationError
from deep_research.models import UploadResponse
from deep_research.routes import upload_document


class DocumentUploadQualityTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
