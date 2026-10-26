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
from aiohttp import web
import base64
import re
from datetime import datetime, timezone, timedelta
from typing import Optional

try:
    from nacl.signing import VerifyKey
    from nacl.exceptions import BadSignatureError
    HAS_NACL = True
except ImportError:
    HAS_NACL = False

ERLC_PUBLIC_KEY_BASE64 = "MCowBQYDK2VwAyEAjSICb9pp0kHizGQtdG8ySWsDChfGqi+gyFCttigBNOA="

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
        self.son_webhook_kayitlari: list = []
        self.toplam_gecerli_webhook: int = 0
        self.toplam_reddedilen_probe: int = 0
        self._session: Optional[aiohttp.ClientSession] = None
        self._web_runner: Optional[web.AppRunner] = None
        self.bot_baslangic_zamani = time.time()

        # Railway HTTP Webhook Sunucusu (ER:LC Event Webhook için)
        port_env = os.getenv("PORT")
        if port_env:
            try:
                self.web_port = int(port_env)
                self.bot.loop.create_task(self.start_web_server())
            except Exception as e:
                print(f"[ATM SOYGUN WEB] Port ayar hatası: {e}", flush=True)

    def cog_unload(self):
        if self._session and not self._session.closed:
            asyncio.create_task(self._session.close())
        if self._web_runner:
            asyncio.create_task(self._web_runner.cleanup())

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def save_data(self):
        self.data["cooldowns"] = self.cooldowns
        kaydet_soygun_data(self.data)

    # ── RESMİ ER:LC EVENT WEBHOOK ALICISI (HTTP POST /erlc-webhook) ──
    async def handle_erlc_event_webhook(self, request: web.Request):
        """
        Roblox ER:LC Event Webhook entegrasyonu (Resmi apidocs.erlc.gg/event-webhooks.md uyumlu).
        - Başlıklar eksik, bozuk veya Ed25519 imzası geçersizse ZORUNLU olarak 401 (4xx) döner.
        - Sadece geçerli imzalı isteklere 200 (2xx) döner.
        """
        body_bytes = await request.read()
        timestamp = request.headers.get("X-Signature-Timestamp")
        sig_hex = request.headers.get("X-Signature-Ed25519")

        # 1. Başlık kontrolü (Eksik veya boşsa 401 dön - ER:LC doğrulama testi için zorunlu)
        if not timestamp or not sig_hex:
            self.toplam_reddedilen_probe += 1
            print("[ER:LC EVENT WEBHOOK] İmza başlığı eksik -> 401 döndürüldü (Doğrulama testi).", flush=True)
            return web.Response(status=401, text="Missing signature headers")

        if not HAS_NACL:
            print("[ER:LC EVENT WEBHOOK HATA] PyNaCl yüklü değil!", flush=True)
            return web.Response(status=500, text="PyNaCl not installed")

        # 2. Hex çözümü ve Ed25519 imza doğrulaması (timestamp + raw_body)
        try:
            sig_bytes = bytes.fromhex(sig_hex)
            if len(sig_bytes) != 64:
                self.toplam_reddedilen_probe += 1
                print("[ER:LC EVENT WEBHOOK] İmza uzunluğu geçersiz -> 401 döndürüldü.", flush=True)
                return web.Response(status=401, text="Malformed signature length")

            raw_key = base64.b64decode(ERLC_PUBLIC_KEY_BASE64)[-32:]
            verify_key = VerifyKey(raw_key)
            message_bytes = timestamp.encode("utf-8") + body_bytes
            verify_key.verify(message_bytes, sig_bytes)
        except (BadSignatureError, ValueError) as e:
            self.toplam_reddedilen_probe += 1
            print(f"[ER:LC EVENT WEBHOOK] Geçersiz imzalı istek reddedildi (401): {e}", flush=True)
            return web.Response(status=401, text="Invalid signature")
        except Exception as e:
            self.toplam_reddedilen_probe += 1
            print(f"[ER:LC EVENT WEBHOOK] İmza doğrulama hatası (401): {e}", flush=True)
            return web.Response(status=401, text="Signature verification failed")

        # 3. İmza Doğrulandı! Ham veriyi kaydet ve logla
        raw_text = body_bytes.decode("utf-8", errors="replace")
        self.toplam_gecerli_webhook += 1
        zaman_str = datetime.now(tz_tr).strftime("%H:%M:%S")
        self.son_webhook_kayitlari.append({
            "zaman": zaman_str,
            "timestamp": timestamp,
            "raw": raw_text[:1500]
        })
        if len(self.son_webhook_kayitlari) > 15:
            self.son_webhook_kayitlari.pop(0)

        print(f"[ER:LC EVENT WEBHOOK] ✅ Geçerli İmzalı Veri Alındı ({zaman_str}): {raw_text}", flush=True)

        if not body_bytes:
            return web.json_response({"status": "ok"}, status=200)

        try:
            parsed = json.loads(raw_text)
        except Exception:
            return web.Response(status=400, text="Bad JSON")

        # ER:LC gerçek şeması: {"server": "...", "events": [{"event": "CustomCommand", "origin": "3847447402", "timestamp": 1792423782, "data": {"command": "atmsoy", "argument": ""}}]}
        if isinstance(parsed, dict) and isinstance(parsed.get("events"), list):
            events = parsed["events"]
        elif isinstance(parsed, list):
            events = parsed
        else:
            events = [parsed]

        for ev in events:
            if not isinstance(ev, dict):
                continue
            self._process_webhook_event_dict(ev)

        return web.json_response({"status": "ok"}, status=200)

    def _process_webhook_event_dict(self, data: dict):
        """
        ER:LC Event Webhook'tan gelen her bir event objesini ayrıştırır.
        Gerçek Şema:
        {
          "event": "CustomCommand",
          "origin": "3847447402",
          "timestamp": 1792423782,
          "data": {"command": "atmsoy", "argument": ""}
        }
        """
        event_type = str(data.get("event") or data.get("type") or "").strip()

        # Doğrulama test isteğini (WebhookProbe) yok say
        if event_type.lower() == "webhookprobe":
            return

        inner = data.get("data") or data.get("payload") or data.get("event_data") or {}
        if not isinstance(inner, dict):
            inner = {}

        # Origin (Roblox User ID) ve diğer olası oyuncu alanlarını oku
        origin_val = str(data.get("origin") or data.get("Origin") or "").strip()
        if origin_val.lower() == "global":
            origin_val = ""

        # Komut ve argümanı oku (ER:LC başında ';' olmadan "atmsoy" olarak gönderir)
        raw_cmd = str(
            inner.get("command") or inner.get("Command") or
            data.get("command") or data.get("Command") or
            inner.get("content") or data.get("content") or
            inner.get("message") or data.get("message") or ""
        ).strip()
        cmd_arg = str(
            inner.get("argument") or inner.get("Argument") or
            data.get("argument") or data.get("Argument") or ""
        ).strip()

        # Komut adını ayrıştır ve normalize et
        cmd_clean = raw_cmd.lstrip(";:!/ ").strip()
        if " " in cmd_clean and not cmd_arg:
            parts = cmd_clean.split(" ", 1)
            cmd_clean = parts[0].strip()
            cmd_arg = parts[1].strip()

        cmd_norm = normalize_erlc_cmd(cmd_clean)
        arg_norm = normalize_erlc_cmd(cmd_arg)
        timestamp = data.get("timestamp") or data.get("Timestamp") or int(time.time())

        # Gelen tüm CustomCommand eventleri için net ve görünür merkezi log (Aşama B)
        print(
            f"[ER:LC KOMUT GELDİ] Tür: '{event_type}' | Origin (Roblox ID): '{origin_val}' | "
            f"Ham: {raw_cmd!r} -> Temiz: '{cmd_clean}' (Normalize: '{cmd_norm}') | Argüman: {cmd_arg!r}",
            flush=True
        )

        # Gelecekteki tüm ';' komutları için genel bot eventi yayınla:
        # Diğer tüm cog'lar @commands.Cog.listener("on_erlc_custom_command") ile dinleyebilir!
        if cmd_clean or cmd_norm:
            self.bot.dispatch("erlc_custom_command", origin_val, cmd_clean, cmd_arg, timestamp, data)

        # Oyuncu adı / ID yedek çözümleme (eski/alternatif şemalar için)
        player_name = ""
        player_id = origin_val

        p_obj = (
            data.get("player") or data.get("Player") or
            inner.get("player") or inner.get("Player") or ""
        )
        if isinstance(p_obj, dict):
            player_name = str(p_obj.get("name") or p_obj.get("username") or p_obj.get("Player") or "").strip()
            if not player_id:
                player_id = str(p_obj.get("id") or p_obj.get("userId") or p_obj.get("playerId") or "").strip()
        elif isinstance(p_obj, str) and p_obj.strip():
            player_name = p_obj.strip()

        # 1. ;atmsoy komutu kontrolü (hem 'atmsoy' hem ';atmsoy' ve varyasyonlar desteklenir)
        is_atmsoy = (
            cmd_norm in ("atmsoy", "atm-soy", "atm_soy") or
            cmd_norm.replace("-", "").replace("_", "") == "atmsoy" or
            any(t in raw_cmd.lower() for t in [";atmsoy", ";atm-soy", ";atm soy", ":atmsoy", ":atm-soy"])
        )
        if is_atmsoy:
            log_payload = {
                "origin": player_id,
                "Player": f"{player_name}:{player_id}" if (player_name and player_id) else (player_name or player_id),
                "Command": cmd_clean or "atmsoy",
                "argument": cmd_arg,
                "Timestamp": timestamp
            }
            print(
                f"[ER:LC EVENT WEBHOOK] 🎯 ;atmsoy yakalandı! Origin(Roblox ID): '{player_id}' | "
                f"Oyuncu: '{player_name}' | Komut: '{cmd_clean}'",
                flush=True
            )
            asyncio.create_task(self.handle_atmsoy_command(log_payload))
            return

        # 2. ;ilkyardım komutu kontrolü (merkezi takip için)
        comp_norm = cmd_norm.replace("-", "").replace("_", "").replace(" ", "")
        is_ilkyardim = (
            comp_norm == "ilkyardim" or
            cmd_norm in ("ilkyardim", "ilk-yardim", "ilk_yardim", "iy") or
            (cmd_norm == "ilk" and "yardim" in arg_norm) or
            cmd_norm in ("yardim", "yardım")
        )
        if is_ilkyardim:
            print(
                f"[ER:LC EVENT WEBHOOK] 🎯 ;ilkyardım yakalandı! İlk yardım modülüne (dispatch) iletildi. Origin: '{origin_val}'",
                flush=True
            )
            return

        # 3. Bilinmeyen komut uyarısı (Aşama B)
        if event_type.lower() == "customcommand":
            print(
                f"[ER:LC BİLİNMEYEN KOMUT] ⚠️ Sistemde kayıtlı olmayan bir komut kullanıldı: '{cmd_clean}' "
                f"(Normalize: '{cmd_norm}') | Origin: '{origin_val}'",
                flush=True
            )

    async def start_web_server(self):
        try:
            app = web.Application()
            app.router.add_post("/erlc-webhook", self.handle_erlc_event_webhook)
            app.router.add_get("/", lambda req: web.Response(text="Piyade RP Webhook Receiver Aktif"))
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, "0.0.0.0", self.web_port)
            await site.start()
            print(f"[ATM SOYGUN WEB] ER:LC Event Webhook dinleyicisi 0.0.0.0:{self.web_port}/erlc-webhook üzerinde hazır!", flush=True)
            self._web_runner = runner
        except Exception as e:
            print(f"[ATM SOYGUN WEB HATA] Web sunucusu başlatılamadı: {e}", flush=True)

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

        # 1. Embed'leri kontrol et (ER:LC Command Webhook)
        for embed in message.embeds:
            cmd_val = ""
            player_val = ""
            user_id_val = ""

            desc = embed.description or ""
            title = embed.title or ""

            # ER:LC Standart Formatı: "Bacon_Exe1341:3847447402 used the command: :mod Bacon_Exe1341"
            m_used = re.search(r"\[?([A-Za-z0-9_]+)\]?(?::(\d+))?\s+used the command:\s*([^\n\r]+)", desc, re.IGNORECASE)
            if m_used:
                player_val = m_used.group(1).strip()
                if m_used.group(2):
                    user_id_val = m_used.group(2).strip()
                cmd_val = m_used.group(3).strip()

            # Alternatif field kontrolü
            for field in embed.fields:
                fn = (field.name or "").strip().lower()
                fv = (field.value or "").strip()
                if any(k in fn for k in ["command", "komut"]):
                    cmd_val = fv
                elif any(k in fn for k in ["player", "oyuncu", "executor", "yetkili", "kullanıcı"]):
                    player_val = fv
                elif any(k in fn for k in ["user id", "userid", "roblox id", "roblox_id"]):
                    user_id_val = fv

            combined_text = f"{message.content or ''} {title} {desc} {cmd_val}".lower()
            if any(trig in combined_text for trig in [";atmsoy", ";atm-soy", ";atm soy", ":atmsoy", ":atm-soy", ":atm soy"]):
                if not player_val:
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
                        "Command": cmd_val or ";atmsoy",
                        "Timestamp": int(time.time())
                    }
                    print(f"[ATM SOYGUN WEBHOOK] Webhook'tan atmsoy yakalandı! Oyuncu: {player_val} (ID: {user_id_val})", flush=True)
                    await self.handle_atmsoy_command(log_payload)
                    return

        # 2. Embedsiz düz metin kontrolü
        content_lower = (message.content or "").lower()
        if any(trig in content_lower for trig in [";atmsoy", ";atm-soy", ";atm soy", ":atmsoy", ":atm-soy", ":atm soy"]):
            m_used_plain = re.search(r"\[?([A-Za-z0-9_]+)\]?(?::(\d+))?\s+used the command:\s*([^\n\r]+)", message.content, re.IGNORECASE)
            p_name = None
            u_id = None
            if m_used_plain:
                p_name = m_used_plain.group(1)
                u_id = m_used_plain.group(2)
            else:
                m_p = re.search(r"(?:player|oyuncu|kullanıcı)[:\s*]+([A-Za-z0-9_]+)", message.content, re.IGNORECASE)
                if m_p:
                    p_name = m_p.group(1)

            if p_name:
                log_payload = {
                    "Player": f"{p_name}:{u_id}" if u_id else p_name,
                    "Command": ";atmsoy",
                    "Timestamp": int(time.time())
                }
                print(f"[ATM SOYGUN DÜZ METİN] Webhook metninden atmsoy yakalandı! Oyuncu: {p_name}", flush=True)
                await self.handle_atmsoy_command(log_payload)

    async def handle_atmsoy_command(self, log: dict):
        origin_id = str(log.get("origin") or log.get("roblox_id") or "").strip()
        player_raw = str(log.get("Player") or log.get("player") or log.get("executor") or log.get("Executor") or "").strip()
        timestamp = log.get("Timestamp") or log.get("timestamp") or 0
        command_str = str(log.get("Command") or log.get("command") or "").strip()

        # Eski komutları filtrele (90 saniyeden eski loglar)
        try:
            ts_float = float(timestamp)
            if ts_float > 1000000000:
                if time.time() - ts_float > 90:
                    return
        except (ValueError, TypeError):
            pass

        log_key = f"{origin_id}_{player_raw}_{command_str}_{timestamp}"
        if log_key in self.islenen_komutlar:
            return
        self.islenen_komutlar.add(log_key)
        if len(self.islenen_komutlar) > 2000:
            self.islenen_komutlar.clear()

        roblox_name = player_raw
        roblox_id = origin_id

        if "[" in roblox_name and "]" in roblox_name:
            roblox_name = roblox_name.split("[")[1].split("]")[0]
        if "(" in roblox_name:
            roblox_name = roblox_name.split("(")[0].strip()
        if ":" in roblox_name:
            parts = roblox_name.split(":", 1)
            roblox_name = parts[0].strip()
            if not roblox_id:
                roblox_id = parts[1].strip()

        # Eğer roblox_name sadece rakamlardan oluşuyorsa (origin ID ise) onu roblox_id olarak al
        if roblox_name.isdigit() and not roblox_id:
            roblox_id = roblox_name
            roblox_name = ""
        elif roblox_name == roblox_id:
            roblox_name = ""

        # 1. LiveRadar üzerinden Roblox ID -> Roblox Kullanıcı Adı çözümlemesi
        radar_cog = self.bot.get_cog("LiveRadar")
        if radar_cog and roblox_id and not roblox_name:
            for p_name, p_loc in (getattr(radar_cog, "aktif_oyuncular", {}) or {}).items():
                if str(p_loc.get("roblox_id") or "") == str(roblox_id):
                    roblox_name = p_name
                    break
            if not roblox_name:
                for p_name, p_loc in (getattr(radar_cog, "son_konumlar", {}) or {}).items():
                    if str(p_loc.get("roblox_id") or "") == str(roblox_id):
                        roblox_name = p_name
                        break

        # 2. Hala roblox_name yoksa Roblox Resmi API'sinden (users.roblox.com) çek
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
                        print(f"[ATM SOYGUN] Roblox API'den ID {roblox_id} -> '{roblox_name}' çözümlendi.", flush=True)
            except Exception as e:
                print(f"[ATM SOYGUN] Roblox API kullanıcı sorgu hatası: {e}", flush=True)

        guild = self.bot.get_guild(GUILD_ID)
        if not guild:
            return

        # 3. Discord Üyesini Bul (Önce kayit_data.json üzerinden roblox_id / roblox_name ile)
        discord_id = roblox_to_discord(roblox_id, roblox_name)
        member = None
        if discord_id:
            member = guild.get_member(discord_id)
            if not member:
                try:
                    member = await guild.fetch_member(discord_id)
                except Exception:
                    member = None

        # 4. Kayıt verisinde bulunamadıysa sunucu üyelerinin isim/takma adlarında roblox_name ara
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
                except Exception as e:
                    print(f"[ATM SOYGUN] query_members hatası: {e}", flush=True)

        if not member:
            hedef_pm = roblox_name or roblox_id
            print(f"[ATM SOYGUN] '{hedef_pm}' (ID: {roblox_id}) için Discord eşleşmesi bulunamadı.", flush=True)
            if roblox_name:
                await send_erlc_command(f":pm {roblox_name} Discord hesabinizi Piyade RP ile eslestirmelisiniz!")
            return

        # Eğer kayıttan member bulunduysa ama roblox_name hala boşsa kayıttaki adını veya display_name'ini al
        if not roblox_name:
            from cogs.envanter_sistemi import discord_to_roblox
            r_ad, _ = discord_to_roblox(member.id, member.display_name)
            roblox_name = r_ad or member.display_name

        print(f"[ATM SOYGUN] ✅ {roblox_name} (Roblox ID: {roblox_id} -> Discord: {member.display_name} / {member.id}) için soygun başlatılıyor!", flush=True)
        await self.execute_atmsoy_flow(member, roblox_name, roblox_id=roblox_id)

    async def execute_atmsoy_flow(
        self,
        member: discord.Member,
        roblox_name: str,
        interaction: Optional[discord.Interaction] = None,
        roblox_id: str = ""
    ):
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
        uygun, durum, hedef_atm, mesafe, p_loc = kullanici_atm_kontrol(self.bot, member)

        # Eğer kullanici_atm_kontrol Discord adından konum bulamazsa doğrudan roblox_id veya roblox_name ile kontrol et
        if not uygun or not hedef_atm:
            radar_cog = self.bot.get_cog("LiveRadar")
            if radar_cog:
                aktif_oyuncular = getattr(radar_cog, "aktif_oyuncular", {}) or {}
                p_loc_direct = None

                if roblox_id:
                    for p_name, loc in aktif_oyuncular.items():
                        if str(loc.get("roblox_id") or "") == str(roblox_id):
                            p_loc_direct = loc
                            break

                if not p_loc_direct and roblox_name:
                    for p_name, loc in aktif_oyuncular.items():
                        if p_name.lower() == roblox_name.lower():
                            p_loc_direct = loc
                            break

                if p_loc_direct:
                    px = p_loc_direct.get("x")
                    pz = p_loc_direct.get("z")
                    if isinstance(px, (int, float)) and isinstance(pz, (int, float)):
                        max_mesafe = get_atm_max_mesafe()
                        yakin_atm, d = en_yakin_atm(px, pz)
                        if yakin_atm:
                            hedef_atm = yakin_atm
                            mesafe = d
                            p_loc = p_loc_direct
                            if d <= max_mesafe:
                                uygun = True

        if not uygun or not hedef_atm:
            en_yakin_isim = hedef_atm['name'] if hedef_atm else "Bilinmiyor"
            mesafe_str = f"{round(mesafe, 1)} metre" if mesafe is not None else "Bilinmiyor"

            dm_text = (
                f"❌ **Bir ATM Cihazının Yanında Değilsiniz!**\n"
                f"ATM soymak için ER:LC oyununda bir ATM cihazının hemen yanında (azami 6 metre) durmalısınız.\n\n"
                f"📍 **En Yakın ATM:** **{en_yakin_isim}**\n"
                f"📏 **Mevcut Mesafeniz:** `{mesafe_str}` *(İzin verilen: 6 metre)*"
            )
            if interaction:
                await interaction.response.send_message(dm_text, ephemeral=True)
            else:
                try:
                    await member.send(dm_text)
                except Exception:
                    pass
                asyncio.create_task(send_erlc_command(f":pm {roblox_name} Bir ATM cihazinin yaninda degilsiniz!"))
            return

        # 3. 10 Dakika Bekleme Süresi (Cooldown) Kontrolü
        now = time.time()
        son_soygun = self.cooldowns.get(str(member.id), 0)
        if now - son_soygun < COOLDOWN_SURESI:
            kalan = int(COOLDOWN_SURESI - (now - son_soygun))
            dakika = kalan // 60
            saniye = kalan % 60

            dm_text = (
                f"⏳ **ATM Soygunu Bekleme Süresi Aktif!**\n"
                f"Son yaptığınız ATM soygununun üzerinden henüz 10 dakika geçmedi.\n\n"
                f"⏱️ **Kalan Süre:** `{dakika} dakika {saniye} saniye` sonra tekrar soyabilirsiniz."
            )
            if interaction:
                await interaction.response.send_message(dm_text, ephemeral=True)
            else:
                try:
                    await member.send(dm_text)
                except Exception:
                    pass
                asyncio.create_task(send_erlc_command(f":pm {roblox_name} Tekrar ATM soymak icin {dakika} dk {saniye} sn beklemelisiniz!"))
            return

        # 4. RFID Disruptor Eşya Kontrolü
        profile = get_user_profile(member.id)
        inv = profile.get("inventory", {})
        has_rfid = any(item.strip().lower() == GEREKLI_ESYA.lower() and count > 0 for item, count in inv.items())
        if not has_rfid:
            dm_text = (
                f"❌ **Gerekli Ekipman Eksik: {GEREKLI_ESYA}**\n"
                f"ATM'nin elektronik kilit sistemini ve banka alarm sinyalini kesmek için envanterinizde **`{GEREKLI_ESYA}`** bulunmalıdır.\n\n"
                f"İllegal pazardan bir RFID Disruptor temin ettikten sonra tekrar deneyiniz."
            )
            if interaction:
                await interaction.response.send_message(dm_text, ephemeral=True)
            else:
                try:
                    await member.send(dm_text)
                except Exception:
                    pass
                asyncio.create_task(send_erlc_command(f":pm {roblox_name} RFID Disruptor olmadan ATM soyamazsin!"))
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
            f"🎯 **Hedeflenen ATM:** **{hedef_atm['name']}**\n"
            f"📮 **Posta Kodu:** `{hedef_atm.get('postal', '-')}`\n"
            f"🛣️ **Bölge:** `{hedef_atm.get('street', '-')}`\n"
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
            await self.start_minigame(member, hedef_atm, roblox_name)

        view = ATMBaslatView(member.id, on_start)

        try:
            await dm_channel.send(embed=embed, view=view)
            if interaction:
                await interaction.response.send_message("✅ **ATM kilit kırma paneli Discord DM kutunuza gönderildi!**", ephemeral=True)
            else:
                asyncio.create_task(send_erlc_command(f":pm {roblox_name} ATM Kilit Kirma Paneli Discord DM kutunuza gonderildi!"))
        except discord.Forbidden:
            err_msg = "❌ Discord DM kutunuz kapalı olduğu için soygun paneli gönderilemedi! Lütfen gizlilik ayarlarından sunucu üyelerinden gelen DM'leri açın."
            if interaction:
                await interaction.response.send_message(err_msg, ephemeral=True)
            else:
                asyncio.create_task(send_erlc_command(f":pm {roblox_name} Discord DM kutunuz kapali! Lutfen DM'leri acin."))

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

    # ── TEŞHİS & TEST KOMUTU (ER:LC Event Webhook Durumu ve Ham Veri Görüntüleyici) ──
    @app_commands.command(name="erlc-durum", description="ER:LC Event Webhook doğrulama durumunu ve oyundan gelen son ham JSON verilerini gösterir.")
    @app_commands.default_permissions(administrator=True)
    async def cmd_erlc_durum(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        outbound_ip = "Bilinmiyor"
        try:
            session = await self.get_session()
            async with session.get("https://api.ipify.org", timeout=aiohttp.ClientTimeout(total=3)) as ip_resp:
                if ip_resp.status == 200:
                    outbound_ip = (await ip_resp.text()).strip()
        except Exception:
            pass

        embed = discord.Embed(
            title="📡 ER:LC Event Webhook & Komut Alıcı Durumu",
            color=discord.Color.green() if self._web_runner else discord.Color.red(),
            timestamp=datetime.now(tz_tr)
        )
        embed.add_field(
            name="🌐 Web Sunucusu",
            value=f"{'✅ Aktif' if self._web_runner else '❌ Kapalı'} (`Port: {getattr(self, 'web_port', 'Yok')}`)",
            inline=True
        )
        embed.add_field(
            name="🔐 Ed25519 (PyNaCl)",
            value="✅ Aktif (Sıkı 401/200 Doğrulama)" if HAS_NACL else "❌ Yüklü Değil",
            inline=True
        )
        embed.add_field(
            name="🌍 Bot Dış IP Adresi (ER:LC Allowlist)",
            value=f"`{outbound_ip}`\n[👉 api.erlc.gg/server-owners](https://api.erlc.gg/server-owners)",
            inline=False
        )
        embed.add_field(
            name="📊 İstatistikler",
            value=(
                f"🛡️ **Reddedilen Test Probe (401):** `{self.toplam_reddedilen_probe}`\n"
                f"✅ **Geçerli İmzalı Webhook (200):** `{self.toplam_gecerli_webhook}`"
            ),
            inline=False
        )

        if self.son_webhook_kayitlari:
            son_kayitlar_str = ""
            for k in reversed(self.son_webhook_kayitlari[-5:]):
                son_kayitlar_str += f"**[{k['zaman']}]** (ts: `{k['timestamp']}`)\n```json\n{k['raw'][:400]}\n```\n"
            embed.add_field(
                name="📥 Oyundan Gelen Son Ham Webhook Verileri (Raw JSON)",
                value=son_kayitlar_str[:1020],
                inline=False
            )
        else:
            embed.add_field(
                name="📥 Oyundan Gelen Son Ham Webhook Verileri",
                value="*Henüz geçerli imzalı bir event gelmedi. Oyunda Event Webhook'u kaydedip sohbete `;atmsoy` yazın.*",
                inline=False
            )

        await interaction.followup.send(embed=embed, ephemeral=True)



async def setup(bot: commands.Bot):
    await bot.add_cog(ATMSoygunu(bot))
