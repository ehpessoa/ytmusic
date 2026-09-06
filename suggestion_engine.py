"""Gera lotes de sugestões de músicas validadas no YouTube Music,
evitando repetir, na mesma sessão de execução, faixas já mostradas ou já
presentes na playlist."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from taste_advisor import TasteAdvisor
from ytmusic_client import Track, YTMusicClient

ProgressCallback = Callable[[int, int], None]

MAX_BATCH_SIZE = 10
# Rodadas extras ao Gemini para compensar sugestões que não existem no
# catálogo do YouTube Music ou que colidem com faixas já vistas.
MAX_GEMINI_ROUNDS = 4


@dataclass
class Suggestion:
    video_id: str
    title: str
    artists: str
    reason: str


class SuggestionEngine:
    def __init__(self, advisor: TasteAdvisor, client: YTMusicClient, existing_tracks: list[Track]):
        self.advisor = advisor
        self.client = client
        self.existing_tracks = existing_tracks
        self.existing_video_ids = {t.video_id for t in existing_tracks}
        self.shown_video_ids: set[str] = set()
        self.suggested_title_artist: set[tuple[str, str]] = set()

    def next_batch(
        self,
        taste_profile: str,
        max_results: int = MAX_BATCH_SIZE,
        on_progress: ProgressCallback | None = None,
    ) -> list[Suggestion]:
        max_results = min(max_results, MAX_BATCH_SIZE)
        batch: list[Suggestion] = []

        for round_num in range(1, MAX_GEMINI_ROUNDS + 1):
            if len(batch) >= max_results:
                break

            if on_progress:
                on_progress(round_num, MAX_GEMINI_ROUNDS)

            candidates = self.advisor.suggest_batch(
                taste_profile, self.existing_tracks, self.suggested_title_artist
            )
            if not candidates:
                break

            for title, artist, reason in candidates:
                key = (title.strip().casefold(), artist.strip().casefold())
                if key in self.suggested_title_artist:
                    continue
                self.suggested_title_artist.add(key)

                track = self.client.search_song(title, artist)
                if track is None:
                    continue
                if track.video_id in self.existing_video_ids or track.video_id in self.shown_video_ids:
                    continue

                self.shown_video_ids.add(track.video_id)
                batch.append(
                    Suggestion(
                        video_id=track.video_id,
                        title=track.title,
                        artists=track.artists,
                        reason=reason,
                    )
                )
                if len(batch) >= max_results:
                    break

        return batch
