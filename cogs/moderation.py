import discord
from discord.ext import commands
from discord import app_commands
from datetime import timedelta
import re


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="temizle")
    @commands.has_permissions(manage_messages=True)
    async def temizle(self, ctx, miktar: int = 5):
        if miktar < 1 or miktar > 100:
            return await ctx.send("1-100 arası sayı gir.", delete_after=5)
        try:
            # check= ile 14 günden eski mesajları atlıyoruz (Discord API limiti)
            import datetime
            sinir = discord.utils.utcnow() - datetime.timedelta(days=14)

            def yeterince_yeni(msg: discord.Message) -> bool:
                return msg.created_at.replace(tzinfo=datetime.timezone.utc) > sinir

            silinenler = await ctx.channel.purge(limit=miktar + 1, check=yeterince_yeni)
            gercek_miktar = max(0, len(silinenler) - 1)
            await ctx.send(f"✅ **{gercek_miktar}** mesaj başarıyla silindi.", delete_after=3)
        except discord.NotFound:
            await ctx.send("✅ Mesajlar silindi (Bazı mesajlar önceden silinmiş olabilir).", delete_after=3)
        except discord.HTTPException as e:
            await ctx.send(f"⚠️ Silme işlemi sırasında bir sorun oluştu: {e}", delete_after=5)

    @app_commands.command(name="kick", description="Üyeyi sunucudan atar")
    @app_commands.describe(uye="Atılacak üye", sebep="Sebep")
    async def kick(self, interaction: discord.Interaction, uye: discord.Member, sebep: str = "Sebep belirtilmedi"):
        if not interaction.user.guild_permissions.kick_members:
            return await interaction.response.send_message("Yetkin yok.", ephemeral=True)
        # Yetkili hiyerarşi kontrolü
        if uye.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message(
                "❌ Bu üyeye işlem yapamazsın — hedefin rolü senden üstün veya sana eşit.", ephemeral=True
            )
        # Bot hiyerarşi kontrolü
        if uye.top_role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                "❌ Bu üyeyi atamam — botun rolü hedefin rolünden düşük veya eşit.", ephemeral=True
            )
        await interaction.response.defer()
        try:
            await uye.kick(reason=sebep)
            await interaction.followup.send(f"{uye.mention} atıldı.\n**Sebep:** {sebep}")
        except discord.Forbidden:
            await interaction.followup.send("❌ Bu üyeyi atma yetkim yok.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Bir hata oluştu: {e}", ephemeral=True)

    @app_commands.command(name="ban", description="Üyeyi yasaklar")
    @app_commands.describe(uye="Yasaklanacak üye", sebep="Sebep")
    async def ban(self, interaction: discord.Interaction, uye: discord.Member, sebep: str = "Sebep belirtilmedi"):
        if not interaction.user.guild_permissions.ban_members:
            return await interaction.response.send_message("Yetkin yok.", ephemeral=True)
        # Yetkili hiyerarşi kontrolü
        if uye.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message(
                "❌ Bu üyeye işlem yapamazsın — hedefin rolü senden üstün veya sana eşit.", ephemeral=True
            )
        # Bot hiyerarşi kontrolü
        if uye.top_role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                "❌ Bu üyeyi yasaklayamam — botun rolü hedefin rolünden düşük veya eşit.", ephemeral=True
            )
        await interaction.response.defer()
        try:
            await uye.ban(reason=sebep)
            await interaction.followup.send(f"{uye.mention} yasaklandı.\n**Sebep:** {sebep}")
        except discord.Forbidden:
            await interaction.followup.send("❌ Bu üyeyi yasaklama yetkim yok.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"❌ Bir hata oluştu: {e}", ephemeral=True)

    @app_commands.command(name="timeout", description="Üyeye timeout uygular")
    @app_commands.describe(uye="Üye", dakika="Kaç dakika", sebep="Sebep")
    async def timeout(self, interaction: discord.Interaction, uye: discord.Member, dakika: int, sebep: str = "Sebep belirtilmedi"):
        if not interaction.user.guild_permissions.moderate_members:
            return await interaction.response.send_message("Yetkin yok.", ephemeral=True)
        if dakika < 1 or dakika > 40320:
            return await interaction.response.send_message("1 ile 40320 arasında sayı gir.", ephemeral=True)
        # Yetkili hiyerarşi kontrolü
        if uye.top_role >= interaction.user.top_role and interaction.user.id != interaction.guild.owner_id:
            return await interaction.response.send_message(
                "❌ Bu üyeye işlem yapamazsın — hedefin rolü senden üstün veya sana eşit.", ephemeral=True
            )
        # Bot hiyerarşi kontrolü
        if uye.top_role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                "❌ Bu üyeye timeout uygulayamam — botun rolü hedefin rolünden düşük veya eşit.", ephemeral=True
            )
        bitis = discord.utils.utcnow() + timedelta(minutes=dakika)
        try:
            await uye.timeout(bitis, reason=sebep)
            await interaction.response.send_message(f"{uye.mention} **{dakika} dakika** timeout yedi.\n**Sebep:** {sebep}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bu üyeye timeout uygulama yetkim yok.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Bir hata oluştu: {e}", ephemeral=True)

    @app_commands.command(name="kanal-ac", description="Kategori içinde kanal oluşturur")
    @app_commands.describe(kategori="Kategori seç", isim="Kanalın adı")
    async def kanal_ac(self, interaction: discord.Interaction, kategori: discord.CategoryChannel, isim: str):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("Yetkin yok.", ephemeral=True)
        try:
            kanal = await kategori.create_text_channel(name=isim)
            await interaction.response.send_message(f"Kanal oluşturuldu: {kanal.mention}")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Kanal oluşturma yetkim yok.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.response.send_message(f"❌ Kanal oluşturulamadı: {e}", ephemeral=True)

    @app_commands.command(name="kanal-kapa", description="Kanal linkiyle kanalı siler")
    @app_commands.describe(kanal_linki="Silinecek kanalın linki")
    async def kanal_kapa(self, interaction: discord.Interaction, kanal_linki: str):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("Yetkin yok.", ephemeral=True)
        eslesme = re.search(r"/channels/\d+/(\d+)", kanal_linki)
        if not eslesme:
            return await interaction.response.send_message("Geçersiz kanal linki.", ephemeral=True)
        kanal = interaction.guild.get_channel(int(eslesme.group(1)))
        if kanal is None:
            return await interaction.response.send_message("Kanal bulunamadı.", ephemeral=True)
        isim = kanal.name
        try:
            await kanal.delete()
            await interaction.response.send_message(f"**{isim}** kanalı silindi.")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Bu kanalı silme yetkim yok.", ephemeral=True)

    @app_commands.command(name="mesaj-gonder", description="Bir kullanıcıya DM gönderir")
    @app_commands.describe(uye="Mesaj gönderilecek kişi", mesaj="Gönderilecek mesaj")
    async def mesaj_gonder(self, interaction: discord.Interaction, uye: discord.Member, mesaj: str):
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("Yetkin yok.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            await uye.send(mesaj)
            await interaction.followup.send(f"{uye.mention} kişisine DM gönderildi.", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("Bu kullanıcıya DM gönderilemiyor.", ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f"Bir hata oluştu: {e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Moderation(bot))