import hashlib
import math
import re

from app.models import EMBEDDING_DIMENSIONS

_TOKEN_PATTERN = re.compile(r"\w+", flags=re.UNICODE)


class DeterministicEmbedding:
    """Keyless feature hashing for local retrieval tests, not semantic embeddings."""

    dimensions = EMBEDDING_DIMENSIONS

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = _TOKEN_PATTERN.findall(text.casefold())
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign

        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude:
            vector = [value / magnitude for value in vector]
        return vector
