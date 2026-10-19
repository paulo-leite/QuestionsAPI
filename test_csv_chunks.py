"""CSV rows should be indexed as individually searchable chunks."""

import unittest

from deep_research.services.csv_service import create_csv_chunks
from deep_research.services.embedding_limits import MAX_EMBEDDING_INPUT_BYTES


class CsvChunkingTest(unittest.TestCase):
    def test_long_row_keeps_all_text_and_row_provenance(self) -> None:
        long_value = "á" * 18000 + "PALAVRA_FINAL"
        content = f"id,descricao\n1,{long_value}\n2,curta\n".encode("utf-8")

        chunks, row_count = create_csv_chunks(content, "dados.csv")

        long_row = [chunk for chunk in chunks if chunk.metadata["row_start"] == 2]
        self.assertEqual(row_count, 2)
        self.assertGreater(len(long_row), 1)
        self.assertEqual(long_row[0].page_content, "Linha 2\nid: 1")
        self.assertEqual(
            "".join(
                chunk.page_content.removeprefix("Linha 2\ndescricao: ")
                for chunk in long_row[1:]
            ),
            long_value,
        )
        self.assertTrue(
            all(chunk.page_content.startswith("Linha 2\ndescricao: ")
                for chunk in long_row[1:])
        )
        self.assertTrue(all(chunk.metadata["row_end"] == 2 for chunk in long_row))
        self.assertEqual(
            [chunk.metadata["part"] for chunk in long_row],
            list(range(1, len(long_row) + 1)),
        )
        self.assertTrue(
            all(len(chunk.page_content.encode("utf-8")) <= MAX_EMBEDDING_INPUT_BYTES
                for chunk in chunks)
        )
        self.assertIn("PALAVRA_FINAL", long_row[-1].page_content)
        self.assertEqual(chunks[-1].page_content, "Linha 3\nid: 2\ndescricao: curta")


if __name__ == "__main__":
    unittest.main()
