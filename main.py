"""Lê a playlist 'Best Pop Rock Ever' do YouTube Music, classifica cada
faixa como Pop ou Rock usando o Gemini, e organiza o resultado em duas
novas playlists: 'Best Pop Ever' e 'Best Rock Ever'.

Uso:
    python main.py [--dry-run]

Configuração via variáveis de ambiente (ou arquivo .env, veja .env.example):
    GEMINI_API_KEY          obrigatório
    GEMINI_MODEL            padrão: gemini-2.5-flash
    YTMUSIC_AUTH_FILE       padrão: oauth.json
    SOURCE_PLAYLIST_NAME    padrão: Best Pop Rock Ever
    POP_PLAYLIST_NAME       padrão: Best Pop Ever
    ROCK_PLAYLIST_NAME      padrão: Best Rock Ever
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from gemini_classifier import GeminiClassifier
from ytmusic_client import PlaylistNotFoundError, YTMusicClient


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classifica e mostra o resultado sem criar/alterar playlists.",
    )
    args = parser.parse_args()

    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        print("Erro: defina a variável de ambiente GEMINI_API_KEY.", file=sys.stderr)
        return 1

    gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    auth_file = os.environ.get("YTMUSIC_AUTH_FILE", "oauth.json")
    source_playlist_name = os.environ.get("SOURCE_PLAYLIST_NAME", "Best Pop Rock Ever")
    pop_playlist_name = os.environ.get("POP_PLAYLIST_NAME", "Best Pop Ever")
    rock_playlist_name = os.environ.get("ROCK_PLAYLIST_NAME", "Best Rock Ever")

    if not os.path.exists(auth_file):
        print(
            f"Erro: arquivo de autenticação '{auth_file}' não encontrado. "
            "Veja o README.md para gerar as credenciais do YouTube Music.",
            file=sys.stderr,
        )
        return 1

    client = YTMusicClient(auth_file)

    print(f"Buscando playlist de origem '{source_playlist_name}'...")
    try:
        source_playlist_id = client.find_playlist_id_by_name(source_playlist_name)
    except PlaylistNotFoundError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    tracks = client.get_playlist_tracks(source_playlist_id)
    print(f"{len(tracks)} faixas encontradas.")
    if not tracks:
        print("Nada a classificar, encerrando.")
        return 0

    print(f"Classificando faixas com o Gemini ({gemini_model})...")
    classifier = GeminiClassifier(api_key=gemini_api_key, model=gemini_model)
    genre_by_video_id = classifier.classify(tracks)

    pop_tracks = [t for t in tracks if genre_by_video_id[t.video_id] == "Pop"]
    rock_tracks = [t for t in tracks if genre_by_video_id[t.video_id] == "Rock"]

    print(f"Pop: {len(pop_tracks)} faixas | Rock: {len(rock_tracks)} faixas")
    for track in tracks:
        print(f"  [{genre_by_video_id[track.video_id]:4}] {track.title} — {track.artists}")

    if args.dry_run:
        print("\n--dry-run ativo: nenhuma playlist foi criada ou alterada.")
        return 0

    description = f"Gerada automaticamente a partir de '{source_playlist_name}' via Gemini."

    print(f"\nCriando/atualizando playlist '{pop_playlist_name}'...")
    pop_playlist_id = client.get_or_create_playlist(pop_playlist_name, description)
    client.add_tracks(pop_playlist_id, [t.video_id for t in pop_tracks])

    print(f"Criando/atualizando playlist '{rock_playlist_name}'...")
    rock_playlist_id = client.get_or_create_playlist(rock_playlist_name, description)
    client.add_tracks(rock_playlist_id, [t.video_id for t in rock_tracks])

    print("\nConcluído.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
