import asyncio
import json
from typing import Any, Protocol

import httpx

from config.computing import COMPUTING_SETTINGS, ComputingSettings


class AsyncLLMClient(Protocol):
    async def generate(self, prompt: str) -> str: ...


class LLMWorker:
    """Concurrency-limited adapter around the existing asynchronous Ollama client."""

    def __init__(
        self,
        client: AsyncLLMClient,
        settings: ComputingSettings = COMPUTING_SETTINGS,
    ):
        self.client = client
        self.settings = settings
        self._semaphore = asyncio.Semaphore(settings.max_llm_parallel)

    async def run(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, str):
            prompt = payload
        elif isinstance(payload, dict):
            prompt = payload.get("prompt")
        else:
            prompt = None

        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("AI_ANALYSIS requires a non-empty prompt.")

        async with self._semaphore:
            for attempt in range(self.settings.llm_retries + 1):
                try:
                    response = await asyncio.wait_for(
                        self.client.generate(prompt),
                        timeout=self.settings.ollama_timeout,
                    )
                    if not isinstance(response, str) or not response.strip():
                        raise ValueError("Ollama returned an empty response.")

                    try:
                        structured = json.loads(response)
                    except json.JSONDecodeError:
                        structured = None

                    return {
                        "raw_response": response,
                        "structured": structured,
                    }
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    if attempt >= self.settings.llm_retries:
                        raise
                    await asyncio.sleep(min(0.5 * (2 ** attempt), 2.0))
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code < 500 or attempt >= self.settings.llm_retries:
                        raise
                    await asyncio.sleep(min(0.5 * (2 ** attempt), 2.0))
                except asyncio.TimeoutError:
                    if attempt >= self.settings.llm_retries:
                        raise
                    await asyncio.sleep(min(0.5 * (2 ** attempt), 2.0))

        raise RuntimeError("LLM request exhausted retries.")
