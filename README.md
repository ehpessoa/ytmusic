# YouTube Music Toolkit

Ferramentas de linha de comando para a sua conta do YouTube Music, com
apoio do **Gemini**:

- **`split-playlist`** — lê qualquer playlist que você informar,
  identifica o que é realmente Pop e o que é realmente Rock, e organiza o
  resultado em duas playlists de destino também informadas por você.
- **`update-playlist`** — analisa o padrão de gosto musical de uma
  playlist existente, busca no YouTube Music novas músicas que combinem
  com esse padrão e deixa você escolher quais adicionar.

Se uma playlist com o nome de destino já existir na sua biblioteca, as
faixas são adicionadas a ela em vez de criar uma duplicata.

## 1. Instalar dependências

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Autenticar no YouTube Music

O YouTube Music não tem uma API pública oficial; o `ytmusicapi` autentica
usando credenciais da sua própria sessão. Escolha uma opção:

**Opção A — OAuth (recomendado, mais estável):**

```bash
ytmusicapi oauth
```

Siga o fluxo indicado no terminal (é necessário um client ID/secret OAuth
do tipo "TV and Limited Input device", criado no
[Google Cloud Console](https://console.cloud.google.com/apis/credentials)
com a YouTube Data API v3 habilitada). Isso gera um arquivo `oauth.json`
nesta pasta.

**Opção B — Cabeçalhos do navegador:**

```bash
ytmusicapi browser
```

Cole os cabeçalhos de uma requisição autenticada feita em
`music.youtube.com` (copiados do DevTools do navegador, aba Network).
Isso gera um arquivo `browser.json`; ajuste `YTMUSIC_AUTH_FILE` no `.env`
para apontar para ele.

## 3. Configurar a chave do Gemini

Gere uma chave em <https://aistudio.google.com/apikey> e configure:

```bash
cp .env.example .env
# edite .env e preencha GEMINI_API_KEY=...
```

## 4. Rodar

### Separar uma playlist em Pop / Rock

```bash
python main.py split-playlist \
  --source "Best Pop Rock Ever" \
  --pop-playlist "Best Pop Ever" \
  --rock-playlist "Best Rock Ever"
```

`--source`, `--pop-playlist` e `--rock-playlist` aceitam qualquer nome de
playlist da sua biblioteca — o comando não fica preso a nomes fixos.

Use `--dry-run` para ver a classificação de cada faixa no terminal sem
criar ou alterar nenhuma playlist na sua conta — útil para conferir o
resultado antes de aplicar.

### Sugerir novas músicas para uma playlist existente

```bash
python main.py update-playlist --playlist "Best Rock Ever"
```

O comando:

1. Lê todas as faixas da playlist informada.
2. Pede ao Gemini um resumo do padrão de gosto musical (gêneros, época,
   artistas de referência, clima).
3. Busca no YouTube Music músicas reais que combinem com esse padrão e
   ainda não estejam na playlist, mostrando até **10 sugestões por vez**
   (use `--batch-size` para pedir menos; o teto de 10 não pode ser
   ultrapassado).
4. Você escolhe quais adicionar digitando os números (ex.: `1,3,5`),
   digita `mais` para ver uma nova leva de sugestões — que nunca repete
   uma música já mostrada nesta mesma execução — ou `sair` para terminar.

## Observações

- A conta usada é a autenticada no passo 2 (ex.: everaldo.pessoa@gmail.com).
  Este projeto não armazena nem transmite essa credencial — ela fica
  apenas no arquivo local `oauth.json`/`browser.json`, que **não deve ser
  commitado** (já está coberto pelo `.gitignore`).
- Faixas indisponíveis (removidas do catálogo) são ignoradas.
- A classificação (`split-playlist`) é feita em lotes de 25 músicas por
  chamada ao Gemini para reduzir custo e latência.
- As sugestões do `update-playlist` vêm do conhecimento do Gemini sobre
  música; cada sugestão só é oferecida depois de confirmada uma
  correspondência real na busca do YouTube Music.
