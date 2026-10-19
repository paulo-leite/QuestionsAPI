"""The keyword search must read large Chroma collections in bounded pages."""

import unittest

from deep_research.services.rag_service import keyword_search


class PagedVectorstore:
    def __init__(self, size: int) -> None:
        self.ids = [str(index) for index in range(size)]
        self.calls: list[tuple[int, int]] = []

    def get(self, *, include: list[str], limit: int, offset: int) -> dict:
        assert include == ["documents", "metadatas"]
        assert limit <= 256
        self.calls.append((limit, offset))
        ids = self.ids[offset:offset + limit]
        return {
            "ids": ids,
            "documents": [
                "girassol exclusivo" if item == "550" else "texto comum"
                for item in ids
            ],
            "metadatas": [{"row_start": int(item)} for item in ids],
        }


class KeywordSearchPagingTest(unittest.TestCase):
    def test_searches_chunks_after_multiple_pages(self) -> None:
        vectorstore = PagedVectorstore(600)

        results = keyword_search(vectorstore, "girassol", 1)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].metadata["row_start"], 550)
        self.assertEqual([offset for _, offset in vectorstore.calls], [0, 256, 512])


if __name__ == "__main__":
    unittest.main()
