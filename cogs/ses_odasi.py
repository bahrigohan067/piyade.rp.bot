import discord
from discord.ext import commands, tasks
import asyncio

AKTIF_ROL_ID = 1534736941973504032
SES_KANALLARI = [
    1551196392138215434,  # Sohbet Odası 1
    1551196508664242186,  # Sohbet Odası 2
    1551196598472540190,  # Sohbet Odası 3
    1551196973590249552,  # İn The Game 1
    1551197003529199727,  # İn The Game 2
    1551197027617079417   # İn The Game 3
]

SABIT_GUILD_ID = 1529545898294509589
SABIT_SES_KANAL_ID = 1551308350615199935


class SesOdasi(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._baglanma_kilit = asyncio.Lock()
        self._ilk_periyot_gecti = False
        self._gecikme_gorevi: asyncio.Task | None = None

    async def cog_load(self):
        self.ses_bekcisi.start()
        self.periyodik_yeniden_baglan.start()

    def cog_unload(self):
        self.ses_bekcisi.cancel()
        self.periyodik_yeniden_baglan.cancel()
        if self._gecikme_gorevi and not self._gecikme_gorevi.done():
            self._gecikme_gorevi.cancel()

    async def _ses_kanalina_baglan(self):
        async with self._baglanma_kilit:
            guild = self.bot.get_guild(SABIT_GUILD_ID)
            if not guild:
                return

            channel = guild.get_channel(SABIT_SES_KANAL_ID)
            if not isinstance(channel, discord.VoiceChannel):
                return

            vc = guild.voice_client

            # Zaten doğru ses kanalında mı?
            if vc and vc.is_connected():
                if vc.channel and vc.channel.id == SABIT_SES_KANAL_ID:
                    return
                # Başka bir kanala çekilmişse doğru kanala taşı
                try:
                    await vc.move_to(channel)
                    print(f"[SES] Bot hedef ses kanalına taşındı: {channel.name}", flush=True)
                    return
                except Exception:
                    try:
                        await vc.disconnect(force=True)
                    except Exception:
                        pass

            # Bağlantı kopmuşsa veya yoksa sıfırdan bağlan
            try:
                if vc:
                    try:
                        await vc.disconnect(force=True)
                    except Exception:
                        pass
                await channel.connect(reconnect=True, self_deaf=True)
                print(f"[SES] Bot 7/24 ses kanalına bağlandı: {channel.name} ({channel.id})", flush=True)
            except Exception as e:
                print(f"[SES] Ses kanalına bağlanırken hata: {e}", flush=True)

    def _tetikle_gecikmeli_baglan(self, saniye: int = 5):
        if self._gecikme_gorevi and not self._gecikme_gorevi.done():
            self._gecikme_gorevi.cancel()

        async def _bekle_ve_baglan():
            try:
                await asyncio.sleep(saniye)
                await self._ses_kanalina_baglan()
            except asyncio.CancelledError:
                pass

        self._gecikme_gorevi = asyncio.create_task(_bekle_ve_baglan())

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # 1) Botun kendi ses durumu kontrolü (1551308350615199935)
        if member.id == self.bot.user.id:
            # Bot kanaldan atıldıysa veya başka kanala çekildiyse 5 saniye sonra tekrar girsin
            if not after.channel or after.channel.id != SABIT_SES_KANAL_ID:
                print("[SES] Bot hedef ses kanalından ayrıldı veya taşındı. 5 sn sonra yeniden bağlanacak...", flush=True)
                self._tetikle_gecikmeli_baglan(5)
            return

        # 2) Diğer botları yoksay
        if member.bot:
            return

        # 3) Üyeler için aktif rol yönetimi
        aktif_rol = member.guild.get_role(AKTIF_ROL_ID)
        if not aktif_rol:
            return

        joined_target = after.channel and after.channel.id in SES_KANALLARI
        left_target = before.channel and before.channel.id in SES_KANALLARI and (not after.channel or after.channel.id not in SES_KANALLARI)

        if joined_target and aktif_rol not in member.roles:
            try:
                await member.add_roles(aktif_rol, reason="Belirlenen ses kanalına katıldı.")
            except discord.Forbidden:
                pass
        elif left_target and aktif_rol in member.roles:
            try:
                await member.remove_roles(aktif_rol, reason="Belirlenen ses kanalından ayrıldı.")
            except discord.Forbidden:
                pass

    @tasks.loop(minutes=2)
    async def ses_bekcisi(self):
        """Kanalda aktif kalmasını sağlayan bekçi döngüsü (her 2 dakikada bir kontrol eder)."""
        guild = self.bot.get_guild(SABIT_GUILD_ID)
        if not guild:
            return
        vc = guild.voice_client
        if not vc or not vc.is_connected() or not vc.channel or vc.channel.id != SABIT_SES_KANAL_ID:
            await self._ses_kanalina_baglan()

    @ses_bekcisi.before_loop
    async def before_ses_bekcisi(self):
        await self.bot.wait_until_ready()
        await self._ses_kanalina_baglan()

    @tasks.loop(hours=72)
    async def periyodik_yeniden_baglan(self):
        """3 günde bir (72 saatte bir) ses kanalından çık-gir yapar."""
        if not self._ilk_periyot_gecti:
            self._ilk_periyot_gecti = True
            return

        print("[SES] 3 günlük periyodik çık-gir işlemi gerçekleştiriliyor...", flush=True)
        guild = self.bot.get_guild(SABIT_GUILD_ID)
        if guild and guild.voice_client:
            try:
                await guild.voice_client.disconnect(force=True)
            except Exception:
                pass
        await asyncio.sleep(5)
        await self._ses_kanalina_baglan()

    @periyodik_yeniden_baglan.before_loop
    async def before_periyodik_yeniden_baglan(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(SesOdasi(bot))
