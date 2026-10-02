import os
import discord
from discord.ext import commands
from discord import app_commands
import re
import aiohttp

# ============================
# KANAL VE ROL ID'LERİ
# ============================
KAYIT_KANAL_ID = 1532831582753128530          # Kayıt butonunun olacağı kanal
ONAY_KANAL_ID = 1532828473972752555           # Yetkililerin önüne düşen başvuru kanalı
KAYIT_LOG_KANAL_ID = 1552306929571733635      # Onaylanan üyelerin duyurulduğu log kanalı

UYE_ROL_ID = 1533919249985437706              # Üye Rolü
WHITELIST_ROL_ID = 1533908873772273715        # Whitelist Rolü
ERKEK_ROL_ID = 1534736940904218755            # Erkek Rolü
KIZ_ROL_ID = 1534736941600342016              # Kız Rolü

KAYITSIZ_ROL_ID = 1542271426386591894         # Kayıtsız Rolü (Onaylanınca alınır)
WHITELIST_YETKILISI_ROL_ID = 1551242344190189718  # Whitelist Yetkilisi Rolü (Bildirim için)

YETKILI_ROL_IDLERI = [
    1529546007635824680,  # KURUCU
    1539167256246747186,  # ÜST YÖNETİM
    1534798061845483694,  # YÖNETİCİ
    1537934087166369812,  # YÖNETİM EKİBİ
    1551242344190189718,  # WHITELIST YETKILISI
]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RED_BANNER_PATH = os.path.join(BASE_DIR, "assets", "roblox_red_banner.png")
PANEL_BANNER_PATH = os.path.join(BASE_DIR, "assets", "yeni_banner.png")
# ============================


