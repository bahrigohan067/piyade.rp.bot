import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord.ui import View, Button, Select, UserSelect
import datetime
import asyncio
import os

# ==================== AYARLAR ====================
VS_TALEP_KANAL_ID = 1537136926287593503          # [vs talep] kanalı
VS_SONUC_KANAL_ID = 1537142672953708685          # [vs sonuç] kanalı

KAPISMA_TALEP_YETKILISI_ROLE = 1553427352044707840

PVP_MANAGER_ROLE = 1539169640326893589
DRIVE_MANAGER_ROLE = 1539169263124746350

YONETIM_ROLLER = [KAPISMA_TALEP_YETKILISI_ROLE]

# Kademe rolleri, en düşükten en yükseğe sıralı.
# Kazanan üye bu listede en yüksek sahip olduğu kademeden bir üst kademeye terfi eder.
TEMEL_KADEME = 1541213765410754640
KADEME_1 = 1541214087155810384
KADEME_2 = 1541215423301681252
KADEME_3 = 1541215599026372688
KADEME_4 = 1541216066532016310
KADEME_5 = 1541216359541645312
KADEME_6 = 1541216610751221851
KADEME_7 = 1541216852905041980

TIER_ORDER = [TEMEL_KADEME, KADEME_1, KADEME_2, KADEME_3, KADEME_4, KADEME_5, KADEME_6, KADEME_7]

VS_LOGO_URL = "https://files.catbox.moe/m3e09z.png"
VS_SURE_SAAT = 48  # 2 gün = 48 saat
VS_UYARI_SAAT = 5  # kapanmadan 5 saat önce uyarı
# =================================================


def build_channel_topic(requester_id: int, victim_id: int, vs_type: str, timestamp: float = None) -> str:
    """Kanal 'topic' alanına talep bilgisini gömer, bot yeniden başlasa bile tuşlar doğru çalışsın diye."""
    if timestamp is None:
        timestamp = datetime.datetime.now(datetime.timezone.utc).timestamp()
    return f"vs|{requester_id}|{victim_id}|{vs_type}|{timestamp}"


def parse_channel_topic(channel: discord.TextChannel):
    topic = channel.topic or ""
    try:
        parts = topic.split("|")
        if parts[0] != "vs":
            return None, None, None, None
        rid = int(parts[1])
        vid = int(parts[2])
        vtype = parts[3]
        ts = float(parts[4]) if len(parts) > 4 else None
        return rid, vid, vtype, ts
    except Exception:
        return None, None, None, None


async def promote_winner(guild: discord.Guild, winner: discord.Member):
    """Kazanan üyeyi bir üst kademeye terfi ettirir. Hiçbir kademe rolü yoksa hiçbir şey yapmaz."""
    if winner is None:
        return
    winner_role_ids = {r.id for r in winner.roles}
    # En yüksek kademeden başlayarak kontrol et, sadece bir terfi uygula.
    for i in range(len(TIER_ORDER) - 2, -1, -1):
        current_id = TIER_ORDER[i]
        next_id = TIER_ORDER[i + 1]
        if current_id in winner_role_ids:
            current_role = guild.get_role(current_id)
            next_role = guild.get_role(next_id)
            try:
                if current_role:
                    await winner.remove_roles(current_role, reason="VS kazandı - kademe terfisi")
                if next_role:
                    await winner.add_roles(next_role, reason="VS kazandı - kademe terfisi")
            except discord.Forbidden:
                pass
            return


async def swap_manager_role(guild: discord.Guild, winner: discord.Member, loser: discord.Member, vs_type: str):
    """
    Kaybeden üyede ilgili Manager rolü varsa, o rol kaybedenden alınıp kazanana verilir.
    """
    if winner is None or loser is None:
        return
    manager_role_id = PVP_MANAGER_ROLE if vs_type == "PVP" else DRIVE_MANAGER_ROLE
    if any(r.id == manager_role_id for r in loser.roles):
        role = guild.get_role(manager_role_id)
        if role:
            try:
                await loser.remove_roles(role, reason="VS kaybetti - manager rolü alındı")
                await winner.add_roles(role, reason="VS kazandı - manager rolü devralındı")
            except discord.Forbidden:
                pass


