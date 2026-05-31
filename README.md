# SpotCalendar

SpotCalendar é uma aplicação Flask que conecta na sua conta Spotify, coleta todas as músicas das suas playlists próprias e exibe uma linha do tempo de quando elas foram adicionadas em anos anteriores.

> Os dados das músicas ficam no navegador do usuário via `localStorage`; o servidor não mantém as faixas.

## Funcionalidades

- Autenticação via Spotify OAuth
- Coleta de todas as playlists próprias do usuário
- Filtragem de músicas locais / sem ID / sem imagem
- Armazenamento temporário em `localStorage` do navegador
- Página de calendário com visualização das músicas por data de adição

## Tecnologias

- Python 3
- Flask
- Spotipy
- HTML/CSS simples para interface

## Configuração

1. Crie um ambiente virtual Python:

```bash
python -m venv venv
```

2. Ative o ambiente virtual:

- Windows PowerShell:

```powershell
venv\Scripts\Activate.ps1
```

- Windows CMD:

```cmd
venv\Scripts\activate.bat
```

3. Instale as dependências:

```bash
pip install -r requirements.txt
```

4. Crie um arquivo `.env` na raiz do projeto com as variáveis:

```env
CLIENT_ID=seu_client_id (disponível no dashboard dev do spotify)
CLIENT_SECRET=seu_client_secret (disponível no dashboard dev do spotify)
REDIRECT_URI=http://127.0.0.1:5000/callback
FLASK_SECRET_KEY=uma_chave_secreta
FLASK_ENV=development
```

5. Execute a aplicação:

```bash
python main.py
```

6. Abra o navegador em:

```text
http://127.0.0.1:5000
```

## Estrutura principal

- `main.py` - inicializa o Flask e registra as rotas
- `routes.py` - define rotas para login, callback, coleta e visualização
- `spotify_helpers.py` - contém a lógica de autenticação e coleta de músicas do Spotify
- `templates/` - páginas html.

## Observações

- A aplicação faz a coleta de forma síncrona no endpoint `/api/collect`.
- O `localStorage` é usado para evitar nova coleta ao navegar novamente para o calendário.
- A rota `/logout` limpa a sessão e o `localStorage` do navegador.
