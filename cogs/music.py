import asyncio
import random
from collections import deque
from pathlib import Path
from typing import Any

import aiosqlite
import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp


COZY_BROWN = 0x8B5A2B
COZY_BEIGE = 0xD2B48C
DB_PATH = Path("database/playlist.db")
FFMPEG_BEFORE_OPTIONS = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTIONS = "-vn"


SEED_TRACKS = [
    "Oba, La Vem Ela - Jorge Ben Jor",
    "O Telefone Tocou Novamente - Jorge Ben Jor",
    "Wave - Tom Jobim",
    "Aguas De Marco - Elis Regina, Tom Jobim",
    "cozy you - aron!",
    "The Girl From Ipanema - Stan Getz, Joao Gilberto",
    "Corcovado - Stan Getz, Joao Gilberto",
    "So Danco Samba - Stan Getz, Joao Gilberto",
    "Para Machuchar Meu Coracao - Stan Getz",
    "Chega De Saudade - Joao Gilberto",
    "Solidao - Joao Gilberto",
    "A Felicidade - Tom Jobim",
    "Preciso Me Encontrar - Cartola",
    "Louco - Joao Gilberto",
    "Melancolia - Luiz Bonfa",
    "Desafinado - Joao Gilberto",
    "Gostava Tanto De Voce - Tim Maia",
    "Onde Anda Voce - Toquinho, Vinicius de Moraes",
    "Se e tarde me perdoa - Joao Gilberto",
    "Voce Vai Ver - Joao Gilberto",
    "Eu Sei Que Vou Te Amar - Tom Jobim",
    "Me De Motivo - Tim Maia",
    "Dedicada a ela - Arthur Verocai",
    "Carta Ao Tom 74 - Vinicius de Moraes",
    "Insensatez - Toquinho, Vinicius de Moraes",
    "Agua de Beber - Quarteto Jobim-Morelenbaum",
    "Por Causa De Voce, Menina - Jorge Ben Jor",
    "Sera que eu to gostando dela? - Tuca Oliveira",
]


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.db: aiosqlite.Connection | None = None
        self.guild_queues: dict[int, deque[dict[str, Any]]] = {}
        self.guild_locks: dict[int, asyncio.Lock] = {}
        self.guild_current: dict[int, dict[str, Any]] = {}
        self.skip_votes: dict[int, set[int]] = {}

    async def cog_load(self) -> None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.db = await aiosqlite.connect(DB_PATH)
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS playlist_comunidade (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT,
                url TEXT,
                adicionado_por TEXT,
                data_adicao TIMESTAMP
            )
            """
        )
        await self.db.commit()

        cursor = await self.db.execute("SELECT COUNT(*) FROM playlist_comunidade")
        row = await cursor.fetchone()
        await cursor.close()
        if row and row[0] == 0:
            await self._run_seed()

    async def cog_unload(self) -> None:
        if self.db:
            await self.db.close()

    def _get_queue(self, guild_id: int) -> deque[dict[str, Any]]:
        return self.guild_queues.setdefault(guild_id, deque())

    def _get_lock(self, guild_id: int) -> asyncio.Lock:
        return self.guild_locks.setdefault(guild_id, asyncio.Lock())

    async def _extract_track(self, search_query: str) -> dict[str, Any]:
        ydl_options = {
            "format": "bestaudio/best",
            "noplaylist": True,
            "default_search": "ytsearch",
            "quiet": True,
            "skip_download": True,
        }

        def _search() -> dict[str, Any]:
            with yt_dlp.YoutubeDL(ydl_options) as ydl:
                info = ydl.extract_info(search_query, download=False)
                if "entries" in info:
                    return info["entries"][0]
                return info

        data = await asyncio.to_thread(_search)
        return {
            "title": data.get("title", "Sem titulo"),
            "webpage_url": data.get("webpage_url", search_query),
            "stream_url": data.get("url"),
            "thumbnail": data.get("thumbnail"),
        }

    async def _run_seed(self) -> None:
        if not self.db:
            return

        for track in SEED_TRACKS:
            try:
                data = await self._extract_track(f"ytsearch1:{track}")
                await self.db.execute(
                    """
                    INSERT INTO playlist_comunidade (titulo, url, adicionado_por, data_adicao)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (data["title"], data["webpage_url"], "Seed: Coffeehouse"),
                )
            except Exception:
                continue
        await self.db.commit()

    async def _connect_voice(
        self, interaction: discord.Interaction
    ) -> discord.VoiceClient | None:
        if not interaction.guild or not interaction.user:
            return None

        user_voice = getattr(interaction.user, "voice", None)
        if not user_voice or not user_voice.channel:
            await interaction.response.send_message(
                "☕ Entre em um canal de voz para usar os comandos de musica.",
                ephemeral=True,
            )
            return None

        voice_client = interaction.guild.voice_client
        if voice_client and voice_client.channel != user_voice.channel:
            await voice_client.move_to(user_voice.channel)
            return voice_client
        if not voice_client:
            return await user_voice.channel.connect()
        return voice_client

    async def _start_next_track(self, guild: discord.Guild) -> None:
        if not guild.voice_client:
            return

        queue = self._get_queue(guild.id)
        if not queue:
            self.guild_current.pop(guild.id, None)
            self.skip_votes.pop(guild.id, None)
            return

        next_track = queue.popleft()
        self.guild_current[guild.id] = next_track
        self.skip_votes[guild.id] = set()
        source = discord.FFmpegPCMAudio(
            next_track["stream_url"],
            before_options=FFMPEG_BEFORE_OPTIONS,
            options=FFMPEG_OPTIONS,
        )

        def _after_playback(error: Exception | None) -> None:
            if error:
                print(f"Erro no player: {error}")
            asyncio.run_coroutine_threadsafe(
                self._start_next_track(guild), self.bot.loop
            )

        guild.voice_client.play(source, after=_after_playback)

    async def _enqueue_and_maybe_play(
        self,
        guild: discord.Guild,
        voice_client: discord.VoiceClient,
        track_data: dict[str, Any],
    ) -> bool:
        lock = self._get_lock(guild.id)
        async with lock:
            queue = self._get_queue(guild.id)
            queue.append(track_data)
            should_start = not voice_client.is_playing() and not voice_client.is_paused()
            if should_start:
                await self._start_next_track(guild)
            return should_start

    def _listeners_in_channel(self, voice_client: discord.VoiceClient) -> list[discord.Member]:
        if not voice_client.channel:
            return []
        return [
            member
            for member in voice_client.channel.members
            if isinstance(member, discord.Member) and not member.bot
        ]

    async def _validate_voice_state(
        self, interaction: discord.Interaction
    ) -> tuple[discord.Guild, discord.VoiceClient] | None:
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message(
                "Esse comando so funciona dentro de um servidor.",
                ephemeral=True,
            )
            return None

        voice_client = guild.voice_client
        if not voice_client or not voice_client.channel:
            await interaction.response.send_message(
                "📻 Nao estou conectado a nenhum canal de voz agora.",
                ephemeral=True,
            )
            return None

        user_voice = getattr(interaction.user, "voice", None)
        if not user_voice or not user_voice.channel:
            await interaction.response.send_message(
                "☕ Entre no meu canal de voz para controlar a reproducao.",
                ephemeral=True,
            )
            return None

        if user_voice.channel != voice_client.channel:
            await interaction.response.send_message(
                "🍂 Voce precisa estar no mesmo canal de voz que eu.",
                ephemeral=True,
            )
            return None

        return guild, voice_client

    def _now_playing_embed(
        self, track_data: dict[str, Any], added_by: str, queued: bool = False
    ) -> discord.Embed:
        title = "📻 Tocando Agora" if not queued else "☕ Musica Adicionada"
        description = (
            f"**{track_data['title']}**\n"
            f"Adicionada por: `{added_by}` 🤎\n"
            f"[Abrir no YouTube]({track_data['webpage_url']})"
        )
        embed = discord.Embed(
            title=title,
            description=description,
            color=COZY_BROWN if not queued else COZY_BEIGE,
        )
        if track_data.get("thumbnail"):
            embed.set_thumbnail(url=track_data["thumbnail"])
        embed.set_footer(text="🍂 P3LUCHE | Cozy Coffeehouse")
        return embed

    @app_commands.command(name="play", description="Toca uma musica por busca ou URL.")
    @app_commands.describe(busca_ou_url="Termo de busca ou URL da musica")
    async def play(self, interaction: discord.Interaction, busca_ou_url: str) -> None:
        voice_client = await self._connect_voice(interaction)
        if not voice_client or not interaction.guild:
            return

        await interaction.response.defer(thinking=True)
        try:
            track_data = await self._extract_track(busca_ou_url)
            track_data["adicionado_por"] = str(interaction.user)
            started_now = await self._enqueue_and_maybe_play(
                interaction.guild,
                voice_client,
                track_data,
            )
            embed = self._now_playing_embed(
                track_data,
                str(interaction.user),
                queued=not started_now,
            )
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(
                f"☕ Nao consegui carregar essa musica agora. Erro: `{exc}`"
            )

    @app_commands.command(
        name="playlist_add", description="Busca e adiciona uma musica na playlist comunitaria."
    )
    @app_commands.describe(busca="Termo de busca no YouTube")
    async def playlist_add(self, interaction: discord.Interaction, busca: str) -> None:
        if not self.db:
            await interaction.response.send_message(
                "Banco de dados ainda nao esta pronto. Tente novamente em alguns segundos.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)
        try:
            track_data = await self._extract_track(f"ytsearch1:{busca}")
            await self.db.execute(
                """
                INSERT INTO playlist_comunidade (titulo, url, adicionado_por, data_adicao)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (track_data["title"], track_data["webpage_url"], str(interaction.user)),
            )
            await self.db.commit()

            embed = self._now_playing_embed(track_data, str(interaction.user), queued=True)
            embed.title = "☕ Musica Salva na Playlist"
            await interaction.followup.send(embed=embed)
        except Exception as exc:
            await interaction.followup.send(
                f"Nao consegui salvar sua musica agora. Erro: `{exc}`"
            )

    @app_commands.command(
        name="playlist_start",
        description="Embaralha e inicia a playlist comunitaria no canal de voz.",
    )
    async def playlist_start(self, interaction: discord.Interaction) -> None:
        if not self.db or not interaction.guild:
            return

        voice_client = await self._connect_voice(interaction)
        if not voice_client:
            return

        await interaction.response.defer(thinking=True)
        cursor = await self.db.execute(
            """
            SELECT titulo, url, adicionado_por
            FROM playlist_comunidade
            ORDER BY id ASC
            """
        )
        rows = await cursor.fetchall()
        await cursor.close()

        if not rows:
            await interaction.followup.send(
                "☕ A playlist comunitaria ainda esta vazia. Use `/playlist_add` primeiro."
            )
            return

        random.shuffle(rows)
        queue = self._get_queue(interaction.guild.id)
        for _, url, adicionado_por in rows:
            try:
                track_data = await self._extract_track(url)
                track_data["adicionado_por"] = adicionado_por
                queue.append(track_data)
            except Exception:
                continue

        if not voice_client.is_playing() and not voice_client.is_paused():
            await self._start_next_track(interaction.guild)

        embed = discord.Embed(
            title="📻 Playlist Comunitaria Iniciada",
            description=(
                f"Foram colocadas **{len(queue)}** musicas na fila.\n"
                "Vibe cozy ativada ☕🤎"
            ),
            color=COZY_BEIGE,
        )
        embed.set_footer(text="🍂 P3LUCHE | Coffeehouse Shuffle")
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="playlist_list",
        description="Lista as musicas salvas na playlist comunitaria.",
    )
    async def playlist_list(self, interaction: discord.Interaction) -> None:
        if not self.db:
            await interaction.response.send_message(
                "Banco de dados ainda nao esta pronto. Tente novamente em alguns segundos.",
                ephemeral=True,
            )
            return

        cursor = await self.db.execute(
            """
            SELECT titulo, adicionado_por
            FROM playlist_comunidade
            ORDER BY id DESC
            LIMIT 20
            """
        )
        rows = await cursor.fetchall()
        await cursor.close()

        if not rows:
            await interaction.response.send_message(
                "☕ Nenhuma musica salva ainda na playlist comunitaria."
            )
            return

        lines = [
            f"`{idx:02d}` **{titulo}** - 🤎 `{adicionado_por}`"
            for idx, (titulo, adicionado_por) in enumerate(rows, start=1)
        ]
        embed = discord.Embed(
            title="🍂 Playlist Comunitaria (ultimas 20)",
            description="\n".join(lines),
            color=COZY_BROWN,
        )
        embed.set_footer(text="☕ Use /playlist_add para contribuir")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="queue",
        description="Mostra a fila atual de reproducao.",
    )
    async def queue(self, interaction: discord.Interaction) -> None:
        if not interaction.guild:
            await interaction.response.send_message(
                "Esse comando so funciona dentro de um servidor.",
                ephemeral=True,
            )
            return

        current = self.guild_current.get(interaction.guild.id)
        queue = list(self._get_queue(interaction.guild.id))

        if not current and not queue:
            await interaction.response.send_message(
                "📻 A fila esta vazia no momento. Use `/play` para comecar."
            )
            return

        lines: list[str] = []
        if current:
            lines.append(
                f"**Agora:** **{current['title']}** - 🤎 `{current.get('adicionado_por', 'Desconhecido')}`"
            )

        if queue:
            for idx, track in enumerate(queue[:20], start=1):
                lines.append(
                    f"`{idx:02d}` **{track['title']}** - ☕ `{track.get('adicionado_por', 'Desconhecido')}`"
                )
            if len(queue) > 20:
                lines.append(f"... e mais **{len(queue) - 20}** musicas.")

        embed = discord.Embed(
            title="📻 Fila Cozy",
            description="\n".join(lines),
            color=COZY_BEIGE,
        )
        embed.set_footer(text="🍂 P3LUCHE | Coffeehouse Queue")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(
        name="skip",
        description="Pula a musica atual (com votacao quando necessario).",
    )
    async def skip(self, interaction: discord.Interaction) -> None:
        validated = await self._validate_voice_state(interaction)
        if not validated:
            return
        guild, voice_client = validated

        if not voice_client.is_playing() and not voice_client.is_paused():
            await interaction.response.send_message(
                "☕ Nao tem nada tocando para pular agora.",
                ephemeral=True,
            )
            return

        listeners = self._listeners_in_channel(voice_client)
        listener_count = len(listeners)
        if listener_count <= 2:
            voice_client.stop()
            await interaction.response.send_message("⏭️ Musica pulada. Bora pra proxima ☕")
            return

        votes = self.skip_votes.setdefault(guild.id, set())
        user_id = interaction.user.id
        if user_id in votes:
            needed = (listener_count // 2) + 1
            await interaction.response.send_message(
                f"🍂 Voce ja votou para pular. Votos: **{len(votes)}/{needed}**.",
                ephemeral=True,
            )
            return

        votes.add(user_id)
        needed = (listener_count // 2) + 1
        if len(votes) >= needed:
            voice_client.stop()
            await interaction.response.send_message(
                f"⏭️ Votacao concluida (**{len(votes)}/{needed}**). Musica pulada!"
            )
            return

        await interaction.response.send_message(
            f"☕ Voto registrado para pular. Progresso: **{len(votes)}/{needed}**."
        )

    @app_commands.command(
        name="stop",
        description="Para a musica, limpa a fila e desconecta do canal de voz.",
    )
    async def stop(self, interaction: discord.Interaction) -> None:
        validated = await self._validate_voice_state(interaction)
        if not validated:
            return
        guild, voice_client = validated

        self._get_queue(guild.id).clear()
        self.guild_current.pop(guild.id, None)
        self.skip_votes.pop(guild.id, None)

        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()
        await voice_client.disconnect(force=True)

        embed = discord.Embed(
            title="☕ Sessao encerrada",
            description="Fila limpa e bot desconectado do canal de voz. Ate ja! 🤎",
            color=COZY_BROWN,
        )
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MusicCog(bot))
