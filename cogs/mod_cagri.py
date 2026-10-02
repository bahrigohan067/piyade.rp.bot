import discord
from discord.ext import commands, tasks
import aiohttp
import os
import asyncio
from datetime import datetime, timezone, timedelta
from utils.storage import load_json, save_json_atomic, async_save_json

# ==================== AYARLAR ====================
MOD_LOG_KANAL_ID = 1555628244806410280
MOD_ROL_ID = 1555628384166346752

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
        has_perm = interaction.user.guild_permissions.administrator or any(
            r.id == MOD_ROL_ID for r in interaction.user.roles
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

        # Veritabanından aktif çağrıyı kaldır
        cagri_data = load_json(CAGRILAR_FILE, {"aktif_cagrilar": {}, "gecmis_cagrilar": []})
        aktif = cagri_data.get("aktif_cagrilar", {})
        silinecek = None
        for k, v in aktif.items():
            if v.get("message_id") == msg.id:
                silinecek = k
                break
        if silinecek:
            kayit = aktif.pop(silinecek)
            kayit["status"] = "cozuldu_discord"
            kayit["closed_by"] = str(interaction.user)
            cagri_data.setdefault("gecmis_cagrilar", []).append(kayit)
            cagri_data["gecmis_cagrilar"] = cagri_data["gecmis_cagrilar"][-100:]
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

        self.mod_takip_loop.start()

    def cog_unload(self):
        self.mod_takip_loop.cancel()
        if self.session and not self.session.closed:
            self.bot.loop.create_task(self.session.close())

    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    @tasks.loop(seconds=10)
    async def mod_takip_loop(self):
        """
        ER:LC API'sini her 10 saniyede bir sorgular:
        1. !mod komutu atan kullanıcıları tespit edip Discord'a rol etiketiyle kırmızı log atar.
        2. Moderatörlerin attığı :to [kullanıcı] komutlarını tespit edip logu griye çevirir ve etiketi siler.
        """
        if not self.bot.is_ready():
            return

        api_key = os.getenv("ERLC_API_KEY")
        if not api_key:
            return

        kanal = self.bot.get_channel(MOD_LOG_KANAL_ID)
        if not kanal:
            try:
                kanal = await self.bot.fetch_channel(MOD_LOG_KANAL_ID)
            except Exception:
                return

        # ER:LC API'sinden hem CommandLogs hem de ModCalls verilerini çek
        try:
            session = await self.get_session()
            headers = {"Server-Key": api_key}
            url = "https://api.erlc.gg/v2/server?CommandLogs=true&ModCalls=true"
            async with session.get(url, headers=headers, timeout=7) as resp:
                if resp.status != 200:
                    return
                data = await resp.json()
                command_logs = data.get("CommandLogs", [])
                mod_calls = data.get("ModCalls", [])
        except Exception as e:
            # Sessiz geçiş (Geçici ağ hataları logu kirletmesin)
            return

        tz_tr = timezone(timedelta(hours=3))
        degisiklik_oldu = False

        # =========================================================================
        # 1. ADIM: !mod ÇAĞRILARINI TESPİT ET VE DİSCORD'A BİLDİR
        # =========================================================================
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
            # !mod, :mod veya benzeri moderatör çağrıları
            if cmd_lower.startswith(("!mod", ":mod", "!yardim", "!destek")):
                player_name = player_raw.split(":")[0]
                player_id = player_raw.split(":")[1] if ":" in player_raw else "0"
                player_key = player_name.lower()

                # Oyuncu zaten beklemede olan bir çağrıya sahipse mükerrer açma
                if player_key in self.aktif_cagrilar:
                    continue

                # Çağrı gerekçesi (Örn: !mod RDM Var -> RDM Var)
                gerekce_parcalar = cmd.split(maxsplit=1)
                gerekce = gerekce_parcalar[1] if len(gerekce_parcalar) > 1 else "*Gerekçe belirtilmedi (Sadece !mod yazıldı)*"

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

                # Mesajı gönder ve rolü etiketle
                try:
                    rol_etiketi = f"<@&{MOD_ROL_ID}>"
                    view = ModCagriView()
                    gonderilen_msg = await kanal.send(content=rol_etiketi, embed=embed, view=view)

                    self.aktif_cagrilar[player_key] = {
                        "player_raw": player_raw,
                        "player_name": player_name,
                        "player_id": player_id,
                        "message_id": gonderilen_msg.id,
                        "channel_id": kanal.id,
                        "gerekce": gerekce,
                        "timestamp": ts or int(datetime.now(timezone.utc).timestamp()),
                        "status": "beklemede"
                    }
                    print(f"[MOD ÇAĞRI] {player_name} oyuncusu !mod gönderdi. Discord'a iletildi.", flush=True)
                except Exception as e:
                    print(f"[MOD ÇAĞRI HATA] Bildirim gönderilemedi: {e}", flush=True)

        # =========================================================================
        # 2. ADIM: MODERATÖRÜN :to [kullanıcı] KOMUTLARINI TESPİT ET VE LOGU GRİYE ÇEVİR
        # =========================================================================
        if self.aktif_cagrilar:
            for item in command_logs:
                cmd = item.get("Command", "").strip()
                cmd_lower = cmd.lower()
                player_raw = str(item.get("Player", "Bilinmiyor:0"))
                mod_name = player_raw.split(":")[0]
                mod_id = player_raw.split(":")[1] if ":" in player_raw else "0"
                cmd_ts = item.get("Timestamp", 0)

                # Moderatör :to <hedef>, :tp <hedef> veya :bring <hedef> attı mı?
                hedef_isim = None
                for prefix in (":to ", ":tp ", ":bring "):
                    if cmd_lower.startswith(prefix):
                        hedef_isim = cmd_lower[len(prefix):].strip()
                        break

                if not hedef_isim:
                    continue

                # Aktif çağrı yapanlardan bu hedef ile eşleşen var mı?
                bulunan_cagri_key = None
                for caller_key in list(self.aktif_cagrilar.keys()):
                    # Tam eşleşme veya Roblox kullanıcı adı başlangıç eşleşmesi
                    if hedef_isim == caller_key or hedef_isim in caller_key or caller_key in hedef_isim:
                        bulunan_cagri_key = caller_key
                        break

                if not bulunan_cagri_key:
                    continue

                cagri_bilgi = self.aktif_cagrilar.pop(bulunan_cagri_key)
                degisiklik_oldu = True

                msg_id = cagri_bilgi.get("message_id")
                if not msg_id:
                    continue

                try:
                    cagri_msg = await kanal.fetch_message(msg_id)
                except Exception:
                    cagri_msg = None

                if not cagri_msg:
                    continue

                # Geçen süreyi hesapla
                ilk_ts = cagri_bilgi.get("timestamp", cmd_ts)
                fark_saniye = max(0, cmd_ts - ilk_ts) if (cmd_ts and ilk_ts) else 0
                if fark_saniye < 60:
                    sure_str = f"**{fark_saniye} saniye**"
                else:
                    dakika = fark_saniye // 60
                    saniye = fark_saniye % 60
                    sure_str = f"**{dakika} dakika {saniye} saniye**"

                # 🔘 GRİ EMBED HAZIRLA (Rol etiketi kaldırılacak)
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
                    # content=None yapılarak @rol etiketi tamamen silinir!
                    # View butonu pasif hale getirilir
                    view = ModCagriView()
                    for item_btn in view.children:
                        item_btn.disabled = True
                    await cagri_msg.edit(content=None, embed=gri_embed, view=view)
                    print(f"[MOD ÇAĞRI ÇÖZÜLDÜ] {mod_name}, {cagri_bilgi['player_name']} çağrısına :to attı. Log griye döndü ve etiket silindi.", flush=True)
                except Exception as e:
                    print(f"[MOD ÇAĞRI HATA] Log güncellenemedi: {e}", flush=True)

                # Geçmişe kaydet
                cagri_bilgi["status"] = "cozuldu_to"
                cagri_bilgi["moderator"] = mod_name
                cagri_bilgi["moderator_id"] = mod_id
                cagri_bilgi["cozulme_ts"] = cmd_ts

                cagri_data = load_json(CAGRILAR_FILE, {"aktif_cagrilar": {}, "gecmis_cagrilar": []})
                cagri_data.setdefault("gecmis_cagrilar", []).append(cagri_bilgi)
                cagri_data["gecmis_cagrilar"] = cagri_data["gecmis_cagrilar"][-100:]
                cagri_data["aktif_cagrilar"] = self.aktif_cagrilar
                await async_save_json(CAGRILAR_FILE, cagri_data)

        # Değişiklik varsa verileri diske kaydet
        if degisiklik_oldu:
            # Bellekteki işlenmiş komutları 300 ile sınırla (Hafıza şişmesini önler)
            if len(self.islenen_komutlar) > 500:
                self.islenen_komutlar = set(list(self.islenen_komutlar)[-300:])
            await async_save_json(ISLENEN_KOMUTLAR_FILE, {"islenen_id": list(self.islenen_komutlar)})

            cagri_data = load_json(CAGRILAR_FILE, {"aktif_cagrilar": {}, "gecmis_cagrilar": []})
            cagri_data["aktif_cagrilar"] = self.aktif_cagrilar
            await async_save_json(CAGRILAR_FILE, cagri_data)

    @mod_takip_loop.before_loop
    async def before_mod_takip(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(ModCagri(bot))
