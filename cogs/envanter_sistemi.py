import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
from datetime import datetime, timezone, timedelta
from utils.storage import load_json, save_json_atomic

# =====================================================================
# ROL VE KANAL AYARLARI
# =====================================================================
GUILD_ID = 1529545898294509589

EKONOMI_YETKILISI_ROL_ID = 1557045970523389952
ILLEGAL_ROL_ID = 1539249508314259567
KURUCU_ROL_ID = 1529546007635824680

ATM_KANAL_ID = 1557055667339137127
MARKET_KANAL_ID = 1557055691405926400
SILAHCI_KANAL_ID = 1557055717389901894
ILLEGAL_MARKET_KANAL_ID = 1557056451644629032
ESK_LOG_KANAL_ID = 1557045447808520393

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
ENVANTER_FILE = os.path.join(DATA_DIR, "envanter_verileri.json")
KAYIT_FILE = os.path.join(DATA_DIR, "kayit_data.json")

# =====================================================================
# EŞYA VE FİYAT TANIMLARI
# =====================================================================
MARKET_ESYALARI = {
    "İlk Yardım Kiti": {"fiyat": 150, "aciklama": "Yaralanmaları tedavi etmek için acil tıbbi ekipman.", "emoji": "🩹"},
    "Levye": {"fiyat": 200, "aciklama": "Ağır hizmet tipi çelik levye.", "emoji": "🪓"},
    "Çekiç": {"fiyat": 100, "aciklama": "Tamirat ve marangozluk işleri için standart çekiç.", "emoji": "🔨"},
    "Kazma": {"fiyat": 250, "aciklama": "Kazı ve maden işlerinde kullanılan sağlam kazma.", "emoji": "⛏️"},
    "Bıçak": {"fiyat": 350, "aciklama": "Keskin paslanmaz çelik av bıçağı.", "emoji": "🔪"},
}

ILLEGAL_ESYALAR = {
    "Cam kesici": {"fiyat": 500, "aciklama": "Sessizce cam vitrinleri ve pencereleri kesmek için özel elmas uç.", "emoji": "💎"},
    "RFID Disruptor": {"fiyat": 1200, "aciklama": "Elektronik kilit sistemlerini ve sinyalleri bozan karıştırıcı cihaz.", "emoji": "📡"},
    "LockPick": {"fiyat": 400, "aciklama": "Mekanik kapı ve kelepçe kilitlerini açmaya yarayan maymuncuk seti.", "emoji": "🔓"},
    "Meth Malzemeleri": {"fiyat": 600, "aciklama": "Kimyasal laboratuvarda madde üretiminde kullanılan ham maddeler.", "emoji": "🧪"},
}

SILAH_ESYALARI = {
    "Beretta 92": {"fiyat": 2500, "aciklama": "İtalyan yapımı güvenilir 9x19mm yarı otomatik beylik tabancası.", "emoji": "🔫"},
    "Colt 1911": {"fiyat": 3000, "aciklama": ".45 ACP kalibre yüksek vuruş gücüne sahip klasik Amerikan tabancası.", "emoji": "🔫"},
}

# =====================================================================
# VERİ TABANI YARDIMCI FONKSİYONLARI
# =====================================================================
_ENV_LOCK = asyncio.Lock()

def _get_raw_data() -> dict:
    default_structure = {
        "users": {},
        "gunshop_stock": {
            "Beretta 92": 50,
            "Colt 1911": 50
        },
        "panel_messages": {
            "atm": None,
            "market": None,
            "gunshop": None,
            "illegal_market": None
        }
    }
    data = load_json(ENVANTER_FILE, default_structure)
    if not isinstance(data, dict):
        data = default_structure
    data.setdefault("users", {})
    data.setdefault("gunshop_stock", {"Beretta 92": 50, "Colt 1911": 50})
    data.setdefault("panel_messages", {"atm": None, "market": None, "gunshop": None, "illegal_market": None})
    return data

def _save_raw_data(data: dict):
    save_json_atomic(ENVANTER_FILE, data)

def get_user_profile(user_id: int | str) -> dict:
    uid = str(user_id)
    data = _get_raw_data()
    users = data["users"]
    if uid not in users:
        users[uid] = {
            "cash": 1000,
            "bank": 5000,
            "inventory": {}
        }
        _save_raw_data(data)
    user_data = users[uid]
    user_data.setdefault("cash", 1000)
    user_data.setdefault("bank", 5000)
    user_data.setdefault("inventory", {})
    return user_data

def update_user_profile(user_id: int | str, profile: dict):
    uid = str(user_id)
    data = _get_raw_data()
    data["users"][uid] = profile
    _save_raw_data(data)

def format_usd(amount: int) -> str:
    return f"${amount:,.0f}".replace(",", ".")

def yetkili_mi(member: discord.Member) -> bool:
    if not isinstance(member, discord.Member):
        return False
    if member.guild_permissions.administrator:
        return True
    return any(r.id in [EKONOMI_YETKILISI_ROL_ID, KURUCU_ROL_ID] for r in member.roles)

