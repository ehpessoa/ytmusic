"""Identifica o padrão de gosto musical de uma playlist e sugere novas
músicas (via Gemini) que combinem com esse padrão."""

from __future__ import annotations

import json

from google import genai
from google.genai import types

from ytmusic_client import Track

# Quantas sugestões pedir ao Gemini por rodada. Pedimos uma folga em relação
# ao tamanho do lote mostrado ao usuário porque nem toda sugestão do modelo
# existe de fato no catálogo do YouTube Music (algumas não serão encontradas
# na busca e são descartadas).
SUGGESTIONS_PER_GEMINI_CALL = 15

_PROFILE_SYSTEM_INSTRUCTION = (
    "Você é um especialista em música. Analise a lista de faixas de uma "
    "playlist e descreva, em um parágrafo curto e em português, o padrão de "
    "gosto musical predominante: gêneros, subgêneros, época/década, artistas "
    "de referência e clima geral (mood). Seja específico e objetivo."
)

_SUGGESTION_SYSTEM_INSTRUCTION = (
    "Você é um especialista em música e curador de playlists. Sugira "
    "músicas reais, que existem e podem ser encontradas no YouTube Music, "
    "que combinem com o padrão de gosto descrito. Nunca sugira uma música "
    "que já esteja na lista de faixas já presentes, nem uma que já conste "
    "na lista de faixas já sugeridas anteriormente nesta sessão — não "
    "repita título+artista já citados em nenhuma das duas listas. Responda "
    "APENAS com o JSON pedido, sem texto adicional."
)

_SUGGESTION_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "suggestions": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "title": types.Schema(type=types.Type.STRING),
                    "artist": types.Schema(type=types.Type.STRING),
                    "reason": types.Schema(type=types.Type.STRING),
                },
                required=["title", "artist", "reason"],
            ),
        )
    },
    required=["suggestions"],
)


class TasteAdvisor:
    def __init__(self, api_key: str, model: str):
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def build_taste_profile(self, tracks: list[Track]) -> str:
        song_list = "\n".join(f"- {t.title} — {t.artists}" for t in tracks)
        prompt = f"Faixas da playlist:\n{song_list}"

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_PROFILE_SYSTEM_INSTRUCTION,
                temperature=0.3,
            ),
        )
        return response.text.strip()

    def suggest_batch(
        self,
        taste_profile: str,
        existing: list[Track],
        already_suggested: set[tuple[str, str]],
    ) -> list[tuple[str, str, str]]:
        """Pede ao Gemini uma leva de sugestões (title, artist, reason)."""
        existing_list = "\n".join(f"- {t.title} — {t.artists}" for t in existing[:300])
        excluded_list = "\n".join(f"- {title} — {artist}" for title, artist in already_suggested)

        prompt = (
            f"Padrão de gosto musical identificado:\n{taste_profile}\n\n"
            f"Faixas já presentes na playlist (não sugerir novamente):\n"
            f"{existing_list or '(nenhuma)'}\n\n"
            f"Faixas já sugeridas nesta sessão (não repetir):\n"
            f"{excluded_list or '(nenhuma)'}\n\n"
            f"Sugira {SUGGESTIONS_PER_GEMINI_CALL} músicas novas e diferentes "
            "das duas listas acima, que combinem com esse padrão de gosto."
        )

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=_SUGGESTION_SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=_SUGGESTION_SCHEMA,
                temperature=0.8,
            ),
        )

        data = json.loads(response.text)
        return [(s["title"], s["artist"], s["reason"]) for s in data["suggestions"]]
