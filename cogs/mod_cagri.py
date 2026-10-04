import discord
from discord.ext import commands, tasks
from discord import app_commands
import aiohttp
import os
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional
from utils.storage import load_json, save_json_atomic, async_save_json

# ==================== AYARLAR ====================
MOD_LOG_KANAL_ID = 1555628244806410280
MOD_ROL_ID = 1555628384166346752
ASIL_KURUCU_ID = 1133815339898122320

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CAGRILAR_FILE = os.path.join(DATA_DIR, "mod_cagrilari.json")
ISLENEN_KOMUTLAR_FILE = os.path.join(DATA_DIR, "islenen_mod_komutlari.json")
# =================================================


class ModCagriView(discord.ui.View):
    """
    Discord üzerinden moderatörlerin çağrıyı manuel olarak kapatabilmesini sağlayan kalıcı buton.
    """
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Çözüldü / Kapat",
        style=discord.ButtonStyle.secondary,
        emoji="✅",
        custom_id="btn_mod_cagri_kapat"
    )
    async def kapat_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Yetkili rolü veya yönetici kontrolü
        has_perm = (
            interaction.user.id == ASIL_KURUCU_ID
            or interaction.user.guild_permissions.administrator
            or any(r.id == MOD_ROL_ID for r in interaction.user.roles)
        )
        if not has_perm:
            return await interaction.response.send_message(
                "❌ Bu çağrıyı sadece **Moderatörler** kapatabilir!",
                ephemeral=True
            )

        msg = interaction.message
        if not msg or not msg.embeds:
            return await interaction.response.send_message("❌ Mesaj bulunamadı.", ephemeral=True)

        embed = msg.embeds[0]
        # Çağrı zaten kapatılmış mı?
        if embed.color and embed.color.value == discord.Color.dark_grey().value:
            return await interaction.response.send_message("ℹ️ Bu çağrı zaten daha önce kapatılmış.", ephemeral=True)

        # Embed'i Gri Yap ve Güncelle
        yeni_embed = discord.Embed(
            title="🔘 PİYADE RP • MODERATÖR ÇAĞRISI (KAPATILDI)",
            description=f"> **Bu çağrı Discord üzerinden {interaction.user.mention} tarafından çözüldü olarak işaretlendi.**",
            color=discord.Color.dark_grey(),
            timestamp=discord.utils.utcnow()
        )

        for field in embed.fields:
            if "Durum" in field.name:
                continue
            yeni_embed.add_field(name=field.name, value=field.value, inline=field.inline)

        yeni_embed.add_field(
            name="🛡️ Kapatan Yetkili",
            value=f"{interaction.user.mention} `({interaction.user.display_name})`",
            inline=True
        )
        yeni_embed.add_field(
            name="📊 Durum",
            value="`🔘 Çözüldü (Discord Üzerinden Kapatıldı)`",
            inline=True
        )
        yeni_embed.set_footer(text="Piyade Roleplay • Moderatör Destek Sistemi (Kapatıldı)")

        await interaction.response.defer()
        # content=None yapılarak @rol etiketi silinir, buton devre dışı bırakılır
        button.disabled = True
        await msg.edit(content=None, embed=yeni_embed, view=self)

        # Cog referansını al ve RAM'deki aktif_cagrilar'dan sil
        cog = interaction.client.get_cog("ModCagri")

        # Oyuncu adını embed alanlarından çek
        player_key_fallback = None
        for field in embed.fields:
            if "Oyuncu" in field.name:
                clean_val = field.value.replace("*", "").strip()
                p_name = clean_val.split("(")[0].strip().split("`")[0].strip()
                if p_name:
                    player_key_fallback = p_name.lower()
                break

        silinecek = None
        if cog and hasattr(cog, "aktif_cagrilar"):
            for k, v in list(cog.aktif_cagrilar.items()):
                if v.get("message_id") == msg.id:
                    silinecek = k
                    break
            if not silinecek and player_key_fallback and player_key_fallback in cog.aktif_cagrilar:
                silinecek = player_key_fallback
            if silinecek:
                cog.aktif_cagrilar.pop(silinecek, None)
            elif player_key_fallback:
                cog.aktif_cagrilar.pop(player_key_fallback, None)

        # Veritabanından aktif çağrıyı kaldır ve geçmişe kaydet
        cagri_data = load_json(CAGRILAR_FILE, {"aktif_cagrilar": {}, "gecmis_cagrilar": []})
        aktif = cagri_data.get("aktif_cagrilar", {})
        if not silinecek:
            for k, v in list(aktif.items()):
                if v.get("message_id") == msg.id:
                    silinecek = k
                    break
        if not silinecek and player_key_fallback and player_key_fallback in aktif:
            silinecek = player_key_fallback

        if silinecek and silinecek in aktif:
            kayit = aktif.pop(silinecek)
            kayit["status"] = "cozuldu_discord"
            kayit["closed_by"] = str(interaction.user)
            kayit["closed_at"] = int(discord.utils.utcnow().timestamp())
            cagri_data.setdefault("gecmis_cagrilar", []).append(kayit)
            cagri_data["gecmis_cagrilar"] = cagri_data["gecmis_cagrilar"][-100:]
            cagri_data["aktif_cagrilar"] = aktif
            await async_save_json(CAGRILAR_FILE, cagri_data)
        elif cog and hasattr(cog, "aktif_cagrilar"):
            cagri_data["aktif_cagrilar"] = cog.aktif_cagrilar
            await async_save_json(CAGRILAR_FILE, cagri_data)