def yetkili_mi(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return any(rol.id in YETKILI_ROL_IDLERI for rol in member.roles)


async def roblox_kullanici_bul(bilgi: str):
    bilgi = bilgi.strip()
    user_id = None
    username = None

    eslesme = re.search(r"/users/(\d+)", bilgi)
    if eslesme:
        user_id = eslesme.group(1)
    elif bilgi.isdigit():
        user_id = bilgi

    async with aiohttp.ClientSession() as session:
        if user_id:
            url = f"https://users.roblox.com/v1/users/{user_id}"
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        username = data.get("name")
            except Exception:
                pass
        else:
            url = "https://users.roblox.com/v1/usernames/users"
            try:
                async with session.post(url, json={"usernames": [bilgi], "excludeBannedUsers": False}, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("data") and len(data["data"]) > 0:
                            user_id = str(data["data"][0]["id"])
                            username = data["data"][0]["name"]
            except Exception:
                pass

        avatar_url = None
        if user_id:
            avatar_api = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=420x420&format=Png&isCircular=false"
            try:
                async with session.get(avatar_api, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("data") and len(data["data"]) > 0:
                            avatar_url = data["data"][0].get("imageUrl")
            except Exception:
                pass

    return username, user_id, avatar_url


class KayitModal(discord.ui.Modal, title="📋 Kayıt Formu"):
    gercek_ad = discord.ui.TextInput(
        label="Gerçek adın nedir?",
        placeholder="Örn: Ahmet Yılmaz",
        max_length=50,
        required=True,
    )
    roblox_link = discord.ui.TextInput(
        label="Roblox Adı, ID'si veya Linki",
        placeholder="Örn: Builderman, 156, veya Link",
        max_length=200,
        required=True,
    )
    cinsiyet = discord.ui.TextInput(
        label="Cinsiyetin nedir?",
        placeholder="Erkek veya Kız yazınız",
        max_length=15,
        required=True,
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        onay_kanal = interaction.guild.get_channel(ONAY_KANAL_ID)
        if onay_kanal is None:
            return await interaction.followup.send(
                "❌ Onaylama kanalı bulunamadı, lütfen yöneticilere haber veriniz.", ephemeral=True
            )

        user_id = interaction.user.id

        # 1. Roblox API Doğrulaması
        roblox_ad, roblox_id, roblox_avatar = await roblox_kullanici_bul(self.roblox_link.value)

        # 2. Roblox Hesabı Bulunamazsa OTOMATİK RED
        if not roblox_ad:
            red_embed = discord.Embed(
                title="❌ Kayıt Başvurunuz Otomatik Olarak Reddedildi",
                description=(
                    f"Merhaba {interaction.user.mention},\n\n"
                    f"**ER:LC Piyadeleri** sunucumuza yaptığınız kayıt başvurusu, girdiğiniz Roblox bilgisi doğrulanamadığı için **otomatik olarak reddedilmiştir.**\n\n"
                    f"### 📌 Reddedilme Gerekçesi:\n"
                    f"Formda belirttiğiniz `{self.roblox_link.value}` bilgisi Roblox sistemlerinde bulunamadı veya geçersiz bir format girildi.\n\n"
                    f"### 💡 Çözüm ve Tekrar Başvuru Rehberi:\n"
                    f"• **Doğru Kullanıcı Adı:** Roblox görünen adınızı (Display Name) değil, asıl hesap adınızı (`@` ile başlayan kullanıcı adı) yazınız.\n"
                    f"• **Profil Linki:** Tarayıcınızdan Roblox profilinize girerek linki kopyalayabilirsiniz (Örn: `https://www.roblox.com/users/12345678/profile`).\n"
                    f"• **Sayısal ID:** Profil linkinizde yer alan sayısal ID numaranızı doğrudan yazabilirsiniz.\n"
                    f"• **Yazım Kontrolü:** Harf, rakam ve boşlukları kontrol ettikten sonra kayıt kanalından tekrar başvurabilirsiniz."
                ),
                color=discord.Color.red()
            )
            red_embed.set_footer(text="ER:LC Piyadeleri Kayıt Yönetimi", icon_url=interaction.guild.icon.url if interaction.guild.icon else None)
            red_embed.timestamp = discord.utils.utcnow()

            dm_gonderildi = True
            try:
                if os.path.exists(RED_BANNER_PATH):
                    dosya = discord.File(RED_BANNER_PATH, filename="roblox_red_banner.png")
                    red_embed.set_image(url="attachment://roblox_red_banner.png")
                    await interaction.user.send(embed=red_embed, file=dosya)
                else:
                    await interaction.user.send(embed=red_embed)
            except discord.Forbidden:
                dm_gonderildi = False

            if dm_gonderildi:
                return await interaction.followup.send(
                    "❌ Girdiğiniz Roblox hesabı bulunamadığı için başvurunuz **otomatik olarak reddedildi**.\n"
                    "Gerekçe, çözüm adımları ve bilgilendirme görseli **DM kutunuza iletildi.** Lütfen kontrol edip tekrar deneyiniz.",
                    ephemeral=True
                )
            else:
                # Kullanıcının DM'leri kapalıysa modal yanıtı olarak görsel ve embed'i göster
                if os.path.exists(RED_BANNER_PATH):
                    dosya = discord.File(RED_BANNER_PATH, filename="roblox_red_banner.png")
                    red_embed.set_image(url="attachment://roblox_red_banner.png")
                    return await interaction.followup.send(
                        content="⚠️ DM kutunuz kapalı olduğu için mesaj özelinize iletilemedi. Lütfen aşağıdaki çözüm adımlarını inceleyiniz:",
                        embed=red_embed,
                        file=dosya,
                        ephemeral=True
                    )
                else:
                    return await interaction.followup.send(
                        content="⚠️ DM kutunuz kapalı olduğu için mesaj özelinize iletilemedi. Lütfen aşağıdaki çözüm adımlarını inceleyiniz:",
                        embed=red_embed,
                        ephemeral=True
                    )

        # 3. Roblox Hesabı Başarıyla Doğrulandıysa Onay Kanalına İlet
        embed = discord.Embed(
            title="🆕 Yeni Kayıt Başvurusu",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Discord Kullanıcı", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
        embed.add_field(name="Gerçek Adı", value=self.gercek_ad.value, inline=True)
        embed.add_field(name="Cinsiyet", value=self.cinsiyet.value, inline=True)
        embed.add_field(name="Roblox Adı (Doğrulandı ✅)", value=f"**{roblox_ad}**", inline=False)
        if roblox_id:
            embed.add_field(name="Roblox Profil Linki", value=f"[{roblox_ad} Profili](https://www.roblox.com/users/{roblox_id}/profile) (ID: `{roblox_id}`)", inline=False)
        else:
            embed.add_field(name="Roblox Profil Linki", value=self.roblox_link.value, inline=False)

        if roblox_avatar:
            embed.set_thumbnail(url=roblox_avatar)
        else:
            embed.set_thumbnail(url=interaction.user.display_avatar.url)

        embed.set_footer(text=f"Başvuran ID: {user_id}")
        embed.timestamp = discord.utils.utcnow()

        await onay_kanal.send(
            content=f"<@&{WHITELIST_YETKILISI_ROL_ID}>",
            embed=embed,
            view=OnayView(user_id=user_id),
        )
        await interaction.followup.send(
            f"✅ Roblox hesabınız doğrulandı (**{roblox_ad}**)! Kayıt başvurunuz yetkililere iletildi, lütfen incelenmesini bekleyiniz.",
            ephemeral=True
        )


class KayitButonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ Kayıt Ol", style=discord.ButtonStyle.green, custom_id="kayit_ol_buton")
    async def kayit_ol(self, interaction: discord.Interaction, button: discord.ui.Button):
        if UYE_ROL_ID in [rol.id for rol in interaction.user.roles]:
            return await interaction.response.send_message("❌ Zaten sunucumuza kayıtlısınız!", ephemeral=True)
        await interaction.response.send_modal(KayitModal())


class RedSebepModal(discord.ui.Modal, title="❌ Başvuru Reddetme"):
    sebep = discord.ui.TextInput(
        label="Reddetme Sebebi",
        style=discord.TextStyle.paragraph,
        placeholder="Örn: Bilgiler eksik veya kural ihlali tespit edildi.",
        max_length=400,
        required=True,
    )

    def __init__(self, hedef_kullanici_id: int, orijinal_mesaj: discord.Message):
        super().__init__()
        self.hedef_kullanici_id = hedef_kullanici_id
        self.orijinal_mesaj = orijinal_mesaj

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        uye = guild.get_member(self.hedef_kullanici_id)

        dm_embed = discord.Embed(
            title="❌ Kayıt Başvurunuz Reddedildi",
            description=(
                f"Merhaba {uye.mention if uye else 'Kullanıcı'},\n\n"
                f"**{guild.name}** sunucusundaki kayıt başvurunuz yetkili ekip tarafından incelenmiş ve **reddedilmiştir.**\n\n"
                f"**Reddedilme Sebebi:**\n```{self.sebep.value}```\n"
                f"Sorularınız veya itirazlarınız için yetkili ekibimizle iletişime geçebilirsiniz."
            ),
            color=discord.Color.red()
        )
        dm_embed.set_footer(text=f"İnceleyen Yetkili: {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        dm_embed.timestamp = discord.utils.utcnow()

        dm_gonderildi = True
        if uye:
            try:
                if os.path.exists(RED_BANNER_PATH):
                    dosya = discord.File(RED_BANNER_PATH, filename="roblox_red_banner.png")
                    dm_embed.set_image(url="attachment://roblox_red_banner.png")
                    await uye.send(embed=dm_embed, file=dosya)
                else:
                    await uye.send(embed=dm_embed)
            except discord.Forbidden:
                dm_gonderildi = False

        embed = self.orijinal_mesaj.embeds[0]
        yeni_embed = embed.copy()
        yeni_embed.add_field(
            name="Sonuç",
            value=f"❌ **Reddedildi** — {interaction.user.mention}\n**Sebep:** {self.sebep.value}",
            inline=False,
        )
        yeni_embed.color = discord.Color.red()

        await self.orijinal_mesaj.edit(embed=yeni_embed, view=None)

        ek_bilgi = "" if dm_gonderildi else "\n⚠️ Kullanıcıya DM gönderilemedi (DM kutusu kapalı)."
        await interaction.followup.send(f"✅ Başvuru başarıyla reddedildi.{ek_bilgi}", ephemeral=True)


class OnayView(discord.ui.View):
    def __init__(self, *, user_id: int | None = None):
        super().__init__(timeout=None)
        uid_str = str(user_id) if user_id else "0"
        self.add_item(_OnaylaButon(uid_str))
        self.add_item(_ReddetButon(uid_str))


class _OnaylaButon(discord.ui.Button):
    def __init__(self, uid_str: str):
        super().__init__(
            label="ONAYLA",
            style=discord.ButtonStyle.green,
            custom_id=f"kayit_onayla_{uid_str}",
        )

    async def callback(self, interaction: discord.Interaction):
        if not yetkili_mi(interaction.user):
            return await interaction.response.send_message("❌ Bu işlemi yapma yetkiniz yok.", ephemeral=True)

        hedef_id = None
        try:
            parts = self.custom_id.split("_")
            if len(parts) > 2 and parts[-1].isdigit() and int(parts[-1]) != 0:
                hedef_id = int(parts[-1])
        except Exception:
            pass

        if not hedef_id and interaction.message and interaction.message.embeds:
            footer = interaction.message.embeds[0].footer.text or ""
            match = re.search(r"\d+", footer)
            if match:
                hedef_id = int(match.group())

        if not hedef_id:
            return await interaction.response.send_message("❌ Kullanıcı ID okunamadı.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        uye = guild.get_member(hedef_id)
        if uye is None:
            try:
                uye = await guild.fetch_member(hedef_id)
            except Exception:
                uye = None

        if uye is None:
            return await interaction.followup.send(
                "❌ Kullanıcı sunucuda bulunamadı (ayrılmış olabilir).", ephemeral=True
            )

        embed = interaction.message.embeds[0]
        gercek_ad = embed.fields[1].value
        cinsiyet_cevap = embed.fields[2].value.lower()
        roblox_link = embed.fields[4].value if len(embed.fields) > 4 else embed.fields[3].value

        # Verilecek Roller: Üye (1533919249985437706), Whitelist (1533908873772273715), Cinsiyet Rolü
        rol_idler = [UYE_ROL_ID, WHITELIST_ROL_ID]
        if "erkek" in cinsiyet_cevap or cinsiyet_cevap.startswith("e"):
            rol_idler.append(ERKEK_ROL_ID)
        elif "kız" in cinsiyet_cevap or "kiz" in cinsiyet_cevap or cinsiyet_cevap.startswith("k"):
            rol_idler.append(KIZ_ROL_ID)

        verilecek_roller = [guild.get_role(rid) for rid in rol_idler if guild.get_role(rid) is not None]
        rol_hatasi = False
        try:
            await uye.add_roles(*verilecek_roller, reason="Kayıt onaylandı")
        except discord.Forbidden:
            rol_hatasi = True

        # Kayıtsız rolünü al
        kayitsiz_rol = guild.get_role(KAYITSIZ_ROL_ID)
        if kayitsiz_rol and kayitsiz_rol in uye.roles:
            try:
                await uye.remove_roles(kayitsiz_rol, reason="Kayıt tamamlandı")
            except Exception:
                pass

        # Roblox bilgilerini tazele ve nickname düzenle
        roblox_ad, roblox_id, roblox_avatar = await roblox_kullanici_bul(roblox_link)
        if roblox_ad is None:
            roblox_ad = "RobloxKullanıcı"

        yeni_nick = f"{gercek_ad} | {roblox_ad}"[:32]
        try:
            await uye.edit(nick=yeni_nick, reason="Kayıt onaylandı")
        except discord.Forbidden:
            pass

        # Kullanıcıya DM ile tebrik mesajı gönder
        try:
            tebrik_embed = discord.Embed(
                title="🎉 Kayıt Başvurunuz Onaylandı!",
                description=(
                    f"Merhaba {uye.mention},\n\n"
                    f"**{guild.name}** sunucumuza yaptığınız kayıt başvurusu yetkililer tarafından onaylanmıştır!\n\n"
                    f"• **Sunucu İçi İsminiz:** `{yeni_nick}`\n"
                    f"• **Roblox Hesabınız:** `{roblox_ad}`\n\n"
                    f"Aramıza hoş geldiniz, keyifli oyunlar dileriz! 🎮✨"
                ),
                color=discord.Color.green()
            )
            tebrik_embed.set_footer(text=guild.name, icon_url=guild.icon.url if guild.icon else None)
            tebrik_embed.timestamp = discord.utils.utcnow()
            await uye.send(embed=tebrik_embed)
        except discord.Forbidden:
            pass

        # Kayıt Log Kanalına Bildir
        kayit_log_kanal = interaction.client.get_channel(KAYIT_LOG_KANAL_ID)
        if not kayit_log_kanal:
            try:
                kayit_log_kanal = await interaction.client.fetch_channel(KAYIT_LOG_KANAL_ID)
            except Exception:
                kayit_log_kanal = None

        if kayit_log_kanal:
            log_embed = discord.Embed(
                title="🎉 Yeni Üye Kaydı",
                description=f"{uye.mention} başarıyla kayıt oldu ve aramıza katıldı!",
                color=discord.Color.green(),
            )
            log_embed.add_field(name="👤 Kullanıcı Adı", value=f"**{roblox_ad}**", inline=True)
            if roblox_id:
                log_embed.add_field(name="🆔 Roblox ID", value=f"`{roblox_id}`", inline=True)
                log_embed.add_field(
                    name="🔗 Profil Linki",
                    value=f"[Roblox Profiline Git](https://www.roblox.com/users/{roblox_id}/profile)",
                    inline=False,
                )
            log_embed.add_field(name="🛡️ Onaylayan Yetkili", value=interaction.user.mention, inline=True)
            if roblox_avatar:
                log_embed.set_thumbnail(url=roblox_avatar)
            log_embed.timestamp = discord.utils.utcnow()
            log_embed.set_footer(text=f"Üye ID: {uye.id}")
            await kayit_log_kanal.send(content=uye.mention, embed=log_embed)

        # Başvuru Mesajını Güncelle
        yeni_embed = embed.copy()
        yeni_embed.add_field(
            name="Sonuç",
            value=f"✅ **Onaylandı** — {interaction.user.mention}",
            inline=False,
        )
        yeni_embed.color = discord.Color.green()
        await interaction.message.edit(embed=yeni_embed, view=None)
        if rol_hatasi:
            await interaction.followup.send(
                f"⚠️ {uye.mention} onaylandı ancak **roller verilemedi!** Botun rolü hiyerarşide yeterince üstte değil. "
                f"Lütfen Discord Sunucu Ayarları → Roller bölümünde botun rolünü `Üye`, `Whitelist` ve `Kayıtsız` rollerinin ÜSTÜNE taşıyın.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"✅ {uye.mention} kullanıcısı onaylandı. Roller verildi ve ismi `{yeni_nick}` olarak güncellendi.",
                ephemeral=True
            )


class _ReddetButon(discord.ui.Button):
    def __init__(self, uid_str: str):
        super().__init__(
            label="REDDET",
            style=discord.ButtonStyle.red,
            custom_id=f"kayit_reddet_{uid_str}",
        )

    async def callback(self, interaction: discord.Interaction):
        if not yetkili_mi(interaction.user):
            return await interaction.response.send_message("❌ Bu işlemi yapma yetkiniz yok.", ephemeral=True)

        hedef_id = None
        try:
            parts = self.custom_id.split("_")
            if len(parts) > 2 and parts[-1].isdigit() and int(parts[-1]) != 0:
                hedef_id = int(parts[-1])
        except Exception:
            pass

        if not hedef_id and interaction.message and interaction.message.embeds:
            footer = interaction.message.embeds[0].footer.text or ""
            match = re.search(r"\d+", footer)
            if match:
                hedef_id = int(match.group())

        if not hedef_id:
            return await interaction.response.send_message("❌ Kullanıcı ID okunamadı.", ephemeral=True)

        await interaction.response.send_modal(RedSebepModal(hedef_id, interaction.message))


class Registration(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="kayit-panel", description="Kayıt panelini bu kanala kurar.")
    async def kayit_panel(self, interaction: discord.Interaction):
        if not discord.utils.get(interaction.user.roles, id=1529546007635824680):
            return await interaction.response.send_message("❌ Bu komutu sadece **Kurucu** kullanabilir!", ephemeral=True)

        if not yetkili_mi(interaction.user):
            return await interaction.response.send_message("❌ Yetkiniz bulunmuyor.", ephemeral=True)

        desc = (
            "> 📜 **Kural & Düzen:** Kayıt olmadan önce kuralları okumayı unutmayınız. Sunucu düzenini ve rol kalitesini bozacak davranışlar yasaktır.\n> \n"
            "> 👁️ **Kanal Erişimi:** Sunucu adının üstüne tıklayarak **Tüm Kanalları Göster** seçeneğini mutlaka aktif edin!\n> \n"
            "> 🔗 **Roblox Doğrulaması:** Başvuru sırasında geçerli **Roblox Profil Linkiniz** gereklidir.\n> \n"
            "> 👤 **İsim Tercihi:** Formda gerçek isminizi belirtmek istemiyorsanız takma ad (Roleplay ismi) kullanabilirsiniz.\n> \n"
            "> 💬 **Sohbet & İletişim:** Kaydınız onaylandıktan sonra sohbet kanallarına ilk mesajınızı gönderip topluluğumuza katılabilirsiniz!\n> \n"
            "> 🎫 **Yardım & Destek:** Kayıt olmakta sorun yaşıyorsanız [Destek Bileti](https://discord.com/channels/1529545898294509589/1534770099179884564) kanalından talep oluşturabilirsiniz.\n\n"
            "Aşağıdaki **Kayıt Ol** butonuna basarak başvurunuzu başlatabilirsiniz! 🥳"
        )
        embed = discord.Embed(
            title="🏛️ PİYADE RP | Kayıt Rehberi & Sistemi",
            description=desc,
            color=discord.Color.green(),
        )
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
        
        await interaction.response.defer(ephemeral=True)
        if os.path.exists(PANEL_BANNER_PATH):
            file = discord.File(PANEL_BANNER_PATH, filename="yeni_banner.png")
            embed.set_image(url="attachment://yeni_banner.png")
            await interaction.channel.send(embed=embed, file=file, view=KayitButonView())
        else:
            await interaction.channel.send(embed=embed, view=KayitButonView())
        await interaction.followup.send("✅ Panel başarıyla gönderildi.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Registration(bot))
