from __future__ import annotations

import os
from typing import Any

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .knowledge import KNOWLEDGE_BASE


class SemanticRetriever:
    """Small in-memory vector index with optional OpenAI embeddings."""

    def __init__(self, documents: list[dict[str, str]] | None = None):
        self.documents = documents or KNOWLEDGE_BASE
        self.texts = [f"{d['title']}\n{d['content']}" for d in self.documents]
        self.vectorizer: TfidfVectorizer | None = None
        self.matrix: Any = None
        self.openai_client: Any = None
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        if os.getenv("OPENAI_API_KEY"):
            try:
                from openai import OpenAI
                self.openai_client = OpenAI()
                self.matrix = np.array(self._openai_embed(self.texts))
            except Exception:
                self.openai_client = None
        if self.openai_client is None:
            self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
            self.matrix = self.vectorizer.fit_transform(self.texts)

    def _openai_embed(self, texts: list[str]) -> list[list[float]]:
        response = self.openai_client.embeddings.create(model=self.embedding_model, input=texts)
        return [item.embedding for item in response.data]

    def search(self, query: str, k: int = 3) -> list[dict[str, Any]]:
        if self.openai_client:
            query_vector = np.array(self._openai_embed([query]))
            scores = cosine_similarity(query_vector, self.matrix)[0]
        else:
            assert self.vectorizer is not None
            scores = cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        indices = scores.argsort()[::-1][:k]
        return [
            {**self.documents[i], "score": round(float(max(0, scores[i])), 3)}
            for i in indices
        ]

