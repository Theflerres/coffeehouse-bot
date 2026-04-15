import discord
from discord.ext import commands, tasks
import yfinance as yf
import datetime
import asyncio
import os

class CoffeeMarketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Pega o ID do canal do .env
        self.canal_id = int(os.getenv('OFFERS_CHANNEL_ID', 0))
        self.daily_coffee_news.start()

    def cog_unload(self):
        self.daily_coffee_news.cancel()

    # Agenda para rodar todos os dias às 09:00 (ajuste o timezone se necessário)
    @tasks.loop(time=datetime.time(hour=9, minute=0))
    async def daily_coffee_news(self):
        if self.canal_id == 0:
            print("Aviso: OFFERS_CHANNEL_ID não configurado no .env")
            return

        canal = self.bot.get_channel(self.canal_id)
        if not canal:
            return

        # Roda a requisição da API de finanças em uma thread separada
        ticker = yf.Ticker("KC=F")
        info = await asyncio.to_thread(getattr, ticker, 'fast_info')
        
        preco_atual = info.last_price
        preco_anterior = info.previous_close
        variacao = preco_atual - preco_anterior
        porcentagem = (variacao / preco_anterior) * 100

        # Define o emoji baseado na alta ou baixa
        tendencia = "📈" if variacao >= 0 else "📉"
        sinal = "+" if variacao >= 0 else ""

        embed = discord.Embed(
            title="☕ Diário do Café: Edição de Hoje",
            description="Bom dia! Aqui está a cotação global do café para você começar o dia.",
            color=0x8B5A2B
        )
        
        embed.add_field(
            name=f"{tendencia} Contrato Futuro (Arábica)", 
            value=f"**US$ {preco_atual:.2f}**\nVariação: {sinal}{variacao:.2f} ({sinal}{porcentagem:.2f}%)", 
            inline=False
        )
        embed.set_footer(text="Tenha um ótimo dia e uma boa xícara de café. 🍂")

        await canal.send(embed=embed)

    @daily_coffee_news.before_loop
    async def before_daily_coffee_news(self):
        # Garante que o bot está logado antes de tentar mandar mensagem
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(CoffeeMarketCog(bot))