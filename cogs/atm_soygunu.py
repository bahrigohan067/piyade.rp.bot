import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import json
import time
import random
import string
import asyncio
import aiohttp
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from config import GUILD_ID
from cogs.envanter_sistemi import (
    get_user_profile,
    update_user_profile,
    kullanici_atm_kontrol,
    format_usd,
    ekonomi_log_gonder,
    en_yakin_atm,
    get_atm_max_mesafe
)
from cogs.live_radar import roblox_to_discord
from cogs.rp_oylama import send_erlc_command

# ── SABİTLER VE AYARLAR ──
POLIS_BILDIRIM_KANAL_ID = 1561019123281039520
POLIS_ROL_ID = 1539318613498929193
COOLDOWN_SURESI = 600      # 10 dakika (600 saniye)
SOYGUN_ODULU = 1000        # $1.000 nakit
GEREKLI_ESYA = "RFID Disruptor"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, "data", "atm_soygun_data.json")
tz_tr = timezone(timedelta(hours=3))


def yukle_soygun_data() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[ATM SOYGUN HATA] Veri dosyası okunamadı: {e}", flush=True)
    return {"cooldowns": {}}


def kaydet_soygun_data(data: dict):
    try:
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        temp_file = f"{DATA_FILE}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_file, DATA_FILE)
    except Exception as e:
        print(f"[ATM SOYGUN HATA] Veri kaydedilemedi: {e}", flush=True)


# =====================================================================
# 1. AŞAMA VIEW (Sayı ve Harf Sıralaması)
# =====================================================================
class Step1View(discord.ui.View):
    def __init__(self, user_id: int, target_sequence: list[str], on_success, on_fail):
        super().__init__(timeout=30.0)
        self.user_id = user_id
        self.target_sequence = target_sequence
        self.current_idx = 0
        self.on_success = on_success
        self.on_fail = on_fail
        self.finished = False

        shuffled = target_sequence.copy()
        random.shuffle(shuffled)

        for i, char in enumerate(shuffled):
            row = 0 if i < 3 else 1
            btn = discord.ui.Button(
                label=char,
                style=discord.ButtonStyle.secondary,
                row=row,
                custom_id=f"step1_{char}_{i}_{random.randint(100, 999)}"
            )
            btn.callback = self.make_callback(char, btn)
            self.add_item(btn)

    def make_callback(self, char: str, button: discord.ui.Button):
        async def button_callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("❌ Bu oturum size ait değil.", ephemeral=True)
            if self.finished:
                return

            expected = self.target_sequence[self.current_idx]
            if char == expected:
                self.current_idx += 1
                button.disabled = True
                button.style = discord.ButtonStyle.success

                if self.current_idx >= len(self.target_sequence):
                    self.finished = True
                    self.stop()
                    await interaction.response.edit_message(content="✅ **1. Aşama Başarılı! 2. Aşamaya geçiliyor...**", view=self)
                    await asyncio.sleep(1)
                    await self.on_success()
                else:
                    progress_parts = [f"`[{c}]`" for c in self.target_sequence[:self.current_idx]]
                    progress_parts += [f"`[  ]`" for _ in range(len(self.target_sequence) - self.current_idx)]
                    progress_str = " ".join(progress_parts)
                    await interaction.response.edit_message(
                        content=f"# 🔐 AŞAMA 1: ŞİFRE HAFIZASI\n### 🎯 Sırasıyla Aklında Tuttuğun Karakterlere Bas!\nİlerleme: {progress_str}",
                        view=self
                    )
            else:
                self.finished = True
                self.stop()
                button.style = discord.ButtonStyle.danger
                for item in self.children:
                    item.disabled = True
                await interaction.response.edit_message(content="❌ **Hatalı tuşlama! Şifre kilitlendi!**", view=self)
                await self.on_fail("1. Aşamada (Karakter Sıralaması) hatalı tuşlama yapıldı.")
        return button_callback

    async def on_timeout(self):
        if not self.finished:
            self.finished = True
            await self.on_fail("1. Aşamada süre doldu (Zaman aşımı).")


# =====================================================================
# 2. AŞAMA VIEW (Renk Stroop Testi)
# =====================================================================
class Step2View(discord.ui.View):
    def __init__(self, user_id: int, correct_color_name: str, options: list[dict], on_success, on_fail):
        super().__init__(timeout=20.0)
        self.user_id = user_id
        self.correct_color_name = correct_color_name
        self.on_success = on_success
        self.on_fail = on_fail
        self.finished = False

        for i, opt in enumerate(options):
            btn = discord.ui.Button(
                label=opt["name"],
                emoji=opt["emoji"],
                style=discord.ButtonStyle.secondary,
                row=0 if i < 2 else 1,
                custom_id=f"step2_{opt['name']}_{i}_{random.randint(100, 999)}"
            )
            btn.callback = self.make_callback(opt["name"], btn)
            self.add_item(btn)

    def make_callback(self, color_name: str, button: discord.ui.Button):
        async def button_callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("❌ Bu oturum size ait değil.", ephemeral=True)
            if self.finished:
                return

            self.finished = True
            self.stop()
            for item in self.children:
                item.disabled = True

            if color_name == self.correct_color_name:
                button.style = discord.ButtonStyle.success
                await interaction.response.edit_message(content="✅ **2. Aşama Başarılı! 3. Aşamaya geçiliyor...**", view=self)
                await asyncio.sleep(1)
                await self.on_success()
            else:
                button.style = discord.ButtonStyle.danger
                await interaction.response.edit_message(content=f"❌ **Hatalı renk seçimi!** Ekranda yazan renk: `{self.correct_color_name}` idi.", view=self)
                await self.on_fail("2. Aşamada (Renk Seçimi) yanlış renk seçildi.")
        return button_callback

    async def on_timeout(self):
        if not self.finished:
            self.finished = True
            await self.on_fail("2. Aşamada süre doldu (Zaman aşımı).")


