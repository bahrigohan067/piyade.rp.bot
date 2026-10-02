import discord
from discord.ext import commands
import random
import re

# ==========================================
# Sa-As Sistemi — Regex tabanlı, noktalama
# ve boşluğa dayanıklı selam algılayıcı
# ==========================================

# Her tetikleyici için \b (sözcük sınırı) ve başına/sonuna anlamsız
# noktalama gelebileceği varsayılır. Arama mesajın herhangi bir yerinde
# yapılmaz; metnin TAMAMININ bu kalıplardan biriyle başlayıp bitmesi
# ya da tek başına bu kelimeden oluşması aranır.
#
# Strateji: Mesajın başında veya tamamen bu kelimeden oluşuyorsa yanıt ver.
# Böylece "saat 12'de sa görüşürüz" gibi cümlelerde yanlış tetiklenme olmaz.

_TETIKLEYICI_KALIPLARI: list[re.Pattern] = [
    # Kısa ve riskli olanlar → mesajın TAMAMI bu kelime olmalı
    re.compile(r"^[\W_]*(sa|slm|s\.a\.?|sea|s\.a)[\W_]*$",                        re.IGNORECASE | re.UNICODE),
    # Biraz daha uzun olanlar → mesajın başında olması yeterli
    re.compile(r"^[\W_]*(selam|selamlar|selam\s+millet|merhabalar|hayırlı\s+günler)[\W_,!?\.]*",
               re.IGNORECASE | re.UNICODE),
    # Selamın Aleyküm varyasyonları — tüm yazım biçimleri
    re.compile(
        r"^[\W_]*(esse?l[aâ]mu?\s*'?aleyk[uü]m|selamın?\s*aleyk[uü]m|"
        r"selamun?\s*aleyk[uü]m|selamına?ley[kq]ü?m)[\W_]*$",
        re.IGNORECASE | re.UNICODE,
    ),
]

YANITLAR: list[str] = [
    "Aleyküm selam, selamın aynısı sana da kardeş! ✌️😎",
    "Ve aleyküm selam, selamın en güzeli senden geldi. ✨",
    "Aleyküm selam, selamına kurban! 🤎",
    "Ve aleyküm selam, buyur başım gözüm üstüne. 👑",
    "Aleyküm selam, selamınla şereflendik. 🌹",
    "Ve aleyküm selam, selametle kal. 🕊️",
    "Aleyküm selam, selamın ağırlığı kadar bereket üzerine olsun. 🤲💎",
    "Ve aleyküm selam, aldım başımın üstüne yeri var. 🫡",
    "Aleyküm selam, selam hadi; aleyküm de hadi! 😅👋",
    "Ve aleyküm selam, aynen iade ediyorum. 🔄😉",
    "Aleyküm selam, selamına selam kattık. ➕🔥",
    "Ve aleyküm selam, selamın bana ulaştı, karşılığı fazlasıyla sana. 💯",
    "Aleyküm selam, selamın tadı damağımda kaldı. 🍬😋",
    "Ve aleyküm selam, selamının kıymetini bilirim. 🌟",
    "Aleyküm selam, selam olsun sana da güzel insan. 💐",
]


def selam_mi(metin: str) -> bool:
    """Mesaj bir selamlama kalıbıyla eşleşiyor mu?"""
    return any(pat.search(metin) for pat in _TETIKLEYICI_KALIPLARI)


class SaAs(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        if selam_mi(message.content):
            try:
                await message.reply(random.choice(YANITLAR), mention_author=False)
            except (discord.Forbidden, discord.HTTPException):
                pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SaAs(bot))
