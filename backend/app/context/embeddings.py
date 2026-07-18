from abc import ABC, abstractmethod
import hashlib
import math
from typing import List, Optional
import httpx
from app.core.config import settings

class EmbeddingGenerator(ABC):
    @abstractmethod
    async def generate_embedding(self, text: str) -> List[float]:
        """Generate a 1536-dimensional vector embedding for text."""
        pass

    @abstractmethod
    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate vector embeddings for a batch of texts."""
        pass


class LocalMockEmbeddingGenerator(EmbeddingGenerator):
    """Local deterministic mock embedding generator producing unit-normalized 1536-dim vectors."""
    def __init__(self, dimension: int = 1536):
        self.dimension = dimension

    def _hash_vector(self, text: str) -> List[float]:
        vec = []
        text_bytes = text.encode("utf-8")
        # Seed pseudo-random numbers deterministically using SHA-256 rounds
        for i in range(self.dimension):
            h = hashlib.sha256(text_bytes + str(i).encode("utf-8")).digest()
            # Convert bytes to float in range [-1.0, 1.0]
            val = (int.from_bytes(h[:4], "big") / (2**32 - 1)) * 2.0 - 1.0
            vec.append(val)
            
        # L2 unit normalization
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 0:
            vec = [x / norm for x in vec]
        return vec

    async def generate_embedding(self, text: str) -> List[float]:
        return self._hash_vector(text)

    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        return [self._hash_vector(t) for t in texts]


class OpenAIEmbeddingGenerator(EmbeddingGenerator):
    """OpenAI REST API embedding generator."""
    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        self.api_key = api_key
        self.model = model
        self.url = "https://api.openai.com/v1/embeddings"

    async def generate_embedding(self, text: str) -> List[float]:
        results = await self.generate_embeddings_batch([text])
        return results[0]

    async def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "input": texts,
            "model": self.model
        }
        async with httpx.AsyncClient() as client:
            res = await client.post(self.url, headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()
            return [item["embedding"] for item in data["data"]]


_embedding_generator_instance: Optional[EmbeddingGenerator] = None

def get_embedding_generator() -> EmbeddingGenerator:
    """Factory helper resolving active embedding generator."""
    global _embedding_generator_instance
    if _embedding_generator_instance is None:
        api_key = getattr(settings, "OPENAI_API_KEY", None)
        if api_key and api_key.strip():
            _embedding_generator_instance = OpenAIEmbeddingGenerator(api_key)
        else:
            _embedding_generator_instance = LocalMockEmbeddingGenerator()
    return _embedding_generator_instance
