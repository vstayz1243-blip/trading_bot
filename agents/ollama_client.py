
import asyncio
import logging

import httpx


logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3:8b",
        timeout: float = 300.0,
        max_concurrent: int = 1,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model

        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=10.0),
        )

        # Zunächst bei einer gleichzeitigen Anfrage bleiben.
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def generate(self, prompt: str) -> str:
        async with self._semaphore:
            response = await self.client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "think": False,
                    "keep_alive": "10m",
                    "options": {
                        "num_predict": 256,
                        "temperature": 0.1,
                    },
                },
            )

            response.raise_for_status()
            data = response.json()

            duration = data.get("total_duration")
            eval_count = data.get("eval_count")
            load_duration = data.get("load_duration")

            logger.info(
                "[Ollama] Modell=%s | Gesamtdauer=%s | "
                "Generierte Tokens=%s | Ladedauer=%s",
                self.model,
                (
                    f"{duration / 1_000_000_000:.2f} s"
                    if isinstance(duration, (int, float))
                    else "unbekannt"
                ),
                eval_count if eval_count is not None else "unbekannt",
                (
                    f"{load_duration / 1_000_000_000:.2f} s"
                    if isinstance(load_duration, (int, float))
                    else "unbekannt"
                ),
            )

            result = data.get("response")

            if not isinstance(result, str) or not result.strip():
                raise ValueError(
                    "Ollama hat keine gültige Antwort zurückgegeben."
                )

            return result

    async def close(self) -> None:
        await self.client.aclose()
