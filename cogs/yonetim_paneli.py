import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from typing import Optional

# YETKİLİ ROLLERİ (KİM KULLANABİLİR)
KURUCU_ROL_ID = 1529546007635824680
UST_YONETIM_ROL_ID = 1539167256246747186

# VERİLECEK ROLLER
TRIAL_STAFF_ID = 1551241468985737376
STAFF_ID = 1551241634094645288
SENIOR_STAFF_ID = 1551241753137254611
WHITELIST_YETKILISI_ID = 1551242344190189718
MESAJ_DENETIMCISI_ID = 1542249243702726796
SES_KANALI_YETKILISI_ID = 1547526649459777556
TAKMA_AD_YETKILISI_ID = 1543075759508164659

TICKET_YETKILISI_ID = 1553333289798869032
KAPISMA_TALEP_YETKILISI_ID = 1553427352044707840
DESTEK_BEKLEME_YETKILISI_ID = 1553473785527537765

def paneli_kullanabilir_mi(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return any(rol.id in [KURUCU_ROL_ID, UST_YONETIM_ROL_ID] for rol in member.roles)

class YonetimUserSelect(discord.ui.UserSelect):
    def __init__(self, islem_turu: str):
        super().__init__(placeholder="Lütfen işlem yapılacak kullanıcıyı seçin", min_values=1, max_values=1)
        self.islem_turu = islem_turu

    async def callback(self, interaction: discord.Interaction):
        hedef_uye = self.values[0]
        guild = interaction.guild

        if not isinstance(hedef_uye, discord.Member):
            return await interaction.response.send_message("❌ Lütfen sunucuda bulunan geçerli bir üyeyi seçin.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        # Roller
        trial_rol = guild.get_role(TRIAL_STAFF_ID)
        staff_rol = guild.get_role(STAFF_ID)
        senior_rol = guild.get_role(SENIOR_STAFF_ID)
        wl_rol = guild.get_role(WHITELIST_YETKILISI_ID)
        mesaj_rol = guild.get_role(MESAJ_DENETIMCISI_ID)
        ses_rol = guild.get_role(SES_KANALI_YETKILISI_ID)
        takma_ad_rol = guild.get_role(TAKMA_AD_YETKILISI_ID)
        ticket_yetk_rol = guild.get_role(TICKET_YETKILISI_ID)
        kapisma_yetk_rol = guild.get_role(KAPISMA_TALEP_YETKILISI_ID)
        destek_bekleme_rol = guild.get_role(DESTEK_BEKLEME_YETKILISI_ID)

        uye_rol_idleri = [r.id for r in hedef_uye.roles]
        
        has_staff_base = any(rid in uye_rol_idleri for rid in [TRIAL_STAFF_ID, STAFF_ID, SENIOR_STAFF_ID])

        mesaj = ""

        try:
            if self.islem_turu == "trial":
                # Tüm roller tek API çağrısında verilir
                roller = [r for r in [trial_rol, wl_rol, ticket_yetk_rol, kapisma_yetk_rol] if r]
                if roller:
                    await hedef_uye.add_roles(*roller)
                mesaj = f"✅  {hedef_uye.mention} başarıyla **Trial Staff**, **Whitelist Yetkilisi**, **Ticket Yetkilisi** ve **Kapışma Talep Yetkilisi** yapıldı."

            elif self.islem_turu == "staff":
                if TRIAL_STAFF_ID not in uye_rol_idleri:
                    return await interaction.followup.send("❌ Bu kişiye **Staff** verebilmek için üzerinde **Trial Staff** rolü olması ZORUNLUDUR!", ephemeral=True)
                ekle = [r for r in [staff_rol, destek_bekleme_rol] if r]
                kaldir = [r for r in [trial_rol] if r]
                if ekle:
                    await hedef_uye.add_roles(*ekle)
                if kaldir:
                    await hedef_uye.remove_roles(*kaldir)
                mesaj = f"✅  {hedef_uye.mention} başarıyla **Staff** ve **Destek Bekleme Yetkilisi** yapıldı (Trial Staff alındı)."

            elif self.islem_turu == "senior":
                if STAFF_ID not in uye_rol_idleri:
                    return await interaction.followup.send("❌ Bu kişiye **Senior Staff** verebilmek için üzerinde **Staff** rolü olması ZORUNLUDUR!", ephemeral=True)
                if senior_rol:
                    await hedef_uye.add_roles(senior_rol)
                if staff_rol:
                    await hedef_uye.remove_roles(staff_rol)
                mesaj = f"✅ {hedef_uye.mention} başarıyla **Senior Staff** yapıldı (Staff alındı)."

            elif self.islem_turu == "mesaj":
                if not has_staff_base:
                    return await interaction.followup.send("❌ Bu rolü alacak kişinin Staff rollerinden birine (Trial Staff, Staff, Senior Staff) sahip olması ZORUNLUDUR!", ephemeral=True)
                if mesaj_rol:
                    await hedef_uye.add_roles(mesaj_rol)
                mesaj = f"✅ {hedef_uye.mention} başarıyla **Mesaj Denetimcisi** yapıldı."

            elif self.islem_turu == "ses":
                if not has_staff_base:
                    return await interaction.followup.send("❌ Bu rolü alacak kişinin Staff rollerinden birine (Trial Staff, Staff, Senior Staff) sahip olması ZORUNLUDUR!", ephemeral=True)
                if ses_rol:
                    await hedef_uye.add_roles(ses_rol)
                mesaj = f"✅ {hedef_uye.mention} başarıyla **Ses Kanalı Yetkilisi** yapıldı."

            elif self.islem_turu == "takma_ad":
                if not has_staff_base:
                    return await interaction.followup.send("❌ Bu rolü alacak kişinin Staff rollerinden birine (Trial Staff, Staff, Senior Staff) sahip olması ZORUNLUDUR!", ephemeral=True)
                if takma_ad_rol:
                    await hedef_uye.add_roles(takma_ad_rol)
                mesaj = f"✅ {hedef_uye.mention} başarıyla **Takma Ad Yetkilisi** yapıldı."

            await interaction.followup.send(mesaj, ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("❌ Botun bu rolleri verme/alma yetkisi yok (Botun rolü, verilecek rolden daha üstte olmalı).", ephemeral=True)

class YonetimSelectView(discord.ui.View):
    def __init__(self, islem_turu: str):
        super().__init__(timeout=120)
        self.add_item(YonetimUserSelect(islem_turu))

class YonetimButonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Trial Staff", style=discord.ButtonStyle.primary, custom_id="ybtn_trial")
    async def btn_trial(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not paneli_kullanabilir_mi(interaction.user):
            return await interaction.response.send_message("❌ Bu paneli kullanma yetkiniz yok.", ephemeral=True)
        await interaction.response.send_message("Lütfen **Trial Staff** yapılacak kişiyi seçin:", view=YonetimSelectView("trial"), ephemeral=True)

    @discord.ui.button(label="Staff", style=discord.ButtonStyle.primary, custom_id="ybtn_staff")
    async def btn_staff(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not paneli_kullanabilir_mi(interaction.user):
            return await interaction.response.send_message("❌ Bu paneli kullanma yetkiniz yok.", ephemeral=True)
        await interaction.response.send_message("Lütfen **Staff** yapılacak kişiyi seçin:", view=YonetimSelectView("staff"), ephemeral=True)

    @discord.ui.button(label="Senior Staff", style=discord.ButtonStyle.primary, custom_id="ybtn_senior")
    async def btn_senior(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not paneli_kullanabilir_mi(interaction.user):
            return await interaction.response.send_message("❌ Bu paneli kullanma yetkiniz yok.", ephemeral=True)
        await interaction.response.send_message("Lütfen **Senior Staff** yapılacak kişiyi seçin:", view=YonetimSelectView("senior"), ephemeral=True)

    @discord.ui.button(label="Mesaj Denetimcisi", style=discord.ButtonStyle.secondary, custom_id="ybtn_mesaj")
    async def btn_mesaj(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not paneli_kullanabilir_mi(interaction.user):
            return await interaction.response.send_message("❌ Bu paneli kullanma yetkiniz yok.", ephemeral=True)
        await interaction.response.send_message("Lütfen **Mesaj Denetimcisi** yapılacak kişiyi seçin:", view=YonetimSelectView("mesaj"), ephemeral=True)

    @discord.ui.button(label="Ses Kanalı Yetkilisi", style=discord.ButtonStyle.secondary, custom_id="ybtn_ses")
    async def btn_ses(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not paneli_kullanabilir_mi(interaction.user):
            return await interaction.response.send_message("❌ Bu paneli kullanma yetkiniz yok.", ephemeral=True)
        await interaction.response.send_message("Lütfen **Ses Kanalı Yetkilisi** yapılacak kişiyi seçin:", view=YonetimSelectView("ses"), ephemeral=True)

    @discord.ui.button(label="Takma Ad Yetkilisi", style=discord.ButtonStyle.secondary, custom_id="ybtn_takma_ad")
    async def btn_takma_ad(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not paneli_kullanabilir_mi(interaction.user):
            return await interaction.response.send_message("❌ Bu paneli kullanma yetkiniz yok.", ephemeral=True)
        await interaction.response.send_message("Lütfen **Takma Ad Yetkilisi** yapılacak kişiyi seçin:", view=YonetimSelectView("takma_ad"), ephemeral=True)


class YonetimPaneli(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="yonetim-panel", description="Yönetim kadro belirleme panelini gönderir.")
    async def yonetim_panel(self, interaction: discord.Interaction):
        if not discord.utils.get(interaction.user.roles, id=1529546007635824680):
            return await interaction.response.send_message("❌ Bu komutu sadece **Kurucu** kullanabilir!", ephemeral=True)

        if not paneli_kullanabilir_mi(interaction.user):
            return await interaction.response.send_message("❌ Bu komutu kullanma yetkiniz yok.", ephemeral=True)

        desc = (
            "Lütfen terfi ettirmek istediğiniz rütbenin butonuna basın, ardından açılacak menüden kullanıcıyı seçin.\n\n"
            "🔸 **Trial Staff:** Seçilen kişiye Trial Staff, Registration Manager (Whitelist Yetkilisi), Ticket Yetkilisi ve Kapışma Talep Yetkilisi verir.\n"
            "🔸 **Staff:** Seçilen kişinin Staff ve Destek Bekleme Yetkilisi olmasını sağlar. *(Trial Staff zorunludur)*.\n"
            "🔸 **Senior Staff:** Seçilen kişinin Senior Staff olmasını sağlar. *(Staff zorunludur)*.\n"
            "🔸 **Mesaj Denetimcisi:** Seçilen kişiye Mesaj Denetimcisi rolü verilir. *(Staff rollerinden biri zorunludur)*.\n"
            "🔸 **Ses Kanalı Yetkilisi:** Seçilen kişiye Ses Kanalı Yetkilisi rolü verilir. *(Staff rollerinden biri zorunludur)*.\n"
            "🔸 **Takma Ad Yetkilisi:** Seçilen kişiye Takma Ad Yetkilisi rolü verilir. *(Staff rollerinden biri zorunludur)*."
        )

        embed = discord.Embed(
            title="Yönetim Kadro Belirleme",
            description=desc,
            color=discord.Color.gold()
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)

        await interaction.channel.send(embed=embed, view=YonetimButonView())
        await interaction.response.send_message("Yönetim paneli gönderildi.", ephemeral=True)

    @app_commands.command(name="rols", description="Sunucudaki tüm rolleri baştan aşağıya dizilimiyle etiketleyip sıralar.")
    @app_commands.describe(
        kanal="Rollerin gönderileceği hedef kanal (Boş bırakılırsa bu kanala gönderilir)",
        detayli="Rol ID'si ve üye sayısını da göstersin mi? (Varsayılan: Hayır)",
        bildirim="Rol sahiplerine bildirim/ping gitsin mi? (Varsayılan: Hayır)"
    )
    async def rols(
        self,
        interaction: discord.Interaction,
        kanal: Optional[discord.TextChannel] = None,
        detayli: bool = False,
        bildirim: bool = False
    ):
        ASIL_KURUCU_ID = 1133815339898122320
        if interaction.user.id != ASIL_KURUCU_ID:
            return await interaction.response.send_message(
                "❌ Bu komutu sadece **Asıl Sunucu Kurucusu** (<@1133815339898122320>) kullanabilir!",
                ephemeral=True
            )

        guild = interaction.guild
        if not guild:
            return await interaction.response.send_message("❌ Bu komut sadece bir sunucuda kullanılabilir.", ephemeral=True)

        hedef_kanal = kanal or interaction.channel

        # Botun hedef kanala yazma yetkisi var mı kontrol et
        perms = hedef_kanal.permissions_for(guild.me)
        if not perms.send_messages:
            return await interaction.response.send_message(
                f"❌ Botun {hedef_kanal.mention} kanalına mesaj gönderme yetkisi yok!",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        # Sunucu ayarlarında roller en alttan (position=0, @everyone) en üste (position=N) sıralıdır.
        # "Baştan aşağıya dizilimi" için en yüksek rolden en alta doğru sıralıyoruz:
        tum_roller = sorted(guild.roles, key=lambda r: r.position, reverse=True)
        sirali_roller = [r for r in tum_roller if not r.is_default()]
        everyone_rol = guild.default_role

        lines = []
        for index, rol in enumerate(sirali_roller, start=1):
            if detayli:
                bot_etiketi = " `[BOT]`" if rol.managed else ""
                lines.append(f"**{index}.** {rol.mention} — `ID: {rol.id}` • `{len(rol.members)} Üye`{bot_etiketi}")
            else:
                lines.append(f"**{index}.** {rol.mention}")

        # En alta @everyone rolünü ekle
        if everyone_rol:
            sira_everyone = len(sirali_roller) + 1
            if detayli:
                lines.append(f"**{sira_everyone}.** `@everyone` — `ID: {everyone_rol.id}` • `{len(guild.members)} Üye`")
            else:
                lines.append(f"**{sira_everyone}.** `@everyone`")

        header = (
            "# 👑 PİYADE ROLEPLAY | ROL HİYERARŞİSİ & DİZİLİMİ\n"
            f"> Sunucu ayarlarındaki **en yüksek rolden en alt role doğru** hiyerarşik sıralama:\n"
            "──────────────────────────────────────────\n"
        )
        footer = f"\n──────────────────────────────────────────\n📊 **Toplam Rol Sayısı:** `{len(tum_roller)}`"

        # Discord 2000 karakter sınırını aşmamak için güvenli parçalama (chunking)
        chunks = []
        current_chunk = header

        for line in lines:
            if len(current_chunk) + len(line) + 1 > 1850:
                chunks.append(current_chunk)
                current_chunk = line + "\n"
            else:
                current_chunk += line + "\n"

        if current_chunk:
            if len(current_chunk) + len(footer) <= 1950:
                current_chunk += footer
                chunks.append(current_chunk)
            else:
                chunks.append(current_chunk)
                chunks.append(footer.strip())

        # allowed_mentions: Bildirim False ise kullanıcıları rahatsız etmemek için ping bildirimleri kapatılır
        # (Discord'da role pill @Rol görünümü korunur, sadece kullanıcılara ses/bildirim zili gitmez)
        allowed_mentions = discord.AllowedMentions(
            roles=bildirim,
            everyone=bildirim,
            users=False
        )

        try:
            for idx, chunk in enumerate(chunks):
                await hedef_kanal.send(chunk, allowed_mentions=allowed_mentions)
                if len(chunks) > 1 and idx < len(chunks) - 1:
                    await asyncio.sleep(0.5)

            await interaction.followup.send(
                f"✅ Başarılı! Toplam **{len(tum_roller)}** rol hiyerarşik dizilimiyle {hedef_kanal.mention} kanalına sıralandı ve gönderildi.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Mesaj gönderilirken bir hata oluştu: {e}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(YonetimPaneli(bot))
