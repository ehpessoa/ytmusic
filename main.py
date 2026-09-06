"""Ferramentas de linha de comando para playlists do YouTube Music.

Comandos disponíveis:

  split-playlist
      Lê qualquer playlist de origem, classifica cada faixa entre dois ou
      mais estilos musicais via Gemini, e organiza o resultado em uma
      playlist de destino por estilo — tudo informado na linha de comando,
      nada fixo no código.

  update-playlist
      Analisa o padrão de gosto musical de uma playlist existente, busca no
      YouTube Music novas músicas que combinem com esse padrão e deixa você
      escolher quais adicionar.

Uso:
    python main.py split-playlist --source "Nome da playlist" \\
        --style "Estilo 1=Playlist de destino 1" \\
        --style "Estilo 2=Playlist de destino 2" \\
        [--style "Estilo 3=Playlist de destino 3" ...] [--dry-run]
    python main.py update-playlist --playlist "Nome da playlist" [--batch-size N]

Exemplos de --style:
    Pop/Rock:   --style "Pop=Best Pop Ever" --style "Rock=Best Rock Ever"
    MPB em 3:   --style "MPB Clássica=MPB Clássica" \\
                --style "Samba=Samba" --style "Rap=Rap"

Configuração via variáveis de ambiente (ou arquivo .env, veja .env.example):
    GEMINI_API_KEY          obrigatório
    GEMINI_MODEL            padrão: gemini-2.5-flash
    YTMUSIC_AUTH_FILE       padrão: oauth.json
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv

from gemini_classifier import GeminiClassifier
from suggestion_engine import MAX_BATCH_SIZE, SuggestionEngine
from taste_advisor import TasteAdvisor
from ytmusic_client import PlaylistNotFoundError, Track, YTMusicClient


def _require_env(auth_file: str) -> tuple[str, str] | int:
    """Valida GEMINI_API_KEY e a existência do arquivo de autenticação.
    Retorna (api_key, model) em caso de sucesso, ou um código de saída."""
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        print("Erro: defina a variável de ambiente GEMINI_API_KEY.", file=sys.stderr)
        return 1

    if not os.path.exists(auth_file):
        print(
            f"Erro: arquivo de autenticação '{auth_file}' não encontrado. "
            "Veja o README.md para gerar as credenciais do YouTube Music.",
            file=sys.stderr,
        )
        return 1

    gemini_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    return gemini_api_key, gemini_model


def _parse_styles(raw_styles: list[str]) -> dict[str, str]:
    """Converte ["Estilo=Playlist", ...] em {"Estilo": "Playlist", ...},
    validando o formato e exigindo pelo menos 2 estilos distintos."""
    styles: dict[str, str] = {}
    for item in raw_styles:
        genre, sep, playlist_name = item.partition("=")
        genre = genre.strip()
        playlist_name = playlist_name.strip()
        if not sep or not genre or not playlist_name:
            raise ValueError(
                f"Formato inválido em --style '{item}'. Use 'Estilo=Nome da Playlist'."
            )
        if genre in styles:
            raise ValueError(f"Estilo '{genre}' repetido em --style.")
        styles[genre] = playlist_name

    if len(styles) < 2:
        raise ValueError("Informe pelo menos 2 --style para dividir a playlist.")
    return styles


def run_split_playlist(args: argparse.Namespace) -> int:
    auth_file = os.environ.get("YTMUSIC_AUTH_FILE", "oauth.json")
    env = _require_env(auth_file)
    if isinstance(env, int):
        return env
    gemini_api_key, gemini_model = env

    try:
        styles = _parse_styles(args.styles)
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    source_playlist_name = args.source
    style_labels = list(styles.keys())

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

    print(f"Classificando faixas com o Gemini ({gemini_model}) nos estilos: {', '.join(style_labels)}...")
    classifier = GeminiClassifier(api_key=gemini_api_key, model=gemini_model)
    genre_by_video_id = classifier.classify(tracks, style_labels)

    tracks_by_style: dict[str, list[Track]] = {label: [] for label in style_labels}
    for track in tracks:
        tracks_by_style[genre_by_video_id[track.video_id]].append(track)

    for label in style_labels:
        print(f"{label}: {len(tracks_by_style[label])} faixas")
    for track in tracks:
        print(f"  [{genre_by_video_id[track.video_id]}] {track.title} — {track.artists}")

    if args.dry_run:
        print("\n--dry-run ativo: nenhuma playlist foi criada ou alterada.")
        return 0

    description = f"Gerada automaticamente a partir de '{source_playlist_name}' via Gemini."

    for label in style_labels:
        playlist_name = styles[label]
        style_tracks = tracks_by_style[label]
        print(f"\nCriando/atualizando playlist '{playlist_name}' ({label})...")
        playlist_id = client.get_or_create_playlist(playlist_name, description)
        client.add_tracks(playlist_id, [t.video_id for t in style_tracks])

    print("\nConcluído.")
    return 0


def _parse_selection(text: str, max_index: int) -> list[int]:
    """Converte "1,3,5" em [1, 3, 5], ignorando entradas inválidas ou fora
    do intervalo do lote atual."""
    indices: list[int] = []
    for part in text.replace(" ", "").split(","):
        if part.isdigit():
            n = int(part)
            if 1 <= n <= max_index and n not in indices:
                indices.append(n)
    return indices


def run_update_playlist(args: argparse.Namespace) -> int:
    auth_file = os.environ.get("YTMUSIC_AUTH_FILE", "oauth.json")
    env = _require_env(auth_file)
    if isinstance(env, int):
        return env
    gemini_api_key, gemini_model = env

    batch_size = min(args.batch_size, MAX_BATCH_SIZE)
    if args.batch_size > MAX_BATCH_SIZE:
        print(f"Aviso: batch-size limitado a {MAX_BATCH_SIZE} sugestões por rodada.")

    client = YTMusicClient(auth_file)

    print(f"Buscando playlist '{args.playlist}'...")
    try:
        playlist_id = client.find_playlist_id_by_name(args.playlist)
    except PlaylistNotFoundError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    tracks = client.get_playlist_tracks(playlist_id)
    print(f"{len(tracks)} faixas na playlist atual.")
    if not tracks:
        print("A playlist está vazia; não há como determinar um padrão de gosto.", file=sys.stderr)
        return 1

    advisor = TasteAdvisor(api_key=gemini_api_key, model=gemini_model)

    print("Analisando o padrão de gosto musical da playlist...")
    taste_profile = advisor.build_taste_profile(tracks)
    print(f"\nPadrão de gosto identificado:\n{taste_profile}\n")

    engine = SuggestionEngine(advisor, client, tracks)
    total_added = 0

    while True:
        print("Buscando sugestões no YouTube Music...")
        batch = engine.next_batch(taste_profile, max_results=batch_size)
        if not batch:
            print("Não há mais sugestões novas no momento.")
            break

        print("\nSugestões (máx. 10 por rodada):")
        for i, suggestion in enumerate(batch, start=1):
            print(f"  {i}. {suggestion.title} — {suggestion.artists}")
            print(f"     motivo: {suggestion.reason}")

        selection = input(
            "\nDigite os números das músicas para adicionar (ex.: 1,3,5), "
            "'mais' para novas sugestões ou 'sair' para terminar: "
        ).strip().casefold()

        if selection in ("sair", "s", "exit", "quit"):
            break
        if selection in ("mais", "m", "more"):
            continue

        chosen_indices = _parse_selection(selection, len(batch))
        if not chosen_indices:
            print("Nenhuma seleção válida reconhecida; tente novamente.")
            continue

        chosen = [batch[i - 1] for i in chosen_indices]
        client.add_tracks(playlist_id, [s.video_id for s in chosen])
        total_added += len(chosen)
        print(f"Adicionada(s) {len(chosen)} música(s) à playlist '{args.playlist}'.")

        again = input("Ver mais sugestões? (s/n): ").strip().casefold()
        if again not in ("s", "sim", "y", "yes"):
            break

    print(f"\nConcluído. Total de músicas adicionadas: {total_added}.")
    return 0


def main() -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    split_parser = subparsers.add_parser(
        "split-playlist",
        help="Classifica as faixas de uma playlist em dois ou mais estilos e as separa em playlists.",
    )
    split_parser.add_argument(
        "--source", required=True, help="Nome da playlist de origem a classificar."
    )
    split_parser.add_argument(
        "--style",
        dest="styles",
        action="append",
        required=True,
        metavar="ESTILO=PLAYLIST",
        help=(
            "Um estilo musical e a playlist de destino para ele, no formato "
            "'Estilo=Nome da Playlist'. Repita --style uma vez por estilo "
            "(mínimo 2). Ex.: --style 'Pop=Best Pop Ever' "
            "--style 'Rock=Best Rock Ever'; ou, para dividir uma playlist de "
            "MPB em três: --style 'MPB Clássica=MPB Clássica' "
            "--style 'Samba=Samba' --style 'Rap=Rap'."
        ),
    )
    split_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classifica e mostra o resultado sem criar/alterar playlists.",
    )

    update_parser = subparsers.add_parser(
        "update-playlist",
        help="Sugere novas músicas para uma playlist existente com base no padrão de gosto dela.",
    )
    update_parser.add_argument(
        "--playlist", required=True, help="Nome da playlist a atualizar."
    )
    update_parser.add_argument(
        "--batch-size",
        type=int,
        default=MAX_BATCH_SIZE,
        help=f"Máximo de sugestões mostradas por rodada (padrão e limite: {MAX_BATCH_SIZE}).",
    )

    args = parser.parse_args()

    if args.command == "split-playlist":
        return run_split_playlist(args)
    return run_update_playlist(args)


if __name__ == "__main__":
    sys.exit(main())
