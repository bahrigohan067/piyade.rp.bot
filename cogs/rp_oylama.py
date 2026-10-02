import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import json
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import Optional

# ── SABİT TANIMLAMALAR VE ID'LER ──
GUILD_ID = 1529545898294509589
PANEL_KANAL_ID = 1554037075563651182       # Oylama ve durum panelinin bulunacağı kanal
DUYURU_KANAL_ID = 1554103929451581460      # Rol başladığında @| Whitelist pingli duyurunun atılacağı kanal
WHITELIST_ROL_ID = 1533908873772273715     # @| Whitelist Rolü
KURUCU_ROL_ID = 1529546007635824680        # Kurucu Rolü
UST_YONETIM_ROL_ID = 1539167256246747186   # Üst Yönetim Rolü

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, "data", "rp_sistemi.json")
BANNER_PATH = os.path.join(BASE_DIR, "assets", "piyade_rp_banner.png")

tz_tr = timezone(timedelta(hours=3))

def yukle_veri():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[RP OYLAMA HATA] Veri dosyası okunamadı: {e}", flush=True)
    return {
        "durum": "OYLAMA",        # "OYLAMA", "BASLADI", "GECE"
        "hedef_oy": 5,
        "oy_verenler": [],
        "panel_mesaj_id": None,
        "son_tarih": None,
        "rp_aktif": False
    }

def kaydet_veri(veri):
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[RP OYLAMA HATA] Veri dosyası kaydedilemedi: {e}", flush=True)

def generate_progress_bar(current: int, total: int, length: int = 5) -> str:
    if total <= 0:
        total = 1
    filled = min(length, max(0, int((current / total) * length)))
    empty = length - filled
    return f"`[ {'🟩 ' * filled}{'⬜ ' * empty}]` **( {current} / {total} Oyuncu )**"

async def send_erlc_announcement(command_text: str = ":m RP Başlamıştır , herkese iyi roller.") -> bool:
    api_key = os.getenv("ERLC_API_KEY")
    if not api_key:
        print("[RP OYLAMA UYARI] ERLC_API_KEY ortam değişkeni bulunamadı! Oyun içi anons gönderilemedi.", flush=True)
        return False
    url = "https://api.erlc.gg/v1/server/command"
    headers = {
        "Server-Key": api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "command": command_text
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=8) as resp:
                if resp.status == 200:
                    print(f"[RP OYLAMA BAŞARILI] Roblox ER:LC anonsu iletildi: {command_text}", flush=True)
                    return True
                else:
                    text = await resp.text()
                    print(f"[RP OYLAMA HATA] ER:LC komut isteği başarısız oldu ({resp.status}): {text}", flush=True)
                    return False
    except Exception as e:
        print(f"[RP OYLAMA HATA] ER:LC API isteğinde istisna: {e}", flush=True)
        return False

