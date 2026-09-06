"""Classifica faixas em 'Pop' ou 'Rock' usando a API do Gemini."""

from __future__ import annotations

import json

from google import genai
from google.genai import types

from ytmusic_client import Track

BATCH_SIZE = 25

_SYSTEM_INSTRUCTION = (
    "Você é um especialista em gêneros musicais. Para cada música recebida "
    "(título e artista), classifique-a em exatamente um dos dois gêneros: "
    "'Pop' ou 'Rock'. Mesmo quando a faixa tiver influências de ambos, "
    "escolha o gênero predominante — nunca responda outra categoria. "
    "Responda APENAS com o JSON pedido, sem texto adicional."
)

_RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "classifications": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "index": types.Schema(type=types.Type.INTEGER),
                    "genre": types.Schema(type=types.Type.STRING, enum=["Pop", "Rock"]),
                },
                required=["index", "genre"],
            ),
        )
    },
    required=["classifications"],
)


class GeminiClassifier:
    def __init__(self, api_key: str, model: str):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def classify(self, tracks: list[Track]) -> dict[str, str]:
        """Retorna um dict video_id -> 'Pop' | 'Rock'."""
        genre_by_video_id: dict[str, str] = {}
        for start in range(0, len(tracks), BATCH_SIZE):
            batch = tracks[start : start + BATCH_SIZE]
            genre_by_video_id.update(self._classify_batch(batch))
        return genre_by_video_id

    def _classify_batch(self, batch: list[Track]) -> dict[str, str]:
        song_list = "\n".join(
            f"{i}. {track.title} — {track.artists}" for i, track in enumerate(batch)
        )
        prompt = (
            "Classifique cada uma destas músicas como 'Pop' ou 'Rock'. "
            f"Retorne um item em 'classifications' para cada índice de 0 a {len(batch) - 1}.\n\n"
            f"{song_list}"
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=_RESPONSE_SCHEMA,
                temperature=0,
            ),
        )

        data = json.loads(response.text)
        result: dict[str, str] = {}
        for item in data["classifications"]:
            index = item["index"]
            if 0 <= index < len(batch):
                result[batch[index].video_id] = item["genre"]

        # Qualquer faixa que o modelo não tenha classificado (resposta
        # incompleta) cai em Pop por padrão para não travar o restante do
        # fluxo.
        for track in batch:
            result.setdefault(track.video_id, "Pop")
        return result
