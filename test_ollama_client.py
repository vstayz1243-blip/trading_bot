import asyncio

from agents.ollama_client import OllamaClient


async def main():
    print("1. Starte Test...")

    ollama = OllamaClient(
        model="qwen3:8b"
    )

    print("2. OllamaClient erstellt")

    response = await ollama.generate(
        "Erkläre in zwei Sätzen, was eine Trading-Strategie ist."
    )

    print("3. Antwort erhalten:")
    print(response)


if __name__ == "__main__":
    print("4. Python-Datei gestartet")
    asyncio.run(main())
