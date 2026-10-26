import discord
from discord.ext import commands
from discord import app_commands
import os
import time
import random
import asyncio
import itertools
import aiohttp
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable, Awaitable

from config import GUILD_ID
from cogs.envanter_sistemi import mesafe_hesapla, discord_to_roblox
from cogs.live_radar import roblox_to_discord
from cogs.rp_oylama import send_erlc_command

# ── SABİTLER VE AYARLAR ──
ILKYARDIM_MAX_MESAFE = 6.0   # Azami 6 birim (ATM yakınlık mantığıyla birebir aynı)
ILKYARDIM_SURESI = 20.0      # 20 saniye müdahale süresi
tz_tr = timezone(timedelta(hours=3))

# 3 Müdahale Türü ve Doğru Sıralı Aşamaları
MUDAHALE_TURLERI = {
    "acik_yara": {
        "baslik": "Açık Yara Müdahalesi",
        "buton_label": "Açık yara",
        "emoji": "🩸",
        "renk": discord.Color.red(),
        "asamalar": [
            "Durumu kontrol et",
            "Yarayı temiz bez ile sar",
            "Stabilize et (Güvenceye Al)"
        ]
    },
    "kemik_kirigi": {
        "baslik": "Kemik Kırığı Müdahalesi",
        "buton_label": "Kemik kırığı",
        "emoji": "🦴",
        "renk": discord.Color.orange(),
        "asamalar": [
            "Durumu kontrol et",
            "Kırık olan kısmı sabitle",
            "Kişiye Hastaneye gitmesi için yardımcı ol"
        ]
    },
    "diger_durumlar": {
        "baslik": "Diğer Durumlar Müdahalesi",
        "buton_label": "Diğer Durumlar",
        "emoji": "🩺",
        "renk": discord.Color.blue(),
        "asamalar": [
            "Durumu kontrol et",
            "İlk Yardım uygula",
            "Stabilize et"
        ]
    }
}

# Butonların her seferinde farklı dizilmesi için son dizilimi takip et
_SON_DIZILIM: Optional[tuple] = None


def farkli_dizilim_uret(asamalar: list[str]) -> list[tuple[int, str]]:
    """
    Verilen 3 aşamayı (orijinal_indeks, metin) olarak her seferinde
    bir öncekinden farklı bir sırayla karıştırır.
    """
    global _SON_DIZILIM
    indexed = list(enumerate(asamalar))
    tum_perm = list(itertools.permutations(indexed))

    # Bir önceki dizilimle aynı olmayanları filtrele
    uygun_perm = [p for p in tum_perm if tuple(x[0] for x in p) != _SON_DIZILIM]
    secilen = random.choice(uygun_perm if uygun_perm else tum_perm)
    _SON_DIZILIM = tuple(x[0] for x in secilen)
    return list(secilen)


def normalize_erlc_cmd(text: str) -> str:
    """
    ER:LC veya chat üzerinden gelen komut metnini güvenli, küçük harfli ve
    Türkçe-İngilizce harf varyasyonlarından arındırılmış saf ASCII haline getirir.
    Örn: ';İlkyardım' -> 'ilkyardim', ';ilk yardım' -> 'ilkyardim'
    """
    if not text:
        return ""
    t = str(text).strip().lstrip(";:!/. \t\r\n")
    # Önce büyük harf Türkçeleri değiştir (Python lower'ın combining dot \u0307 üretmesini engellemek için)
    t = (
        t.replace("İ", "i")
        .replace("I", "i")
        .replace("Ş", "s")
        .replace("Ğ", "g")
        .replace("Ü", "u")
        .replace("Ö", "o")
        .replace("Ç", "c")
    )
    t = t.lower()
    t = (
        t.replace("\u0307", "")
        .replace("ı", "i")
        .replace("ş", "s")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ö", "o")
        .replace("ç", "c")
        .strip()
    )
    return t


