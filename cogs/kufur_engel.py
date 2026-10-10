import discord
from discord.ext import commands
import re
import unicodedata

# ==================== AYARLAR ====================
KUFUR_LOG_KANAL_ID = 1551257729530855464
MESAJ_DENETIMCI_ROL_ID = 1542249243702726796
# ==================================================


def _normalize(text: str) -> str:
    """
    Metni normalize eder:
    - Küçük harfe çevirir
    - Unicode NFD formuna getirip aksan işaretlerini soyar
    - Türkçe karakterleri karşılıklarına çevirir
    - Leetspeak (1=i, 3=e, 0=o, @=a, 4=a, 5=s vb.) karşılıklarına çevirir
    - Tekrar eden harfleri teke indirir (örn. "siiikkk" → "sik")
    - Noktalama ve boşlukları kaldırır
    """
    text = text.lower()

    # Türkçe normalize
    tr_map = str.maketrans("çğışöüİĞŞÜÖÇ", "cgisouIGSUOC")
    text = text.translate(tr_map)

    # Aksan işaretlerini kaldır
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")

    # Leetspeak karşılıkları
    leet_map = str.maketrans({
        "1": "i", "!": "i", "|": "i",
        "3": "e",
        "0": "o",
        "@": "a", "4": "a",
        "5": "s", "$": "s",
        "7": "t",
        "8": "b",
        "+": "t",
        "(": "c",
    })
    text = text.translate(leet_map)

    # Tekrar eden harfleri teke indir (sssiikk → sik)
    text = re.sub(r"(.)\1+", r"\1", text)

    return text


def _build_pattern(word: str) -> re.Pattern:
    r"""
    Verilen kelimenin aralarına herhangi bir karakter/boşluk girebileceği
    toleranslı bir regex deseni oluşturur. Örneğin "sik" → \b s\W*i\W*k \b
    """
    pattern_str = r"\W*".join(re.escape(c) for c in word)
    return re.compile(r"\b" + pattern_str + r"\b", re.IGNORECASE)


# ============================
#   KUFÜR / HAKARET KÖKLERİ
# ============================
# Kelimelerin normalleştirilmiş (Türkçe, leet-free, tekrar harfsiz) halleri yazılmıştır.
# Bunlar _normalize() işleminden geçirilmiş metinde aranır.
# Kelimelerin normalleştirilmiş (Türkçe, leet-free, tekrar harfsiz) halleri yazılmıştır.
# Bunlar _normalize() işleminden geçirilmiş metinde aranır.
# Masum kelimelerin (örn. asalak, kontaminasyon, kombina) hatalı engellenmemesi için
# tüm köklerde sözcük sınırı (\b) kullanılır.

KUFUR_KOKLERI: list[str] = [
    # Cinsel
    "sik", "siker", "sikey", "sikim", "sikis", "sikik", "sikiyor",
    "sktr", "siktir", "soke", "sokey",
    "yarrak", "yarak", "yarram",
    "amk", "amq", "bok",
    "amina", "amini", "amcik",
    "got", "gotten", "gotlek",
    "pic", "serefsiz", "serefsizler",
    "orospu", "orospular", "orsp",
    "pezevenk", "pezevenkler",
    "ibne", "ibneler",
    "gavat", "kahpe",
    "tasak", "tassak", "yavşak", "yavsak", "yavsaklar",
    "dol",
    # Hakaret
    "gerizekal", "gerizekali", "gerizekalilar", "aptal", "aptallar", "salak", "salaklar", "ahmak",
    "bok", "pislik",
    "manyak", "manyaklar",
    "bok kafal", "bok kafali",
    "beyinsiz",
    # Aile hakareti
    "anani", "ananin", "bacini", "karini", "ananizi",
    # Irkçılık/ayrımcılık kelimeleri (ön ek ile tespit)
    "zenci", "gavur",
]

# Köklerin de _normalize() işleminden geçirilmiş halleri aranır
_NORM_KOKLER: set[str] = {_normalize(k) for k in KUFUR_KOKLERI}

# Kısa kökler (≤3 harf normalize) için tam sözcük eşleşmesi gerektir
_KISA_ESLESME: set[str] = {k for k in _NORM_KOKLER if len(k) <= 3}

# Uzun kökler (>3 harf)
_UZUN_KOKLER: list[str] = sorted([k for k in _NORM_KOKLER if len(k) > 3], key=len, reverse=True)

