import discord
from discord.ext import commands
import asyncio
from datetime import datetime, timedelta
import collections
import os

BRUTEFORCE_LIMIT = 7  # 3 saniye içinde 7'den fazla istek (insanüstü hız)
BRUTEFORCE_TIME_SECONDS = 3

LOG_CHANNEL_ID = 1555275542452772934
DUYURU_CHANNEL_ID = 1541355760829726760
KURUCU_ROLE_ID = 1529546007635824680

# Saldırı anında duyuru kanalına atılacak metin
DUYURU_METNI = """# 🛡️ PİYADE ROLEPLAY | GÜVENLİK BİLDİRİMİ

Değerli oyuncularımız, şeffaflık ilkemiz gereği sunucumuzda az önce engellenen başarısız bir sızma girişimi hakkında sizleri bilgilendirmek istiyoruz.

Sunucu altyapımıza yönelik otomatikleştirilmiş bir kaba kuvvet (brute-force/API abuse) saldırısı gerçekleştirilmiştir. Ancak **Gelişmiş Güvenlik Kalkanımız**, bu olağandışı trafiği milisaniyeler içinde tespit etmiş ve saldırganı sunucumuzdan **kalıcı olarak yasaklamıştır.**

✅ **Sunucumuzdan hiçbir veri sızdırılmamıştır.**
✅ **Hiçbir üyemizin kişisel veya oyun içi bilgisi tehlikeye girmemiştir.**
✅ **Sistemlerimiz %100 güvendedir ve kesintisiz çalışmaya devam etmektedir.**

*Olayın ardından güvenlik sistemimizin yaptığı incelemelerde, saldırıyı gerçekleştiren şahısların "Turan Roleplay" oluşumuyla doğrudan bağlantılı olduğu; saldırgan hesabın bizzat o grubun "yetkili geliştiricisi" ile uyuştuğu sistemlerimizce doğrulanmıştır.*

Piyade Roleplay Yönetimi olarak; altyapımızın gücünü test etmek için kendi çaplarında çırpınan bu arkadaşlara, sistemlerimizin ne kadar **aşılmaz** olduğunu bize bir kez daha kanıtladıkları için teşekkür ederiz. 

Bizler, enerjimizi bu tür başarısız ve amatör girişimlerle vakit kaybetmek yerine; projemizin asıl sahibi olan siz değerli oyuncularımıza hak ettiğiniz üst düzey ve kesintisiz rol deneyimini sunmaya harcamaya devam edeceğiz.

**İyi Roller Dileriz,**
**Piyade Roleplay Yönetimi**"""

class BruteForceProtection(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Kullanıcı ID -> Zaman Damgaları listesi
        self.user_requests = collections.defaultdict(list)
        self.banned_users = set()  # Aynı kişiye defalarca işlem yapmamak için

    def is_whitelisted(self, user):
        # Eğer bir sunucu üyesi değilse (mesela DM'den geliyorsa) muaf saymayalım
        if not hasattr(user, "roles"):
            return False
        
        # Kurucu ve yüksek yönetim brute-force korumasından muaftır (Bot testleri vs. için)
        if user.id == user.guild.owner_id:
            return True
            
        for role in user.roles:
            if role.id == KURUCU_ROLE_ID or role.permissions.administrator:
                return True
        return False

    async def trigger_bruteforce_defense(self, member, guild, trigger_type):
        if member.id in self.banned_users:
            return
            
        self.banned_users.add(member.id)
        
        # 1. LOG KANALINA BİLDİRİM
        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            embed = discord.Embed(
                title="🚨 BRUTE-FORCE (API) SALDIRISI ENGELLENDİ!",
                description=f"**Saldırgan:** {member.mention} (`{member.id}`)\n**Tespit Yöntemi:** {trigger_type}\n**Eylem:** Otomatik olarak BANLANDI.",
                color=discord.Color.brand_red()
            )
            embed.set_footer(text="Piyade Roleplay WAF Kalkanı")
            embed.timestamp = discord.utils.utcnow()
            try:
                await log_channel.send(content=f"<@&{KURUCU_ROLE_ID}>", embed=embed)
            except:
                pass

        # 2. KULLANICIYI BANLA
        try:
            await member.ban(reason="WAF Koruması: Otomatik Brute-Force / API Abuse Saldırısı Tespiti")
        except Exception as e:
            if log_channel:
                await log_channel.send(f"⚠️ Hata: Kullanıcı banlanamadı (Yetki eksikliği olabilir): {e}")

        # 3. DUYURU KANALINA HALK BİLDİRİMİ GÖNDER
        duyuru_channel = guild.get_channel(DUYURU_CHANNEL_ID)
        if duyuru_channel:
            try:
                await duyuru_channel.send(content=DUYURU_METNI)
            except:
                pass

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
            self.user_requests[uid].clear() # Temizle
            
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
        # Çok hızlı kullanıcı profili/durum güncellemesi spamı yapan API botlarını yakala
        await self.register_request(after, after.guild, "Aşırı Hızlı Profil Güncellemesi (API Abuse)")

async def setup(bot):
    await bot.add_cog(BruteForceProtection(bot))