# =====================================================================
# 2. ADIM: 3 AŞAMALI MÜDAHALE BUTONLARI (20 SANİYE SÜRELİ & KARIŞIK DİZİLİMLİ)
# =====================================================================
class IlkYardimAsamaView(discord.ui.View):
    def __init__(
        self,
        user_id: int,
        tur_key: str,
        hedef_oyuncu: str,
        on_success: Callable[[discord.Interaction], Awaitable[None]],
        on_fail: Callable[[Optional[discord.Interaction], str], Awaitable[None]]
    ):
        super().__init__(timeout=ILKYARDIM_SURESI)
        self.user_id = user_id
        self.tur_key = tur_key
        self.tur_bilgi = MUDAHALE_TURLERI[tur_key]
        self.hedef_oyuncu = hedef_oyuncu
        self.dogru_asamalar: list[str] = self.tur_bilgi["asamalar"]
        self.on_success = on_success
        self.on_fail = on_fail
        self.current_step = 0
        self.finished = False

        # Aşama butonlarını her seferinde farklı şekilde diz
        karisik_liste = farkli_dizilim_uret(self.dogru_asamalar)

        for dogru_idx, asama_metni in karisik_liste:
            btn = discord.ui.Button(
                label=asama_metni,
                style=discord.ButtonStyle.secondary,
                custom_id=f"iy_step_{tur_key}_{dogru_idx}_{random.randint(1000, 9999)}"
            )
            btn.callback = self._make_callback(dogru_idx, asama_metni, btn)
            self.add_item(btn)

    def _make_callback(self, dogru_idx: int, asama_metni: str, button: discord.ui.Button):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("❌ Bu ilk yardım paneli size ait değil.", ephemeral=True)
            if self.finished:
                return

            # Doğru sıradaki butona mı basıldı?
            if dogru_idx == self.current_step:
                self.current_step += 1
                button.style = discord.ButtonStyle.success
                button.disabled = True

                # 3 aşamanın tamamı doğru sırayla tamamlandı!
                if self.current_step >= len(self.dogru_asamalar):
                    self.finished = True
                    self.stop()
                    for item in self.children:
                        item.disabled = True
                    await self.on_success(interaction)
                else:
                    tamamlananlar = "\n".join(
                        f"✅ **{i + 1}. Aşama:** `{ self.dogru_asamalar[i] }`"
                        for i in range(self.current_step)
                    )
                    kalan_sayi = len(self.dogru_asamalar) - self.current_step
                    embed = discord.Embed(
                        title=f"{self.tur_bilgi['emoji']} {self.tur_bilgi['baslik']} Devam Ediyor...",
                        description=(
                            f"🤕 **Yaralı Oyuncu:** **{self.hedef_oyuncu}**\n"
                            f"──────────────────────────────────────────\n"
                            f"{tamamlananlar}\n\n"
                            f"⏳ **Sıradaki Adım:** Kalan **{kalan_sayi}** aşamayı doğru sırayla seçin!"
                        ),
                        color=self.tur_bilgi["renk"],
                        timestamp=datetime.now(tz_tr)
                    )
                    embed.set_footer(text="Piyade RP • Acil İlk Yardım Sistemi")
                    await interaction.response.edit_message(embed=embed, view=self)
            else:
                # Hatalı sıralama! Mesaj silinecek ve işlemin başarısız olduğu belirtilecek.
                self.finished = True
                self.stop()
                await self.on_fail(
                    interaction,
                    f"Müdahale aşamalarına yanlış sırayla bastınız! (Seçilen: `{asama_metni}`, Beklenen: `{self.dogru_asamalar[self.current_step]}`)"
                )

        return callback