class ModCagri(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = None

        # İşlenmiş komut kimlikleri (Timestamp + Player + Command hash)
        islenen_data = load_json(ISLENEN_KOMUTLAR_FILE, {"islenen_id": []})
        self.islenen_komutlar = set(islenen_data.get("islenen_id", []))

        # Aktif çağrılar bellekte tutulur
        cagri_data = load_json(CAGRILAR_FILE, {"aktif_cagrilar": {}, "gecmis_cagrilar": []})
        self.aktif_cagrilar = cagri_data.get("aktif_cagrilar", {})

        # Bot başlarken 10 dakikadan eski veya kapanmış çağrıları temizle
        self.stale_cagrilari_temizle()
        print(f"[MOD ÇAĞRI BAŞLATILDI v2] Aktif çağrı sayısı: {len(self.aktif_cagrilar)}, İşlenen komut: {len(self.islenen_komutlar)}", flush=True)

        self.mod_takip_loop.start()

    def stale_cagrilari_temizle(self):
        """
        10 dakikadan (600 sn) eski çağrıları veya tamamlanmış kayıtları aktif listeden temizler.
        Böylece oyuncular kilitli kalmaz.
        """
        now = int(datetime.now(timezone.utc).timestamp())
        silinecekler = []
        for k, v in list(self.aktif_cagrilar.items()):
            ts = v.get("timestamp", 0)
            status = v.get("status", "beklemede")
            if (now - ts > 600) or status != "beklemede":
                silinecekler.append(k)
        for k in silinecekler:
            self.aktif_cagrilar.pop(k, None)

    def cog_unload(self):
        self.mod_takip_loop.cancel()
        if self.session and not self.session.closed:
            self.bot.loop.create_task(self.session.close())

    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def discorda_cagri_gonder(self, kanal: discord.TextChannel, player_raw: str, gerekce: str, ts: int):
        """
        Discord kanalına @Moderatör rol etiketiyle kırmızı renkli çağrı mesajı atar.
        """
        player_name = player_raw.split(":")[0]
        player_id = player_raw.split(":")[1] if ":" in player_raw else "0"
        player_key = player_name.lower()

        # Eğer zaten aktif çağrı varsa durumunu ve yaşını kontrol et
        if player_key in self.aktif_cagrilar:
            mevcut = self.aktif_cagrilar[player_key]
            now_ts = int(datetime.now(timezone.utc).timestamp())
            c_ts = mevcut.get("timestamp", 0)
            if (now_ts - c_ts > 600) or (mevcut.get("status") != "beklemede"):
                self.aktif_cagrilar.pop(player_key, None)
            else:
                # Gerçekten aktif ve 10 dakikadan taze bir çağrısı var, spam engeli
                print(f"[MOD ÇAĞRI] {player_name} zaten aktif bir çağrıya sahip ({now_ts - c_ts}s önce). Mükerrer bildirim engellendi.", flush=True)
                return None

        tz_tr = timezone(timedelta(hours=3))
        dt_ts = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(tz_tr)

        embed = discord.Embed(
            title="🚨 PİYADE ROLEPLAY • MODERATÖR ÇAĞRISI",
            description=(
                f"> **ER:LC oyun sunucusunda bir oyuncu moderatör talep etti!**\n"
                f"> *Oyunda bulunan moderatörlerimizin derhal `:to {player_name}` atarak müdahale etmesi gerekmektedir.*"
            ),
            color=discord.Color.red(),
            timestamp=dt_ts
        )
        embed.add_field(
            name="👤 Çağrı Yapan Oyuncu (Roblox)",
            value=f"**{player_name}** `(ID: {player_id})`",
            inline=True
        )
        embed.add_field(
            name="💬 Gerekçe / Mesaj",
            value=f"`{gerekce}`",
            inline=True
        )
        embed.add_field(
            name="⏳ Çağrı Durumu",
            value="`🔴 Beklemede (Yetkili müdahalesi bekleniyor)`",
            inline=False
        )
        embed.add_field(
            name="💡 Nasıl Müdahale Edilir?",
            value=f"Oyun içerisinde **`:to {player_name}`** komutunu kullanarak oyuncuya ışınlanabilirsiniz.",
            inline=False
        )
        embed.set_footer(text="Piyade Roleplay • Oyun İçi Yetkili Takip Sistemi")

        rol_etiketi = f"<@&{MOD_ROL_ID}>"
        view = ModCagriView()

        try:
            msg = await kanal.send(content=rol_etiketi, embed=embed, view=view)
            self.aktif_cagrilar[player_key] = {
                "player_raw": player_raw,
                "player_name": player_name,
                "player_id": player_id,
                "message_id": msg.id,
                "channel_id": kanal.id,
                "gerekce": gerekce,
                "timestamp": ts or int(datetime.now(timezone.utc).timestamp()),
                "status": "beklemede"
            }
            print(f"[MOD ÇAĞRI] {player_name} için Discord'a bildirim iletildi (Mesaj ID: {msg.id})", flush=True)
            return msg
        except discord.Forbidden:
            print(f"[MOD ÇAĞRI HATA] Botun {kanal.name} kanalına mesaj gönderme yetkisi yok! Lütfen kanal izinlerini kontrol edin.", flush=True)
            return None
        except Exception as e:
            print(f"[MOD ÇAĞRI HATA] Mesaj gönderilemedi: {e}", flush=True)
            return None

    async def cagriyi_coz(self, kanal: discord.TextChannel, caller_key: str, mod_name: str, mod_id: str, cmd_ts: int):
        """
        Moderatör :to [oyuncu] attığında veya çağrıyı yanıtladığında Discord mesajını griye çevirir ve etiketi siler.
        """
        cagri_bilgi = self.aktif_cagrilar.pop(caller_key, None)
        if not cagri_bilgi:
            return

        msg_id = cagri_bilgi.get("message_id")
        if not msg_id:
            return

        try:
            cagri_msg = await kanal.fetch_message(msg_id)
        except Exception:
            cagri_msg = None

        if not cagri_msg:
            return

        tz_tr = timezone(timedelta(hours=3))
        ilk_ts = cagri_bilgi.get("timestamp", cmd_ts)
        fark_saniye = max(0, cmd_ts - ilk_ts) if (cmd_ts and ilk_ts) else 0
        if fark_saniye < 60:
            sure_str = f"**{fark_saniye} saniye**"
        else:
            dakika = fark_saniye // 60
            saniye = fark_saniye % 60
            sure_str = f"**{dakika} dakika {saniye} saniye**"

        dt_cmd = datetime.fromtimestamp(cmd_ts, tz=timezone.utc) if cmd_ts else datetime.now(tz_tr)

        gri_embed = discord.Embed(
            title="🔘 PİYADE RP • MODERATÖR ÇAĞRISI (YANITLANDI)",
            description=(
                f"> **Bu çağrı oyun içinde yetkili tarafından başarıyla devralındı.**\n"
                f"> *İlgili moderatör oyuncunun yanına ışınlandı (`:to {cagri_bilgi['player_name']}`).*"
            ),
            color=discord.Color.dark_grey(),
            timestamp=dt_cmd
        )
        gri_embed.add_field(
            name="👤 Çağrı Yapan Oyuncu",
            value=f"**{cagri_bilgi['player_name']}** `(ID: {cagri_bilgi.get('player_id', '0')})`",
            inline=True
        )
        gri_embed.add_field(
            name="🛡️ Yanıtlayan Moderatör",
            value=f"**{mod_name}** `(ID: {mod_id})`",
            inline=True
        )
        gri_embed.add_field(
            name="💬 Gerekçe",
            value=f"`{cagri_bilgi.get('gerekce', '-')}`",
            inline=True
        )
        gri_embed.add_field(
            name="⏱️ Yanıt Süresi",
            value=f"Çağrı {sure_str} içinde yanıtlandı.",
            inline=True
        )
        gri_embed.add_field(
            name="📊 Durum",
            value="`🔘 Yanıtlandı & Kapatıldı (:to Atıldı)`",
            inline=True
        )
        gri_embed.set_footer(text="✅ Piyade Roleplay • Moderatör Müdahalesi Tamamlandı")

        try:
            view = ModCagriView()
            for btn in view.children:
                btn.disabled = True
            # content=None yapılarak @rol etiketi tamamen silinir!
            await cagri_msg.edit(content=None, embed=gri_embed, view=view)
            print(f"[MOD ÇAĞRI ÇÖZÜLDÜ] {mod_name}, {cagri_bilgi['player_name']} çağrısını devraldı. Log griye döndü ve etiket silindi.", flush=True)
        except Exception as e:
            print(f"[MOD ÇAĞRI HATA] Log düzenlenemedi: {e}", flush=True)

        cagri_bilgi["status"] = "cozuldu_to"
        cagri_bilgi["moderator"] = mod_name
        cagri_bilgi["moderator_id"] = mod_id
        cagri_bilgi["cozulme_ts"] = cmd_ts

        cagri_data = load_json(CAGRILAR_FILE, {"aktif_cagrilar": {}, "gecmis_cagrilar": []})
        cagri_data.setdefault("gecmis_cagrilar", []).append(cagri_bilgi)
        cagri_data["gecmis_cagrilar"] = cagri_data["gecmis_cagrilar"][-100:]
        cagri_data["aktif_cagrilar"] = self.aktif_cagrilar
        await async_save_json(CAGRILAR_FILE, cagri_data)

    @tasks.loop(seconds=8)
    async def mod_takip_loop(self):
        """
        ER:LC API'sini her 8 saniyede bir sorgular:
        1. !mod / :mod çağrılarını hem ModCalls hem de CommandLogs üzerinden tespit eder.
        2. :to [oyuncu] atan moderatörleri tespit edip logu griye çevirir ve rol etiketini siler.
        """
        if not self.bot.is_ready():
            return

        # 10 dakikadan eski veya kapanmış çağrıları otomatik olarak aktif RAM'den düşür
        self.stale_cagrilari_temizle()

        api_key = os.getenv("ERLC_API_KEY")
        if not api_key:
            return

        kanal = self.bot.get_channel(MOD_LOG_KANAL_ID)
        if not kanal:
            try:
                kanal = await self.bot.fetch_channel(MOD_LOG_KANAL_ID)
            except Exception:
                return

        # ER:LC API Verilerini Çek
        try:
            session = await self.get_session()
            headers = {"Server-Key": api_key}
            url = "https://api.erlc.gg/v2/server?CommandLogs=true&ModCalls=true"
            async with session.get(url, headers=headers, timeout=6) as resp:
                if resp.status != 200:
                    err_txt = await resp.text()
                    print(f"[MOD ÇAĞRI API HATA] HTTP {resp.status}: {err_txt}", flush=True)
                    return
                data = await resp.json()
                command_logs = data.get("CommandLogs", [])
                mod_calls = data.get("ModCalls", [])
        except Exception as e:
            print(f"[MOD ÇAĞRI API BAĞLANTI HATASI] {e}", flush=True)
            return

        degisiklik_oldu = False

        # =========================================================================
        # 1. KAYNAK: ModCalls (ER:LC Resmi Moderatör Çağrı Listesi)
        # =========================================================================
        # NOT: ER:LC'nin ModCalls listesi oyun içi ":mod" komutundan tetiklenir.
        # Kullanıcı :mod ve ;mod çağrılarını kesinlikle istemediği için (SADECE !mod istendiği için),
        # ModCalls üzerinden yeni çağrı bildirimi GÖNDERİLMİYOR.
        # Sadece in-game bir yetkili çağrıyı devraldıysa (Moderator != null), aktif !mod çağrısını çözmek için kullanılır.
        if mod_calls:
            for mc in mod_calls:
                caller_raw = str(mc.get("Caller", "Bilinmiyor:0"))
                moderator_raw = mc.get("Moderator")
                ts = mc.get("Timestamp", 0)
                mc_id = f"mc_{caller_raw}_{ts}"

                caller_name = caller_raw.split(":")[0]
                caller_key = caller_name.lower()

                # A) Eğer henüz bir moderatör yanıtlamadıysa (Moderator == null):
                # :mod ve ;mod yok sayıldığından yeni bildirim atılmaz, sadece işlendi olarak işaretlenir.
                if not moderator_raw:
                    if mc_id not in self.islenen_komutlar:
                        self.islenen_komutlar.add(mc_id)
                        degisiklik_oldu = True

                # B) Eğer bir moderatör in-game yanıtladıysa (Moderator != null):
                else:
                    if caller_key in self.aktif_cagrilar:
                        mod_str = str(moderator_raw)
                        mod_name = mod_str.split(":")[0]
                        mod_id = mod_str.split(":")[1] if ":" in mod_str else "0"
                        await self.cagriyi_coz(kanal, caller_key, mod_name, mod_id, ts)
                        degisiklik_oldu = True

        # =========================================================================
        # 2. KAYNAK: CommandLogs (Tüm Komutlar: :mod, !mod, ;mod ve :to)
        # =========================================================================
        if command_logs:
            for item in command_logs:
                cmd = item.get("Command", "").strip()
                ts = item.get("Timestamp", 0)
                player_raw = str(item.get("Player", "Bilinmiyor:0"))
                komut_id = f"{player_raw}_{cmd}_{ts}"

                if komut_id in self.islenen_komutlar:
                    continue

                self.islenen_komutlar.add(komut_id)
                degisiklik_oldu = True

                cmd_lower = cmd.lower()

                # :mod ve ;mod kesinlikle yok sayılır (kullanıcı talebi: sadece !mod dikkate alınır)
                if cmd_lower.startswith((":mod", ";mod")):
                    print(f"[MOD ÇAĞRI YOK SAYILDI] {player_raw} komut: '{cmd}' (:mod ve ;mod devre dışı)", flush=True)
                    continue

                # A) Çağrı Komutları (SADECE !mod ve !modcall kabul edilir)
                if cmd_lower.startswith(("!mod", "!modcall")):
                    print(f"[MOD ÇAĞRI ALGILANDI] {player_raw} komut: '{cmd}'", flush=True)
                    caller_name = player_raw.split(":")[0]
                    caller_key = caller_name.lower()

                    if caller_key in self.aktif_cagrilar:
                        mevcut = self.aktif_cagrilar[caller_key]
                        now_ts = int(datetime.now(timezone.utc).timestamp())
                        if (now_ts - mevcut.get("timestamp", 0) > 600) or (mevcut.get("status") != "beklemede"):
                            self.aktif_cagrilar.pop(caller_key, None)
                        else:
                            print(f"[MOD ÇAĞRI ENGEL] {caller_name} zaten aktif çağrıda! Status: {mevcut.get('status')}", flush=True)

                    if caller_key not in self.aktif_cagrilar:
                        gerekce_parcalar = cmd.split(maxsplit=1)
                        gerekce = gerekce_parcalar[1] if len(gerekce_parcalar) > 1 else "*Gerekçe belirtilmedi*"
                        await self.discorda_cagri_gonder(kanal, player_raw, gerekce, ts)

                # B) Moderatör Müdahale Komutları (:to [oyuncu], :tp [oyuncu], :bring [oyuncu], :goto [oyuncu])
                for prefix in (":to ", ":tp ", ":bring ", ";to ", "!to ", ":goto ", ";goto ", "!goto ", ":teleport "):
                    if cmd_lower.startswith(prefix):
                        hedef_isim = cmd_lower[len(prefix):].strip()
                        mod_name = player_raw.split(":")[0]
                        mod_id = player_raw.split(":")[1] if ":" in player_raw else "0"

                        # Aktif çağrılarda bu hedefle eşleşen var mı?
                        for caller_key in list(self.aktif_cagrilar.keys()):
                            if hedef_isim == caller_key or hedef_isim in caller_key or caller_key in hedef_isim:
                                await self.cagriyi_coz(kanal, caller_key, mod_name, mod_id, ts)
                                break
                        break

        # Verileri kaydet
        if degisiklik_oldu:
            if len(self.islenen_komutlar) > 500:
                self.islenen_komutlar = set(list(self.islenen_komutlar)[-300:])
            await async_save_json(ISLENEN_KOMUTLAR_FILE, {"islenen_id": list(self.islenen_komutlar)})

            cagri_data = load_json(CAGRILAR_FILE, {"aktif_cagrilar": {}, "gecmis_cagrilar": []})
            cagri_data["aktif_cagrilar"] = self.aktif_cagrilar
            await async_save_json(CAGRILAR_FILE, cagri_data)

    @mod_takip_loop.before_loop
    async def before_mod_takip(self):
        await self.bot.wait_until_ready()

    # =========================================================================
    # TEST VE YÖNETİM SLASH KOMUTLARI (Kurucuya Özel)
    # =========================================================================
    @app_commands.command(name="test-cagri", description="Moderatör çağrı sistemini test etmek için sanal çağrı gönderir.")
    @app_commands.describe(
        roblox_adi="Test çağrısı yapacak oyuncunun Roblox adı",
        sebep="Çağrı gerekçesi"
    )
    async def test_cagri(self, interaction: discord.Interaction, roblox_adi: str, sebep: Optional[str] = "Test Çağrısı (RDM İhbarı)"):
        if interaction.user.id != ASIL_KURUCU_ID and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Bu komutu sadece **Kurucu** kullanabilir!", ephemeral=True)

        kanal = self.bot.get_channel(MOD_LOG_KANAL_ID)
        if not kanal:
            return await interaction.response.send_message(f"❌ Hedef kanal (<#{MOD_LOG_KANAL_ID}>) bulunamadı!", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        now_ts = int(datetime.now(timezone.utc).timestamp())
        msg = await self.discorda_cagri_gonder(kanal, f"{roblox_adi}:999999", sebep, now_ts)

        if msg:
            await interaction.followup.send(
                f"✅ Test çağrısı başarıyla {kanal.mention} kanalına gönderildi!\nŞimdi test için `/test-to roblox_adi:{roblox_adi}` komutunu kullanabilir veya butona basabilirsiniz.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"❌ Test çağrısı gönderilemedi. Lütfen botun {kanal.mention} kanalındaki izinlerini kontrol edin!",
                ephemeral=True
            )

    @app_commands.command(name="test-to", description="Moderatörün oyunda :to attığı durumu simüle eder.")
    @app_commands.describe(
        roblox_adi="Çağrıyı yapan oyuncunun Roblox adı",
        mod_adi="Oyuncuya ışınlanan moderatörün adı"
    )
    async def test_to(self, interaction: discord.Interaction, roblox_adi: str, mod_adi: Optional[str] = "YoneticiMod"):
        if interaction.user.id != ASIL_KURUCU_ID and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Bu komutu sadece **Kurucu** kullanabilir!", ephemeral=True)

        kanal = self.bot.get_channel(MOD_LOG_KANAL_ID)
        if not kanal:
            return await interaction.response.send_message(f"❌ Hedef kanal (<#{MOD_LOG_KANAL_ID}>) bulunamadı!", ephemeral=True)

        caller_key = roblox_adi.lower()
        if caller_key not in self.aktif_cagrilar:
            return await interaction.response.send_message(
                f"❌ `{roblox_adi}` adına ait aktif bir çağrı bulunamadı. Önce `/test-cagri` atın.",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)
        now_ts = int(datetime.now(timezone.utc).timestamp())
        await self.cagriyi_coz(kanal, caller_key, mod_adi, "123456", now_ts)

        await interaction.followup.send(
            f"✅ `{mod_adi}` yetkilisinin `{roblox_adi}` oyuncusuna `:to` attığı simüle edildi. {kanal.mention} kanalındaki log griye dönmüş ve etiket silinmiş olmalı!",
            ephemeral=True
        )

    @app_commands.command(name="cagri-temizle", description="Aktif moderatör çağrı kuyruğunu veya belirtilen oyuncunun çağrısını sıfırlar.")
    @app_commands.describe(
        roblox_adi="Sıfırlanacak oyuncunun Roblox adı (boş bırakılırsa tüm aktif çağrılar temizlenir)"
    )
    async def cagri_temizle(self, interaction: discord.Interaction, roblox_adi: Optional[str] = None):
        if interaction.user.id != ASIL_KURUCU_ID and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Bu komutu sadece **Kurucu** veya **Yönetici** kullanabilir!", ephemeral=True)

        cagri_data = load_json(CAGRILAR_FILE, {"aktif_cagrilar": {}, "gecmis_cagrilar": []})
        aktif_disk = cagri_data.get("aktif_cagrilar", {})

        if roblox_adi:
            caller_key = roblox_adi.lower()
            ram_silindi = self.aktif_cagrilar.pop(caller_key, None)
            disk_silindi = aktif_disk.pop(caller_key, None)
            cagri_data["aktif_cagrilar"] = self.aktif_cagrilar
            await async_save_json(CAGRILAR_FILE, cagri_data)

            if ram_silindi or disk_silindi:
                await interaction.response.send_message(
                    f"✅ `{roblox_adi}` adlı oyuncunun aktif çağrısı sıfırlandı. Artık yeni `!mod` atabilir.",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    f"ℹ️ `{roblox_adi}` adına ait aktif bir çağrı bulunamadı.",
                    ephemeral=True
                )
        else:
            toplam = len(self.aktif_cagrilar)
            self.aktif_cagrilar.clear()
            cagri_data["aktif_cagrilar"] = {}
            await async_save_json(CAGRILAR_FILE, cagri_data)
            await interaction.response.send_message(
                f"✅ Toplam **{toplam}** aktif çağrı tamamen temizlendi ve sıfırlandı.",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(ModCagri(bot))
