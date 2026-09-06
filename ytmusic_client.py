"""Thin wrapper around ytmusicapi for the operations this tool needs."""

from __future__ import annotations

from dataclasses import dataclass

from ytmusicapi import YTMusic


@dataclass
class Track:
    video_id: str
    title: str
    artists: str


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

    def get_playlist_tracks(self, playlist_id: str) -> list[Track]:
        playlist = self.yt.get_playlist(playlist_id, limit=None)
        tracks = []
        for item in playlist.get("tracks", []):
            video_id = item.get("videoId")
            if not video_id:
                continue  # faixa indisponível/removida do catálogo
            artists = ", ".join(a["name"] for a in item.get("artists") or [])
            tracks.append(Track(video_id=video_id, title=item.get("title", ""), artists=artists))
        return tracks

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

    def add_tracks(self, playlist_id: str, video_ids: list[str], chunk_size: int = 100) -> None:
        for i in range(0, len(video_ids), chunk_size):
            chunk = video_ids[i : i + chunk_size]
            self.yt.add_playlist_items(playlist_id, chunk, duplicates=False)
