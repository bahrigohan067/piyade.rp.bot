import discord
from discord.ext import commands
from discord.ext import tasks
import os

HOSGELDIN_KANAL_ID = 1532829955409449081
CIKIS_KANAL_ID = 1533621981830844538
KATILIMCI_SAYISI_KANAL_ID = 1551308350615199935

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Kanalı en son hangi isimle güncellediğimizi takip ediyoruz
        # böylece gereksiz API çağrısından kaçınıyoruz
        self._son_gosterilen_sayi: int | None = None
        self.katilimci_sayisi_guncelle.start()

    def cog_unload(self):
        self.katilimci_sayisi_guncelle.cancel()

    # ── Discord rate limit: kanal adı maksimum 2 kez / 10 dakika değişebilir.
    # 15 dakikada bir güncellemek bu sınırın tamamen dışında kalır. ──
    @tasks.loop(minutes=15)
    async def katilimci_sayisi_guncelle(self):
        for guild in self.bot.guilds:
            kanal = guild.get_channel(KATILIMCI_SAYISI_KANAL_ID)
            if not kanal:
                continue
            yeni_sayi = guild.member_count
            if yeni_sayi == self._son_gosterilen_sayi:
                continue  # Sayı değişmemişse API çağrısı yapma
            yeni_isim = f"══▐ {yeni_sayi} KATILIMCI▐ ══"
            try:
                await kanal.edit(name=yeni_isim)
                self._son_gosterilen_sayi = yeni_sayi
            except discord.HTTPException as e:
                print(f"[welcome] Katılımcı sayısı güncellenemedi: {e}")

    @katilimci_sayisi_guncelle.before_loop
    async def before_guncelle(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_join(self, member):
        # Katılımcı sayısı artık task loop tarafından güncelleniyor.
        
        # Kayıtsız rolünü ver
        kayitsiz_rol = member.guild.get_role(1542271426386591894)
        if kayitsiz_rol:
            try:
                await member.add_roles(kayitsiz_rol, reason="Sunucuya katıldı")
            except Exception:
                pass
        
        channel = member.guild.get_channel(HOSGELDIN_KANAL_ID)
        if channel is None:
            return

        member_count = member.guild.member_count

        embed = discord.Embed(
            title="✨ Sunucumuza Hoş Geldin!",
            description=(
                f"Merhaba {member.mention}!\n\n"
                f"**{member.guild.name}** ailesine katıldığın için çok mutluyuz.\n"
                f"Seninle birlikte artık **{member_count}** kişiyiz!\n\n"
                f"📜 Kuralları okumayı unutma\n"
                f"💬 Sohbete katılmaktan çekinme\n"
                f"🎮 İyi eğlenceler dileriz!"
            ),
            color=discord.Color.from_rgb(147, 112, 219)
        )
        embed.set_thumbnail(url=member.display_avatar.url)

        gif_path = os.path.join(os.path.dirname(__file__), "..", "assets", "hosgeldin.gif")
        dosya = None
        if os.path.exists(gif_path):
            dosya = discord.File(gif_path, filename="hosgeldin.gif")
            embed.set_image(url="attachment://hosgeldin.gif")

        embed.set_footer(
            text=f"ID: {member.id} • Katılma",
            icon_url=member.guild.icon.url if member.guild.icon else None
        )
        embed.timestamp = discord.utils.utcnow()

        if dosya:
            await channel.send(content=f"Hoş geldin {member.mention} 💜", embed=embed, file=dosya)
        else:
            await channel.send(content=f"Hoş geldin {member.mention} 💜", embed=embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        
        channel = member.guild.get_channel(CIKIS_KANAL_ID)
        if channel is None:
            return

        embed = discord.Embed(
            title="👋 Bir Üye Ayrıldı",
            description=f"**{member.display_name}** ({member.mention}) aramızdan ayrıldı.",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"ID: {member.id}")
        embed.timestamp = discord.utils.utcnow()

        await channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Welcome(bot))