def yetkili_mi(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    return any(rol.id in [KURUCU_ROL_ID, UST_YONETIM_ROL_ID] for rol in getattr(interaction.user, "roles", []))


# ── KALICI (PERSISTENT) OYLAMA BUTONU VIEW ──
class RPOylamaView(discord.ui.View):
    def __init__(self, cog=None):
        super().__init__(timeout=None)
        self.cog = cog

    def guncelle_buton(self, oy_sayisi: int, hedef_oy: int):
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.custom_id == "rp_oylama_katil_butonu":
                child.label = f"Role Katıl / Oy Ver ({oy_sayisi}/{hedef_oy})"

    @discord.ui.button(
        label="Role Katıl / Oy Ver",
        style=discord.ButtonStyle.primary,
        emoji="🗳️",
        custom_id="rp_oylama_katil_butonu"
    )
    async def oy_ver_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = self.cog
        if not cog:
            cog = interaction.client.get_cog("RPOylama")
        if not cog:
            return await interaction.response.send_message("❌ Sistem yükleniyor, lütfen birkaç saniye sonra tekrar deneyin.", ephemeral=True)
        await cog.oy_kullan(interaction)


# ── RP OYLAMA VE BAŞLANGIÇ COG ──
class RPOylama(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.veri = yukle_veri()
        self.durum = self.veri.get("durum", "OYLAMA")
        self.hedef_oy = self.veri.get("hedef_oy", 5)
        self.oy_verenler = set(self.veri.get("oy_verenler", []))
        self.panel_mesaj_id = self.veri.get("panel_mesaj_id")
        self.son_tarih = self.veri.get("son_tarih")
        self.rp_aktif = self.veri.get("rp_aktif", False)
        self.banner_url = None

        # Dışarıdan veya diğer cog'lardan erişim için bot nesnesine bağla
        self.bot.is_rp_active = self.is_rp_active

        self.zaman_kontrol_loop.start()

    def cog_unload(self):
        self.zaman_kontrol_loop.cancel()

    def is_rp_active(self) -> bool:
        """Rolün resmi olarak aktif olup olmadığını döndürür."""
        return self.durum == "BASLADI" and self.rp_aktif

    def kaydet_durum(self):
        self.veri["durum"] = self.durum
        self.veri["hedef_oy"] = self.hedef_oy
        self.veri["oy_verenler"] = list(self.oy_verenler)
        self.veri["panel_mesaj_id"] = self.panel_mesaj_id
        self.veri["son_tarih"] = self.son_tarih
        self.veri["rp_aktif"] = self.rp_aktif
        kaydet_veri(self.veri)

    # ── EMBED OLUŞTURUCULAR ──
    def olustur_oylama_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🛡️ PRP | GÜNLÜK ROL OYLAMASI",
            color=discord.Color.from_rgb(52, 152, 219),
            timestamp=datetime.now(tz_tr)
        )
        embed.description = (
            "# 🌆 Los Angeles Şehri Kapılarını Açıyor!\n"
            "──────────────────────────────────────────\n"
            "Değerli **Piyade Roleplay** sakinleri; şehrin düzenini sağlamak, devriyeleri başlatmak ve sivil yaşamı canlandırmak için günlük rol oylaması başlamıştır.\n\n"
            "Rolün resmi olarak başlaması için aşağıda belirtilen oyuncu katılım barajının aşılması gerekmektedir. Yeterli çoğunluk sağlandığında Roblox ER:LC sunucusunda otomatik anons geçilecek ve resmi rol süreci başlayacaktır!\n"
            "──────────────────────────────────────────"
        )
        oy_sayisi = len(self.oy_verenler)
        progress = generate_progress_bar(oy_sayisi, self.hedef_oy)
        embed.add_field(
            name="📊 Katılım & Oylama Durumu",
            value=f"{progress}\n🎯 **Hedef:** Rolün başlaması için en az **{self.hedef_oy}** oyuncunun oylamaya katılması gerekmektedir.",
            inline=False
        )
        embed.add_field(
            name="📌 Bilgilendirme & Katılım Kuralları",
            value=(
                "• Aşağıdaki **Role Katıl / Oy Ver** butonuna tıklayarak oyunuzu iletebilirsiniz.\n"
                "• Her oyuncunun yalnızca **1** oy hakkı bulunmaktadır (tekrar basıldığında oy geri çekilemez).\n"
                "• Hedef sayıya ulaşıldığında oyun içi ekran duyurusu otomatik gönderilecektir."
            ),
            inline=False
        )
        embed.add_field(
            name="⏰ Günlük Rol Saatlerimiz",
            value=(
                "• 🔓 **Oylama & Başlangıç:** Her gün saat `12:00`\n"
                "• 🔒 **Gün Sonu & Kapanış:** Her gece saat `01:00`"
            ),
            inline=False
        )
        embed.set_footer(text="Piyade Roleplay • Güvenli ve Kaliteli Rol Deneyimi")
        return embed

    def olustur_basladi_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🟢 PRP | ROL RESMEN BAŞLAMIŞTIR!",
            color=discord.Color.green(),
            timestamp=datetime.now(tz_tr)
        )
        embed.description = (
            "# 🎉 Şehirde Hayat Başladı! Herkese İyi Roller!\n"
            "──────────────────────────────────────────\n"
            "Beklenen oyuncu barajına ulaşıldı ve **Los Angeles** sokakları resmen aktif edildi! Kolluk kuvvetleri devriyeye çıktı, sağlık ekipleri görev yerlerini aldı ve sivil işletmeler açıldı.\n\n"
            "Roblox ER:LC sunucusuna bağlanarak karakterinizin hikayesine kaldığınız yerden devam edebilirsiniz!\n"
            "──────────────────────────────────────────"
        )
        embed.add_field(
            name="📋 Hatırlatmalar & Rol İlkeleri",
            value=(
                "• 🛡️ **Safezone Koruması:** Güvenli bölgelerde (PD, FD, Gunshop, Spawn) çatışma ve cinayet kesinlikle yasaktır; sistemlerimiz ihlalleri anlık izler.\n"
                "• ⚖️ **Kuralcılık:** Fear RP, Fail RP, VDM ve RDM kurallarına harfiyen uyunuz. Eğlenceyi kimsenin bozmasına izin vermeyin.\n"
                "• 📻 **Telsiz & İletişim:** Birlik ve departman içi telsiz kanallarını aktif kullanın.\n"
                "• 🥳 **Tadını Çıkarın:** Tüm oyuncularımıza keyifli, aksiyon dolu ve unutulmaz anlar dileriz!"
            ),
            inline=False
        )
        embed.add_field(
            name="⏱️ Rol Bilgileri & Durum",
            value=(
                "• 🎮 **Sunucu Durumu:** `Aktif / Rolde`\n"
                "• 📡 **Oyun İçi Anons:** Ekranlara gönderildi (`:m`)\n"
                "• 🌙 **Gece Kapanış Saati:** `01:00` (Şehir bu saatte uyku moduna geçer)"
            ),
            inline=False
        )
        embed.add_field(
            name="🔑 Sunucu Katılım Kodu:",
            value="> `piyade`",
            inline=False
        )
        embed.set_footer(text="Piyade RP ∞ | Sunucu Yönetimi™")
        return embed

    def olustur_gece_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🌙 PRP | ŞEHİR DİNLENME MODUNDA",
            color=discord.Color.from_rgb(43, 45, 49),
            timestamp=datetime.now(tz_tr)
        )
        embed.description = (
            "# 💤 Şu Anda Rol Saatleri Dışındayız\n"
            "──────────────────────────────────────────\n"
            "Los Angeles sokakları gece sessizliğine bürünmüştür. Günlük rol sürecimiz tamamlanmış olup tüm birimler dinlenme saatindedir.\n\n"
            "Bu saatler arasında sunucuda resmi rol yapılmamaktadır. Yeni günün rol oylaması saat **12:00**'da açılacaktır.\n"
            "──────────────────────────────────────────"
        )
        embed.add_field(
            name="⏰ Resmi Rol Saatlerimiz",
            value=(
                "• 🔓 **Oylama Başlangıcı:** Her gün saat `12:00`\n"
                "• 🔒 **Gün Sonu Kapanış:** Her gece saat `01:00`"
            ),
            inline=False
        )
        embed.add_field(
            name="ℹ️ Bilgilendirme",
            value=(
                "• Saat 12:00 olduğunda bu kanalda yeni günün oylama paneli otomatik olarak açılacaktır.\n"
                "• Tüm oyuncularımıza iyi istirahatler dileriz!"
            ),
            inline=False
        )
        embed.set_footer(text="Piyade Roleplay • Gece Sessizliği • Yeni oylama saat 12:00'da")
        return embed

    def olustur_duyuru_embed(self, tetikleyen: Optional[discord.User] = None) -> discord.Embed:
        embed = discord.Embed(
            title="🚨 DİKKAT: ROL RESMEN BAŞLADI!",
            color=discord.Color.green(),
            timestamp=datetime.now(tz_tr)
        )
        embed.description = (
            "# 📢 TÜM WHITELIST ÜYELERİMİZİN DİKKATİNE!\n"
            "──────────────────────────────────────────\n"
            "Topluluk oylaması başarıyla tamamlandı ve **Piyade Roleplay** sunucumuzda rol süreci resmen başladı!\n\n"
            "Oyun sunucumuza bağlanarak görev yerlerinizi alabilir, işletmelerinizi açabilir ve şehre dahil olabilirsiniz.\n"
            "──────────────────────────────────────────"
        )
        embed.add_field(
            name="🎮 ER:LC Sunucusuna Bağlanın",
            value=(
                "• Oyun içi genel anons ekranlara iletildi (`:m`).\n"
                "• Safezone korumalarına ve rol kurallarına uymayı unutmayın.\n"
                "• Herkese keyifli ve bol aksiyonlu roller dileriz!"
            ),
            inline=False
        )
        embed.add_field(
            name="🔑 Sunucu Katılım Kodu:",
            value="> `piyade`",
            inline=False
        )
        embed.set_footer(text="Piyade RP ∞ | Sunucu Yönetimi™")
        return embed

    def olustur_kapanis_duyuru_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🌙 PRP | GÜN SONU: ROL SÜRECİ BİTMİŞTİR",
            color=discord.Color.from_rgb(44, 62, 80),
            timestamp=datetime.now(tz_tr)
        )
        embed.description = (
            "# 💤 Los Angeles Sokakları Sessizliğe Büründü!\n"
            "──────────────────────────────────────────\n"
            "Bugünkü resmi rol sürecimiz saat **01:00** itibarıyla tamamlanmıştır. Role katılan, kurallara özen gösteren ve şehre hayat veren tüm oyuncularımıza teşekkür ederiz!\n\n"
            "Yeni günün rol oylaması yarın saat **12:00**'da tekrar açılacaktır. Tüm sakinlerimize ve birimlerimize iyi istirahatler dileriz!\n"
            "──────────────────────────────────────────"
        )
        embed.add_field(
            name="📋 Bilgilendirme & Durum",
            value=(
                "• 🎮 **Sunucu Durumu:** `Dinlenme Modunda (Rol Kapalı)`\n"
                "• 📡 **Oyun İçi Anons:** Ekranlara gönderildi (`:m`)\n"
                "• 🔓 **Yeni Oylama Başlangıcı:** Saat `12:00`"
            ),
            inline=False
        )
        embed.set_footer(text="Piyade RP ∞ | Sunucu Yönetimi™")
        return embed

    async def kapanis_duyuru_gonder(self):
        duyuru_kanali = self.bot.get_channel(DUYURU_KANAL_ID)
        if not duyuru_kanali:
            try:
                duyuru_kanali = await self.bot.fetch_channel(DUYURU_KANAL_ID)
            except Exception as e:
                print(f"[RP OYLAMA HATA] Kapanış duyuru kanalı ({DUYURU_KANAL_ID}) bulunamadı: {e}", flush=True)
                return

        embed = self.olustur_kapanis_duyuru_embed()
        content = f"<@&{WHITELIST_ROL_ID}>"

        if os.path.exists(BANNER_PATH):
            file = discord.File(BANNER_PATH, filename="piyade_rp_banner.png")
            embed.set_image(url="attachment://piyade_rp_banner.png")
            try:
                await duyuru_kanali.send(content=content, embed=embed, file=file)
            except Exception as e:
                print(f"[RP OYLAMA HATA] Resimli kapanış duyurusu gönderilemedi: {e}", flush=True)
        else:
            try:
                await duyuru_kanali.send(content=content, embed=embed)
            except Exception as e:
                print(f"[RP OYLAMA HATA] Kapanış duyurusu gönderilemedi: {e}", flush=True)

    # ── KANAL VE PANEL YÖNETİMİ ──
    async def temizle_ve_panel_gonder(self, mod: str):
        channel = self.bot.get_channel(PANEL_KANAL_ID)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(PANEL_KANAL_ID)
            except Exception as e:
                print(f"[RP OYLAMA HATA] Panel kanalı ({PANEL_KANAL_ID}) bulunamadı: {e}", flush=True)
                return

        # Kanalı temizle (Sadece 1 adet sabit mesaj kalacak)
        try:
            await channel.purge(limit=50)
        except Exception as e:
            print(f"[RP OYLAMA UYARI] Kanal temizlenirken istisna (yetkiyi kontrol edin): {e}", flush=True)

        if mod == "GECE":
            embed = self.olustur_gece_embed()
            view = None
        elif mod == "BASLADI":
            embed = self.olustur_basladi_embed()
            view = None
        else:  # "OYLAMA"
            embed = self.olustur_oylama_embed()
            view = RPOylamaView(self)
            view.guncelle_buton(len(self.oy_verenler), self.hedef_oy)

        msg = None
        if os.path.exists(BANNER_PATH):
            file = discord.File(BANNER_PATH, filename="piyade_rp_banner.png")
            embed.set_image(url="attachment://piyade_rp_banner.png")
            try:
                if view:
                    msg = await channel.send(embed=embed, file=file, view=view)
                else:
                    msg = await channel.send(embed=embed, file=file)
            except Exception as e:
                print(f"[RP OYLAMA HATA] Resimli panel gönderilemedi: {e}", flush=True)
        else:
            try:
                if view:
                    msg = await channel.send(embed=embed, view=view)
                else:
                    msg = await channel.send(embed=embed)
            except Exception as e:
                print(f"[RP OYLAMA HATA] Panel gönderilemedi: {e}", flush=True)

        if msg:
            self.panel_mesaj_id = msg.id
            if msg.attachments:
                self.banner_url = msg.attachments[0].url
            self.kaydet_durum()
            print(f"[RP OYLAMA] Panel başarıyla güncellendi (Mod: {mod}, Mesaj ID: {msg.id})", flush=True)

    async def panel_sayac_guncelle(self):
        """Oylama sırasında sadece sayacı ve ilerleme çubuğunu günceller."""
        channel = self.bot.get_channel(PANEL_KANAL_ID)
        if not channel:
            return
        msg = None
        if self.panel_mesaj_id:
            try:
                msg = await channel.fetch_message(self.panel_mesaj_id)
            except Exception:
                msg = None

        embed = self.olustur_oylama_embed()
        view = RPOylamaView(self)
        view.guncelle_buton(len(self.oy_verenler), self.hedef_oy)

        if self.banner_url:
            embed.set_image(url=self.banner_url)
        else:
            embed.set_image(url="attachment://piyade_rp_banner.png")

        if msg:
            try:
                await msg.edit(embed=embed, view=view)
            except Exception as e:
                print(f"[RP OYLAMA HATA] Sayaç düzenlenemedi: {e}", flush=True)
        else:
            await self.temizle_ve_panel_gonder("OYLAMA")

    async def rolu_baslat(self, tetikleyen: Optional[discord.User] = None):
        """Rolün resmi olarak başlamasını sağlar."""
        self.durum = "BASLADI"
        self.rp_aktif = True
        self.kaydet_durum()

        # 1. Roblox ER:LC sunucusuna anons komutunu ilet
        erlc_komut = ":m RP Başlamıştır , herkese iyi roller."
        await send_erlc_announcement(erlc_komut)

        # 2. Panel kanalındaki embed'i Yeşile çevir ve butonu kaldır
        channel = self.bot.get_channel(PANEL_KANAL_ID)
        if channel:
            msg = None
            if self.panel_mesaj_id:
                try:
                    msg = await channel.fetch_message(self.panel_mesaj_id)
                except Exception:
                    msg = None

            embed = self.olustur_basladi_embed()
            if self.banner_url:
                embed.set_image(url=self.banner_url)
            else:
                embed.set_image(url="attachment://piyade_rp_banner.png")

            if msg:
                try:
                    await msg.edit(embed=embed, view=None)
                except Exception as e:
                    print(f"[RP OYLAMA HATA] Panel yeşile çevrilirken hata: {e}", flush=True)
            else:
                await self.temizle_ve_panel_gonder("BASLADI")

        # 3. Whitelist duyuru kanalına pingli duyuruyu gönder
        await self.duyuru_gonder(tetikleyen)

    async def duyuru_gonder(self, tetikleyen: Optional[discord.User] = None):
        duyuru_kanali = self.bot.get_channel(DUYURU_KANAL_ID)
        if not duyuru_kanali:
            try:
                duyuru_kanali = await self.bot.fetch_channel(DUYURU_KANAL_ID)
            except Exception as e:
                print(f"[RP OYLAMA HATA] Duyuru kanalı ({DUYURU_KANAL_ID}) bulunamadı: {e}", flush=True)
                return

        embed = self.olustur_duyuru_embed(tetikleyen)
        content = f"<@&{WHITELIST_ROL_ID}>"

        if os.path.exists(BANNER_PATH):
            file = discord.File(BANNER_PATH, filename="piyade_rp_banner.png")
            embed.set_image(url="attachment://piyade_rp_banner.png")
            try:
                await duyuru_kanali.send(content=content, embed=embed, file=file)
            except Exception as e:
                print(f"[RP OYLAMA HATA] Resimli duyuru gönderilemedi: {e}", flush=True)
        else:
            try:
                await duyuru_kanali.send(content=content, embed=embed)
            except Exception as e:
                print(f"[RP OYLAMA HATA] Duyuru gönderilemedi: {e}", flush=True)

    async def gece_moduna_gec(self, bildirim_gonder: bool = True):
        """01:00 gece moduna geçiş: ER:LC anonsu, Whitelist kapanış pingi, eski mesajları temizleme ve gece panelini koyma."""
        self.durum = "GECE"
        self.rp_aktif = False
        self.oy_verenler = set()
        self.kaydet_durum()

        # Eğer bildirim gönderilecekse (Saat 01:00 olduğunda veya yetkili /rp-durdur kullandığında)
        if bildirim_gonder:
            # 1. Roblox ER:LC oyun içi kapanış anonsu
            erlc_komut = ":m Rol bitmiştir , herkese iyi istirahatler dileriz."
            await send_erlc_announcement(erlc_komut)

            # 2. Whitelist duyuru kanalına pingli kapanış bildirimi
            await self.kapanis_duyuru_gonder()

        # 3. Panel kanalındaki eski mesajları temizle ve gece panelini yerleştir
        await self.temizle_ve_panel_gonder("GECE")

    async def gunduz_moduna_gec(self):
        """12:00 gündüz oylama moduna geçiş: Eski mesajları sil, oylama panelini koy."""
        now = datetime.now(tz_tr)
        self.durum = "OYLAMA"
        self.rp_aktif = False
        self.oy_verenler = set()
        self.son_tarih = now.strftime("%Y-%m-%d")
        self.kaydet_durum()
        await self.temizle_ve_panel_gonder("OYLAMA")

    async def oy_kullan(self, interaction: discord.Interaction):
        """Kullanıcının butona bastığında çalışan oy kullanma işlemi."""
        user_id = interaction.user.id

        if self.durum != "OYLAMA":
            if self.durum == "BASLADI":
                return await interaction.response.send_message("🟢 **Rol zaten başladı!** ER:LC sunucusuna bağlanabilirsiniz.", ephemeral=True)
            else:
                return await interaction.response.send_message("🌙 **Şu anda rol saatleri dışındayız.** Oylama saat 12:00'da açılacaktır.", ephemeral=True)

        if user_id in self.oy_verenler:
            return await interaction.response.send_message("❌ **Zaten oy kullandınız!** Oyunuz sisteme kayıtlıdır ve geri çekilemez.", ephemeral=True)

        self.oy_verenler.add(user_id)
        self.kaydet_durum()

        oy_sayisi = len(self.oy_verenler)

        # Hedefe ulaşıldı mı?
        if oy_sayisi >= self.hedef_oy:
            await interaction.response.defer(ephemeral=True)
            await self.rolu_baslat(tetikleyen=interaction.user)
            await interaction.followup.send(f"🎉 **Tebrikler!** **{oy_sayisi}.** oyu vererek rolün resmen başlamasını sağladınız!", ephemeral=True)
        else:
            kalan = self.hedef_oy - oy_sayisi
            await interaction.response.defer(ephemeral=True)
            await self.panel_sayac_guncelle()
            await interaction.followup.send(f"✅ **Oyunuz başarıyla kaydedildi!**\n📊 Mevcut Oy: **{oy_sayisi}/{self.hedef_oy}** (Kalan: **{kalan}** oy)", ephemeral=True)

    # ── ZAMANLAYICI VE SAAT DÖNGÜSÜ (01:00 ve 12:00) ──
    @tasks.loop(seconds=20)
    async def zaman_kontrol_loop(self):
        if not self.bot.is_ready():
            return

        now = datetime.now(tz_tr)
        saat = now.hour
        bugun = now.strftime("%Y-%m-%d")

        # Gece saati kontrolü: 01:00 <= saat < 12:00
        gece_vakti = (1 <= saat < 12)

        if gece_vakti:
            # Gece vakti ama sistem henüz gece moduna geçmemişse (Saat 01:00 olduğunda otomatik tetiklenir)
            if self.durum != "GECE":
                print(f"[RP ZAMANLAYICI] Saat 01:00 gece moduna girildi ({saat}:{now.minute:02d}). Rol sonlandırılıyor ve anonslar yapılıyor...", flush=True)
                await self.gece_moduna_gec(bildirim_gonder=True)
        else:
            # Gündüz vakti (saat >= 12 veya saat == 0)
            # Gece modundaysak veya tarih değişip yeni güne girildiyse oylama aç
            if self.durum == "GECE" or (self.son_tarih != bugun and saat >= 12):
                print(f"[RP ZAMANLAYICI] Gündüz oylama saatine girildi ({saat}:{now.minute:02d}). Oylama paneli açılıyor...", flush=True)
                await self.gunduz_moduna_gec()

    @zaman_kontrol_loop.before_loop
    async def before_loop_ready(self):
        await self.bot.wait_until_ready()
        # Bot açıldığında kanalın durumunu senkronize et
        channel = self.bot.get_channel(PANEL_KANAL_ID)
        if channel:
            msg = None
            if self.panel_mesaj_id:
                try:
                    msg = await channel.fetch_message(self.panel_mesaj_id)
                except Exception:
                    msg = None
            if not msg:
                now = datetime.now(tz_tr)
                gece_vakti = (1 <= now.hour < 12)
                mod = "GECE" if gece_vakti else self.durum
                await self.temizle_ve_panel_gonder(mod)

    # ── YÖNETİCİ SLASH KOMUTLARI ──
    @app_commands.command(name="rp-baslat", description="Oylama barajını beklemeden rolü anında başlatır.")
    async def cmd_rp_baslat(self, interaction: discord.Interaction):
        if not yetkili_mi(interaction):
            return await interaction.response.send_message("❌ Bu komutu kullanmak için yetkiniz bulunmamaktadır.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        await self.rolu_baslat(tetikleyen=interaction.user)
        await interaction.followup.send("🟢 **Rol başarıyla manuel olarak başlatıldı!** Panel yeşile çevrildi ve anonslar yapıldı.", ephemeral=True)

    @app_commands.command(name="rp-durdur", description="Rolü sonlandırır, anonsları geçer ve kanalı gece dinlenme moduna alır.")
    async def cmd_rp_durdur(self, interaction: discord.Interaction):
        if not yetkili_mi(interaction):
            return await interaction.response.send_message("❌ Bu komutu kullanmak için yetkiniz bulunmamaktadır.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        await self.gece_moduna_gec(bildirim_gonder=True)
        await interaction.followup.send("🌙 **Rol sonlandırıldı!** Roblox'a kapanış anonsu gönderildi, Whitelist rolü etiketlenerek duyuru geçildi ve kanal gece dinlenme moduna alındı.", ephemeral=True)

    @app_commands.command(name="rp-hedef-belirle", description="Rol başlangıcı için gereken hedef oy sayısını belirler.")
    @app_commands.describe(sayi="Rolün başlaması için gereken oy barajı (Varsayılan: 5)")
    async def cmd_rp_hedef(self, interaction: discord.Interaction, sayi: int):
        if not yetkili_mi(interaction):
            return await interaction.response.send_message("❌ Bu komutu kullanmak için yetkiniz bulunmamaktadır.", ephemeral=True)

        if sayi < 1:
            return await interaction.response.send_message("❌ Hedef oy sayısı en az 1 olmalıdır.", ephemeral=True)

        self.hedef_oy = sayi
        self.kaydet_durum()

        if self.durum == "OYLAMA":
            await self.panel_sayac_guncelle()

        await interaction.response.send_message(f"🎯 **RP başlangıç hedefi {sayi} oy olarak ayarlandı.**", ephemeral=True)

    @app_commands.command(name="rp-panel-gonder", description="Oylama veya durum panelini kanala sıfırdan temizleyip gönderir.")
    async def cmd_rp_panel_gonder(self, interaction: discord.Interaction):
        if not yetkili_mi(interaction):
            return await interaction.response.send_message("❌ Bu komutu kullanmak için yetkiniz bulunmamaktadır.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        now = datetime.now(tz_tr)
        gece_vakti = (1 <= now.hour < 12)
        mod = "GECE" if gece_vakti else self.durum
        await self.temizle_ve_panel_gonder(mod)
        await interaction.followup.send("✅ **Panel kanala sıfırdan başarıyla gönderildi ve kanal temizlendi.**", ephemeral=True)

    @app_commands.command(name="rp-durum", description="Mevcut RP durumunu, oy sayısını ve oylayanları gösterir.")
    async def cmd_rp_durum(self, interaction: discord.Interaction):
        durum_metin = {
            "OYLAMA": "🟡 Oylama Devam Ediyor",
            "BASLADI": "🟢 Rol Aktif / Başladı",
            "GECE": "🌙 Gece Dinlenme Modu"
        }.get(self.durum, self.durum)

        oy_sayisi = len(self.oy_verenler)
        progress = generate_progress_bar(oy_sayisi, self.hedef_oy)

        embed = discord.Embed(
            title="📊 Piyade RP • Durum Raporu",
            color=discord.Color.blue(),
            timestamp=datetime.now(tz_tr)
        )
        embed.add_field(name="📍 Mevcut Durum", value=f"**{durum_metin}**", inline=True)
        embed.add_field(name="🛡️ Rol Durumu", value="`Aktif`" if self.rp_aktif else "`Kapalı`", inline=True)
        embed.add_field(name="🎯 Hedef Barajı", value=f"**{self.hedef_oy} Oy**", inline=True)
        embed.add_field(name="📈 İlerleme", value=progress, inline=False)

        if self.oy_verenler:
            oylayanlar_str = ", ".join([f"<@{uid}>" for uid in list(self.oy_verenler)[:25]])
            if len(self.oy_verenler) > 25:
                oylayanlar_str += f" ve {len(self.oy_verenler) - 25} kişi daha..."
            embed.add_field(name="👥 Oy Kullananlar", value=oylayanlar_str, inline=False)
        else:
            embed.add_field(name="👥 Oy Kullananlar", value="*Henüz kimse oy kullanmadı.*", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(RPOylama(bot))
