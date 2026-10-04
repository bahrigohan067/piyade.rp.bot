import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import os
import asyncio
from datetime import datetime, timezone

class BotStatus(commands.Cog):
    """
    ER:LC oyun sunucusundaki anlık aktif oyuncu sayısını ve sıradaki (kuyruktaki) kişi sayısını
    her 10 saniyede bir döngüsel olarak botun Discord durumunda (Presence / Activity) günceller.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = None
        self.cycle_index = 0

        # Son başarılı veriler hafızada tutulur (Geçici API kopmalarında durumun sıfırlanmasını önler)
        self.last_current_players = 0
        self.last_max_players = 40
        self.last_queue_count = 0
        self.last_server_name = "Piyade Roleplay"
        self.has_data = False

        self.status_loop.start()

    def cog_unload(self):
        self.status_loop.cancel()
        if self.session and not self.session.closed:
            self.bot.loop.create_task(self.session.close())

    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def fetch_erlc_data(self) -> bool:
        """
        ER:LC API'sinden anlık oyuncu ve sıra verilerini çeker.
        """
        api_key = os.getenv("ERLC_API_KEY")
        if not api_key:
            return False

        try:
            session = await self.get_session()
            headers = {"Server-Key": api_key}
            url = "https://api.erlc.gg/v2/server?Queue=true"
            async with session.get(url, headers=headers, timeout=5) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.last_current_players = data.get("CurrentPlayers", 0)
                    self.last_max_players = data.get("MaxPlayers", 40)
                    queue_data = data.get("Queue", [])
                    if isinstance(queue_data, list):
                        self.last_queue_count = len(queue_data)
                    else:
                        self.last_queue_count = int(queue_data or 0)
                    self.last_server_name = data.get("Name", "Piyade Roleplay")
                    self.has_data = True
                    return True
                else:
                    return False
        except Exception:
            return False

    @tasks.loop(seconds=10)
    async def status_loop(self):
        """
        Her 10 saniyede bir çalışan ana durum döngüsü.
        Oyuncu ve sıra sayısını farklı şık formatlarda dönüştürerek gösterir.
        """
        if not self.bot.is_ready():
            return

        # ER:LC API verisini çek
        await self.fetch_erlc_data()

        cur = self.last_current_players
        max_p = self.last_max_players
        queue = self.last_queue_count

        # Her 10 saniyede bir sırayla değişen durum metinleri:
        # Adım 0: Sunucudaki Oyuncu Sayısı (İzliyor)
        # Adım 1: Sırada Bekleyen Sayısı (İzliyor)
        # Adım 2: Kombine Hızlı Özet (Oynuyor)
        # Adım 3: Sunucu Adı & ER:LC (Oynuyor)
        activity = None

        if self.cycle_index == 0:
            activity = discord.Activity(
                type=discord.ActivityType.watching,
                name=f"👥 Sunucu: {cur}/{max_p} Oyuncu"
            )
        elif self.cycle_index == 1:
            if queue > 0:
                sira_metin = f"⏳ Sırada: {queue} Kişi"
            else:
                sira_metin = "✨ Sırada Kimse Yok (Hemen Gir!)"
            activity = discord.Activity(
                type=discord.ActivityType.watching,
                name=sira_metin
            )
        elif self.cycle_index == 2:
            activity = discord.Game(
                name=f"🎮 {cur}/{max_p} Oyuncu | ⏳ {queue} Sıra"
            )
        else:
            activity = discord.Game(
                name=f"🚨 Piyade RP • {self.last_server_name}"
            )

        try:
            await self.bot.change_presence(
                activity=activity,
                status=discord.Status.online
            )
        except Exception:
            pass

        # Bir sonraki adıma geç (0 -> 1 -> 2 -> 3 -> 0)
        self.cycle_index = (self.cycle_index + 1) % 4

    @status_loop.before_loop
    async def before_status_loop(self):
        await self.bot.wait_until_ready()

    # =========================================================================
    # SLASH KOMUT: /sunucu-durum
    # =========================================================================
    @app_commands.command(name="sunucu-durum", description="ER:LC Piyade Roleplay oyun sunucusunun anlık oyuncu ve sıra sayısını gösterir.")
    async def sunucu_durum(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.fetch_erlc_data()

        cur = self.last_current_players
        max_p = self.last_max_players
        queue = self.last_queue_count

        embed = discord.Embed(
            title="🎮 PİYADE ROLEPLAY • ANLIK SUNUCU DURUMU",
            description=f"> **Oyun sunucumuzun anlık doluluk ve sıra bilgileri aşağıda listelenmiştir.**",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(name="🏷️ Sunucu Adı", value=f"**{self.last_server_name}**", inline=False)
        embed.add_field(name="👥 Aktif Oyuncu", value=f"**{cur} / {max_p}**", inline=True)
        embed.add_field(name="⏳ Sırada Bekleyen", value=f"**{queue} Kişi**" if queue > 0 else "✨ **Sıra Yok**", inline=True)
        embed.add_field(name="🟢 Sunucu Durumu", value="`Aktif & Açık`", inline=True)
        embed.set_footer(text="Piyade Roleplay • Canlı Sunucu Takip")

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(BotStatus(bot))