# =====================================================================
# 1. ADIM: ANA SEÇİM PANELİ (AÇIK YARA / KEMİK KIRIĞI / DİĞER DURUMLAR)
# =====================================================================
class IlkYardimSecimView(discord.ui.View):
    def __init__(self, cog: "IlkYardimSistemi", member: discord.Member, healer_roblox: str, hedef_roblox: str, mesafe: float):
        super().__init__(timeout=120.0)
        self.cog = cog
        self.member = member
        self.healer_roblox = healer_roblox
        self.hedef_roblox = hedef_roblox
        self.mesafe = mesafe
        self.secildi = False

    async def _baslat_mudahale(self, interaction: discord.Interaction, tur_key: str):
        if interaction.user.id != self.member.id:
            return await interaction.response.send_message("❌ Bu ilk yardım paneli size ait değil.", ephemeral=True)
        if self.secildi:
            return
        self.secildi = True
        self.stop()

        await self.cog.baslat_asama_sureci(
            interaction=interaction,
            member=self.member,
            healer_roblox=self.healer_roblox,
            hedef_roblox=self.hedef_roblox,
            tur_key=tur_key
        )

    @discord.ui.button(label="Açık yara", emoji="🩸", style=discord.ButtonStyle.danger, custom_id="btn_iy_acik_yara")
    async def btn_acik_yara(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._baslat_mudahale(interaction, "acik_yara")

    @discord.ui.button(label="Kemik kırığı", emoji="🦴", style=discord.ButtonStyle.primary, custom_id="btn_iy_kemik_kirigi")
    async def btn_kemik_kirigi(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._baslat_mudahale(interaction, "kemik_kirigi")

    @discord.ui.button(label="Diğer Durumlar", emoji="🩺", style=discord.ButtonStyle.success, custom_id="btn_iy_diger_durumlar")
    async def btn_diger_durumlar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._baslat_mudahale(interaction, "diger_durumlar")

    async def on_timeout(self):
        if not self.secildi:
            self.secildi = True
            self.cog.aktif_ilkyardimlar.discard(self.member.id)


# =====================================================================
# İLK YARDIM SİSTEMİ COG
# =====================================================================
class IlkYardimSistemi(commands.Cog):
    """Roblox ER:LC ;ilkyardım komutu ve 3 aşamalı ilk yardım müdahale sistemi."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.islenen_komutlar: set = set()
        self.aktif_ilkyardimlar: set = set()
        self._session: Optional[aiohttp.ClientSession] = None

    def cog_unload(self):
        if self._session and not self._session.closed:
            asyncio.create_task(self._session.close())

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    # ── 1. ER:LC EVENT WEBHOOK DİNLEYİCİSİ (;ilkyardım) ──
    @commands.Cog.listener("on_erlc_custom_command")
    async def on_erlc_custom_command(self, origin_id: str, cmd_clean: str, cmd_arg: str, timestamp: any, raw_data: dict):
        cmd_norm = normalize_erlc_cmd(cmd_clean)
        arg_norm = normalize_erlc_cmd(cmd_arg)
        comp_norm = cmd_norm.replace("-", "").replace("_", "").replace(" ", "")

        # ;ilkyardım, ;ilkyardim, ;İlkyardım, ;ILKYARDIM, ;ilk-yardım, ;ilk yardım, ;iy, ;yardım vb. tüm yazılışları yakala
        is_ilkyardim = (
            comp_norm == "ilkyardim" or
            cmd_norm in ("ilkyardim", "ilk-yardim", "ilk_yardim", "iy") or
            (cmd_norm == "ilk" and "yardim" in arg_norm) or
            cmd_norm in ("yardim", "yardım")
        )
        if not is_ilkyardim:
            return

        print(
            f"[İLK YARDIM WEBHOOK] 🎯 ;ilkyardım algılandı! Origin(Roblox ID): '{origin_id}' | "
            f"Ham: {cmd_clean!r} (Normalize: '{cmd_norm}') | Argüman: {cmd_arg!r}",
            flush=True
        )
        await self.handle_ilkyardim_trigger(
            origin_id=origin_id,
            player_raw="",
            cmd_arg=cmd_arg if cmd_norm != "ilk" else "",
            timestamp=timestamp
        )

    # ── 2. YEDEK: WEBHOOK KANALI METİN/EMBED DİNLEYİCİSİ ──
    @commands.Cog.listener("on_message")
    async def on_message(self, message: discord.Message):
        if not (message.author.bot or message.webhook_id):
            return

        for embed in message.embeds:
            desc = embed.description or ""
            title = embed.title or ""
            combined = normalize_erlc_cmd(f"{message.content or ''} {title} {desc}")
            if any(t in combined for t in ["ilkyardim", "ilk-yardim", "ilk yardim", "yardim"]):
                m_used = re.search(r"\[?([A-Za-z0-9_]+)\]?(?::(\d+))?\s+used the command:\s*([^\n\r]+)", desc, re.IGNORECASE)
                if m_used:
                    p_name = m_used.group(1).strip()
                    u_id = (m_used.group(2) or "").strip()
                    await self.handle_ilkyardim_trigger(origin_id=u_id, player_raw=p_name, cmd_arg="", timestamp=int(time.time()))
                    return

    async def handle_ilkyardim_trigger(self, origin_id: str, player_raw: str, cmd_arg: str, timestamp: any):
        # Tekrarlayan eventleri filtrele
        log_key = f"iy_{origin_id}_{player_raw}_{timestamp}"
        if log_key in self.islenen_komutlar:
            return
        self.islenen_komutlar.add(log_key)
        if len(self.islenen_komutlar) > 2000:
            self.islenen_komutlar.clear()

        roblox_name = player_raw.strip()
        roblox_id = str(origin_id or "").strip()

        if ":" in roblox_name:
            parts = roblox_name.split(":", 1)
            roblox_name = parts[0].strip()
            if not roblox_id:
                roblox_id = parts[1].strip()

        # 1. LiveRadar üzerinden Roblox ID -> Roblox Kullanıcı Adı çözümlemesi
        radar_cog = self.bot.get_cog("LiveRadar")
        if radar_cog and roblox_id and not roblox_name:
            for p_name, p_loc in (getattr(radar_cog, "aktif_oyuncular", {}) or {}).items():
                if str(p_loc.get("roblox_id") or "") == roblox_id:
                    roblox_name = p_name
                    break
            if not roblox_name:
                for p_name, p_loc in (getattr(radar_cog, "son_konumlar", {}) or {}).items():
                    if str(p_loc.get("roblox_id") or "") == roblox_id:
                        roblox_name = p_name
                        break

        # 2. Hala roblox_name yoksa Roblox Resmi API'sinden çek
        if roblox_id and not roblox_name and roblox_id.isdigit():
            try:
                session = await self.get_session()
                async with session.get(
                    f"https://users.roblox.com/v1/users/{roblox_id}",
                    timeout=aiohttp.ClientTimeout(total=4)
                ) as r_resp:
                    if r_resp.status == 200:
                        r_data = await r_resp.json()
                        roblox_name = str(r_data.get("name") or "").strip()
            except Exception as e:
                print(f"[İLK YARDIM] Roblox API isim sorgu hatası: {e}", flush=True)

        guild = self.bot.get_guild(GUILD_ID)
        if not guild:
            print("[İLK YARDIM HATA] Discord sunucusu (Guild) bulunamadı!", flush=True)
            return

        # 3. Discord Üyesini Bul
        discord_id = roblox_to_discord(roblox_id, roblox_name)
        member = None
        if discord_id:
            member = guild.get_member(discord_id)
            if not member:
                try:
                    member = await guild.fetch_member(discord_id)
                except Exception:
                    member = None

        if not member and roblox_name:
            r_lower = roblox_name.lower()
            for m in guild.members:
                disp_parts = [p.strip().lower() for p in m.display_name.split("|")]
                if (
                    r_lower == m.display_name.lower() or
                    r_lower in disp_parts or
                    r_lower == m.name.lower() or
                    (m.nick and r_lower == m.nick.lower()) or
                    r_lower in m.display_name.lower()
                ):
                    member = m
                    break

            if not member:
                try:
                    queried = await guild.query_members(query=roblox_name, limit=5)
                    for qm in queried:
                        if (
                            r_lower == qm.display_name.lower() or
                            r_lower in qm.display_name.lower() or
                            r_lower == qm.name.lower()
                        ):
                            member = qm
                            break
                except Exception:
                    pass

        # Discord eşleşmesi bulunamadıysa (Aşama C: Tam geri bildirim)
        if not member:
            print(f"[İLK YARDIM HATA] '{roblox_name or roblox_id}' için Discord kaydı/eşleşmesi bulunamadı!", flush=True)
            if roblox_name:
                asyncio.create_task(send_erlc_command(f":pm {roblox_name} Ilk yardim icin Discord hesabinizi Piyade RP ile eslestirmelisiniz!"))
            return

        if not roblox_name:
            r_ad, _ = discord_to_roblox(member.id, member.display_name)
            roblox_name = r_ad or member.display_name

        await self.execute_ilkyardim_flow(
            member=member,
            healer_roblox_name=roblox_name,
            healer_roblox_id=roblox_id,
            cmd_arg=cmd_arg,
            interaction=None
        )

    async def _en_yakin_oyuncuyu_bul(
        self,
        member: discord.Member,
        healer_roblox_name: str,
        healer_roblox_id: str = ""
    ) -> tuple[bool, str, Optional[str], Optional[float], Optional[dict]]:
        """
        Komutu kullanan oyuncunun konumunu bulur ve KENDİSİ HARİÇ en yakınındaki
        oyuncuyu ve mesafesini döndürür.
        Aşama D: Canlı radar API'sinden taze konum çeker.
        Dönüş: (uygun_mu, durum_kodu, hedef_roblox_adi, mesafe, healer_konumu)
        """
        radar_cog = self.bot.get_cog("LiveRadar")
        if not radar_cog:
            return False, "radar_yok", None, None, None

        # Taze konumları al
        aktif_oyuncular = {}
        if hasattr(radar_cog, "get_taze_oyuncu_konumlari"):
            try:
                aktif_oyuncular = await radar_cog.get_taze_oyuncu_konumlari()
            except Exception as e:
                print(f"[İLK YARDIM] Taze konum çekme hatası (önbelleğe geçiliyor): {e}", flush=True)
                aktif_oyuncular = getattr(radar_cog, "aktif_oyuncular", {}) or {}
        else:
            aktif_oyuncular = getattr(radar_cog, "aktif_oyuncular", {}) or {}

        if not aktif_oyuncular:
            # Yedek: son_konumlar
            aktif_oyuncular = getattr(radar_cog, "son_konumlar", {}) or {}

        if not aktif_oyuncular:
            return False, "oyunda_degil", None, None, None

        kayitli_ad, kayitli_id = discord_to_roblox(member.id, member.display_name)
        aranan_id = str(healer_roblox_id or kayitli_id or "").strip()
        aranan_ad = (healer_roblox_name or kayitli_ad or "").strip()

        healer_gercek_ad = None
        healer_loc = None

        # 1. Önce Roblox ID ile komutu kullanan oyuncunun konumunu bul
        if aranan_id:
            for p_name, p_loc in aktif_oyuncular.items():
                if str(p_loc.get("roblox_id") or "") == aranan_id:
                    healer_gercek_ad = p_name
                    healer_loc = p_loc
                    break

        # 2. Roblox adıyla ara
        if not healer_loc and aranan_ad:
            for p_name, p_loc in aktif_oyuncular.items():
                if p_name.lower() == aranan_ad.lower():
                    healer_gercek_ad = p_name
                    healer_loc = p_loc
                    break

        # 3. Discord display_name '|' parçalarıyla ara
        if not healer_loc and "|" in member.display_name:
            for parca in member.display_name.split("|"):
                temiz = parca.strip()
                if len(temiz) >= 3:
                    for p_name, p_loc in aktif_oyuncular.items():
                        if p_name.lower() == temiz.lower():
                            healer_gercek_ad = p_name
                            healer_loc = p_loc
                            break
                if healer_loc:
                    break

        # 4. Hala bulunamadıysa radarın son_konumlar önbelleğini tara
        if not healer_loc and hasattr(radar_cog, "son_konumlar"):
            for p_name, p_loc in (radar_cog.son_konumlar or {}).items():
                p_rid = str(p_loc.get("roblox_id") or "")
                if (aranan_id and p_rid == aranan_id) or (aranan_ad and p_name.lower() == aranan_ad.lower()):
                    healer_gercek_ad = p_name
                    healer_loc = p_loc
                    break

        if not healer_loc or not healer_gercek_ad:
            return False, "oyunda_degil", None, None, None

        hx = healer_loc.get("x")
        hz = healer_loc.get("z")
        if not isinstance(hx, (int, float)) or not isinstance(hz, (int, float)):
            return False, "konum_gecersiz", None, None, healer_loc

        # 5. KENDİSİ HARİÇ en yakın oyuncuyu bul ([ Bir kullanıcı kendine ilkyardım uygulayamaz. ])
        en_yakin_hedef = None
        min_dist = float("inf")

        for p_name, p_loc in aktif_oyuncular.items():
            p_id = str(p_loc.get("roblox_id") or "")
            # Kendisini kesinlikle hariç tut
            if p_name.lower() == healer_gercek_ad.lower():
                continue
            if aranan_id and p_id and p_id == aranan_id:
                continue

            ox = p_loc.get("x")
            oz = p_loc.get("z")
            if not isinstance(ox, (int, float)) or not isinstance(oz, (int, float)):
                continue

            try:
                d = mesafe_hesapla(hx, hz, ox, oz)
                if d < min_dist:
                    min_dist = d
                    en_yakin_hedef = p_name
            except Exception:
                continue

        if not en_yakin_hedef:
            return False, "baska_oyuncu_yok", None, None, healer_loc

        if min_dist <= ILKYARDIM_MAX_MESAFE:
            return True, "basarili", en_yakin_hedef, min_dist, healer_loc
        else:
            return False, "uzakta", en_yakin_hedef, min_dist, healer_loc

    async def execute_ilkyardim_flow(
        self,
        member: discord.Member,
        healer_roblox_name: str,
        healer_roblox_id: str = "",
        cmd_arg: str = "",
        interaction: Optional[discord.Interaction] = None
    ):
        # 1. Aktif ilk yardım işlemi kontrolü
        if member.id in self.aktif_ilkyardimlar:
            msg = "⚠️ **Zaten devam eden aktif bir ilk yardım müdahaleniz bulunuyor!** Lütfen Discord DM kutunuzu kontrol edin."
            print(f"[İLK YARDIM BİLGİ] {healer_roblox_name} zaten devam eden bir ilk yardıma sahip.", flush=True)
            if interaction:
                return await interaction.response.send_message(msg, ephemeral=True)
            try:
                await member.send(msg)
            except Exception:
                pass
            if healer_roblox_name:
                asyncio.create_task(send_erlc_command(f":pm {healer_roblox_name} Zaten aktif ilk yardiminiz var! Discord DM kutunuzu kontrol edin."))
            return

        # 2. Kullanıcı argüman olarak kendi adını yazdıysa engelle ([ Bir kullanıcı kendine ilkyardım uygulayamaz. ])
        if cmd_arg and healer_roblox_name and cmd_arg.strip().lower() == healer_roblox_name.strip().lower():
            msg = "❌ **Kendinize ilk yardım uygulayamazsınız!** İlk yardım yalnızca yakınınızdaki başka bir yaralıya uygulanabilir."
            print(f"[İLK YARDIM UYARI] {healer_roblox_name} kendine ilk yardım uygulamaya çalıştı.", flush=True)
            if interaction:
                return await interaction.response.send_message(msg, ephemeral=True)
            try:
                await member.send(msg)
            except Exception:
                pass
            asyncio.create_task(send_erlc_command(f":pm {healer_roblox_name} Kendinize ilk yardim uygulayamazsiniz!"))
            return

        # 3. En yakındaki oyuncuyu ve 6 birim yakınlık şartını kontrol et (Aşama D)
        uygun, durum, hedef_oyuncu, mesafe, healer_loc = await self._en_yakin_oyuncuyu_bul(
            member, healer_roblox_name, healer_roblox_id
        )

        if not uygun or not hedef_oyuncu:
            if durum == "oyunda_degil":
                dm_text = (
                    "❌ **Oyun İçi Konumunuz Tespit Edilemedi!**\n"
                    "İlk yardım uygulayabilmek için ER:LC sunucusunda aktif olmalısınız."
                )
                pm_text = f":pm {healer_roblox_name} Konumunuz alinamadi! ER:LC sunucusunda aktif oldugunuzdan emin olun."
                print(f"[İLK YARDIM HATA] {healer_roblox_name} konum tespit edilemedi (oyunda değil veya radarda yok).", flush=True)
            elif durum == "baska_oyuncu_yok":
                dm_text = (
                    "❌ **Yakınınızda Başka Bir Oyuncu Bulunmuyor!**\n"
                    "Sunucuda şu anda ilk yardım uygulayabileceğiniz başka bir oyuncu yok.\n"
                    "*(Unutmayın: Bir kullanıcı kendisine ilk yardım uygulayamaz!)*"
                )
                pm_text = f":pm {healer_roblox_name} Sunucuda ilk yardim uygulayabileceginiz baska oyuncu yok!"
                print(f"[İLK YARDIM BİLGİ] {healer_roblox_name} çevresinde başka oyuncu yok.", flush=True)
            else:
                en_yakin_str = f"**{hedef_oyuncu}** (`{round(mesafe, 1)} birim`)" if (hedef_oyuncu and mesafe is not None) else "Yok"
                dm_text = (
                    f"❌ **Yakınınızda İlk Yardım Uygulanacak Kimse Yok!**\n"
                    f"İlk yardım uygulamak için yaralı oyuncunun **en fazla 6 birim** yakınında durmalısınız.\n\n"
                    f"🧍 **En Yakın Oyuncu:** {en_yakin_str}\n"
                    f"📏 **Gereken Mesafe:** `Azami 6 birim`"
                )
                pm_hedef = f"En yakin: {hedef_oyuncu} ({round(mesafe, 1)}m)" if (hedef_oyuncu and mesafe is not None) else ""
                pm_text = f":pm {healer_roblox_name} 6 birim yakininizda kimse yok! {pm_hedef}".strip()
                print(f"[İLK YARDIM BİLGİ] {healer_roblox_name} için en yakın oyuncu {hedef_oyuncu} ({round(mesafe, 1) if mesafe else '?'}m > 6m).", flush=True)

            if interaction:
                return await interaction.response.send_message(dm_text, ephemeral=True)
            try:
                await member.send(dm_text)
            except Exception:
                pass
            if healer_roblox_name:
                asyncio.create_task(send_erlc_command(pm_text))
            return

        # 4. DM Kanalını Aç ve 3 Butonlu İlk Yardım Panelini Gönder
        try:
            dm_channel = member.dm_channel or await member.create_dm()
        except Exception:
            dm_channel = None

        if not dm_channel:
            err = "❌ Discord DM kanalınız açılamadı."
            if interaction:
                return await interaction.response.send_message(err, ephemeral=True)
            if healer_roblox_name:
                asyncio.create_task(send_erlc_command(f":pm {healer_roblox_name} Discord DM kanaliniz acilamadi!"))
            return

        self.aktif_ilkyardimlar.add(member.id)

        posta = healer_loc.get("postal", "-") if healer_loc else "-"
        sokak = healer_loc.get("street", "-") if healer_loc else "-"

        embed = discord.Embed(
            title="🚑 PİYADE RP • ACİL İLK YARDIM MÜDAHALE PANELİ",
            color=discord.Color.from_rgb(231, 76, 60),
            timestamp=datetime.now(tz_tr)
        )
        embed.description = (
            f"# 🩺 İlk Yardım Müdahalesi Başlatıldı!\n"
            f"──────────────────────────────────────────\n"
            f"🤕 **Müdahale Edilecek Kişi:** **{hedef_oyuncu}**\n"
            f"📏 **Mesafe:** `{round(mesafe, 1)} birim` *(Uygun ✅)*\n"
            f"📍 **Konum:** `Posta: {posta} | {sokak}`\n"
            f"──────────────────────────────────────────\n"
            f"### 📋 Butonların Açıklaması ve Kullanım Rehberi\n"
            f"Aşağıdaki **3 butondan** yaralının durumuna uygun olanı seçin. Butona bastığınızda **20 saniye** süreniz başlayacak ve **karışık sırada** gelen 3 aşama butonuna aşağıdaki **doğru sırayla** basmanız gerekecektir:\n\n"
            f"🩸 **1. Açık yara**\n"
            f"> Kanamalı ve kesik yaralanmalarında kullanılır.\n"
            f"> **Doğru Sıralama:** `Durumu kontrol et` ➔ `Yarayı temiz bez ile sar` ➔ `Stabilize et (Güvenceye Al)`\n\n"
            f"🦴 **2. Kemik kırığı**\n"
            f"> Kırık, çıkık ve ağır darbe durumlarında kullanılır.\n"
            f"> **Doğru Sıralama:** `Durumu kontrol et` ➔ `Kırık olan kısmı sabitle` ➔ `Kişiye Hastaneye gitmesi için yardımcı ol`\n\n"
            f"🩺 **3. Diğer Durumlar**\n"
            f"> Bayılma, şok ve genel travma durumlarında kullanılır.\n"
            f"> **Doğru Sıralama:** `Durumu kontrol et` ➔ `İlk Yardım uygula` ➔ `Stabilize et`\n"
            f"──────────────────────────────────────────\n"
            f"⚠️ **DİKKAT:** Buton sıralamasında hata yaparsanız veya **20 saniye** içinde tamamlamazsanız mesaj silinir ve ilk yardım başarısız olur!"
        )
        embed.set_footer(text="Piyade RP • Acil İlk Yardım Sistemi")

        view = IlkYardimSecimView(
            cog=self,
            member=member,
            healer_roblox=healer_roblox_name,
            hedef_roblox=hedef_oyuncu,
            mesafe=mesafe
        )

        try:
            await dm_channel.send(embed=embed, view=view)
            print(f"[İLK YARDIM BİLGİ] {healer_roblox_name} -> {hedef_oyuncu} ({round(mesafe, 1)}m) DM paneli başarıyla gönderildi.", flush=True)
            if interaction:
                await interaction.response.send_message(
                    f"✅ **{hedef_oyuncu}** için ilk yardım müdahale paneli Discord DM kutunuza gönderildi!",
                    ephemeral=True
                )
            else:
                asyncio.create_task(send_erlc_command(f":pm {healer_roblox_name} Ilk yardim paneli Discord DM kutunuza iletildi!"))
        except discord.Forbidden:
            self.aktif_ilkyardimlar.discard(member.id)
            err_msg = "❌ Discord DM kutunuz kapalı olduğu için ilk yardım paneli gönderilemedi! Lütfen DM'lerinizi açın."
            print(f"[İLK YARDIM HATA] {healer_roblox_name} ({member}) Discord DM kutusu kapalı!", flush=True)
            if interaction:
                await interaction.response.send_message(err_msg, ephemeral=True)
            else:
                asyncio.create_task(send_erlc_command(f":pm {healer_roblox_name} Discord DM kutunuz kapali! Lutfen DM ayarinizi acip tekrar deneyin."))

    async def baslat_asama_sureci(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        healer_roblox: str,
        hedef_roblox: str,
        tur_key: str
    ):
        tur_bilgi = MUDAHALE_TURLERI[tur_key]
        bitis_ts = int(time.time() + ILKYARDIM_SURESI)
        done_event = asyncio.Event()

        async def on_success(step_interaction: discord.Interaction):
            if done_event.is_set():
                return
            done_event.set()
            self.aktif_ilkyardimlar.discard(member.id)

            basari_embed = discord.Embed(
                title="✅ İLK YARDIM BAŞARIYLA UYGULANDI!",
                description=(
                    f"# 🚑 Yaralı Hayata Döndürüldü!\n"
                    f"──────────────────────────────────────────\n"
                    f"**{tur_bilgi['emoji']} {tur_bilgi['baslik']}** kapsamındaki 3 aşamayı da **20 saniye** dolmadan eksiksiz ve doğru sırayla tamamladınız!\n\n"
                    f"🤕 **İyileştirilen Oyuncu:** **{hedef_roblox}**\n"
                    f"💉 **Uygulanan Komut:** `:heal {hedef_roblox}`\n"
                    f"──────────────────────────────────────────"
                ),
                color=discord.Color.green(),
                timestamp=datetime.now(tz_tr)
            )
            basari_embed.set_footer(text="Piyade RP • Acil İlk Yardım Sistemi")

            try:
                await step_interaction.response.edit_message(content=None, embed=basari_embed, view=None)
            except Exception:
                pass

            # Oyun içinde ":heal [kullanıcı adı]" komutunu çalıştır
            print(f"[İLK YARDIM BAŞARILI] {healer_roblox} -> {hedef_roblox} iyileştirildi (:heal {hedef_roblox})", flush=True)
            await send_erlc_command(f":heal {hedef_roblox}")
            await send_erlc_command(f":pm {hedef_roblox} {healer_roblox} tarafindan ilk yardim ile iyilestirildiniz.")
            await send_erlc_command(f":pm {healer_roblox} Ilk yardim basarili! {hedef_roblox} iyilestirildi.")

        async def on_fail(step_interaction: Optional[discord.Interaction], sebep: str):
            if done_event.is_set():
                return
            done_event.set()
            self.aktif_ilkyardimlar.discard(member.id)

            print(f"[İLK YARDIM BAŞARISIZ] {healer_roblox} -> {hedef_roblox} başarısız oldu: {sebep}", flush=True)

            # Kural: "Eğer buton sıralaşında hata yaparsa veya süreye uymazsa mesaj silinsin ve işlemin başarısız olduğunu belirtsin."
            try:
                if step_interaction and step_interaction.message:
                    await step_interaction.message.delete()
                elif interaction.message:
                    await interaction.message.delete()
            except Exception:
                pass

            fail_embed = discord.Embed(
                title="❌ İLK YARDIM İŞLEMİ BAŞARISIZ OLDU!",
                description=(
                    f"**{hedef_roblox}** adlı oyuncuya uyguladığınız **{tur_bilgi['baslik']}** başarısız oldu ve iptal edildi!\n\n"
                    f"⚠️ **Sebep:** {sebep}"
                ),
                color=discord.Color.red(),
                timestamp=datetime.now(tz_tr)
            )
            fail_embed.set_footer(text="Piyade RP • Acil İlk Yardım Sistemi")

            try:
                dm_ch = member.dm_channel or await member.create_dm()
                await dm_ch.send(embed=fail_embed)
            except Exception:
                pass

            if healer_roblox:
                asyncio.create_task(send_erlc_command(f":pm {healer_roblox} Ilk yardim basarisiz oldu: Sure doldu veya hatali asama!"))

        asama_view = IlkYardimAsamaView(
            user_id=member.id,
            tur_key=tur_key,
            hedef_oyuncu=hedef_roblox,
            on_success=on_success,
            on_fail=on_fail
        )

        asama_embed = discord.Embed(
            title=f"{tur_bilgi['emoji']} {tur_bilgi['baslik'].upper()} (20 SANİYE)",
            description=(
                f"🤕 **Müdahale Edilen Kişi:** **{hedef_roblox}**\n"
                f"⏱️ **Kalan Süre:** <t:{bitis_ts}:R> *(20 Saniye)*\n"
                f"──────────────────────────────────────────\n"
                f"Aşağıdaki karışık dizilmiş **3 müdahale aşamasına** doğru sırayla basın!\n"
                f"⚠️ *Yanlış sırayla basarsanız veya 20 saniye içinde tamamlamazsanız mesaj silinir ve işlem başarısız olur.*"
            ),
            color=tur_bilgi["renk"],
            timestamp=datetime.now(tz_tr)
        )
        asama_embed.set_footer(text="Aşama 1/3 Bekleniyor • Piyade RP İlk Yardım")

        await interaction.response.edit_message(content=None, embed=asama_embed, view=asama_view)

        # Kesin 20 saniye zamanlayıcısı
        async def _timeout_watcher():
            await asyncio.sleep(ILKYARDIM_SURESI)
            if not done_event.is_set():
                asama_view.finished = True
                asama_view.stop()
                await on_fail(None, "20 saniyelik müdahale süresi doldu (Zaman aşımı).")

        asyncio.create_task(_timeout_watcher())

    # ── DISCORD SLASH KOMUTU (Discord üzerinden de kullanılabilir) ──
    @app_commands.command(name="ilkyardim", description="Oyun içinde en yakınınızdaki (6 birim) oyuncuya ilk yardım uygular.")
    async def cmd_ilkyardim(self, interaction: discord.Interaction):
        r_ad, r_id = discord_to_roblox(interaction.user.id, interaction.user.display_name)
        await self.execute_ilkyardim_flow(
            member=interaction.user,
            healer_roblox_name=r_ad or interaction.user.display_name,
            healer_roblox_id=r_id or "",
            cmd_arg="",
            interaction=interaction
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(IlkYardimSistemi(bot))
