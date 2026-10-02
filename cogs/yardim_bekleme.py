import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import datetime

from utils.storage import load_json, save_json_atomic

# ============================
# KANAL VE ROL ID'LERİ (İsteğine göre ayarlandı)
YARDIM_BEKLEME_VC_ID = 1532829788824404274
YARDIM_VC_ID = 1532829837150916719
ONEMLI_LOG_KANALI = 1532829734742786168
ONLY_MOD_KANALI = 1532828404347437287
DESTEK_BEKLEME_YETKILISI_ROL = 1553473785527537765

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATA_FILE = os.path.join(DATA_DIR, "mod_stats.json")
DESTEK_ID_FILE = os.path.join(DATA_DIR, "destek_id.json")
GUNLUK_HEDEF_SANIYE = 5 * 60 * 60  # 5 saat
# ============================

def load_stats():
    return load_json(DATA_FILE, {})

def save_stats(data):
    save_json_atomic(DATA_FILE, data)

def update_mod_stat(mod_id, key, amount=1):
    data = load_stats()
    mod_id = str(mod_id)
    if mod_id not in data: data[mod_id] = {"voice_time": 0, "supports": 0, "tickets": 0}
    data[mod_id][key] += amount
    save_stats(data)

def progress_bar(current, total, length=15):
    progress = min(1.0, current / total)
    filled = int(length * progress)
    return "█" * filled + "░" * (length - filled)


