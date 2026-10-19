"""Tests for the embedding model's per-input context limit."""

import unittest
from types import SimpleNamespace

from deep_research.services.embedding_service import (
    OpenAICompatibleEmbeddings,
)
from deep_research.services.embedding_limits import MAX_EMBEDDING_INPUT_BYTES


class EmbeddingInputLimitTest(unittest.TestCase):
    def test_batches_do_not_mix_embeddings_from_adjacent_texts(self) -> None:
        calls: list[list[str]] = []

        def create(*, model: str, input: list[str]) -> SimpleNamespace:
            self.assertEqual(model, "test-model")
            calls.append(input)
            # Return items in reverse order to exercise the API index handling.
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        index=index,
                        embedding=[float(ord(input[index][0])), 0.0],
                    )
                    for index in reversed(range(len(input)))
                ]
            )

        service = OpenAICompatibleEmbeddings.__new__(OpenAICompatibleEmbeddings)
        service.model = "test-model"
        service.client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
        texts = [character * 1499 for character in "ABCDEFGHIJKLMNOPQ"]

        result = service.embed_documents(texts)

        self.assertEqual(len(calls), 2)
        self.assertEqual([text for batch in calls for text in batch], texts)
        self.assertEqual(
            result,
            [[float(ord(character)), 0.0] for character in "ABCDEFGHIJKLMNOPQ"],
        )

    def test_long_unicode_input_is_split_and_recombined(self) -> None:
        calls: list[list[str]] = []

        def create(*, model: str, input: list[str]) -> SimpleNamespace:
            self.assertEqual(model, "test-model")
            calls.append(input)
            return SimpleNamespace(
                data=[
                    SimpleNamespace(index=index, embedding=[1.0, 0.0])
                    for index in range(len(input))
                ]
            )

        service = OpenAICompatibleEmbeddings.__new__(OpenAICompatibleEmbeddings)
        service.model = "test-model"
        service.client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
        long_text = "á" * 18000 + "fim" * 1700

        result = service.embed_documents(["short", long_text, "last"])

        sent = [part for batch in calls for part in batch]
        self.assertEqual(sent[0], "short")
        self.assertEqual(sent[-1], "last")
        self.assertEqual("".join(sent[1:-1]), long_text)
        self.assertGreater(len(calls), 1)
        self.assertTrue(
            all(len(part.encode("utf-8")) <= MAX_EMBEDDING_INPUT_BYTES for part in sent)
        )
        self.assertEqual(result, [[1.0, 0.0]] * 3)


if __name__ == "__main__":
    unittest.main()
