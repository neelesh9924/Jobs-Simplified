from django.conf import settings
from google import genai
from google.genai import types

from .base import LLMProvider


class GeminiProvider(LLMProvider):
    MODEL = "gemini-2.5-flash"
    EMBED_MODEL = "gemini-embedding-001"

    def __init__(self):
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)

    def embed(self, text: str) -> list[float]:
        resp = self._client.models.embed_content(model=self.EMBED_MODEL, contents=text[:8000])
        return list(resp.embeddings[0].values)

    def complete(self, system: str, prompt: str) -> str:
        response = self._client.models.generate_content(
            model=self.MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.3,
            ),
        )
        return response.text