# =====================================================================
# 3. AŞAMA VIEW (Şekil Sıralaması)
# =====================================================================
class Step3View(discord.ui.View):
    def __init__(self, user_id: int, target_sequence: list[str], on_success, on_fail):
        super().__init__(timeout=25.0)
        self.user_id = user_id
        self.target_sequence = target_sequence
        self.current_idx = 0
        self.on_success = on_success
        self.on_fail = on_fail
        self.finished = False

        shuffled = target_sequence.copy()
        random.shuffle(shuffled)

        for i, sym in enumerate(shuffled):
            btn = discord.ui.Button(
                emoji=sym,
                style=discord.ButtonStyle.secondary,
                row=0,
                custom_id=f"step3_{i}_{random.randint(100, 999)}"
            )
            btn.callback = self.make_callback(sym, btn)
            self.add_item(btn)

    def make_callback(self, sym: str, button: discord.ui.Button):
        async def button_callback(interaction: discord.Interaction):
            if interaction.user.id != self.user_id:
                return await interaction.response.send_message("❌ Bu oturum size ait değil.", ephemeral=True)
            if self.finished:
                return

            expected = self.target_sequence[self.current_idx]
            if sym == expected:
                self.current_idx += 1
                button.disabled = True
                button.style = discord.ButtonStyle.success

                if self.current_idx >= len(self.target_sequence):
                    self.finished = True
                    self.stop()
                    await interaction.response.edit_message(content="🎉 **Tüm Aşamalar Başarılı! Para bölmesi açılıyor...**", view=self)
                    await asyncio.sleep(1)
                    await self.on_success()
                else:
                    progress_parts = [f"`[ {s} ]`" for s in self.target_sequence[:self.current_idx]]
                    progress_parts += [f"`[   ]`" for _ in range(len(self.target_sequence) - self.current_idx)]
                    progress_str = " ".join(progress_parts)
                    await interaction.response.edit_message(
                        content=f"# ⚡ AŞAMA 3: DONANIM KİLİDİ\n### 🎯 Sırasıyla Aklında Tuttuğun Şekillere Bas!\nİlerleme: {progress_str}",
                        view=self
                    )
            else:
                self.finished = True
                self.stop()
                button.style = discord.ButtonStyle.danger
                for item in self.children:
                    item.disabled = True
                await interaction.response.edit_message(content="❌ **Hatalı şekil sıralaması! Güvenlik kilidi kapandı!**", view=self)
                await self.on_fail("3. Aşamada (Şekil Sıralaması) hatalı tuşlama yapıldı.")
        return button_callback

    async def on_timeout(self):
        if not self.finished:
            self.finished = True
            await self.on_fail("3. Aşamada süre doldu (Zaman aşımı).")


