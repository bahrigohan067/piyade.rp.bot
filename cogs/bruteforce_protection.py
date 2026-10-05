import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta
import collections
import os

BRUTEFORCE_LIMIT = 7  # 3 saniye içinde 7'den fazla istek (insanüstü hız)
BRUTEFORCE_TIME_SECONDS = 3

LOG_CHANNEL_ID = 1555275542452772934
KURUCU_ROLE_ID = 1529546007635824680
UST_YONETIM_ROLE_ID = 1539167256246747186
YASAKLI_ROL_ID = 1534715583826759790

WHITELISTED_ROLES = [KURUCU_ROLE_ID, UST_YONETIM_ROLE_ID]

class BruteForceProtection(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Kullanıcı ID -> Zaman Damgaları listesi
        self.user_requests = collections.defaultdict(list)
        self.suspended_users = set()  # Aynı kişiye mükerrer işlem yapılmaması için

    def is_whitelisted(self, user):
        if not hasattr(user, "roles"):
            return False
        
        # Sunucu sahibi muaf
        if hasattr(user, "guild") and user.guild and user.id == user.guild.owner_id:
            return True
            
        for role in user.roles:
            if role.id in WHITELISTED_ROLES or role.permissions.administrator:
                return True
        return False

    async def suspend_member(self, member: discord.Member, guild: discord.Guild, title: str, reason: str, details: dict = None):
        """Kullanıcının rollerini alır, Yasaklı rolü verir, askıya alır (timeout) ve log kanalına bildirir."""
        if member.id in self.suspended_users:
            return

        # Kullanıcı zaten yasaklı/askıda ise tekrar tetiklenme
        if any(r.id == YASAKLI_ROL_ID for r in member.roles):
            return

        self.suspended_users.add(member.id)
        log_channel = guild.get_channel(LOG_CHANNEL_ID)

        # 1. LOG KANALINA DETAYLI BİLDİRİM
        if log_channel:
            embed = discord.Embed(
                title=f"🛡️ {title}",
                description=f"**Kullanıcı:** {member.mention} (`{member.id}`)\n**Sebep / Tespit:** {reason}",
                color=discord.Color.orange() if "PROFİL" in title.upper() else discord.Color.brand_red()
            )
            if details:
                for k, v in details.items():
                    embed.add_field(name=k, value=v, inline=True)

            embed.add_field(
                name="⚡ Uygulanan Güvenlik Önlemleri",
                value="• Kişinin tüm rolleri alındı.\n• Yasaklı (Askı) rolü verildi.\n• 28 gün süreyle askıya alındı (Timeout).",
                inline=False
            )
            embed.set_footer(text="Piyade Roleplay Güvenlik Kalkanı")
            embed.timestamp = discord.utils.utcnow()
            try:
                await log_channel.send(content=f"<@&{KURUCU_ROLE_ID}>", embed=embed)
            except Exception as e:
                print(f"[bruteforce_protection] Log gönderilemedi: {e}")

        # 2. KİŞİNİN TÜM ROLLERİNİ AL
        roles_to_remove = [
            r for r in member.roles
            if r.id != guild.id
            and not r.is_integration()
            and not r.is_premium_subscriber()
            and r < guild.me.top_role
        ]
        if roles_to_remove:
            try:
                await member.remove_roles(*roles_to_remove, reason=f"Güvenlik Kalkanı: {reason} - Tüm rolleri alındı")
            except Exception as e:
                print(f"[bruteforce_protection] Roller alınamadı: {e}")
                if log_channel:
                    try:
                        await log_channel.send(f"⚠️ Hata: {member.mention} kullanıcısının rolleri alınırken hata oluştu: {e}")
                    except:
                        pass

        # 3. YASAKLI ROLÜNÜ VER (ASKI ROLÜ)
        yasakli_rol = guild.get_role(YASAKLI_ROL_ID)
        if yasakli_rol and yasakli_rol < guild.me.top_role:
            try:
                await member.add_roles(yasakli_rol, reason=f"Güvenlik Kalkanı: {reason} - Askıya alındı")
            except Exception as e:
                print(f"[bruteforce_protection] Yasaklı rolü verilemedi: {e}")
                if log_channel:
                    try:
                        await log_channel.send(f"⚠️ Hata: {member.mention} kullanıcısına Yasaklı rolü verilemedi: {e}")
                    except:
                        pass

        # 4. KULLANICIYI ASKIYA AL (TIMEOUT - 28 GÜN)
        try:
            await member.timeout(timedelta(days=28), reason=f"Güvenlik Kalkanı: {reason} - Askıya alındı")
        except Exception as e:
            print(f"[bruteforce_protection] Timeout uygulanamadı: {e}")
            if log_channel:
                try:
                    await log_channel.send(f"⚠️ Hata: {member.mention} kullanıcısına timeout uygulanamadı: {e}")
                except:
                    pass

        # NOT: DUYURU KANALINA ASLA MESAJ GÖNDERİLMEZ (Duyuru mesajı gönderimi tamamen kaldırılmıştır)

    async def trigger_bruteforce_defense(self, member, guild, trigger_type):
        """API abuse ve brute-force saldırılarında kullanıcıyı askıya alır."""
        await self.suspend_member(
            member=member,
            guild=guild,
            title="BRUTE-FORCE / API SUİSTİMALİ ENGELLENDİ!",
            reason=trigger_type,
            details={"Tespit Yöntemi": f"`{trigger_type}`"}
        )

    async def register_request(self, user, guild, trigger_type):
        if user.bot or not guild:
            return
            
        if self.is_whitelisted(user):
            return
            
        uid = user.id
        now = datetime.now()
        
        self.user_requests[uid].append(now)
        # Sadece son N saniye içindeki istekleri tut
        self.user_requests[uid] = [t for t in self.user_requests[uid] if (now - t).total_seconds() <= BRUTEFORCE_TIME_SECONDS]
        
        if len(self.user_requests[uid]) >= BRUTEFORCE_LIMIT:
            self.user_requests[uid].clear()  # Temizle
            
            member = guild.get_member(uid)
            if member:
                await self.trigger_bruteforce_defense(member, guild, trigger_type)

    @commands.Cog.listener()
    async def on_message(self, message):
        # Normal mesaj atma hızı kontrolü (Eğer 3 saniyede 7 mesaj atıyorsa bu bir self-bot spam'idir)
        await self.register_request(message.author, message.guild, "Aşırı Hızlı Mesaj Gönderimi (Message Spam)")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        # Butonlara, menülere veya slash komutlara saniyeler içinde defalarca tıklayan API yazılımlarını engelle
        await self.register_request(interaction.user, interaction.guild, "Aşırı Hızlı API İsteği (Interaction Abuse)")
        
    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if after.bot or not after.guild:
            return
            
        guild = after.guild

        # Eğer yetkili tarafından Yasaklı rolü kaldırıldıysa, askı takip listesinden çıkar
        if YASAKLI_ROL_ID in [r.id for r in before.roles] and YASAKLI_ROL_ID not in [r.id for r in after.roles]:
            self.suspended_users.discard(after.id)
            return

        if self.is_whitelisted(after):
            return

        # Sadece gerçek profil değişikliklerini kontrol et (rol/durum oynamalarında tetiklenmez)
        nick_changed = (before.nick != after.nick)
        name_changed = (before.name != after.name or before.display_name != after.display_name)
        avatar_changed = (before.display_avatar.url != after.display_avatar.url)

        if not (nick_changed or name_changed or avatar_changed):
            return

        # Denetim kaydı (Audit Log) kontrolü: Değişiklik bot veya yetkili tarafından mı yapıldı?
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update):
                time_diff = (discord.utils.utcnow() - entry.created_at).total_seconds()
                if entry.target.id == after.id and time_diff <= 5:
                    if entry.user.id != after.id:
                        # Değişiklik bot (kayıt vs.) veya yetkili tarafından yapılmış, yoksay
                        return
                    break
        except Exception:
            pass

        # Değişiklik detaylarını topla
        degisiklikler = {}
        if nick_changed:
            degisiklikler["📝 Eski Sunucu İsmi"] = f"`{before.nick or 'Yok'}`"
            degisiklikler["📝 Yeni Sunucu İsmi"] = f"`{after.nick or 'Yok'}`"
        if name_changed:
            degisiklikler["👤 Eski Görünen Ad"] = f"`{before.display_name}`"
            degisiklikler["👤 Yeni Görünen Ad"] = f"`{after.display_name}`"
        if avatar_changed:
            degisiklikler["🖼️ Eski Avatar"] = f"[Görüntüle]({before.display_avatar.url})"
            degisiklikler["🖼️ Yeni Avatar"] = f"[Görüntüle]({after.display_avatar.url})"

        # 1. Hızlı Profil Güncellemesi Rate Limit Kontrolü
        await self.register_request(after, guild, "Aşırı Hızlı Profil Güncellemesi (API Abuse)")

        # 2. Profil Değişimi Bildirimi ve Askıya Alma (Rolleri al, Yasaklı ver, Timeout at)
        await self.suspend_member(
            member=after,
            guild=guild,
            title="PROFİL DEĞİŞİKLİĞİ TESPİT EDİLDİ",
            reason="İzinsiz Profil / İsim Güncellemesi",
            details=degisiklikler
        )

async def setup(bot):
    await bot.add_cog(BruteForceProtection(bot))
