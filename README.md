# ☕ Coffeehouse Discord Bot

Um bot para Discord construído em **Python 3.13** utilizando `discord.py`. O objetivo deste projeto é criar e manter o ambiente de uma comunidade focado na estética *Coffeehouse*, contando com um sistema de rádio próprio, assíncrono e persistente.

## 🛠️ Tecnologias Utilizadas
* Python 3.13
* [discord.py](https://discordpy.readthedocs.io/) (Slash Commands)
* [yt-dlp](https://github.com/yt-dlp/yt-dlp) & FFmpeg (Processamento de Áudio)
* aiosqlite (Banco de Dados Assíncrono)

## 📦 Funcionalidades Atuais
* **Player Independente:** Toca músicas diretamente via YouTube, sem depender de chaves da API do Spotify.
* **Playlist da Comunidade:** Uma rádio colaborativa guardada em banco de dados SQLite, inicializada com clássicos da MPB e Bossa Nova.

## 🚀 Como Rodar Localmente

1. Clone o repositório:
```bash
git clone [https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git](https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git)
cd SEU_REPOSITORIO