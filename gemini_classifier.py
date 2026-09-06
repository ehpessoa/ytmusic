"""Classifica faixas em um conjunto arbitrário de estilos musicais,
definido por quem chama, usando a API do Gemini."""

from __future__ import annotations

import json
import math
from typing import Callable

from google import genai
from google.genai import types

from ytmusic_client import Track

BATCH_SIZE = 25

ProgressCallback = Callable[[int, int], None]


class GeminiClassifier:
    def __init__(self, api_key: str, model: str):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def classify(
        self,
        tracks: list[Track],
        styles: list[str],
        on_progress: ProgressCallback | None = None,
    ) -> dict[str, str]:
        """Retorna um dict video_id -> um dos rótulos em `styles`.

        `styles` deve ter pelo menos 2 rótulos (ex.: ["Pop", "Rock"] ou
        ["MPB Clássica", "Samba", "Rap"] para dividir uma playlist de MPB
        em mais de duas categorias).

        Se `on_progress` for informado, é chamado com (lotes_concluídos,
        total_de_lotes) após cada chamada ao Gemini.
        """
        total_batches = math.ceil(len(tracks) / BATCH_SIZE)
        genre_by_video_id: dict[str, str] = {}
        for batch_num, start in enumerate(range(0, len(tracks), BATCH_SIZE), start=1):
            batch = tracks[start : start + BATCH_SIZE]
            genre_by_video_id.update(self._classify_batch(batch, styles))
            if on_progress:
                on_progress(batch_num, total_batches)
        return genre_by_video_id

    def _classify_batch(self, batch: list[Track], styles: list[str]) -> dict[str, str]:
        song_list = "\n".join(
            f"{i}. {track.title} — {track.artists}" for i, track in enumerate(batch)
        )
        styles_list = ", ".join(f"'{s}'" for s in styles)

        system_instruction = (
            "Você é um especialista em gêneros musicais. Para cada música "
            f"recebida (título e artista), classifique-a em exatamente um "
            f"destes estilos: {styles_list}. Mesmo quando a faixa tiver "
            "influências de mais de um estilo, escolha o predominante — "
            "nunca responda um estilo fora dessa lista. Responda APENAS "
            "com o JSON pedido, sem texto adicional."
        )
        prompt = (
            f"Classifique cada uma destas músicas em um dos estilos "
            f"{styles_list}. Retorne um item em 'classifications' para "
            f"cada índice de 0 a {len(batch) - 1}.\n\n{song_list}"
        )
        response_schema = types.Schema(
            type=types.Type.OBJECT,
            properties={
                "classifications": types.Schema(
                    type=types.Type.ARRAY,
                    items=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "index": types.Schema(type=types.Type.INTEGER),
                            "genre": types.Schema(type=types.Type.STRING, enum=styles),
                        },
                        required=["index", "genre"],
                    ),
                )
            },
            required=["classifications"],
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=response_schema,
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
        # incompleta) cai no primeiro estilo da lista por padrão, para não
        # travar o restante do fluxo.
        default_style = styles[0]
        for track in batch:
            result.setdefault(track.video_id, default_style)
        return result