# =====================================================================
# ATM MODALLARI VE GÖRÜNÜMÜ
# =====================================================================
class ATMYatirModal(discord.ui.Modal, title="🏧 ATM • Para Yatırma"):
    tutar = discord.ui.TextInput(
        label="Yatırılacak Miktar ($)",
        placeholder="Örn: 500",
        min_length=1,
        max_length=9,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.tutar.value.strip())
            if val <= 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Geçerli ve pozitif bir sayı girmelisiniz!", ephemeral=True)

        async with _ENV_LOCK:
            user = get_user_profile(interaction.user.id)
            if user["cash"] < val:
                return await interaction.response.send_message(
                    f"❌ Yetersiz nakit para! Cüzdanında **{format_usd(user['cash'])}** nakit bulunuyor.",
                    ephemeral=True
                )

            user["cash"] -= val
            user["bank"] += val
            update_user_profile(interaction.user.id, user)

        embed = discord.Embed(
            title="🏧 İşlem Başarılı • Para Yatırıldı",
            color=discord.Color.green(),
            description=f"Bankadaki hesabınıza **{format_usd(val)}** başarıyla yatırıldı."
        )
        embed.add_field(name="💵 Kalan Nakit", value=f"`{format_usd(user['cash'])}`", inline=True)
        embed.add_field(name="💳 Güncel Banka", value=f"`{format_usd(user['bank'])}`", inline=True)
        embed.set_footer(text="Piyade RP ATM Sistemi")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class ATMCekModal(discord.ui.Modal, title="🏧 ATM • Para Çekme"):
    tutar = discord.ui.TextInput(
        label="Çekilecek Miktar ($)",
        placeholder="Örn: 500",
        min_length=1,
        max_length=9,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.tutar.value.strip())
            if val <= 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Geçerli ve pozitif bir sayı girmelisiniz!", ephemeral=True)

        async with _ENV_LOCK:
            user = get_user_profile(interaction.user.id)
            if user["bank"] < val:
                return await interaction.response.send_message(
                    f"❌ Yetersiz banka bakiyesi! Hesabında **{format_usd(user['bank'])}** bulunuyor.",
                    ephemeral=True
                )

            user["bank"] -= val
            user["cash"] += val
            update_user_profile(interaction.user.id, user)

        embed = discord.Embed(
            title="🏧 İşlem Başarılı • Para Çekildi",
            color=discord.Color.green(),
            description=f"Banka hesabınızdan **{format_usd(val)}** nakit olarak çekildi."
        )
        embed.add_field(name="💵 Güncel Nakit", value=f"`{format_usd(user['cash'])}`", inline=True)
        embed.add_field(name="💳 Kalan Banka", value=f"`{format_usd(user['bank'])}`", inline=True)
        embed.set_footer(text="Piyade RP ATM Sistemi")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class ATMView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Para Yatır", emoji="📥", style=discord.ButtonStyle.success, custom_id="atm_btn_yatir")
    async def yatir_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ATMYatirModal())

    @discord.ui.button(label="Para Çek", emoji="📤", style=discord.ButtonStyle.primary, custom_id="atm_btn_cek")
    async def cek_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ATMCekModal())

    @discord.ui.button(label="Hesap Özeti", emoji="💳", style=discord.ButtonStyle.secondary, custom_id="atm_btn_bakiye")
    async def bakiye_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = get_user_profile(interaction.user.id)
        embed = discord.Embed(
            title="💳 HESAP BİLGİLERİNİZ & BAKİYE",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.description = f"Merhaba {interaction.user.mention}, güncel hesap özetiniz aşağıdadır:"
        embed.add_field(name="💵 Nakit Cüzdan", value=f"**{format_usd(user['cash'])}**", inline=True)
        embed.add_field(name="🏦 Banka Hesabı", value=f"**{format_usd(user['bank'])}**", inline=True)
        embed.add_field(name="💰 Toplam Varlık", value=f"**{format_usd(user['cash'] + user['bank'])}**", inline=False)
        embed.set_footer(text="Gizli Mesaj • Yalnızca siz görebilirsiniz")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# =====================================================================
# GENEL MARKET GÖRÜNÜMÜ
# =====================================================================
class MarketSelect(discord.ui.Select):
    def __init__(self):
        options = []
        for name, info in MARKET_ESYALARI.items():
            options.append(discord.SelectOption(
                label=f"{name} — {format_usd(info['fiyat'])}",
                description=info["aciklama"][:100],
                emoji=info["emoji"],
                value=name
            ))
        super().__init__(
            placeholder="🛒 Satın almak istediğiniz market ürününü seçin...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="market_select_item"
        )

    async def callback(self, interaction: discord.Interaction):
        item_name = self.values[0]
        item_info = MARKET_ESYALARI.get(item_name)
        if not item_info:
            return await interaction.response.send_message("❌ Ürün bulunamadı!", ephemeral=True)

        fiyat = item_info["fiyat"]
        async with _ENV_LOCK:
            user = get_user_profile(interaction.user.id)
            if user["cash"] < fiyat:
                return await interaction.response.send_message(
                    f"❌ **Yetersiz Nakit Para!**\n"
                    f"Bu ürünü alabilmek için cebinizde **{format_usd(fiyat)}** nakit bulunmalıdır.\n"
                    f"Şu anki nakit paranız: **{format_usd(user['cash'])}**",
                    ephemeral=True
                )

            user["cash"] -= fiyat
            user["inventory"][item_name] = user["inventory"].get(item_name, 0) + 1
            update_user_profile(interaction.user.id, user)

        embed = discord.Embed(
            title="✅ Alışveriş Tamamlandı",
            color=discord.Color.green(),
            description=f"{item_info['emoji']} **1x {item_name}** satın aldınız ve envanterinize eklendi!"
        )
        embed.add_field(name="💸 Ödenen Tutar", value=f"`{format_usd(fiyat)}` (Nakit)", inline=True)
        embed.add_field(name="💵 Kalan Nakit", value=f"`{format_usd(user['cash'])}`", inline=True)
        embed.add_field(name="🎒 Envanterdeki Adet", value=f"`{user['inventory'][item_name]} adet`", inline=True)
        embed.set_footer(text="Piyade RP Market Sistemi")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class MarketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(MarketSelect())

# =====================================================================
# İLLEGAL MARKET GÖRÜNÜMÜ
# =====================================================================
class IllegalMarketSelect(discord.ui.Select):
    def __init__(self):
        options = []
        for name, info in ILLEGAL_ESYALAR.items():
            options.append(discord.SelectOption(
                label=f"{name} — {format_usd(info['fiyat'])}",
                description=info["aciklama"][:100],
                emoji=info["emoji"],
                value=name
            ))
        super().__init__(
            placeholder="🌑 Satın almak istediğiniz illegal malzemeyi seçin...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="illegal_market_select_item"
        )

    async def callback(self, interaction: discord.Interaction):
        item_name = self.values[0]
        item_info = ILLEGAL_ESYALAR.get(item_name)
        if not item_info:
            return await interaction.response.send_message("❌ Ürün bulunamadı!", ephemeral=True)

        fiyat = item_info["fiyat"]
        async with _ENV_LOCK:
            user = get_user_profile(interaction.user.id)
            if user["cash"] < fiyat:
                return await interaction.response.send_message(
                    f"❌ **Yetersiz Nakit Para!**\n"
                    f"Bu illegal malzemeyi alabilmek için yanınızda **{format_usd(fiyat)}** nakit bulunmalıdır.\n"
                    f"Mevcut nakitiniz: **{format_usd(user['cash'])}**",
                    ephemeral=True
                )

            user["cash"] -= fiyat
            user["inventory"][item_name] = user["inventory"].get(item_name, 0) + 1
            update_user_profile(interaction.user.id, user)

        embed = discord.Embed(
            title="🌑 İllegal Alışveriş Tamamlandı",
            color=discord.Color.dark_grey(),
            description=f"{item_info['emoji']} **1x {item_name}** gizlice teslim alındı ve zulanıza/envanterinize eklendi."
        )
        embed.add_field(name="💸 Ödenen Nakit", value=f"`{format_usd(fiyat)}`", inline=True)
        embed.add_field(name="💵 Kalan Nakit", value=f"`{format_usd(user['cash'])}`", inline=True)
        embed.add_field(name="🎒 Toplam Miktar", value=f"`{user['inventory'][item_name]} adet`", inline=True)
        embed.set_footer(text="Piyade RP Kara Borsa")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class IllegalMarketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(IllegalMarketSelect())

# =====================================================================
# SİLAHÇI (GUNSHOP) MODAL VE GÖRÜNÜMÜ (STOK SİSTEMLİ)
# =====================================================================
class GunshopAdetModal(discord.ui.Modal):
    def __init__(self, silah_adi: str, bot_cog):
        super().__init__(title=f"🔫 {silah_adi} Satın Alım")
        self.silah_adi = silah_adi
        self.bot_cog = bot_cog
        self.fiyat = SILAH_ESYALARI[silah_adi]["fiyat"]

        self.adet = discord.ui.TextInput(
            label=f"Kaç adet almak istiyorsunuz? (Adet: {format_usd(self.fiyat)})",
            placeholder="Örn: 1 veya 2",
            min_length=1,
            max_length=4,
            required=True
        )
        self.add_item(self.adet)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            adet_val = int(self.adet.value.strip())
            if adet_val <= 0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Geçerli ve pozitif bir sayı girmelisiniz!", ephemeral=True)

        async with _ENV_LOCK:
            data = _get_raw_data()
            stoklar = data.setdefault("gunshop_stock", {"Beretta 92": 50, "Colt 1911": 50})
            mevcut_stok = stoklar.get(self.silah_adi, 0)

            if mevcut_stok <= 0:
                return await interaction.response.send_message(
                    f"❌ **{self.silah_adi}** stokları tükenmiştir! Lütfen Ekonomi Yetkilisinin stok yenilemesini bekleyiniz.",
                    ephemeral=True
                )

            if adet_val > mevcut_stok:
                return await interaction.response.send_message(
                    f"❌ Yetersiz mağaza stoğu! Şu anda mağazada yalnızca **{mevcut_stok} adet** {self.silah_adi} bulunmaktadır.",
                    ephemeral=True
                )

            toplam_tutar = adet_val * self.fiyat
            user = get_user_profile(interaction.user.id)

            if user["cash"] < toplam_tutar:
                return await interaction.response.send_message(
                    f"❌ **Yetersiz Nakit Para!**\n"
                    f"**{adet_val} adet {self.silah_adi}** satın almak için **{format_usd(toplam_tutar)}** nakit gerekiyor.\n"
                    f"Cebinizdeki nakit: **{format_usd(user['cash'])}**",
                    ephemeral=True
                )

            # İşlemi tamamla
            user["cash"] -= toplam_tutar
            user["inventory"][self.silah_adi] = user["inventory"].get(self.silah_adi, 0) + adet_val
            stoklar[self.silah_adi] -= adet_val
            data["users"][str(interaction.user.id)] = user
            _save_raw_data(data)

        # Paneli canlı güncelle
        await self.bot_cog.guncelle_gunshop_paneli(interaction.guild)

        embed = discord.Embed(
            title="🔫 Ruhsatsız Silah Satın Alındı",
            color=discord.Color.gold(),
            description=f"Başarıyla **{adet_val}x {self.silah_adi}** (Ruhsatsız) satın aldınız ve envanterinize kayıt edildi!"
        )
        embed.add_field(name="💸 Toplam Tutar", value=f"`{format_usd(toplam_tutar)}` (Nakit)", inline=True)
        embed.add_field(name="💵 Kalan Nakit", value=f"`{format_usd(user['cash'])}`", inline=True)
        embed.add_field(name="📦 Kalan Mağaza Stoğu", value=f"`{stoklar[self.silah_adi]} adet`", inline=True)
        embed.set_footer(text="Piyade RP Ammu-Nation • Ruhsatsız Silah Kaydı")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class GunshopView(discord.ui.View):
    def __init__(self, bot_cog=None):
        super().__init__(timeout=None)
        self.bot_cog = bot_cog

    @discord.ui.button(label="Beretta 92 Satın Al", emoji="🔫", style=discord.ButtonStyle.primary, custom_id="gunshop_btn_beretta")
    async def beretta_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = self.bot_cog or interaction.client.get_cog("EnvanterSistemi")
        await interaction.response.send_modal(GunshopAdetModal("Beretta 92", cog))

    @discord.ui.button(label="Colt 1911 Satın Al", emoji="🔫", style=discord.ButtonStyle.primary, custom_id="gunshop_btn_colt")
    async def colt_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        cog = self.bot_cog or interaction.client.get_cog("EnvanterSistemi")
        await interaction.response.send_modal(GunshopAdetModal("Colt 1911", cog))

    @discord.ui.button(label="Stok Durumu", emoji="📦", style=discord.ButtonStyle.secondary, custom_id="gunshop_btn_stok")
    async def stok_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = _get_raw_data()
        stoklar = data.get("gunshop_stock", {"Beretta 92": 50, "Colt 1911": 50})
        b_stok = stoklar.get("Beretta 92", 0)
        c_stok = stoklar.get("Colt 1911", 0)

        embed = discord.Embed(
            title="📦 AMMU-NATION CANLI STOK ÇİZELGESİ",
            color=discord.Color.dark_gold(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.add_field(
            name="• Beretta 92 (9mm)",
            value=f"Stok: **{b_stok} adet** {'🔴 (TÜKENDİ)' if b_stok <= 0 else '🟢 (MEVCUT)'}\nFiyat: `{format_usd(SILAH_ESYALARI['Beretta 92']['fiyat'])}`",
            inline=True
        )
        embed.add_field(
            name="• Colt 1911 (.45 ACP)",
            value=f"Stok: **{c_stok} adet** {'🔴 (TÜKENDİ)' if c_stok <= 0 else '🟢 (MEVCUT)'}\nFiyat: `{format_usd(SILAH_ESYALARI['Colt 1911']['fiyat'])}`",
            inline=True
        )
        embed.set_footer(text="Stok yenilemeleri sadece Ekonomi Yetkilisi tarafından yapılır.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# =====================================================================
# ENVANTER SİSTEMİ ANA COG
# =====================================================================
class EnvanterSistemi(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def guncelle_gunshop_paneli(self, guild: discord.Guild):
        """Silahçı panelinin mesajını kanalda bulup stok bilgisini anlık günceller."""
        if not guild:
            return
        kanal = guild.get_channel(SILAHCI_KANAL_ID)
        if not kanal:
            return

        data = _get_raw_data()
        msg_id = data.get("panel_messages", {}).get("gunshop")
        if not msg_id:
            return

        stoklar = data.get("gunshop_stock", {"Beretta 92": 50, "Colt 1911": 50})
        b_stok = stoklar.get("Beretta 92", 0)
        c_stok = stoklar.get("Colt 1911", 0)

        embed = discord.Embed(
            title="🔫 AMMU-NATION • SİLAH & MÜHİMMAT MAĞAZASI",
            description=(
                "Los Santos Ammu-Nation silah mağazasına hoş geldiniz.\n"
                "Aşağıdaki butonları kullanarak doğrudan satın alım yapabilirsiniz.\n\n"
                "⚠️ **ÖNEMLİ BİLGİLENDİRME:**\n"
                "• **Silahçıdan satın alınan tüm silahlar RUHSATSIZDIR!**\n"
                "• Emniyet birimlerinin yapacağı üst aramasında veya denetimlerde ruhsatsız silah bulundurmak suç teşkil eder.\n"
                "• Ödemeler doğrudan **NAKİT** cüzdanınızdan tahsil edilir.\n"
                "• Satın aldığınız silahlar anında dijital envanterinize kaydedilir.\n"
                "• Sunucu kuralları gereği envantersiz silah kullanımı (E.S.K) cezalandırılır.\n"
                "──────────────────────────────────────────"
            ),
            color=discord.Color.gold()
        )

        b_durum = f"**{b_stok} Adet**" if b_stok > 0 else "**TÜKENDİ (Stok Yok)** ❌"
        c_durum = f"**{c_stok} Adet**" if c_stok > 0 else "**TÜKENDİ (Stok Yok)** ❌"

        embed.add_field(
            name="• Beretta 92 (9mm)",
            value=f"💵 Fiyat: `{format_usd(SILAH_ESYALARI['Beretta 92']['fiyat'])}`\n📦 Kalan Stok: {b_durum}\n*Standart hafif yarı otomatik beylik tabancası.*",
            inline=True
        )
        embed.add_field(
            name="• Colt 1911 (.45 ACP)",
            value=f"💵 Fiyat: `{format_usd(SILAH_ESYALARI['Colt 1911']['fiyat'])}`\n📦 Kalan Stok: {c_durum}\n*Ağır kalibre klasik çelik gövde tabanca.*",
            inline=True
        )

        embed.set_footer(text="Stok Kontrolü: Ekonomi Yetkilisi • Piyade RP Ammu-Nation")

        try:
            msg = await kanal.fetch_message(int(msg_id))
            await msg.edit(embed=embed, view=GunshopView(self))
        except Exception:
            pass

    # -----------------------------------------------------------------
    # SLASH KOMUTLARI
    # -----------------------------------------------------------------
    @app_commands.command(name="envanter", description="Envanterinizdeki eşyaları ve silahları görüntüler.")
    @app_commands.describe(kullanici="İncelenecek üye (Sadece Ekonomi Yetkilisi başkasına bakabilir)")
    async def cmd_envanter(self, interaction: discord.Interaction, kullanici: discord.Member = None):
        hedef = kullanici or interaction.user

        # Başkasının envanterini görme yetkisi kontrolü
        if hedef.id != interaction.user.id and not yetkili_mi(interaction.user):
            return await interaction.response.send_message(
                f"❌ Başka bir üyenin envanterini yalnızca <@&{EKONOMI_YETKILISI_ROL_ID}> rolüne sahip yetkililer inceleyebilir!",
                ephemeral=True
            )

        user_data = get_user_profile(hedef.id)
        inv = user_data.get("inventory", {})

        embed = discord.Embed(
            title=f"🎒 ENVANTER • {hedef.display_name}",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=hedef.display_avatar.url)

        # Silahlar ve Eşyaları ayır
        silahlar = []
        esayalar = []

        for item, count in inv.items():
            if count <= 0:
                continue
            if item in SILAH_ESYALARI:
                emoji = SILAH_ESYALARI[item]["emoji"]
                silahlar.append(f"{emoji} **{item}:** `{count} adet`")
            elif item in ILLEGAL_ESYALAR:
                emoji = ILLEGAL_ESYALAR[item]["emoji"]
                esayalar.append(f"{emoji} **{item}:** `{count} adet` *(İllegal)*")
            else:
                emoji = MARKET_ESYALARI.get(item, {}).get("emoji", "📦")
                esayalar.append(f"{emoji} **{item}:** `{count} adet`")

        if not silahlar and not esayalar:
            embed.description = "*Bu kullanıcının envanterinde kayıtlı herhangi bir eşya veya silah bulunmamaktadır.*"
        else:
            embed.description = f"**Kullanıcı:** {hedef.mention} `({hedef.id})`\n──────────────────────────────"
            embed.add_field(
                name="🔫 Ruhsatsız Silahlar",
                value="\n".join(silahlar) if silahlar else "*Silah bulunmuyor.*",
                inline=False
            )
            embed.add_field(
                name="📦 Genel Malzemeler & Envanter",
                value="\n".join(esayalar) if esayalar else "*Eşya bulunmuyor.*",
                inline=False
            )

        embed.set_footer(text="Piyade RP Envanter Sistemi")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="param", description="Nakit ve banka bakiye miktarınızı görüntüler.")
    @app_commands.describe(kullanici="Bakiye bilgisine bakılacak üye (Sadece Ekonomi Yetkilisi)")
    async def cmd_param(self, interaction: discord.Interaction, kullanici: discord.Member = None):
        hedef = kullanici or interaction.user

        # Başkasının parasını görme yetkisi kontrolü
        if hedef.id != interaction.user.id and not yetkili_mi(interaction.user):
            return await interaction.response.send_message(
                f"❌ Başka bir kullanıcının para miktarını yalnızca <@&{EKONOMI_YETKILISI_ROL_ID}> rolüne sahip yetkililer inceleyebilir!",
                ephemeral=True
            )

        user_data = get_user_profile(hedef.id)
        nakit = user_data.get("cash", 0)
        banka = user_data.get("bank", 0)
        toplam = nakit + banka

        embed = discord.Embed(
            title=f"💰 MALİ VARLIK TABLOSU • {hedef.display_name}",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_thumbnail(url=hedef.display_avatar.url)
        embed.description = f"Kullanıcı: {hedef.mention}\n──────────────────────────────"
        embed.add_field(name="💵 Nakit Para (Cebinizde)", value=f"**{format_usd(nakit)}**", inline=True)
        embed.add_field(name="💳 Banka Hesabı (ATM)", value=f"**{format_usd(banka)}**", inline=True)
        embed.add_field(name="📊 Toplam Servet", value=f"**{format_usd(toplam)}**", inline=False)
        embed.set_footer(text="Gizli Mesaj • Sadece siz görebilirsiniz")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="stok-yenile", description="Silahçıdaki silah stoklarına 50'şer adet ekler.")
    async def cmd_stok_yenile(self, interaction: discord.Interaction):
        if not yetkili_mi(interaction.user):
            return await interaction.response.send_message(
                f"❌ Bu komutu yalnızca <@&{EKONOMI_YETKILISI_ROL_ID}> rolüne sahip Ekonomi Yetkilileri kullanabilir!",
                ephemeral=True
            )

        async with _ENV_LOCK:
            data = _get_raw_data()
            stoklar = data.setdefault("gunshop_stock", {"Beretta 92": 0, "Colt 1911": 0})
            stoklar["Beretta 92"] = stoklar.get("Beretta 92", 0) + 50
            stoklar["Colt 1911"] = stoklar.get("Colt 1911", 0) + 50
            _save_raw_data(data)

        # Paneli anlık güncelle
        await self.guncelle_gunshop_paneli(interaction.guild)

        embed = discord.Embed(
            title="📦 SİLAH STOKLARI YENİLENDİ",
            color=discord.Color.gold(),
            description=(
                f"✅ {interaction.user.mention} tarafından mağaza stokları güncellendi!\n\n"
                f"• **Beretta 92:** +50 Adet eklendi (Yeni Stok: **{stoklar['Beretta 92']}**)\n"
                f"• **Colt 1911:** +50 Adet eklendi (Yeni Stok: **{stoklar['Colt 1911']}**)"
            )
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="market-panelleri-kur", description="ATM, Market, Silahçı ve İllegal Market panellerini kurar.")
    async def cmd_market_panelleri_kur(self, interaction: discord.Interaction):
        if not yetkili_mi(interaction.user):
            return await interaction.response.send_message("❌ Bu işlem için yetkiniz bulunmamaktadır.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        log_rapor = []
        data = _get_raw_data()
        p_msgs = data.setdefault("panel_messages", {})

        # 1. ATM Kanalı
        atm_kanal = guild.get_channel(ATM_KANAL_ID)
        if atm_kanal:
            atm_embed = discord.Embed(
                title="🏧 PACIFIC BANK • CANLI ATM TERMİNALİ",
                description=(
                    "Pacific Bankası 7/24 kesintisiz ATM terminaline hoş geldiniz.\n"
                    "Para yatırma ve para çekme işlemlerinizi aşağıdaki butonlarla yapabilirsiniz.\n\n"
                    "⚠️ **ÖNEMLİ KURAL:**\n"
                    "Bu paneli yalnızca oyun içerisinde bir **ATM noktasının** yanındayken kullanabilirsiniz.\n"
                    "──────────────────────────────────────────"
                ),
                color=discord.Color.blue()
            )
            atm_embed.add_field(name="📥 Para Yatır", value="Cebinizdeki nakit parayı güvenle banka hesabınıza yatırır.", inline=True)
            atm_embed.add_field(name="📤 Para Çek", value="Banka hesabınızdan nakit çekerek cebinize aktarır.", inline=True)
            atm_embed.add_field(name="💳 Bakiye Sorgula", value="Hesap bakiyenizi gizli olarak görüntüler.", inline=True)
            atm_embed.set_footer(text="Pacific Bank • Güvenli Bankacılık Ağı")

            try:
                await atm_kanal.purge(limit=10)
            except Exception:
                pass
            msg = await atm_kanal.send(embed=atm_embed, view=ATMView())
            p_msgs["atm"] = msg.id
            log_rapor.append("✅ ATM Paneli kuruldu.")
        else:
            log_rapor.append("⚠️ ATM Kanalı bulunamadı!")

        # 2. Market Kanalı
        market_kanal = guild.get_channel(MARKET_KANAL_ID)
        if market_kanal:
            m_embed = discord.Embed(
                title="🏪 24/7 SÜPERMARKET • GENEL İHTİYAÇLAR",
                description=(
                    "Los Santos süpermarketine hoş geldiniz!\n"
                    "İhtiyacınız olan ürünleri aşağıdaki menüden seçerek anında satın alabilirsiniz.\n\n"
                    "💵 **Ödeme Yöntemi:** Yalnızca **NAKİT** cüzdanınızdan kesilir.\n"
                    "──────────────────────────────────────────"
                ),
                color=discord.Color.green()
            )
            for k, v in MARKET_ESYALARI.items():
                m_embed.add_field(
                    name=f"{v['emoji']} {k} — {format_usd(v['fiyat'])}",
                    value=v["aciklama"],
                    inline=False
                )
            m_embed.set_footer(text="Piyade RP 24/7 Market • İyi Alışverişler!")

            try:
                await market_kanal.purge(limit=10)
            except Exception:
                pass
            msg = await market_kanal.send(embed=m_embed, view=MarketView())
            p_msgs["market"] = msg.id
            log_rapor.append("✅ 24/7 Market Paneli kuruldu.")
        else:
            log_rapor.append("⚠️ Market Kanalı bulunamadı!")

        # 3. Silahçı Kanalı
        silah_kanal = guild.get_channel(SILAHCI_KANAL_ID)
        if silah_kanal:
            stoklar = data.get("gunshop_stock", {"Beretta 92": 50, "Colt 1911": 50})
            b_stok = stoklar.get("Beretta 92", 50)
            c_stok = stoklar.get("Colt 1911", 50)

            s_embed = discord.Embed(
                title="🔫 AMMU-NATION • SİLAH & MÜHİMMAT MAĞAZASI",
                description=(
                    "Los Santos Ammu-Nation silah mağazasına hoş geldiniz.\n"
                    "Aşağıdaki butonları kullanarak doğrudan satın alım yapabilirsiniz.\n\n"
                    "⚠️ **ÖNEMLİ BİLGİLENDİRME:**\n"
                    "• **Silahçıdan satın alınan tüm silahlar RUHSATSIZDIR!**\n"
                    "• Emniyet birimlerinin yapacağı üst aramasında veya denetimlerde ruhsatsız silah bulundurmak suç teşkil eder.\n"
                    "• Ödemeler doğrudan **NAKİT** cüzdanınızdan tahsil edilir.\n"
                    "• Satın aldığınız silahlar anında dijital envanterinize kaydedilir.\n"
                    "• Sunucu kuralları gereği envantersiz silah kullanımı (E.S.K) cezalandırılır.\n"
                    "──────────────────────────────────────────"
                ),
                color=discord.Color.gold()
            )
            s_embed.add_field(
                name="• Beretta 92 (9mm)",
                value=f"💵 Fiyat: `{format_usd(SILAH_ESYALARI['Beretta 92']['fiyat'])}`\n📦 Kalan Stok: **{b_stok} Adet**\n*Standart hafif yarı otomatik beylik tabancası.*",
                inline=True
            )
            s_embed.add_field(
                name="• Colt 1911 (.45 ACP)",
                value=f"💵 Fiyat: `{format_usd(SILAH_ESYALARI['Colt 1911']['fiyat'])}`\n📦 Kalan Stok: **{c_stok} Adet**\n*Ağır kalibre klasik çelik gövde tabanca.*",
                inline=True
            )
            s_embed.set_footer(text="Stok Kontrolü: Ekonomi Yetkilisi • Piyade RP Ammu-Nation")

            try:
                await silah_kanal.purge(limit=10)
            except Exception:
                pass
            msg = await silah_kanal.send(embed=s_embed, view=GunshopView(self))
            p_msgs["gunshop"] = msg.id
            log_rapor.append("✅ Ammu-Nation Silahçı Paneli kuruldu.")
        else:
            log_rapor.append("⚠️ Silahçı Kanalı bulunamadı!")

        # 4. İllegal Market Kanalı
        ill_kanal = guild.get_channel(ILLEGAL_MARKET_KANAL_ID)
        if ill_kanal:
            ill_embed = discord.Embed(
                title="🌑 KARA BORSA • İLLEGAL MARKET",
                description=(
                    "Yeraltı dünyasının teçhizat ve kimyasal madde tedarik noktası.\n"
                    "Buradaki ürünler polisin dikkatini çeker. Dikkatli kullanın.\n\n"
                    "💵 **Ödeme:** Sadece elden **NAKİT** para kabul edilir.\n"
                    "──────────────────────────────────────────"
                ),
                color=discord.Color.dark_red()
            )
            for k, v in ILLEGAL_ESYALAR.items():
                ill_embed.add_field(
                    name=f"{v['emoji']} {k} — {format_usd(v['fiyat'])}",
                    value=v["aciklama"],
                    inline=False
                )
            ill_embed.set_footer(text="Piyade RP Yeraltı Şebekesi • Gizlilik Esastır")

            try:
                await ill_kanal.purge(limit=10)
            except Exception:
                pass
            msg = await ill_kanal.send(embed=ill_embed, view=IllegalMarketView())
            p_msgs["illegal_market"] = msg.id
            log_rapor.append("✅ İllegal Market Paneli kuruldu.")
        else:
            log_rapor.append("⚠️ İllegal Market Kanalı bulunamadı!")

        _save_raw_data(data)
        await interaction.followup.send("\n".join(log_rapor), ephemeral=True)

    # -----------------------------------------------------------------
    # YÖNETSEL BAKİYE VE EŞYA AYARLAMA KOMUTLARI
    # -----------------------------------------------------------------
    @app_commands.command(name="bakiye-ver", description="Bir kullanıcıya nakit veya banka parası ekler.")
    @app_commands.describe(
        kullanici="Para verilecek üye",
        tur="Nakit veya Banka hesabı",
        miktar="Eklenecek dolar tutarı"
    )
    @app_commands.choices(tur=[
        app_commands.Choice(name="Nakit Para (Cüzdan)", value="cash"),
        app_commands.Choice(name="Banka Hesabı", value="bank")
    ])
    async def cmd_bakiye_ver(self, interaction: discord.Interaction, kullanici: discord.Member, tur: app_commands.Choice[str], miktar: int):
        if not yetkili_mi(interaction.user):
            return await interaction.response.send_message("❌ Bu komutu yalnızca Ekonomi Yetkilileri kullanabilir!", ephemeral=True)

        if miktar <= 0:
            return await interaction.response.send_message("❌ Miktar pozitif bir sayı olmalıdır!", ephemeral=True)

        async with _ENV_LOCK:
            user = get_user_profile(kullanici.id)
            user[tur.value] += miktar
            update_user_profile(kullanici.id, user)

        await interaction.response.send_message(
            f"✅ {kullanici.mention} kullanıcısına **{format_usd(miktar)}** ({tur.name}) başarıyla eklendi!\n"
            f"Yeni Bakiye: `{format_usd(user[tur.value])}`",
            ephemeral=True
        )

    @app_commands.command(name="esya-ver", description="Bir kullanıcıya envanter eşyası veya silah verir.")
    @app_commands.describe(
        kullanici="Eşya verilecek üye",
        esya_adi="Verilecek eşya/silah adı",
        adet="Verilecek miktar"
    )
    async def cmd_esya_ver(self, interaction: discord.Interaction, kullanici: discord.Member, esya_adi: str, adet: int = 1):
        if not yetkili_mi(interaction.user):
            return await interaction.response.send_message("❌ Bu komutu yalnızca Ekonomi Yetkilileri kullanabilir!", ephemeral=True)

        if adet <= 0:
            return await interaction.response.send_message("❌ Adet pozitif bir sayı olmalıdır!", ephemeral=True)

        # Geçerli eşya mı kontrolü
        tum_esyalar = {**MARKET_ESYALARI, **ILLEGAL_ESYALAR, **SILAH_ESYALARI}
        eslesen_esya = None
        for item in tum_esyalar:
            if item.lower() == esya_adi.strip().lower():
                eslesen_esya = item
                break

        if not eslesen_esya:
            esya_listesi = ", ".join(tum_esyalar.keys())
            return await interaction.response.send_message(
                f"❌ Geçersiz eşya adı! Geçerli eşyalar şunlardır:\n`{esya_listesi}`",
                ephemeral=True
            )

        async with _ENV_LOCK:
            user = get_user_profile(kullanici.id)
            user["inventory"][eslesen_esya] = user["inventory"].get(eslesen_esya, 0) + adet
            update_user_profile(kullanici.id, user)

        await interaction.response.send_message(
            f"✅ {kullanici.mention} kullanıcısına **{adet}x {eslesen_esya}** verildi.\n"
            f"Kullanıcının Envanterindeki Toplam: `{user['inventory'][eslesen_esya]} adet`",
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    cog = EnvanterSistemi(bot)
    await bot.add_cog(cog)
