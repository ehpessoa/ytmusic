# YouTube Music Pop/Rock Classifier

Lê todas as músicas da playlist **Best Pop Rock Ever** da sua conta do
YouTube Music, usa o **Gemini** para identificar o que é realmente Pop e o
que é realmente Rock, e organiza o resultado em duas novas playlists:

- **Best Pop Ever**
- **Best Rock Ever**

Se uma playlist com esse nome já existir na sua biblioteca, as faixas são
adicionadas a ela em vez de criar uma duplicata.

## 1. Instalar dependências

```bash
cd youtube-music-classifier
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

```bash
python main.py
```

Use `python main.py --dry-run` para ver a classificação de cada faixa no
terminal sem criar ou alterar nenhuma playlist na sua conta — útil para
conferir o resultado antes de aplicar.

## Observações

- A conta usada é a autenticada no passo 2 (ex.: everaldo.pessoa@gmail.com).
  Este projeto não armazena nem transmite essa credencial — ela fica
  apenas no arquivo local `oauth.json`/`browser.json`, que **não deve ser
  commitado** (já está coberto pelo `.gitignore`).
- Faixas indisponíveis (removidas do catálogo) são ignoradas.
- A classificação é feita em lotes de 25 músicas por chamada ao Gemini
  para reduzir custo e latência.
