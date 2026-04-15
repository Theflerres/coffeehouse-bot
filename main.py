import asyncio
import os
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv


BASE_DIR = Path(__file__).parent
COGS_DIR = BASE_DIR / "cogs"


class PelucheBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = False
        super().__init__(
            command_prefix="!",
            intents=intents,
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="Bossa Nova ☕",
            ),
        )

    async def setup_hook(self) -> None:
        for file_path in COGS_DIR.glob("*.py"):
            if file_path.name.startswith("_"):
                continue
            await self.load_extension(f"cogs.{file_path.stem}")

        synced = await self.tree.sync()
        print(f"Slash commands sincronizados: {len(synced)}")

    async def on_ready(self) -> None:
        print(f"{self.user} conectado e pronto.")


async def main() -> None:
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN nao encontrado no .env")

    bot = PelucheBot()
    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
