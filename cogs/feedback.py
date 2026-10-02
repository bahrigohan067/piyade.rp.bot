import discord
from discord.ext import commands
from discord import app_commands
import json
import os

FEEDBACK_LOG_KANAL_ID = 1551250833625186344

YETKILI_ROL_IDLERI = [
    1551241753137254611,  # Senior Staff
    1551241634094645288,  # Staff
    1551241468985737376,  # Trial Staff
    1529546007635824680,  # Kurucu
    1539167256246747186,  # Üst Yönetim
    1534798061845483694,  # Yönetici
    1537934087166369812,  # Yönetim ekibi
]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback_data.json")

os.makedirs(DATA_DIR, exist_ok=True)

def load_feedback():
    if not os.path.exists(FEEDBACK_FILE):
        return {}
    with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return {}

def save_feedback(data):
    with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def hedef_yetkili_mi(member: discord.Member) -> bool:
    return any(rol.id in YETKILI_ROL_IDLERI for rol in member.roles)

def yonetim_mi(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return any(rol.id in [1529546007635824680, 1539167256246747186] for rol in member.roles)

class FeedbackCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="feedback", description="Bir yetkiliyi anonim olarak değerlendirir.")
    @app_commands.describe(
        yetkili="Değerlendirmek istediğiniz yetkili",
        puan="1 ile 5 arasında bir puan verin",
        yorum="Yetkili hakkındaki yorumunuz"
    )
    @app_commands.checks.cooldown(1, 3600.0, key=lambda i: i.user.id)
    async def feedback_komutu(self, interaction: discord.Interaction, yetkili: discord.Member, puan: int, yorum: str):
        if interaction.user.id == yetkili.id:
            return await interaction.response.send_message("❌ Kendinize geri bildirim veremezsiniz!", ephemeral=True)

        if not hedef_yetkili_mi(yetkili):
            return await interaction.response.send_message("❌ Seçtiğiniz kişi yetkili kadrosunda değil. Sadece geçerli yetkilileri değerlendirebilirsiniz.", ephemeral=True)
            
        if puan < 1 or puan > 5:
            return await interaction.response.send_message("❌ Puanınız 1 ile 5 arasında olmalıdır!", ephemeral=True)
            
        kanal = self.bot.get_channel(FEEDBACK_LOG_KANAL_ID)
        if not kanal:
            return await interaction.response.send_message("❌ Feedback kanalı bulunamadı. Kurucuya haber verin.", ephemeral=True)

        data = load_feedback()
        yid = str(yetkili.id)
        if yid not in data:
            data[yid] = {"total": 0, "count": 0}
        
        data[yid]["total"] += puan
        data[yid]["count"] += 1
        save_feedback(data)

        yildizlar = "⭐" * puan

        embed = discord.Embed(
            title="📝 Yeni Yetkili Değerlendirmesi",
            color=discord.Color.gold()
        )
        embed.add_field(name="Yetkili", value=yetkili.mention, inline=False)
        embed.add_field(name="Puan", value=f"{yildizlar} ({puan}/5)", inline=False)
        embed.add_field(name="Yorum", value=yorum, inline=False)
        embed.set_footer(text="Bu değerlendirme anonim olarak gönderilmiştir.")
        embed.timestamp = discord.utils.utcnow()

        await kanal.send(embed=embed)
        await interaction.response.send_message("✅ Geri bildiriminiz başarıyla anonim olarak iletildi. Teşekkür ederiz!", ephemeral=True)


    @app_commands.command(name="ortalama-puan", description="Yetkililerin toplam geri bildirim ortalamalarını listeler.")
    async def ortalama_puan(self, interaction: discord.Interaction):
        if not yonetim_mi(interaction.user):
            return await interaction.response.send_message("❌ Bu komutu sadece Kurucu veya Üst Yönetim kullanabilir.", ephemeral=True)
            
        data = load_feedback()
        if not data:
            return await interaction.response.send_message("Henüz hiçbir yetkili için geri bildirim girilmemiş.", ephemeral=True)

        siralamalar = []
        for yid_str, stats in data.items():
            count = stats.get("count", 0)
            if count > 0:
                ortalama = stats["total"] / count
                siralamalar.append((int(yid_str), ortalama, count))
                
        # Ortalamaya göre büyükten küçüğe sırala
        siralamalar.sort(key=lambda x: x[1], reverse=True)
        
        desc = ""
        for i, (yid, ort, count) in enumerate(siralamalar, 1):
            desc += f"**{i}.** <@{yid}> — **{ort:.1f}/5** *(Toplam {count} oy)*\n"
            
        if not desc:
            desc = "Henüz yeterli veri yok."

        embed = discord.Embed(
            title="📊 Yetkili Geri Bildirim Ortalamaları",
            description=desc,
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(FeedbackCog(bot))
