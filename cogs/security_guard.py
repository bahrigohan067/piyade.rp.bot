import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from datetime import timedelta, datetime
import collections
import os
import json

# ================= KORUMA AYARLARI =================
SPAM_MESSAGE_LIMIT = 5
SPAM_TIME_SECONDS = 5
SPAM_TIMEOUT_DURATION = 5  # Dakika

RAID_JOIN_LIMIT = 5
RAID_TIME_SECONDS = 15

NUKE_ACTION_LIMIT = 3
NUKE_TIME_SECONDS = 30

WHITELISTED_ROLES = [1529546007635824680, 1539167256246747186]

SECURITY_LOG_CHANNEL_ID = 1555275542452772934
RAID_BYPASS_LOG_CHANNEL = 1533621981830844538

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
SECURITY_DATA_FILE = os.path.join(DATA_DIR, "security_settings.json")
os.makedirs(DATA_DIR, exist_ok=True)

from utils.storage import load_json, save_json_atomic

def load_security_data():
    return load_json(SECURITY_DATA_FILE, {})

def save_security_data(data):
    save_json_atomic(SECURITY_DATA_FILE, data)

class RaidBypassView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Etkinleştir", style=discord.ButtonStyle.success, custom_id="raid_enable_btn", emoji="🛡️")
    async def enable_raid(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Sadece kurucu
        if 1529546007635824680 not in [r.id for r in interaction.user.roles] and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Bu butonu sadece Kurucu kullanabilir!", ephemeral=True)
            
        data = load_security_data()
        data["raid_bypass_until"] = None
        save_security_data(data)
        
        button.disabled = True
        button.label = "Yeniden Aktif Edildi"
        button.style = discord.ButtonStyle.secondary
        await interaction.response.edit_message(content=f"✅ **Raid Koruması (Saldırı Modu) {interaction.user.mention} tarafından erkenden YENİDEN AKTİF edildi!**", embed=None, view=self)
        
        # Güvenlik loguna da bildir
        sec_cog = interaction.client.get_cog("SecurityGuard")
        if sec_cog:
            await sec_cog.alert(interaction.guild, "Raid Koruması Aktif Edildi", f"Raid koruması manuel olarak {interaction.user.mention} tarafından tekrar açıldı.", discord.Color.green())

class SecurityGuard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_messages = collections.defaultdict(list)
        self.recent_joins = []
        self.raid_mode = False
        self.admin_actions = collections.defaultdict(list)
        self.log_channel = None
        self.raid_cooldown_task = None
        self.bot.add_view(RaidBypassView())

    def is_raid_bypassed(self):
        data = load_security_data()
        bypass_str = data.get("raid_bypass_until")
        if bypass_str:
            bypass_time = datetime.fromisoformat(bypass_str)
            if datetime.now() < bypass_time:
                return True
        return False

    async def get_log_channel(self, guild):
        if self.log_channel:
            return self.log_channel
        kanal = guild.get_channel(SECURITY_LOG_CHANNEL_ID)
        if kanal:
            self.log_channel = kanal
            return kanal
        for channel in guild.text_channels:
            if "güvenlik" in channel.name.lower() or "security" in channel.name.lower():
                self.log_channel = channel
                return channel
        return None

    def is_whitelisted(self, member):
        if member.id == member.guild.owner_id:
            return True
        for role in member.roles:
            if role.id in WHITELISTED_ROLES:
                return True
            if role.permissions.administrator:
                pass
        return False

    async def alert(self, guild, title, description, color=discord.Color.red()):
        kanal = await self.get_log_channel(guild)
        if kanal:
            embed = discord.Embed(title=f"🛡️ {title}", description=description, color=color)
            embed.timestamp = discord.utils.utcnow()
            try:
                await kanal.send(content="<@&1529546007635824680> 🚨 **GÜVENLİK UYARISI**", embed=embed)
            except:
                pass

    @app_commands.command(name="raidmod_kapa", description="Raid (Saldırı) korumasını 24 saatliğine kapatır (Sadece Kurucu).")
    async def raidmod_kapa(self, interaction: discord.Interaction):
        if 1529546007635824680 not in [r.id for r in interaction.user.roles] and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Bu komutu sadece Kurucu kullanabilir!", ephemeral=True)
            
        now = datetime.now()
        bypass_until = now + timedelta(hours=24)
        
        data = load_security_data()
        data["raid_bypass_until"] = bypass_until.isoformat()
        save_security_data(data)
        
        self.raid_mode = False # Mevcut raid modunu da kapat
        self.recent_joins.clear()
        
        await interaction.response.send_message("✅ Raid Koruması 24 saatliğine başarıyla kapatıldı! Bildirim kanalına gönderiliyor...", ephemeral=True)
        
        log_channel = interaction.guild.get_channel(RAID_BYPASS_LOG_CHANNEL)
        if log_channel:
            timestamp = int(bypass_until.timestamp())
            embed = discord.Embed(
                title="⚠️ Raid Koruması Devre Dışı", 
                description=f"Raid (Saldırı Modu) koruması yetkili tarafından geçici olarak durduruldu.\n\n⏳ **Otomatik Aktifleşme:** <t:{timestamp}:R>", 
                color=discord.Color.orange()
            )
            embed.set_footer(text=f"Kapatan: {interaction.user.display_name}")
            await log_channel.send(content="<@&1529546007635824680>", embed=embed, view=RaidBypassView())
            
        await self.alert(interaction.guild, "Raid Koruması Kapatıldı", f"{interaction.user.mention} tarafından 24 saatliğine durduruldu.", discord.Color.orange())

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        if self.is_whitelisted(message.author):
            return

        uid = message.author.id
        now = datetime.now()
        
        self.user_messages[uid].append((now, message))
        self.user_messages[uid] = [(t, msg) for t, msg in self.user_messages[uid] if (now - t).total_seconds() <= SPAM_TIME_SECONDS]
        
        if len(self.user_messages[uid]) > SPAM_MESSAGE_LIMIT:
            messages_to_delete = [msg for _, msg in self.user_messages[uid]]
            self.user_messages[uid].clear()
            try:
                await message.channel.delete_messages(messages_to_delete)
            except:
                pass
            try:
                await message.author.timeout(timedelta(minutes=SPAM_TIMEOUT_DURATION), reason="Anti-Spam: Hızlı mesaj gönderme.")
                await message.channel.send(f"⚠️ {message.author.mention}, spam yaptığınız için {SPAM_TIMEOUT_DURATION} dakika susturuldunuz!", delete_after=10)
                await self.alert(message.guild, "Anti-Spam Tetiklendi", f"👤 **Kullanıcı:** {message.author.mention}\n📍 **Kanal:** {message.channel.mention}\n⚡ **Sebep:** Kısa sürede çok fazla mesaj.")
            except discord.Forbidden:
                pass

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if self.is_raid_bypassed():
            return
            
        now = datetime.now()
        self.recent_joins.append(now)
        self.recent_joins = [t for t in self.recent_joins if (now - t).total_seconds() <= RAID_TIME_SECONDS]
        
        if len(self.recent_joins) > RAID_JOIN_LIMIT:
            if not self.raid_mode:
                self.raid_mode = True
                await self.alert(member.guild, "Anti-Raid / Spawn Koruması Aktif!", f"🚨 Sunucuya kısa sürede {RAID_JOIN_LIMIT}'den fazla giriş oldu!\nBot saldırısı (Raid) şüphesiyle yeni katılanlar otomatik olarak atılacak. Tehlike geçene kadar bu durum devam edecek.", discord.Color.dark_red())
            
        if self.raid_mode:
            try:
                await member.send("Sunucumuzda şu an yoğun bir giriş tespit edildiği için (Raid Modu) güvenlik amacıyla atıldınız. Lütfen bir süre sonra tekrar katılmayı deneyin.")
            except:
                pass
            try:
                await member.kick(reason="Anti-Raid Sistemi: Sunucu saldırı altında.")
            except:
                pass

            # Singleton Cooldown Task: Her giriş için ayrı sleep açmak yerine tek bir zamanlayıcı yönetilir
            if self.raid_cooldown_task and not self.raid_cooldown_task.done():
                self.raid_cooldown_task.cancel()
            self.raid_cooldown_task = asyncio.create_task(self._raid_cooldown_handler(member.guild))

    async def _raid_cooldown_handler(self, guild):
        try:
            await asyncio.sleep(30)
            now_check = datetime.now()
            if not any((now_check - t).total_seconds() <= 30 for t in self.recent_joins):
                if self.raid_mode:
                    self.raid_mode = False
                    await self.alert(guild, "Anti-Raid Modu Kapatıldı", "✅ Tehlike geçti, sunucu girişleri tekrar normale döndü.", discord.Color.green())
        except asyncio.CancelledError:
            pass

    async def check_nuke(self, guild, action_type, reason):
        await asyncio.sleep(2)
        try:
            async for entry in guild.audit_logs(limit=1, action=action_type):
                user = entry.user
                if user.bot or user.id == guild.owner_id:
                    continue
                member = guild.get_member(user.id)
                # Kurucu veya Üst Yönetim rolü / Sunucu Sahibi denetimi
                if member and (any(r.id in [1529546007635824680, 1539167256246747186] for r in member.roles) or member.id == guild.owner_id):
                    continue
                now = datetime.now()
                self.admin_actions[user.id].append(now)
                self.admin_actions[user.id] = [t for t in self.admin_actions[user.id] if (now - t).total_seconds() <= NUKE_TIME_SECONDS]
                if len(self.admin_actions[user.id]) >= NUKE_ACTION_LIMIT:
                    self.admin_actions[user.id].clear()
                    await self.alert(guild, "ANTI-NUKE TETİKLENDİ!", f"🚨 **Tespiti Yapılan Yetkili:** {user.mention} ({user.id})\n❌ **Eylem:** Çok kısa sürede çok fazla sunucu yapısına zarar verdi ({reason}).\n⚠️ **Otomatik İşlem:** Kullanıcının tüm yetkileri elinden alındı ve sunucudan uzaklaştırıldı!", discord.Color.dark_red())
                    try:
                        await user.ban(reason="Anti-Nuke: Sunucuya Zarar Verme Girişimi")
                    except Exception as e:
                        try:
                            silinecek = [r for r in user.roles if r.name != "@everyone"]
                            await user.remove_roles(*silinecek, reason="Anti-Nuke Koruması")
                        except:
                            pass
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        await self.check_nuke(channel.guild, discord.AuditLogAction.channel_delete, "Kanal Silme")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        await self.check_nuke(role.guild, discord.AuditLogAction.role_delete, "Rol Silme")

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        await self.check_nuke(guild, discord.AuditLogAction.ban, "Kullanıcı Banlama")

async def setup(bot):
    await bot.add_cog(SecurityGuard(bot))
