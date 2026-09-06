"""Thin wrapper around ytmusicapi for the operations this tool needs."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from ytmusicapi import YTMusic

ProgressCallback = Callable[[int, int], None]


@dataclass
class Track:
    video_id: str
    title: str
    artists: str


@dataclass
class PlaylistInfo:
    id: str
    title: str
    owner: str
    privacy: str
    tracks: list[Track]


@dataclass
class AddTracksResult:
    added: int
    already_present: int
    failed_video_ids: list[str]


class PlaylistNotFoundError(Exception):
    pass


class YTMusicClient:
    def __init__(self, auth_file: str):
        self.yt = YTMusic(auth_file)

    def find_playlist_id_by_name(self, name: str) -> str:
        playlists = self.yt.get_library_playlists(limit=None)
        target = name.strip().casefold()
        for playlist in playlists:
            if playlist.get("title", "").strip().casefold() == target:
                return playlist["playlistId"]
        raise PlaylistNotFoundError(
            f"Playlist '{name}' não encontrada na biblioteca do YouTube Music."
        )

    @staticmethod
    def _parse_tracks(items: list[dict]) -> list[Track]:
        tracks = []
        for item in items:
            video_id = item.get("videoId")
            if not video_id:
                continue  # faixa indisponível/removida do catálogo
            artists = ", ".join(a["name"] for a in item.get("artists") or [])
            tracks.append(Track(video_id=video_id, title=item.get("title", ""), artists=artists))
        return tracks

    def _get_playlist_safe(self, playlist_id: str) -> dict:
        try:
            return self.yt.get_playlist(playlist_id, limit=None)
        except KeyError:
            # Playlist vazia (por exemplo, recém-criada): nesse caso a API
            # do YouTube Music não retorna a estrutura usual de conteúdo, e
            # o ytmusicapi levanta KeyError ao navegar a resposta.
            return {}

    def get_playlist_tracks(self, playlist_id: str) -> list[Track]:
        playlist = self._get_playlist_safe(playlist_id)
        return self._parse_tracks(playlist.get("tracks", []))

    def get_playlist_info(self, playlist_id: str) -> PlaylistInfo:
        """Busca metadados e faixas de uma playlist em uma única chamada."""
        playlist = self._get_playlist_safe(playlist_id)

        author = playlist.get("author")
        if isinstance(author, list):
            owner = ", ".join(a.get("name", "") for a in author) or "Desconhecido"
        elif isinstance(author, dict):
            owner = author.get("name", "Desconhecido")
        else:
            owner = "Desconhecido"

        return PlaylistInfo(
            id=playlist.get("id", playlist_id),
            title=playlist.get("title", ""),
            owner=owner,
            privacy=playlist.get("privacy", "Desconhecida"),
            tracks=self._parse_tracks(playlist.get("tracks", [])),
        )

    def get_or_create_playlist(self, name: str, description: str) -> str:
        try:
            return self.find_playlist_id_by_name(name)
        except PlaylistNotFoundError:
            playlist_id = self.yt.create_playlist(
                title=name, description=description, privacy_status="PRIVATE"
            )
            # create_playlist normalmente retorna o ID como string; em alguns
            # erros da API retorna um dict com a mensagem de erro.
            if isinstance(playlist_id, dict):
                raise RuntimeError(f"Falha ao criar playlist '{name}': {playlist_id}")
            return playlist_id

    def get_playlist_video_ids(self, playlist_id: str) -> set[str]:
        playlist = self._get_playlist_safe(playlist_id)
        return {item["videoId"] for item in playlist.get("tracks", []) if item.get("videoId")}

    def _add_chunk(self, playlist_id: str, chunk: list[str]) -> list[str]:
        """Tenta adicionar um lote; com duplicates=False a API do YouTube
        Music rejeita o LOTE INTEIRO (sem adicionar nada) se encontrar
        qualquer duplicata nele. Para não perder faixas silenciosamente,
        checamos o status e, se falhar, bissectamos o lote recursivamente
        até isolar exatamente quais video_ids não puderam ser adicionados."""
        if not chunk:
            return []
        response = self.yt.add_playlist_items(playlist_id, chunk, duplicates=False)
        status = response.get("status", "") if isinstance(response, dict) else ""
        if "SUCCEEDED" in status:
            return []
        if len(chunk) == 1:
            return list(chunk)
        mid = len(chunk) // 2
        return self._add_chunk(playlist_id, chunk[:mid]) + self._add_chunk(playlist_id, chunk[mid:])

    def add_tracks(
        self,
        playlist_id: str,
        video_ids: list[str],
        chunk_size: int = 100,
        on_progress: ProgressCallback | None = None,
    ) -> AddTracksResult:
        """Adiciona video_ids à playlist sem perder faixas silenciosamente:
        remove duplicatas (entre si e contra o que já está na playlist,
        já que a API falha o lote inteiro diante de uma duplicata) e
        reporta quais video_ids não puderam ser confirmados como
        adicionados, em vez de simplesmente ignorar."""
        seen = self.get_playlist_video_ids(playlist_id)
        already_present = 0
        to_add: list[str] = []
        for video_id in video_ids:
            if video_id in seen:
                already_present += 1
                continue
            seen.add(video_id)
            to_add.append(video_id)

        failed: list[str] = []
        total_chunks = math.ceil(len(to_add) / chunk_size) if to_add else 0
        for chunk_num, i in enumerate(range(0, len(to_add), chunk_size), start=1):
            chunk = to_add[i : i + chunk_size]
            failed.extend(self._add_chunk(playlist_id, chunk))
            if on_progress:
                on_progress(chunk_num, total_chunks)

        return AddTracksResult(
            added=len(to_add) - len(failed),
            already_present=already_present,
            failed_video_ids=failed,
        )

    def search_song(self, title: str, artist: str) -> Track | None:
        """Busca uma faixa real no YouTube Music a partir de título/artista
        sugeridos pelo Gemini. Retorna None se nada correspondente for
        encontrado."""
        query = f"{title} {artist}".strip()
        results = self.yt.search(query, filter="songs", limit=5)
        for result in results:
            video_id = result.get("videoId")
            if not video_id:
                continue
            artists = ", ".join(a["name"] for a in result.get("artists") or [])
            return Track(video_id=video_id, title=result.get("title", title), artists=artists)
        return None