# Ön derleme → her başlatmada tekrar derlenmez
_KISA_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _KISA_ESLESME) + r")\b"
) if _KISA_ESLESME else None

# Uzun kökler: Masum kelimelerin (örn. asalak, kontaminasyon, kombina) engellenmemesi için \b kelime sınırı uygulanır
_UZUN_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b" + re.escape(k) + r"\b") for k in _UZUN_KOKLER
]

# Performans için tek birleşik regex
_UZUN_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in _UZUN_KOKLER) + r")\b"
) if _UZUN_KOKLER else None

# Özel harf-arası boşluk toleransı (s i k, s.i.k, s*i*k)
_TOLERANSLI_PATTERNS: list[re.Pattern] = [
    _build_pattern(k) for k in _KISA_ESLESME
]


def kufur_mu(metin: str) -> bool:
    """
    Metni normalize edip küfür içerip içermediğini döndürür.
    Hem orijinal hem normalize metni kontrol eder.
    """
    if not metin or not metin.strip():
        return False

    norm = _normalize(metin)

    # Kısa kökler: tam sözcük eşleşmesi (normalize metinde)
    if _KISA_PATTERN and _KISA_PATTERN.search(norm):
        return True

    # Kısa kökler: boşluk/noktalama toleransı (orijinal metinde)
    metin_lower = metin.lower()
    for pat in _TOLERANSLI_PATTERNS:
        if pat.search(metin_lower):
            return True

    # Uzun kökler: \b kelime sınırı ile arama (normalize metinde)
    if _UZUN_PATTERN and _UZUN_PATTERN.search(norm):
        return True
    for pat in _UZUN_PATTERNS:
        if pat.search(norm):
            return True

    return False


# ==================== DISCORD COG ====================

class KufurEngel(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ----- Log gönderici -----
    async def _log_gonder(self, message: discord.Message, tur: str) -> None:
        log_kanal = self.bot.get_channel(KUFUR_LOG_KANAL_ID)
        if not log_kanal:
            return

        # Mesaj içeriği 1024 karakteri geçmesin (embed field limiti)
        icerik = message.content[:1024] or "*[Boş mesaj / ek içerik]*"

        embed = discord.Embed(
            title="🚨 Uygunsuz İçerik Tespit Edildi",
            color=discord.Color.brand_red(),
        )
        embed.set_author(
            name=f"{message.author} ({message.author.id})",
            icon_url=message.author.display_avatar.url,
        )
        embed.add_field(name="👤 Kullanıcı", value=message.author.mention, inline=True)
        embed.add_field(name="📍 Kanal", value=message.channel.mention, inline=True)
        embed.add_field(name="🔖 Tür", value=tur, inline=True)
        embed.add_field(name="💬 Mesaj İçeriği", value=f"```{icerik}```", inline=False)
        embed.add_field(
            name="🔗 Mesaj Linki",
            value=f"[Mesaja Git]({message.jump_url})",
            inline=False,
        )
        embed.set_footer(text=f"Kullanıcı ID: {message.author.id}")
        embed.timestamp = discord.utils.utcnow()

        try:
            await log_kanal.send(
                content=f"<@&{MESAJ_DENETIMCI_ROL_ID}>",
                embed=embed,
            )
        except discord.Forbidden:
            pass

    # ----- DM gönderici -----
    async def _dm_gonder(self, message: discord.Message) -> None:
        try:
            await message.author.send(
                f"⚠️ **{message.guild.name}** sunucusunda uygunsuz bir ifade kullandığın tespit edildi.\n"
                f"Lütfen sunucu kurallarına uy ve saygılı bir dil kullan.\n"
                f"Tekrarlanması durumunda yönetim tarafından işlem yapılabilir."
            )
        except (discord.Forbidden, discord.HTTPException):
            # DM kapalıysa sessizce devam et
            pass

    # ----- Yeni mesaj dinleyicisi -----
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if not message.guild:
            return

        if kufur_mu(message.content):
            await self._log_gonder(message, "Yeni Mesaj")
            await self._dm_gonder(message)
            # ⚠️ Kullanıcının isteği üzerine mesaj SİLİNMİYOR

    # ----- Düzenlenen mesaj dinleyicisi -----
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if after.author.bot:
            return
        if not after.guild:
            return
        # Sadece içerik gerçekten değiştiyse kontrol et
        if before.content == after.content:
            return

        if kufur_mu(after.content):
            await self._log_gonder(after, "Düzenlenen Mesaj")
            await self._dm_gonder(after)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(KufurEngel(bot))