class VSTypeSelect(Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="PVP", value="PVP", description="PVP kapışması", emoji="⚔️"),
            discord.SelectOption(label="DRIVE", value="DRIVE", description="Drive kapışması", emoji="🚗"),
        ]
        super().__init__(
            placeholder="Hangi türde kapışmak istiyorsun?",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="vs_type_select"
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_type = self.values[0]
        await interaction.response.defer()


class VSUserSelect(UserSelect):
    def __init__(self):
        super().__init__(
            placeholder="Kiminle kapışmak istiyorsun? (Mağdur)",
            min_values=1,
            max_values=1,
            custom_id="vs_user_select"
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_user = self.values[0]
        await interaction.response.defer()


class VSRequestView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.selected_user = None
        self.selected_type = None
        self.add_item(VSUserSelect())
        self.add_item(VSTypeSelect())

    @discord.ui.button(label="Talebi Gönder", style=discord.ButtonStyle.danger, emoji="⚔️", custom_id="vs_submit")
    async def submit(self, interaction: discord.Interaction, button: Button):
        if self.selected_user is None or self.selected_type is None:
            await interaction.response.send_message(
                "❌ Lütfen **hem kişiyi** hem de **türü** seçmelisin!",
                ephemeral=True
            )
            return

        if self.selected_user.id == interaction.user.id:
            await interaction.response.send_message("❌ Kendinle kapışamazsın!", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        requester = interaction.user
        victim = self.selected_user
        vs_type = self.selected_type

        # Zaten açık bir talebi olup olmadığını kontrol et
        kategori = interaction.channel.category
        if kategori:
            for channel in kategori.text_channels:
                rid, vid, vtype, ts = parse_channel_topic(channel)
                if rid == requester.id:
                    await interaction.followup.send("❌ Zaten açık bir VS talebiniz bulunuyor. Mevcut kanalınız kapanmadan yenisini açamazsınız!", ephemeral=True)
                    return

        # Kanal ismi — Discord kanal adlarında emoji ve özel karakterler 400 hatasına neden olur.
        # Güvenli karakterleri filtrele: sadece harf, rakam, boşluk ve tire bırak.
        import re as _re
        def _guveni_yap(s: str) -> str:
            s = s[:10]
            s = _re.sub(r"[^\w\s-]", "", s, flags=_re.UNICODE)
            s = s.strip().replace(" ", "-").lower()
            return s or "oyuncu"

        channel_name = f"vs-{_guveni_yap(requester.display_name)}-vs-{_guveni_yap(victim.display_name)}"

        # Overwrites
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            requester: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            victim: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }

        # Kapışma Talep Yetkilisi rolü
        for role_id in YONETIM_ROLLER:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        # Manager rolü
        manager_role_id = PVP_MANAGER_ROLE if vs_type == "PVP" else DRIVE_MANAGER_ROLE
        manager_role = guild.get_role(manager_role_id)
        if manager_role:
            overwrites[manager_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        # Zaman damgası
        now = datetime.datetime.now(datetime.timezone.utc)
        deadline = now + datetime.timedelta(hours=VS_SURE_SAAT)
        discord_ts = int(deadline.timestamp())

        # Kanal oluştur
        category = interaction.channel.category
        new_channel = await guild.create_text_channel(
            name=channel_name,
            overwrites=overwrites,
            category=category,
            topic=build_channel_topic(requester.id, victim.id, vs_type, now.timestamp()),
            reason=f"VS Talebi: {requester} vs {victim} ({vs_type})"
        )

        # Sabit mesaj + butonlar
        embed = discord.Embed(
            title="⚔️ VS Talebi Açıldı",
            description=(
                f"**Açan:** {requester.mention}\n"
                f"**Mağdur:** {victim.mention}\n"
                f"**Tür:** `{vs_type}`\n\n"
                f"⏰ **Son Tarih:** <t:{discord_ts}:F> (<t:{discord_ts}:R>)\n\n"
                f"Kapışma Talep Yetkilisi aşağıdan sonucu belirlesin."
            ),
            color=0xE74C3C
        )

        view = VSChannelView(
            requester_label=f"{requester.display_name} Kazandı",
            victim_label=f"{victim.display_name} Kazandı",
        )
        msg = await new_channel.send(
            content=f"{requester.mention} {victim.mention} "
                    f"{' '.join([f'<@&{r}>' for r in YONETIM_ROLLER])} "
                    f"<@&{manager_role_id}>",
            embed=embed,
            view=view
        )
        await msg.pin()

        await interaction.followup.send(
            f"✅ VS talebin oluşturuldu → {new_channel.mention}",
            ephemeral=True
        )


class VSChannelView(View):
    """
    Bu View artık talep bilgisini kendi içinde tutmuyor (requester_id/victim_id gibi) —
    her tuşa basıldığında bilgiyi kanalın 'topic' alanından okuyor.
    """
    def __init__(self, requester_label: str = "Talebi Açan Kazandı", victim_label: str = "Mağdur Kazandı"):
        super().__init__(timeout=None)
        for child in self.children:
            if getattr(child, "custom_id", None) == "vs_requester_win":
                child.label = requester_label
            elif getattr(child, "custom_id", None) == "vs_victim_win":
                child.label = victim_label

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Sadece Kapışma Talep Yetkilisi basabilir
        user_roles = [r.id for r in interaction.user.roles]
        if not any(r in user_roles for r in YONETIM_ROLLER):
            await interaction.response.send_message("❌ Bu butonlara sadece Kapışma Talep Yetkilisi basabilir!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Talebi Açan Kazandı", style=discord.ButtonStyle.success, custom_id="vs_requester_win")
    async def requester_win(self, interaction: discord.Interaction, button: Button):
        requester_id, victim_id, vs_type, ts = parse_channel_topic(interaction.channel)
        if requester_id is None:
            await interaction.response.send_message("❌ Bu kanalın VS bilgisi okunamadı.", ephemeral=True)
            return
        await self._finish(interaction, winner_id=requester_id, loser_id=victim_id, vs_type=vs_type)

    @discord.ui.button(label="Mağdur Kazandı", style=discord.ButtonStyle.primary, custom_id="vs_victim_win")
    async def victim_win(self, interaction: discord.Interaction, button: Button):
        requester_id, victim_id, vs_type, ts = parse_channel_topic(interaction.channel)
        if requester_id is None:
            await interaction.response.send_message("❌ Bu kanalın VS bilgisi okunamadı.", ephemeral=True)
            return
        await self._finish(interaction, winner_id=victim_id, loser_id=requester_id, vs_type=vs_type)

    @discord.ui.button(label="Talep İptal Edildi", style=discord.ButtonStyle.danger, custom_id="vs_cancel")
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.defer()
        channel = interaction.channel
        if channel:
            await channel.delete(reason="VS Talebi iptal edildi")

    async def _finish(self, interaction: discord.Interaction, winner_id: int, loser_id: int, vs_type: str):
        await interaction.response.defer()

        guild = interaction.guild
        winner = guild.get_member(winner_id)
        loser = guild.get_member(loser_id)

        sonuc_kanal = guild.get_channel(VS_SONUC_KANAL_ID)
        if sonuc_kanal:
            embed = discord.Embed(
                title="🏆 VS Sonucu",
                description=(
                    f"**Kazanan:** {winner.mention if winner else f'<@{winner_id}>'}\n"
                    f"**Kaybeden:** {loser.mention if loser else f'<@{loser_id}>'}\n"
                    f"**Tür:** `{vs_type}`"
                ),
                color=0x2ECC71
            )
            await sonuc_kanal.send(embed=embed)

        # Kademe terfisi (sadece kazanan tarafta kademe rolü varsa çalışır)
        await promote_winner(guild, winner)

        # Manager rolü devri (sadece kaybeden tarafta ilgili manager rolü varsa çalışır)
        await swap_manager_role(guild, winner, loser, vs_type)

        channel = interaction.channel
        if channel:
            await channel.delete(reason="VS sonucu belirlendi")


class VSSetupView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="VS Talep Oluştur", style=discord.ButtonStyle.danger, emoji="⚔️", custom_id="vs_open_request")
    async def open_request(self, interaction: discord.Interaction, button: Button):
        view = VSRequestView()
        await interaction.response.send_message(
            "Aşağıdan **kimi** ve **hangi türde** kapışmak istediğini seç, sonra **Talebi Gönder** butonuna bas:",
            view=view,
            ephemeral=True
        )


class VSTalepCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.vs_deadline_check.start()

    def cog_unload(self):
        self.vs_deadline_check.cancel()


    @app_commands.command(name="vs_talep_panel_kur", description="VS Talep panelini kurar")
    async def vs_talep_panel_kur(self, interaction: discord.Interaction):
        # Yetki kontrolü (sadece Kurucu - 1529546007635824680)
        if not interaction.user.guild_permissions.administrator and not any(rol.id == 1529546007635824680 for rol in interaction.user.roles):
            await interaction.response.send_message("Bu komutu kullanma yetkin yok.", ephemeral=True)
            return

        embed = discord.Embed(
            description=(
                "# PRP | VS Talep\n\n"
                "> Hoş geldiniz. Size en iyi ve en hızlı kapışmayı sunabilmemiz için aşağıdaki kurallara dikkat edin.\n\n"
                "---\n\n"
                "**Kurallar**\n"
                "> • Gereksiz, trolleme amaçlı veya konu dışı talep açmak yasaktır.\n"
                "> • Talep açıldıktan sonra 2 gün süresi vardır. Süre dolunca sorgusuz kapanır.\n"
                "> • Managerlara ya da <@&1553427352044707840>'ne kanıt göstermek zorundasınız.\n"
                "> • Kanıt olmadan hiç bir işlem yapılamaz. ( Geçerli bir kayıt olması lazım)\n"
                "> • Talep sonrası Alay/Dalga/Küçümseme gibi durumlar kabul edilemez.\n"
                "> • Dürüst ve adaletli bir kapışma olsun. (M13!)\n"
                "> • Burada yapılan etkinlikler RP içeriğini etkilemeyecektir!\n\n"
                "---\n\n"
                "Aşağıdaki butona tıklayarak kişiyi ve uygun kısmı seçerek talep oluşturabilirsiniz."
            ),
            color=0x9B59B6
        )
        banner_path = os.path.join(os.path.dirname(__file__), "..", "assets", "yeni_banner.png")
        view = VSSetupView()
        if os.path.exists(banner_path):
            file = discord.File(banner_path, filename="yeni_banner.png")
            embed.set_image(url="attachment://yeni_banner.png")
            await interaction.channel.send(embed=embed, file=file, view=view)
        else:
            embed.set_image(url=VS_LOGO_URL)
            await interaction.channel.send(embed=embed, view=view)
        await interaction.response.send_message("VS Talep paneli başarıyla kuruldu.", ephemeral=True)

    @tasks.loop(minutes=30)
    async def vs_deadline_check(self):
        """Her 30 dakikada bir VS kanallarını kontrol et, süresi dolanlara uyarı/silme uygula."""
        now = datetime.datetime.now(datetime.timezone.utc)

        for guild in self.bot.guilds:
            vs_kanal = guild.get_channel(VS_TALEP_KANAL_ID)
            if not vs_kanal or not vs_kanal.category:
                continue

            for channel in vs_kanal.category.text_channels:
                if channel.id == VS_TALEP_KANAL_ID:
                    continue

                rid, vid, vtype, ts = parse_channel_topic(channel)
                if rid is None or ts is None:
                    continue

                creation_time = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
                elapsed = (now - creation_time).total_seconds() / 3600  # saat cinsinden

                # 2 gün (48 saat) dolmuşsa kanalı sil
                if elapsed >= VS_SURE_SAAT:
                    try:
                        await channel.send("⏰ **Süre doldu!** Bu VS talebi 2 gün içinde sonuçlandırılmadığı için otomatik olarak iptal ediliyor.")
                        await asyncio.sleep(5)
                        await channel.delete(reason="VS Talebi süre aşımı (2 gün)")
                    except Exception:
                        pass
                    continue

                # Kapanmaya 5 saat kala uyarı gönder (43. saat ve sonrası)
                uyari_baslangic = VS_SURE_SAAT - VS_UYARI_SAAT
                if elapsed >= uyari_baslangic:
                    topic_str = channel.topic or ""
                    uyari_atildi = "|warned" in topic_str
                    if not uyari_atildi:
                        async for msg in channel.history(limit=25):
                            if msg.author == self.bot.user and "⚠️ **Dikkat!**" in (msg.content or ""):
                                uyari_atildi = True
                                break

                    if not uyari_atildi:
                        deadline_ts = int(creation_time.timestamp() + VS_SURE_SAAT * 3600)
                        try:
                            await channel.send(
                                f"⚠️ **Dikkat!** Bu VS talebinin kapanmasına **5 saat** kaldı!\n"
                                f"⏰ Son tarih: <t:{deadline_ts}:F> (<t:{deadline_ts}:R>)\n\n"
                                f"Lütfen sonucu belirleyin, aksi takdirde talep otomatik iptal edilecektir."
                            )
                            if topic_str and "|warned" not in topic_str:
                                await channel.edit(topic=f"{topic_str}|warned")
                        except Exception:
                            pass

    @vs_deadline_check.before_loop
    async def before_deadline_check(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(VSTalepCog(bot))