class DestekBitirModal(discord.ui.Modal, title="Desteği Sonlandır"):
    sonuc = discord.ui.TextInput(
        label="Katılımcı Neden Yardım İstedi? Sonuç Ne?",
        style=discord.TextStyle.paragraph,
        placeholder="Örn: Kullanıcının kayıt sorunu çözüldü, kurallar hatırlatıldı.",
        required=True,
        max_length=1000
    )

    def __init__(self, baslangic_zamani: datetime.datetime, yardim_isteyen_id: int):
        super().__init__()
        self.baslangic_zamani = baslangic_zamani
        self.yardim_isteyen_id = yardim_isteyen_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        bitis_zamani = discord.utils.utcnow()
        fark = bitis_zamani - self.baslangic_zamani
        dakika = int(fark.total_seconds() // 60)
        saniye = int(fark.total_seconds() % 60)
        sure_metni = f"{dakika} dk {saniye} sn"

        update_mod_stat(interaction.user.id, "supports", 1)

        log_kanal = interaction.guild.get_channel(ONLY_MOD_KANALI)
        if log_kanal:
            embed = discord.Embed(title="✅ Destek Sonlandırıldı", color=discord.Color.green())
            embed.description = f"{interaction.user.mention}, <@{self.yardim_isteyen_id}> kullanıcısının desteğini sonlandırdı.\n**Süre:** {sure_metni}\n**Sonuç:** {self.sonuc.value}"
            await log_kanal.send(embed=embed)

        await interaction.message.edit(content=f"✅ {interaction.user.mention} desteği sonlandırdı.", view=None, embed=None)
        await interaction.followup.send("Destek başarıyla sonlandırıldı ve log iletildi.", ephemeral=True)


class DestekAktifView(discord.ui.View):
    def __init__(self, yetkili_id: int = None, yardim_isteyen_id: int = None, baslangic_zamani: datetime.datetime = None):
        super().__init__(timeout=None)
        self.yetkili_id = yetkili_id
        self.yardim_isteyen_id = yardim_isteyen_id
        self.baslangic_zamani = baslangic_zamani

    def _get_meta(self, interaction: discord.Interaction):
        yetkili_id = self.yetkili_id
        yardim_isteyen_id = self.yardim_isteyen_id
        baslangic = self.baslangic_zamani or discord.utils.utcnow()

        if interaction.message and interaction.message.embeds:
            footer = interaction.message.embeds[0].footer.text or ""
            for item in footer.split("|"):
                if item.startswith("yetkili:"):
                    try:
                        yetkili_id = int(item.split(":")[1])
                    except:
                        pass
                elif item.startswith("kullanici:"):
                    try:
                        yardim_isteyen_id = int(item.split(":")[1])
                    except:
                        pass
                elif item.startswith("baslangic:"):
                    try:
                        baslangic = datetime.datetime.fromtimestamp(int(item.split(":")[1]), tz=datetime.timezone.utc)
                    except:
                        pass
        return yetkili_id, yardim_isteyen_id, baslangic

    @discord.ui.button(label="Desteği Bitir", style=discord.ButtonStyle.success, emoji="✅", custom_id="destek_bitir_btn")
    async def bitir_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        yetkili_id, yardim_isteyen_id, baslangic = self._get_meta(interaction)
        if yetkili_id and interaction.user.id != yetkili_id and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Sadece desteği devralan yetkili bu işlemi yapabilir!", ephemeral=True)
        await interaction.response.send_modal(DestekBitirModal(baslangic, yardim_isteyen_id or 0))

    @discord.ui.button(label="Boş Çıktı", style=discord.ButtonStyle.secondary, emoji="🗑️", custom_id="destek_bos_btn")
    async def bos_cikti_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        yetkili_id, yardim_isteyen_id, _ = self._get_meta(interaction)
        if yetkili_id and interaction.user.id != yetkili_id and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Sadece desteği devralan yetkili bu işlemi yapabilir!", ephemeral=True)
        await interaction.response.defer()
        
        log_kanal = interaction.guild.get_channel(ONLY_MOD_KANALI)
        if log_kanal:
            embed = discord.Embed(title="❌ Destek Boş Çıktı", color=discord.Color.light_grey())
            embed.description = f"{interaction.user.mention}, <@{yardim_isteyen_id}> kullanıcısının desteğini **'Boş'** olarak sonuçlandırdı."
            await log_kanal.send(embed=embed)

        await interaction.message.edit(content=f"❌ {interaction.user.mention} desteği boş olarak sonlandırdı.", view=None, embed=None)
        await interaction.followup.send("Kullanıcı boş çıktığı için destek sonlandırıldı.", ephemeral=True)


class DevralView(discord.ui.View):
    def __init__(self, yardim_isteyen_id: int = None):
        super().__init__(timeout=None)
        self.yardim_isteyen_id = yardim_isteyen_id

    def _get_kullanici_id(self, interaction: discord.Interaction):
        if self.yardim_isteyen_id:
            return self.yardim_isteyen_id
        if interaction.message and interaction.message.embeds:
            footer = interaction.message.embeds[0].footer.text or ""
            if "destek_kullanici:" in footer:
                try:
                    return int(footer.split("destek_kullanici:")[1].strip())
                except Exception:
                    pass
        if interaction.message and interaction.message.mentions:
            return interaction.message.mentions[0].id
        return None

    @discord.ui.button(label="Katılımcıyı Devral", style=discord.ButtonStyle.success, emoji="👋", custom_id="destek_devral_btn")
    async def devral_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        guild = interaction.guild
        kullanici_id = self._get_kullanici_id(interaction)
        yardim_isteyen = guild.get_member(kullanici_id) if kullanici_id else None
        yardim_kanal = guild.get_channel(YARDIM_VC_ID)

        if not yardim_isteyen or not yardim_isteyen.voice:
            await interaction.followup.send("❌ Katılımcı şu anda seste değil!", ephemeral=True)
            await interaction.message.edit(content="❌ Katılımcı sesten ayrıldığı için işlem iptal edildi.", view=None, embed=None)
            return

        try:
            await yardim_isteyen.move_to(yardim_kanal)
            await yardim_isteyen.edit(mute=False)
        except Exception:
            await interaction.followup.send("❌ Kullanıcı odaya çekilirken hata oluştu. (Belki sesten çıkmıştır)", ephemeral=True)
            return

        baslangic = discord.utils.utcnow()
        active_embed = discord.Embed(
            title="🎧 Destek Devralındı",
            description=f"👋 {interaction.user.mention}, <@{kullanici_id}> kullanıcısının desteğini devraldı.\n(Odaya çekildi ve susturması açıldı)",
            color=discord.Color.blue()
        )
        active_embed.set_footer(text=f"yetkili:{interaction.user.id}|kullanici:{kullanici_id}|baslangic:{int(baslangic.timestamp())}")

        await interaction.message.edit(
            content=None,
            embed=active_embed,
            view=DestekAktifView(interaction.user.id, kullanici_id, baslangic)
        )
        await interaction.followup.send("Destek başarıyla devralındı.", ephemeral=True)

    @discord.ui.button(label="Beklemeden Çıkar", style=discord.ButtonStyle.danger, emoji="🚪", custom_id="destek_at_btn")
    async def at_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        guild = interaction.guild
        kullanici_id = self._get_kullanici_id(interaction)
        yardim_isteyen = guild.get_member(kullanici_id) if kullanici_id else None

        if yardim_isteyen and yardim_isteyen.voice:
            try:
                await yardim_isteyen.move_to(None)
            except Exception:
                pass

        log_kanal = interaction.guild.get_channel(ONLY_MOD_KANALI)
        if log_kanal:
            embed = discord.Embed(title="🚪 Katılımcı Atıldı", color=discord.Color.red())
            embed.description = f"{interaction.user.mention}, <@{kullanici_id}> kullanıcısını **Yardım Bekleme** kanalından beklemeden çıkardı."
            await log_kanal.send(embed=embed)

        await interaction.message.edit(content=f"🚪 {interaction.user.mention}, katılımcıyı beklemeden çıkardı.", view=None, embed=None)


class YardimBekleme(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_voice_sessions = {}
        self.gunluk_rapor.start()

    @app_commands.command(name="destek-bildir", description="Belirtilen kullanıcıyı destek bekleme odasına yönlendirir.")
    @app_commands.describe(
        kisi="Çağrılacak kişi",
        sebep="Çağrı sebebi",
        tahmini_sure="Tahmini destek süresi"
    )
    async def destek_bildir(self, interaction: discord.Interaction, kisi: discord.Member, sebep: str, tahmini_sure: str):
        admin_roles = {
            1529546007635824680: "Kurucu",
            1539167256246747186: "Üst Yönetim",
            1534798061845483694: "Yönetici",
            1537934087166369812: "Yönetim Ekibi",
            1551241753137254611: "Senior Staff",
            1551241634094645288: "Staff",
            1551241468985737376: "Trial Staff"
        }
        
        yetkili_rol_adi = "Yetkili"
        for role_id, role_name in admin_roles.items():
            if discord.utils.get(interaction.user.roles, id=role_id):
                yetkili_rol_adi = role_name
                break
                
        user_roles = {
            1539249508314259567: "İllegal",
            1539318613498929193: "Legal"
        }
        
        kisi_rol_adi = "Sivil"
        for role_id, role_name in user_roles.items():
            if discord.utils.get(kisi.roles, id=role_id):
                kisi_rol_adi = role_name
                break
                
        def get_next_destek_id():
            os.makedirs(DATA_DIR, exist_ok=True)
            if not os.path.exists(DESTEK_ID_FILE):
                last_id = 0
            else:
                try:
                    with open(DESTEK_ID_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        last_id = data.get("last_id", 0)
                except Exception:
                    last_id = 0
            new_id = last_id + 1
            with open(DESTEK_ID_FILE, "w", encoding="utf-8") as f:
                json.dump({"last_id": new_id}, f, indent=4, ensure_ascii=False)
            return f"PRP-{new_id:05d}"
            
        destek_id = get_next_destek_id()
        
        embed = discord.Embed(
            description=(
                f"## ✉️ Destek Çağrı Bildirimi\n"
                f"Kullanıcı destek bekleme ses kanalına yönlendirildi.\n"
                f"{kisi.mention} | {kisi_rol_adi}\n\n"
                f"***\n\n"
                f"### 📌 Çağrı Bilgisi\n"
                f"• **Çağrı ID:** {destek_id}\n"
                f"• **Kullanıcı:** {kisi.mention} | {kisi_rol_adi}\n"
                f"• **Çağıran Yetkili:** {interaction.user.mention} | {yetkili_rol_adi}\n"
                f"• **Süre:** {tahmini_sure}\n\n"
                f"***\n\n"
                f"### ✨ Yönlendirme\n"
                f"• **Sebep:** {sebep}\n\n"
                f"Lütfen [Yardım bekleme](https://discord.com/channels/1529545898294509589/1532829788824404274) ses kanalına geçiniz. Yetkili hazır olduğunda destek odasına alınacaksınız."
            ),
            color=discord.Color.from_rgb(254, 231, 92) # #FEE75C in RGB
        )
        
        embed.set_footer(text="© 2026 PRP")
        
        logo_path = os.path.join(BASE_DIR, "assets", "uyari_logo.png")
        if not os.path.exists(logo_path):
            logo_path = os.path.join(BASE_DIR, "assets", "yeni_banner.png")
            
        file_attachment = None
        if os.path.exists(logo_path):
            file_attachment = discord.File(logo_path, filename="logo.png")
            embed.set_thumbnail(url="attachment://logo.png")
        elif interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
            
        target_channel = interaction.client.get_channel(1552041858530672670)
        if target_channel:
            if file_attachment:
                await target_channel.send(content=f"{kisi.mention}", embed=embed, file=file_attachment)
            else:
                await target_channel.send(content=f"{kisi.mention}", embed=embed)
            await interaction.response.send_message("✅ Bildirim başarıyla gönderildi.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Hedef kanal bulunamadı (1552041858530672670).", ephemeral=True)

    def cog_unload(self):
        self.gunluk_rapor.cancel()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot: return

        if before.channel is None and after.channel is not None:
            # Yalnızca yetkililerin ses süresini takip et
            if any(r.id == DESTEK_BEKLEME_YETKILISI_ROL for r in member.roles):
                self.active_voice_sessions[member.id] = discord.utils.utcnow()
        elif before.channel is not None and after.channel is None:
            if member.id in self.active_voice_sessions:
                join_time = self.active_voice_sessions.pop(member.id)
                fark = (discord.utils.utcnow() - join_time).total_seconds()
                update_mod_stat(member.id, "voice_time", fark)

        if after.channel and after.channel.id == YARDIM_BEKLEME_VC_ID and (before.channel is None or before.channel.id != YARDIM_BEKLEME_VC_ID):
            try:
                await member.edit(mute=True)
            except Exception:
                pass
            
            kanal = self.bot.get_channel(ONEMLI_LOG_KANALI)
            if kanal:
                embed = discord.Embed(
                    title="👀 Yardım Bekleyen Var!", 
                    description=f"{member.mention} **Yardım Bekleme** kanalına giriş yaptı ve destek bekliyor.", 
                    color=discord.Color.orange()
                )
                embed.set_footer(text=f"destek_kullanici:{member.id}")
                embed.timestamp = discord.utils.utcnow()
                
                ping_msg = f"<@&{DESTEK_BEKLEME_YETKILISI_ROL}>"
                await kanal.send(content=ping_msg, embed=embed, view=DevralView(member.id))

        elif before.channel and before.channel.id == YARDIM_BEKLEME_VC_ID:
            if after.channel is not None and after.channel.id != YARDIM_BEKLEME_VC_ID:
                try:
                    await member.edit(mute=False)
                except Exception:
                    pass

    @tasks.loop(time=datetime.time(hour=21, minute=0, tzinfo=datetime.timezone.utc))
    async def gunluk_rapor(self):
        await self.bot.wait_until_ready()
        kanal = self.bot.get_channel(ONLY_MOD_KANALI)
        if not kanal: return

        data = load_stats()
        if not data:
            return await kanal.send("📊 **Günün Özeti:** Bugün hiçbir veri kaydedilmedi.")

        embed = discord.Embed(title="📊 Günlük Yetkili İstatistikleri", description="Günün analizi ve sıralama tablosu. Veriler sıfırlanıyor...", color=discord.Color.blue())
        
        for mod_id, stat in sorted(data.items(), key=lambda x: x[1]["voice_time"], reverse=True):
            user = self.bot.get_user(int(mod_id))
            if not user: continue
            
            toplam_saniye = stat["voice_time"]
            saat = int(toplam_saniye // 3600)
            dak = int((toplam_saniye % 3600) // 60)
            bar = progress_bar(toplam_saniye, GUNLUK_HEDEF_SANIYE)
            hedef_durum = "✅ Tamamlandı" if toplam_saniye >= GUNLUK_HEDEF_SANIYE else "❌ Eksik"

            aciklama = (
                f"**Ses Süresi:** {saat}s {dak}dk\n"
                f"**İlerleme:** `{bar}` ({hedef_durum})\n"
                f"**Baktığı Destek:** {stat['supports']}\n"
                f"**Baktığı Bilet:** {stat['tickets']}"
            )
            embed.add_field(name=f"👤 {user.display_name}", value=aciklama, inline=False)
            
        await kanal.send(embed=embed)
        save_stats({})
        self.active_voice_sessions.clear()


async def setup(bot):
    await bot.add_cog(YardimBekleme(bot))
    # Persistent views: bot restart sonrası aktif destek mesajlarındaki butonlar çalışmaya devam eder
    # bot.add_view(DestekAktifView(...) removed to fix cog loading)
    # bot.add_view(DevralView(...) removed to fix cog loading
