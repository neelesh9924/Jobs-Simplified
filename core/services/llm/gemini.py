import time

from django.conf import settings
from google import genai
from google.genai import types

from .base import LLMProvider


def _is_rate_limit(exc) -> bool:
    s = str(exc)
    return "429" in s or "RESOURCE_EXHAUSTED" in s


def _retry(fn, attempts=3, base_wait=5):
    """Retry a Gemini call on transient 429/quota errors with linear backoff."""
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            if _is_rate_limit(exc) and i < attempts - 1:
                time.sleep(base_wait * (i + 1))
                continue
            raise


class GeminiProvider(LLMProvider):
    MODEL = "gemini-2.5-flash"
    EMBED_MODEL = "gemini-embedding-001"
    EMBED_DIM = 1536  # smaller than the 3072 default — plenty for cosine, less storage

    def __init__(self):
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        resp = _retry(lambda: self._client.models.embed_content(
            model=self.EMBED_MODEL,
            contents=[t[:8000] for t in texts],
            config=types.EmbedContentConfig(output_dimensionality=self.EMBED_DIM),
        ))
        return [list(e.values) for e in resp.embeddings]

    def complete(self, system: str, prompt: str) -> str:
        response = _retry(lambda: self._client.models.generate_content(
            model=self.MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.3,
            ),
        ))
        return response.text