# =====================================================================
# BAŞLATMA BUTONU VIEW
# =====================================================================
class ATMBaslatView(discord.ui.View):
    def __init__(self, user_id: int, on_start):
        super().__init__(timeout=120.0)
        self.user_id = user_id
        self.on_start = on_start
        self.clicked = False

    @discord.ui.button(label="ATM'yi Soy", emoji="🔓", style=discord.ButtonStyle.danger, custom_id="btn_atm_soy_baslat")
    async def btn_baslat(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Bu buton size ait değil.", ephemeral=True)
        if self.clicked:
            return
        self.clicked = True
        self.stop()
        button.disabled = True
        await interaction.response.edit_message(content="🔄 **Bypass Protokolü Başlatılıyor... Kilitler Hazırlanıyor...**", embed=None, view=None)
        await self.on_start()


# =====================================================================
# ATM SOYGUNU COG
# =====================================================================
class ATMSoygunu(commands.Cog):
    """Roblox ER:LC ;atmsoy komutu ve 3 aşamalı kilit kırma soygun sistemi."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data = yukle_soygun_data()
        self.cooldowns: dict = self.data.get("cooldowns", {})
        self.islenen_komutlar: set = set()
        self.aktif_soygunlar: set = set()
        self._session: Optional[aiohttp.ClientSession] = None
        self.bot_baslangic_zamani = time.time()
        self.arkaplan_komut_loop.start()

    def cog_unload(self):
        self.arkaplan_komut_loop.cancel()
        if self._session and not self._session.closed:
            asyncio.create_task(self._session.close())

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def save_data(self):
        self.data["cooldowns"] = self.cooldowns
        kaydet_soygun_data(self.data)

    # ── ER:LC KOMUT LOGU DÖNGÜSÜ (Periyodik API Polling) ──
    @tasks.loop(seconds=3)
    async def arkaplan_komut_loop(self):
        """
        ER:LC API'sinden komut kayıtlarını (commandlogs) düzenli olarak çeker.
        Oyuncuların oyun içi sohbete yazdığı ;atmsoy komutunu algılar.
        """
        if not self.bot.is_ready():
            return

        api_key = os.getenv("ERLC_API_KEY", "").strip("'\" \r\n\t")
        if not api_key:
            return

        session = await self.get_session()
        headers = {'Server-Key': api_key}
        urls = [
            'https://api.erlc.gg/v2/server/commandlogs',
            'https://api.erlc.gg/v1/server/commandlogs'
        ]

        command_logs = None
        for url in urls:
            try:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                            if isinstance(data, list):
                                command_logs = data
                                break
                        except Exception:
                            continue
                    elif resp.status == 429:
                        return
            except Exception:
                continue

        if not command_logs or not isinstance(command_logs, list):
            return

        for log in command_logs:
            cmd = str(log.get("Command") or log.get("command") or "").strip().lower()
            if any(t in cmd for t in [";atmsoy", ";atm-soy", ";atm soy", ":atmsoy", ":atm-soy"]):
                await self.handle_atmsoy_command(log)

    @arkaplan_komut_loop.before_loop
    async def before_arkaplan_komut_loop(self):
        await self.bot.wait_until_ready()

    # ── ER:LC KOMUT LOGU DİNLEYİCİSİ (Dış event çağrıları için) ──
    @commands.Cog.listener("on_erlc_command_logs")
    async def on_erlc_command_logs(self, command_logs: list):
        if not command_logs:
            return

        for log in command_logs:
            cmd = str(log.get("Command") or log.get("command") or "").strip().lower()
            if any(t in cmd for t in [";atmsoy", ";atm-soy", ";atm soy", ":atmsoy", ":atm-soy"]):
                await self.handle_atmsoy_command(log)

    # ── FALLBACK & ANLIK: WEBHOOK KANALI DİNLEYİCİSİ ──
    @commands.Cog.listener("on_message")
    async def on_message(self, message: discord.Message):
        if not (message.author.bot or message.webhook_id):
            return

        # 1. Embed'leri kontrol et (ER:LC Command Webhook genellikle Embed gönderir)
        for embed in message.embeds:
            cmd_val = ""
            player_val = ""
            user_id_val = ""

            for field in embed.fields:
                fn = (field.name or "").strip().lower()
                fv = (field.value or "").strip()
                if any(k in fn for k in ["command", "komut"]):
                    cmd_val = fv
                elif any(k in fn for k in ["player", "oyuncu", "executor", "yetkili", "kullanıcı"]):
                    player_val = fv
                elif any(k in fn for k in ["user id", "userid", "roblox id", "roblox_id"]):
                    user_id_val = fv

            combined_text = f"{message.content or ''} {embed.title or ''} {embed.description or ''} {cmd_val}".lower()
            if any(trig in combined_text for trig in [";atmsoy", ";atm-soy", ";atm soy", ":atmsoy", ":atm-soy"]):
                if not player_val:
                    desc = embed.description or message.content or ""
                    m_p = re.search(r"(?:Player|Oyuncu|Executor)[:\s*]+([A-Za-z0-9_]+)", desc, re.IGNORECASE)
                    if m_p:
                        player_val = m_p.group(1)

                if player_val:
                    if "[" in player_val and "]" in player_val:
                        player_val = player_val.split("[")[1].split("]")[0]
                    if "(" in player_val:
                        player_val = player_val.split("(")[0].strip()
                    if ":" in player_val and not user_id_val:
                        parts = player_val.split(":", 1)
                        player_val = parts[0].strip()
                        user_id_val = parts[1].strip()

                    log_payload = {
                        "Player": f"{player_val}:{user_id_val}" if user_id_val else player_val,
                        "Command": ";atmsoy",
                        "Timestamp": int(time.time())
                    }
                    print(f"[ATM SOYGUN WEBHOOK] Webhook'tan ;atmsoy yakalandı! Oyuncu: {player_val}", flush=True)
                    await self.handle_atmsoy_command(log_payload)
                    return

        # 2. Embedsiz düz metin kontrolü
        content_lower = (message.content or "").lower()
        if any(trig in content_lower for trig in [";atmsoy", ";atm-soy", ";atm soy", ":atmsoy", ":atm-soy"]):
            m_p = re.search(r"(?:player|oyuncu|kullanıcı)[:\s*]+([A-Za-z0-9_]+)", message.content, re.IGNORECASE)
            if m_p:
                p_name = m_p.group(1)
                log_payload = {
                    "Player": p_name,
                    "Command": ";atmsoy",
                    "Timestamp": int(time.time())
                }
                print(f"[ATM SOYGUN DÜZ METİN] Webhook metninden ;atmsoy yakalandı! Oyuncu: {p_name}", flush=True)
                await self.handle_atmsoy_command(log_payload)

    async def handle_atmsoy_command(self, log: dict):
        player_raw = str(log.get("Player") or log.get("player") or log.get("executor") or log.get("Executor") or "").strip()
        timestamp = log.get("Timestamp") or log.get("timestamp") or 0
        command_str = str(log.get("Command") or log.get("command") or "").strip()

        # Eski komutları filtrele (Bot başlangıcından önceki veya 90 saniyeden eski loglar)
        try:
            ts_float = float(timestamp)
            if ts_float > 1000000000:
                if time.time() - ts_float > 90:
                    return
                if ts_float < (self.bot_baslangic_zamani - 10):
                    return
        except (ValueError, TypeError):
            pass

        log_key = f"{player_raw}_{command_str}_{timestamp}"
        if log_key in self.islenen_komutlar:
            return
        self.islenen_komutlar.add(log_key)
        if len(self.islenen_komutlar) > 2000:
            self.islenen_komutlar.clear()

        roblox_name = player_raw
        roblox_id = ""

        if "[" in roblox_name and "]" in roblox_name:
            roblox_name = roblox_name.split("[")[1].split("]")[0]
        if "(" in roblox_name:
            roblox_name = roblox_name.split("(")[0].strip()
        if ":" in roblox_name:
            parts = roblox_name.split(":", 1)
            roblox_name = parts[0].strip()
            roblox_id = parts[1].strip()

        guild = self.bot.get_guild(GUILD_ID)
        if not guild:
            return

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
                if (r_lower == m.display_name.lower() or 
                    r_lower in m.display_name.lower() or 
                    r_lower == m.name.lower() or 
                    r_lower in m.name.lower() or 
                    (m.nick and r_lower in m.nick.lower())):
                    member = m
                    break

            if not member:
                try:
                    queried = await guild.query_members(query=roblox_name, limit=5)
                    for qm in queried:
                        if (r_lower == qm.display_name.lower() or 
                            r_lower in qm.display_name.lower() or 
                            r_lower == qm.name.lower() or 
                            r_lower in qm.name.lower()):
                            member = qm
                            break
                except Exception as e:
                    print(f"[ATM SOYGUN] query_members hatası: {e}", flush=True)

        if not member:
            print(f"[ATM SOYGUN] '{roblox_name}' için Discord eşleşmesi bulunamadı.", flush=True)
            await send_erlc_command(f":pm {roblox_name} Discord hesabinizi Piyade RP ile eslestirmelisiniz!")
            return

        print(f"[ATM SOYGUN] {roblox_name} (Discord: {member.display_name} - {member.id}) için soygun tetiklendi.", flush=True)
        await self.execute_atmsoy_flow(member, roblox_name)

    async def execute_atmsoy_flow(self, member: discord.Member, roblox_name: str, interaction: Optional[discord.Interaction] = None):
        # 1. Aktif Soygun Oturumu Kontrolü
        if member.id in self.aktif_soygunlar:
            msg = "⚠️ **Zaten devam eden aktif bir ATM kilit kırma işleminiz bulunuyor!** Lütfen Discord DM kutunuzu kontrol edin."
            if interaction:
                return await interaction.response.send_message(msg, ephemeral=True)
            else:
                try:
                    await member.send(msg)
                except Exception:
                    pass
            return

        # 2. Canlı Radar ve ATM Yakınlık Kontrolü (Azami 6 metre)
        uygun, durum, en_yakin_atm, mesafe, p_loc = kullanici_atm_kontrol(self.bot, member)

        # Eğer kullanici_atm_kontrol Discord adından roblox konumunu bulamazsa doğrudan roblox_name ile kontrol et
        if (not uygun or not en_yakin_atm) and roblox_name:
            radar_cog = self.bot.get_cog("LiveRadar")
            if radar_cog:
                aktif_oyuncular = getattr(radar_cog, "aktif_oyuncular", {}) or {}
                p_loc_direct = None
                for p_name, loc in aktif_oyuncular.items():
                    if p_name.lower() == roblox_name.lower():
                        p_loc_direct = loc
                        break
                if p_loc_direct:
                    px = p_loc_direct.get("x")
                    pz = p_loc_direct.get("z")
                    if isinstance(px, (int, float)) and isinstance(pz, (int, float)):
                        max_mesafe = get_atm_max_mesafe()
                        en_yakin, d = en_yakin_atm(px, pz)
                        if en_yakin:
                            en_yakin_atm = en_yakin
                            mesafe = d
                            p_loc = p_loc_direct
                            if d <= max_mesafe:
                                uygun = True
        if not uygun or not en_yakin_atm:
            en_yakin_isim = en_yakin_atm['name'] if en_yakin_atm else "Bilinmiyor"
            mesafe_str = f"{round(mesafe, 1)} metre" if mesafe is not None else "Bilinmiyor"

            await send_erlc_command(f":pm {roblox_name} Bir ATM cihazinin yaninda degilsiniz!")

            dm_text = (
                f"❌ **Bir ATM Cihazının Yanında Değilsiniz!**\n"
                f"ATM soymak için ER:LC oyununda bir ATM cihazının hemen yanında (azami 6 metre) durmalısınız.\n\n"
                f"📍 **En Yakın ATM:** **{en_yakin_isim}**\n"
                f"📏 **Mevcut Mesafeniz:** `{mesafe_str}` *(İzin verilen: 6 metre)*"
            )
            if interaction:
                return await interaction.response.send_message(dm_text, ephemeral=True)
            else:
                try:
                    await member.send(dm_text)
                except Exception:
                    pass
            return

        # 3. 10 Dakika Bekleme Süresi (Cooldown) Kontrolü
        now = time.time()
        son_soygun = self.cooldowns.get(str(member.id), 0)
        if now - son_soygun < COOLDOWN_SURESI:
            kalan = int(COOLDOWN_SURESI - (now - son_soygun))
            dakika = kalan // 60
            saniye = kalan % 60

            await send_erlc_command(f":pm {roblox_name} Tekrar ATM soymak icin {dakika} dk {saniye} sn beklemelisiniz!")

            dm_text = (
                f"⏳ **ATM Soygunu Bekleme Süresi Aktif!**\n"
                f"Son yaptığınız ATM soygununun üzerinden henüz 10 dakika geçmedi.\n\n"
                f"⏱️ **Kalan Süre:** `{dakika} dakika {saniye} saniye` sonra tekrar soyabilirsiniz."
            )
            if interaction:
                return await interaction.response.send_message(dm_text, ephemeral=True)
            else:
                try:
                    await member.send(dm_text)
                except Exception:
                    pass
            return

        # 4. RFID Disruptor Eşya Kontrolü
        profile = get_user_profile(member.id)
        inv = profile.get("inventory", {})
        has_rfid = any(item.strip().lower() == GEREKLI_ESYA.lower() and count > 0 for item, count in inv.items())
        if not has_rfid:
            # Oyun içine sadece kişiye özel mesaj gönder (:pm)
            await send_erlc_command(f":pm {roblox_name} RFID Disruptor olmadan ATM soyamazsin!")

            dm_text = (
                f"❌ **Gerekli Ekipman Eksik: {GEREKLI_ESYA}**\n"
                f"ATM'nin elektronik kilit sistemini ve banka alarm sinyalini kesmek için envanterinizde **`{GEREKLI_ESYA}`** bulunmalıdır.\n\n"
                f"İllegal pazardan bir RFID Disruptor temin ettikten sonra tekrar deneyiniz."
            )
            if interaction:
                return await interaction.response.send_message(dm_text, ephemeral=True)
            else:
                try:
                    await member.send(dm_text)
                except Exception:
                    pass
            return

        # 5. Tüm Kontroller Başarılı: Discord DM Paneli Gönder
        try:
            dm_channel = member.dm_channel or await member.create_dm()
        except Exception:
            dm_channel = None

        if not dm_channel:
            err = "❌ Discord DM kanalınız açılamadı."
            if interaction:
                return await interaction.response.send_message(err, ephemeral=True)
            return

        embed = discord.Embed(
            title="🏧 PACIFIC BANK • ATM SOYGUN PROTOKOLÜ",
            color=discord.Color.from_rgb(46, 204, 113),
            timestamp=datetime.now(tz_tr)
        )
        embed.description = (
            f"# 🔓 ATM Terminaline Bağlantı Sağlandı!\n"
            f"──────────────────────────────────────────\n"
            f"🎯 **Hedeflenen ATM:** **{en_yakin_atm['name']}**\n"
            f"📮 **Posta Kodu:** `{en_yakin_atm.get('postal', '-')}`\n"
            f"🛣️ **Bölge:** `{en_yakin_atm.get('street', '-')}`\n"
            f"📡 **Ekipman:** `{GEREKLI_ESYA}` (Bypass Cihazı Devrede ✅)\n"
            f"──────────────────────────────────────────\n"
            f"Aşağıdaki **ATM'yi Soy** butonuna bastığınızda **3 aşamalı kilit kırma** süreci başlayacaktır:\n\n"
            f"1️⃣ **1. Aşama (6 Saniye):** Sayı ve harfleri aklında tut, ardından sırasıyla butonlara bas!\n"
            f"2️⃣ **2. Aşama (3 Saniye):** Ekranda yazan rengi aklında tut ve doğru rengi seç!\n"
            f"3️⃣ **3. Aşama (6 Saniye):** Özel şekilleri sırasıyla aklında tut ve doğru dizilimle bas!\n\n"
            f"⚠️ **DİKKAT:** Herhangi bir aşamada hata yaparsanız soygun anında iptal edilir ve **Polis Departmanı**'na ihbar sinyali iletilir!\n"
            f"──────────────────────────────────────────"
        )
        embed.set_footer(text="Piyade RP • İllegal Kazanç & ATM Hack Sistemi")

        async def on_start():
            await self.start_minigame(member, en_yakin_atm, roblox_name)

        view = ATMBaslatView(member.id, on_start)

        try:
            await dm_channel.send(embed=embed, view=view)
            if interaction:
                await interaction.response.send_message("✅ **ATM kilit kırma paneli Discord DM kutunuza gönderildi!**", ephemeral=True)
            else:
                await send_erlc_command(f":pm {roblox_name} ATM Kilit Kirma Paneli Discord DM kutunuza gonderildi!")
        except discord.Forbidden:
            err_msg = "❌ Discord DM kutunuz kapalı olduğu için soygun paneli gönderilemedi! Lütfen gizlilik ayarlarından sunucu üyelerinden gelen DM'leri açın."
            if interaction:
                await interaction.response.send_message(err_msg, ephemeral=True)
            else:
                await send_erlc_command(f":pm {roblox_name} Discord DM kutunuz kapali! Lutfen DM'leri acin.")

    # =====================================================================
    # 3 AŞAMALI KİLİT KIRMA MİNİ OYUNU
    # =====================================================================
    async def start_minigame(self, member: discord.Member, atm_info: dict, roblox_name: str = ""):
        if member.id in self.aktif_soygunlar:
            return
        self.aktif_soygunlar.add(member.id)

        try:
            dm_channel = member.dm_channel or await member.create_dm()

            # ─────────────────────────────────────────────────────────────
            # 1. AŞAMA: SAYI VE HARFLERİ AKLINDA TUT (6 Saniye)
            # ─────────────────────────────────────────────────────────────
            char_pool = [c for c in string.ascii_uppercase + string.digits if c not in "0OI1"]
            seq1 = random.sample(char_pool, 6)

            embed1 = discord.Embed(
                title="🔐 1. AŞAMA: SAYILARI VE HARFLERİ AKLINDA TUT!",
                color=discord.Color.blue(),
                timestamp=datetime.now(tz_tr)
            )
            embed1.description = (
                "### ⏱️ Bu karakterler 6 saniye sonra gizlenecektir!\n\n"
                "# " + "  ".join([f"`[ {c} ]`" for c in seq1]) + "\n\n"
                "⚠️ **Dizilişi soldan sağa dikkatlice aklında tut!**\n"
                "*6 saniye sonra butonlar açılacak ve sırasıyla doğru basman gerekecek.*"
            )
            embed1.set_footer(text="Aşama 1/3 • Şifre Hafızası")
            step1_msg = await dm_channel.send(embed=embed1)
            await asyncio.sleep(6)

            step1_passed = asyncio.Event()
            step1_failed = asyncio.Event()
            fail_reason = [""]

            async def on_s1_success():
                step1_passed.set()

            async def on_s1_fail(reason: str):
                fail_reason[0] = reason
                step1_failed.set()

            v1 = Step1View(member.id, seq1, on_s1_success, on_s1_fail)
            progress_str = " ".join(["`[  ]`" for _ in range(6)])
            await step1_msg.edit(
                content=f"# 🔐 AŞAMA 1: ŞİFRE HAFIZASI\n### 🎯 Sırasıyla Aklında Tuttuğun Karakterlere Bas!\nİlerleme: {progress_str}",
                embed=None,
                view=v1
            )

            done, pending = await asyncio.wait([
                asyncio.create_task(step1_passed.wait()),
                asyncio.create_task(step1_failed.wait())
            ], return_when=asyncio.FIRST_COMPLETED)

            for task in pending:
                task.cancel()

            if step1_failed.is_set():
                await self.trigger_police_alert(atm_info, fail_reason[0])
                return

            # 1. aşamadaki mesaj silinip 2. aşama mesajı gelecek
            try:
                await step1_msg.delete()
            except Exception:
                pass

            # ─────────────────────────────────────────────────────────────
            # 2. AŞAMA: RENGİ AKLINDA TUT (Stroop Renk Testi - 3 Saniye)
            # ─────────────────────────────────────────────────────────────
            colors_list = [
                {"name": "Kırmızı", "emoji": "🔴"},
                {"name": "Mavi", "emoji": "🔵"},
                {"name": "Yeşil", "emoji": "🟢"},
                {"name": "Sarı", "emoji": "🟡"},
                {"name": "Turuncu", "emoji": "🟠"},
                {"name": "Mor", "emoji": "🟣"},
                {"name": "Beyaz", "emoji": "⚪"},
                {"name": "Siyah", "emoji": "⚫"}
            ]
            target_color = random.choice(colors_list)
            distractor = random.choice([c for c in colors_list if c["name"] != target_color["name"]])

            embed2 = discord.Embed(
                title="🎨 2. AŞAMA: RENGİ AKLINDA TUT!",
                color=discord.Color.gold(),
                timestamp=datetime.now(tz_tr)
            )
            embed2.description = (
                "### ⏱️ Bu yazı 3 saniye sonra gizlenecektir!\n\n"
                f"# [ {distractor['emoji']} **{target_color['name']}** ]\n\n"
                "⚠️ **DİKKAT:** Emojinin rengini DEĞİL, **yazan rengi** oku ve aklında tut!\n"
                "*3 saniye sonra seçenek butonları gelecektir.*"
            )
            embed2.set_footer(text="Aşama 2/3 • Renk Algısı")
            step2_msg = await dm_channel.send(embed=embed2)
            await asyncio.sleep(3)

            step2_passed = asyncio.Event()
            step2_failed = asyncio.Event()

            async def on_s2_success():
                step2_passed.set()

            async def on_s2_fail(reason: str):
                fail_reason[0] = reason
                step2_failed.set()

            other_colors = [c for c in colors_list if c["name"] not in (target_color["name"], distractor["name"])]
            selected_others = random.sample(other_colors, 2)
            s2_options = [target_color, distractor] + selected_others
            random.shuffle(s2_options)

            v2 = Step2View(member.id, target_color["name"], s2_options, on_s2_success, on_s2_fail)
            await step2_msg.edit(
                content="# 🎨 AŞAMA 2: RENK ALGISI\n### 🎯 Ekranda YAZAN Renk Hangisiydi?",
                embed=None,
                view=v2
            )

            done, pending = await asyncio.wait([
                asyncio.create_task(step2_passed.wait()),
                asyncio.create_task(step2_failed.wait())
            ], return_when=asyncio.FIRST_COMPLETED)

            for task in pending:
                task.cancel()

            if step2_failed.is_set():
                await self.trigger_police_alert(atm_info, fail_reason[0])
                return

            # 2. aşamadaki mesaj silinip 3. aşama mesajı gelecek
            try:
                await step2_msg.delete()
            except Exception:
                pass

            # ─────────────────────────────────────────────────────────────
            # 3. AŞAMA: ŞEKİLLERİ AKLINDA TUT (6 Saniye)
            # ─────────────────────────────────────────────────────────────
            symbols_pool = ["⚡", "💡", "📡", "🔐", "🔩", "🔌", "⌨️"]
            seq3 = random.sample(symbols_pool, 4)

            embed3 = discord.Embed(
                title="⚡ 3. AŞAMA: ŞEKİLLERİ AKLINDA TUT!",
                color=discord.Color.purple(),
                timestamp=datetime.now(tz_tr)
            )
            embed3.description = (
                "### ⏱️ Bu şekiller 6 saniye sonra gizlenecektir!\n\n"
                "# " + "  ".join([f"`[ {s} ]`" for s in seq3]) + "\n\n"
                "⚠️ **Şekillerin sırasını dikkatlice aklında tut!**\n"
                "*6 saniye sonra butonlar açılacak ve sırayla basman gerekecek.*"
            )
            embed3.set_footer(text="Aşama 3/3 • Donanım Kilidi")
            step3_msg = await dm_channel.send(embed=embed3)
            await asyncio.sleep(6)

            step3_passed = asyncio.Event()
            step3_failed = asyncio.Event()

            async def on_s3_success():
                step3_passed.set()

            async def on_s3_fail(reason: str):
                fail_reason[0] = reason
                step3_failed.set()

            v3 = Step3View(member.id, seq3, on_s3_success, on_s3_fail)
            progress_str3 = " ".join(["`[   ]`" for _ in range(4)])
            await step3_msg.edit(
                content=f"# ⚡ AŞAMA 3: DONANIM KİLİDİ\n### 🎯 Sırasıyla Aklında Tuttuğun Şekillere Bas!\nİlerleme: {progress_str3}",
                embed=None,
                view=v3
            )

            done, pending = await asyncio.wait([
                asyncio.create_task(step3_passed.wait()),
                asyncio.create_task(step3_failed.wait())
            ], return_when=asyncio.FIRST_COMPLETED)

            for task in pending:
                task.cancel()

            if step3_failed.is_set():
                await self.trigger_police_alert(atm_info, fail_reason[0])
                return

            try:
                await step3_msg.delete()
            except Exception:
                pass

            # ─────────────────────────────────────────────────────────────
            # BAŞARILI SONUÇ
            # ─────────────────────────────────────────────────────────────
            await self.process_success(member, atm_info, roblox_name)

        except Exception as e:
            print(f"[ATM SOYGUN HATA] Soygun akışında beklenmeyen hata: {e}", flush=True)
        finally:
            self.aktif_soygunlar.discard(member.id)

    # ── POLİS BİLDİRİMİ (Hatalı İşlemde Tetiklenir) ──
    async def trigger_police_alert(self, atm_info: dict, reason: str = ""):
        guild = self.bot.get_guild(GUILD_ID)
        if not guild:
            return

        channel = guild.get_channel(POLIS_BILDIRIM_KANAL_ID)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(POLIS_BILDIRIM_KANAL_ID)
            except Exception as e:
                print(f"[ATM SOYGUN POLİS ALARM] Kanal ({POLIS_BILDIRIM_KANAL_ID}) bulunamadı: {e}", flush=True)
                return

        embed = discord.Embed(
            title="🚨 911 İHBARI | ATM SİNYAL KESİNTİSİ & SOYGUN GİRİŞİMİ",
            color=discord.Color.red(),
            timestamp=datetime.now(tz_tr)
        )
        embed.description = (
            "# ⚠️ GÜVENLİK ALARMI TETİKLENDİ!\n"
            "Pacific Bank Güvenlik Merkezi, aşağıdaki ATM terminalinde yetkisiz bir **elektronik bypass / kilit kırma (RFID)** girişimi saptadı!\n\n"
            "Şüpheli şahıs güvenlik kilitlerini kırmaya çalışırken şifre korumasını tetikledi ve sistem kendini kapattı. "
            "Şüpheli olay yerinden uzaklaşıyor olabilir!"
        )
        embed.add_field(name="🏧 Hedeflenen ATM", value=f"**{atm_info.get('name', 'Bilinmeyen ATM')}**", inline=True)
        embed.add_field(name="📮 Posta Kodu", value=f"`{atm_info.get('postal', '-')}`", inline=True)
        embed.add_field(name="📍 GPS Koordinatları", value=f"`X: {atm_info.get('x', '-')} | Z: {atm_info.get('z', '-')}`", inline=True)
        embed.add_field(name="🛣️ Cadde / Konum Detayı", value=f"`{atm_info.get('street', '-')} ({atm_info.get('detay', '-')})`", inline=False)
        embed.add_field(name="👤 Şüpheli Kimliği", value="*Bilinmiyor (Fail Meçhul / Yapan kişi tespit edilemedi)*", inline=False)
        embed.add_field(name="📻 Devriye Talimatı", value="En yakın kolluk kuvveti birimleri ivedilikle belirtilen konuma intikal etsin ve çevredeki şüphelileri kontrol etsin!", inline=False)
        embed.set_footer(text="Pacific Bank Güvenlik İzleme Birimi • 911 Dispatch")

        try:
            await channel.send(content=f"<@&{POLIS_ROL_ID}>", embed=embed)
            print(f"[ATM SOYGUN POLİS ALARM] Polis ihbarı başarıyla iletildi: {atm_info.get('name')}", flush=True)
        except Exception as e:
            print(f"[ATM SOYGUN POLİS ALARM HATA] İhbar gönderilemedi: {e}", flush=True)

    # ── BAŞARILI SOYGUN ÖDÜL VE COOLDOWN İŞLEMİ ──
    async def process_success(self, member: discord.Member, atm_info: dict, roblox_name: str = ""):
        # 1. 10 Dakika Cooldown Kaydet
        self.cooldowns[str(member.id)] = time.time()
        self.save_data()

        # 2. $1.000 Nakit Ekle
        profile = get_user_profile(member.id)
        eski_nakit = profile.get("cash", 0)
        profile["cash"] = eski_nakit + SOYGUN_ODULU
        update_user_profile(member.id, profile)

        # 3. Kullanıcıya DM ile Başarı Embedi Gönder
        embed = discord.Embed(
            title="🎉 ATM SOYGUNU BAŞARIYLA TAMAMLANDI!",
            color=discord.Color.green(),
            timestamp=datetime.now(tz_tr)
        )
        embed.description = (
            f"# 💰 $1.000 NAKİT PARA ELE GEÇİRİLDİ!\n"
            f"──────────────────────────────────────────\n"
            f"**{atm_info.get('name')}** cihazının tüm elektronik güvenlik katmanlarını başarıyla devre dışı bıraktın ve para haznesini boşalttın!\n\n"
            f"💵 **Cebinize Eklenen:** `+$1.000 Nakit` (Yeni Bakiye: **{format_usd(profile['cash'])}**)\n"
            f"⏱️ **Bekleme Süresi:** Sistem kendini korumaya aldı. **10 dakika** boyunca başka bir ATM soyamazsınız.\n"
            f"──────────────────────────────────────────\n"
            f"⚠️ *Polis ekipleri sinyal kopukluğunu fark etmeden derhal bölgeden uzaklaşın!*"
        )
        embed.set_footer(text="Piyade RP • İllegal Kazanç Sistemi")
        try:
            await member.send(embed=embed)
        except Exception:
            pass

        # 4. Ekonomi Log Kanalına Bildir
        guild = self.bot.get_guild(GUILD_ID)
        if guild:
            log_embed = discord.Embed(
                title="🏧 İLLEGAL KAZANÇ | BAŞARILI ATM SOYGUNU",
                color=discord.Color.dark_green(),
                timestamp=datetime.now(tz_tr)
            )
            log_embed.add_field(name="👤 Soyguncu", value=f"<@{member.id}> (`{member.id}`)", inline=True)
            log_embed.add_field(name="🏧 Hedef ATM", value=f"**{atm_info.get('name')}**", inline=True)
            log_embed.add_field(name="💰 Eklenen Nakit", value=f"**+{format_usd(SOYGUN_ODULU)}**", inline=True)
            log_embed.add_field(name="📍 Konum", value=f"`Posta: {atm_info.get('postal')} | {atm_info.get('street')}`", inline=False)
            log_embed.set_footer(text="Piyade RP Ekonomi & Güvenlik Denetimi")
            await ekonomi_log_gonder(guild, log_embed)

    # ── SLASH KOMUT (Discord üzerinden de tetiklenebilir) ──
    @app_commands.command(name="atmsoy", description="En yakınınızdaki ATM'yi soymak için kilit kırma arayüzünü açar.")
    async def cmd_atmsoy(self, interaction: discord.Interaction):
        await self.execute_atmsoy_flow(interaction.user, interaction.user.display_name, interaction=interaction)

    # ── TEŞHİS & TEST KOMUTU (ER:LC API Bağlantı Durumu) ──
    @app_commands.command(name="atm-komut-test", description="ER:LC CommandLogs API ve komut algılama durumunu test eder.")
    @app_commands.default_permissions(administrator=True)
    async def cmd_atm_komut_test(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        api_key = os.getenv("ERLC_API_KEY", "").strip("'\" \r\n\t")
        if not api_key:
            return await interaction.followup.send("❌ `ERLC_API_KEY` ortam değişkeni sunucuda ayarlanmamış!", ephemeral=True)

        session = await self.get_session()
        headers = {'Server-Key': api_key}

        results = []
        for url in ["https://api.erlc.gg/v2/server/commandlogs", "https://api.erlc.gg/v1/server/commandlogs"]:
            try:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    status = resp.status
                    text = await resp.text()
                    results.append(f"**URL:** `{url}`\n**HTTP Kod:** `{status}`\n**Cevap (İlk 300 Karakter):**\n```{text[:300]}```")
            except Exception as e:
                results.append(f"**URL:** `{url}`\n**Hata:** `{e}`")

        embed = discord.Embed(
            title="🔍 ER:LC Command Logs API Test Raporu",
            color=discord.Color.blue(),
            timestamp=datetime.now(tz_tr)
        )
        embed.description = "\n\n────────────────\n\n".join(results)
        embed.add_field(
            name="💡 Önemli Bilgi",
            value=(
                "Eğer ER:LC API komut loglarını vermiyorsa (403/404), Roblox ER:LC oyun içi sunucu ayarlarından "
                "**'Komut Kayıtları Webhooku'** alanına bu sunucuda oluşturacağınız bir Discord Webhook bağlantısını yapıştırmanız yeterlidir!\n"
                "Bot webhook üzerinden gelen `;atmsoy` komutlarını anlık (0 gecikmeyle) otomatik olarak yakalar."
            ),
            inline=False
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ATMSoygunu(bot))
