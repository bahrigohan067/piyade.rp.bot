import os
import discord
from discord.ext import commands
from discord import app_commands
import asyncio

# ============================
TICKET_KANAL_ID = 1534770099179884564
TICKET_KATEGORI_ID = None
BILET_LOG_KANAL_ID = 1532828404347437287   # Kapatılan ticket loglarının gideceği kanal

YETKILI_ROL_IDLERI = [
    1553333289798869032,  # TICKET YETKILISI
]
# ============================


def yetkili_mi(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return any(r.id in YETKILI_ROL_IDLERI for r in member.roles)


class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Kapat", style=discord.ButtonStyle.red, custom_id="ticket_kapat_buton")
    async def kapat(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not yetkili_mi(interaction.user):
            return await interaction.response.send_message(
                "❌ Bu işlemi sadece yetkililer yapabilir.", ephemeral=True
            )

        kanal = interaction.channel
        topic = kanal.topic or ""
        acan_id = None
        if "acan_id:" in topic:
            try:
                acan_id = int(topic.split("acan_id:")[1].strip())
            except Exception:
                acan_id = None

        acan_uye = kanal.guild.get_member(acan_id) if acan_id else None

        log_kanal = kanal.guild.get_channel(BILET_LOG_KANAL_ID)
        if log_kanal:
            embed = discord.Embed(
                title="🔒 Ticket Kapatıldı",
                color=discord.Color.red(),
            )
            embed.add_field(name="Kanal", value=f"#{kanal.name}", inline=True)
            embed.add_field(name="Açan Kişi", value=acan_uye.mention if acan_uye else "Bilinmiyor (ayrılmış olabilir)", inline=True)
            embed.add_field(name="Kapatan Kişi", value=interaction.user.mention, inline=True)
            embed.add_field(name="Açılış Tarihi", value=discord.utils.format_dt(kanal.created_at, style="F"), inline=False)
            embed.timestamp = discord.utils.utcnow()
            await log_kanal.send(embed=embed)

        await interaction.response.send_message("Kanal 5 saniye içinde silinecek...")
        # NOT: discord.py'de TextChannel.delete() 'delay' parametresi ALMAZ
        # (bu parametre sadece Message.delete() için var). Eskiden kanal.delete(delay=5)
        # çağrıldığı için arka planda TypeError fırlatıyordu ve kanal hiç silinmiyordu.
        await asyncio.sleep(5)
        try:
            await kanal.delete(reason=f"Ticket kapatıldı - {interaction.user}")
        except discord.NotFound:
            pass


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Ticket Aç", style=discord.ButtonStyle.green, custom_id="ticket_ac_buton")
    async def ticket_ac(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        kanal_adi = f"ticket-{interaction.user.name}".lower()
        acan_tag = f"acan_id:{interaction.user.id}"
        var_olan = next((c for c in guild.text_channels if c.topic and acan_tag in c.topic), None)
        if not var_olan:
            var_olan = discord.utils.get(guild.text_channels, name=kanal_adi)
        if var_olan:
            return await interaction.response.send_message(
                f"Zaten açık bir ticket'ın var: {var_olan.mention}", ephemeral=True
            )

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        }
        for rol_id in YETKILI_ROL_IDLERI:
            rol = guild.get_role(rol_id)
            if rol:
                overwrites[rol] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        kategori = guild.get_channel(TICKET_KATEGORI_ID) if TICKET_KATEGORI_ID else interaction.channel.category

        try:
            kanal = await guild.create_text_channel(
                kanal_adi,
                overwrites=overwrites,
                category=kategori,
                topic=f"acan_id:{interaction.user.id}",
            )
        except discord.Forbidden:
            return await interaction.response.send_message("Botun kanal oluşturma yetkisi yok.", ephemeral=True)

        rol_etiketleri = " ".join(f"<@&{rid}>" for rid in YETKILI_ROL_IDLERI)

        embed = discord.Embed(
            title="🎫 Destek Talebi",
            description=f"{interaction.user.mention} bir destek talebi oluşturdu.\nYetkililer en kısa sürede ilgilenecek.",
            color=discord.Color.blurple(),
        )

        await kanal.send(content=f"{interaction.user.mention} {rol_etiketleri}", embed=embed, view=CloseTicketView())
        await interaction.response.send_message(f"Ticket açıldı: {kanal.mention}", ephemeral=True)


class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ticket-panel", description="Ticket panelini gönderir")
    async def ticket_panel(self, interaction: discord.Interaction):
        if not discord.utils.get(interaction.user.roles, id=1529546007635824680):
            return await interaction.response.send_message("❌ Bu komutu sadece **Kurucu** kullanabilir!", ephemeral=True)

        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("Yetkin yok.", ephemeral=True)
            
        desc = (
            "### • Bilet açma işlemini boşa kullanmayınız. 😇\n\n"
            "### • Bilet butonuna basarak biletinizi açabilirsiniz.\n\n"
            "### • Bileti açtıktan sonra bot yardımcı olacaktır fakat eğer bot istediğiniz yardımı sağlayamadıysa yönetim kadrosunu etiketleyebilirsiniz. [<@&1534798061845483694>]\n\n"
            "### • Bileti açtığınızda saçma sorular sormayın, şımarmayın.\n\n"
            "### • Biz sizlere yardımcı olmak istiyoruz, nasıl yardım edebiliriz? 🌸"
        )
        embed = discord.Embed(
            title="🎫 Destek Sistemi",
            description=desc,
            color=discord.Color.blurple(),
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        
        await interaction.response.defer(ephemeral=True)
        banner_path = os.path.join(os.path.dirname(__file__), "..", "assets", "yeni_banner.png")
        if os.path.exists(banner_path):
            file = discord.File(banner_path, filename="yeni_banner.png")
            embed.set_image(url="attachment://yeni_banner.png")
            await interaction.channel.send(embed=embed, file=file, view=TicketPanelView())
        else:
            await interaction.channel.send(embed=embed, view=TicketPanelView())
        await interaction.followup.send("Panel başarıyla gönderildi.", ephemeral=True)

    @app_commands.command(name="ekle", description="Mevcut bilete bir kullanıcı ekler.")
    @app_commands.describe(
        kisi1="Bilete eklenecek 1. kullanıcı",
        kisi2="Bilete eklenecek 2. kullanıcı (İsteğe bağlı)",
        kisi3="Bilete eklenecek 3. kullanıcı (İsteğe bağlı)"
    )
    async def ekle(self, interaction: discord.Interaction, kisi1: discord.Member, kisi2: discord.Member = None, kisi3: discord.Member = None):
        kanal = interaction.channel
        topic = kanal.topic or ""
        if "acan_id:" not in topic:
            return await interaction.response.send_message("❌ Bu komut sadece bilet (ticket) kanallarında kullanılabilir.", ephemeral=True)
            
        acan_id = None
        try:
            acan_id = int(topic.split("acan_id:")[1].strip())
        except Exception:
            pass

        if interaction.user.id != acan_id and not yetkili_mi(interaction.user):
            return await interaction.response.send_message("❌ Bu bilete kişi ekleme yetkiniz yok.", ephemeral=True)

        kisiler = [k for k in [kisi1, kisi2, kisi3] if k is not None]
        eklenenler = []
        for k in kisiler:
            await kanal.set_permissions(k, view_channel=True, send_messages=True, read_message_history=True)
            eklenenler.append(k.mention)
            
        await interaction.response.send_message(f"✅ Başarıyla bilete eklendi: {', '.join(eklenenler)}")

async def setup(bot):
    await bot.add_cog(Tickets(bot))
