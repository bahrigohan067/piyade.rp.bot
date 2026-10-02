import discord
from discord.ext import commands
from discord import app_commands
import asyncio

COMMAND_OWNER_ID = 1133815339898122320

ROLE_ORDER = [
    1545525713032184039, # 1
    1529546007635824680, # 2
    1542271077206458489, # 3
    1544590583106895913, # 4
    1542262938478575636, # 5
    1544152662784876627, # 6
    1547579436361060465, # 7
    1552707281857151087, # 8
    1540082352703676516, # 9
    1539167256246747186, # 10
    1546884597311348777, # 11
    1534798061845483694, # 12
    1547559312501641338, # 13
    1537934087166369812, # 14
    1551241753137254611, # 15
    1551241634094645288, # 16
    1551241468985737376, # 17
    1551545853141983232, # 18
    1551546608305573989, # 19
    1551242344190189718, # 20
    1553333289798869032, # 21
    1553473785527537765, # 22
    1553427352044707840, # 23
    1545685296539111494, # 24
    1543074569034801244, # 25
    1547526649459777556, # 26
    1543075759508164659, # 27
    1542249243702726796, # 28
    1539318613498929193, # 29
    1539249508314259567, # 30
    1540423283952976054, # 31
    1540417049518407751, # 32
    1539170698344271882, # 33
    1534712195709927605, # 34
    1534717680676765867, # 35
    1534724764948631703, # 36
    1551552841716334592, # 37
    1551553107492601876, # 38
    1533919249985437706, # 39
    1533908873772273715, # 40
    1542271426386591894, # 41
    1551287340444549191, # 42
    1551287502667776130, # 43
    1551287599983755405, # 44
    1534715251323572315, # 45
    1534715383507058749, # 46
    1534715488716853278, # 47
    1553054768388374620, # 48
    1553055210073497710, # 49
    1553053929087172768, # 50
    1534715583826759790, # 51
    1541223489246076990, # 52
    1534890486316138536, # 53
    1539169640326893589, # 54
    1541216852905041980, # 55
    1541216610751221851, # 56
    1541216359541645312, # 57
    1541216066532016310, # 58
    1541215599026372688, # 59
    1541215423301681252, # 60
    1541214087155810384, # 61
    1541213765410754640, # 62
    1534736939675160637, # 63
    1539169263124746350, # 64
    1534736940279005326, # 65
    1539170448548429885, # 66
    1534756885016871083, # 67
    1547589732937240627, # 68
    1541213549144317953, # 69
    1544777693030125720, # 70
    1534736940904218755, # 71
    1541213335012376678, # 72
    1534736941600342016, # 73
    1534736941973504032, # 74
    1542415011786526780, # 75
    1534741499726663690, # 76
    1534757047919317172, # 77
    1539361424487481404, # 78
    1534768485803102299, # 79
    1544692476218974228, # 80
    1534957731499212900, # 81
    1533621555920371825, # 82
    1534713383587418232, # 83
    1554843177263956148  # 84
]

class RoleManagerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_base_user_perms(self):
        perms = discord.Permissions.none()
        perms.update(
            view_channel=True,
            send_messages=True,
            embed_links=True,
            attach_files=True,
            read_message_history=True,
            use_application_commands=True,
            send_voice_messages=True,
            connect=True,
            speak=True,
            add_reactions=True,
            use_external_emojis=True,
            use_external_stickers=True
        )
        return perms

    def get_staff_perms(self):
        perms = self.get_base_user_perms()
        perms.update(
            manage_channels=True,
            manage_roles=True,
            manage_nicknames=True,
            change_nickname=True,
            manage_messages=True,
            manage_threads=True,
            create_public_threads=True,
            create_private_threads=True,
            mute_members=True,
            deafen_members=True,
            move_members=True,
            kick_members=True,
            ban_members=True,
            moderate_members=True,
            priority_speaker=True
        )
        return perms

    @app_commands.command(name="rol-sifirla", description="Sunucudaki tüm rolleri kurala göre ayarlar ve sıralar.")
    async def rol_sifirla(self, interaction: discord.Interaction):
        if interaction.user.id != COMMAND_OWNER_ID:
            return await interaction.response.send_message("❌ Bu komutu sadece Kurucu (Özel ID) kullanabilir!", ephemeral=True)
            
        await interaction.response.defer()
        
        guild = interaction.guild
        msg = await interaction.followup.send("🔄 **Rol hiyerarşisi ve izinleri sıfırlanıyor...** Lütfen bekleyin, bu işlem birkaç dakika sürebilir.", wait=True)
        
        # Siralama
        # Discord'da en yǬksek pozisyon = en Ǭstteki rol
        top_position = len(guild.roles) - 1 # @everyone hari
        
        # 1. ADIM: @everyone iznini ayarla
        everyone_role = guild.default_role
        try:
            await everyone_role.edit(permissions=self.get_base_user_perms(), reason="Toplu Rol Sfrlama: @everyone izinleri gǬncellendi")
        except:
            pass

        # 2. ADIM: Belirtilen tǬm rolleri gǬncelle
        hatalar = []
        basarili = 0
        
        # Admin rolleri
        admin_indices = [4, 5, 6, 7, 8, 82, 83]
        # Staff rolleri
        staff_indices = [10, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28]
        # Base (oye) rolleri
        user_indices = [39, 40, 41]
        
        for index, role_id in enumerate(ROLE_ORDER, start=1):
            if index in [1, 2, 3]:
                continue # Bu rollere dokunulmas yasak
                
            role = guild.get_role(role_id)
            if not role:
                hatalar.append(f"Rol bulunamad (Sira {index}: {role_id})")
                continue
                
            # zinleri belirle
            if index in admin_indices:
                perms = discord.Permissions(administrator=True)
            elif index in staff_indices:
                perms = self.get_staff_perms()
            elif index in user_indices:
                perms = self.get_base_user_perms()
            else:
                perms = discord.Permissions.none() # Hibir izne sahip deYildir
                
            try:
                # Botun rolǬnǬn yetmediYi veya deYiYtirilemeyen (Managed) rolleri atla
                if not role.managed and role < guild.me.top_role:
                    await role.edit(permissions=perms, reason="Toplu Rol Sfrlama: zinler sfrland")
                    basarili += 1
                await asyncio.sleep(0.5) # Rate limit korumas
            except Exception as e:
                hatalar.append(f"{role.name} yetkileri dǬzenlenemedi.")

        # 3. ADIM: Rolleri Srala
        # Discord apisinde edit_role_positions dict alr: {role: position, ...}
        # En alt = 1, En Ǭst = max
        # ROLE_ORDER en Ǭstten aYaY (1 = en yǬksek)
        
        roles_to_move = {}
        # Geerli olan tǬm rolleri filtrele
        valid_roles = [guild.get_role(rid) for rid in ROLE_ORDER if guild.get_role(rid)]
        
        # Sralama mantY: En sondaki (84.) rolǬn pozisyonu en dǬYǬk olmal.
        # Bu yǬzden valid_roles listesini ters evirip pozisyonlar 1'den baYlayarak artryoruz.
        current_position = 1
        for role in reversed(valid_roles):
            if role and role < guild.me.top_role:
                roles_to_move[role] = current_position
                current_position += 1
                
        try:
            await guild.edit_role_positions(positions=roles_to_move, reason="Toplu Rol Sfrlama: Sralama dǬzenlendi")
        except Exception as e:
            hatalar.append(f"Rol Sralamas yaplrken hata oluYtu (Baz roller botun rolǬnden yǬksek olabilir).")

        # Sonu raporu
        embed = discord.Embed(title="✅ Rol Hiyerarşisi ve İzinler Başarıyla Sıfırlandı", color=discord.Color.green())
        embed.description = f"**{basarili} adet rolün** izinleri kurallara göre tek tek revize edildi ve `@everyone` dahil tüm ayarlar eşitlendi.\nSıralamalar otomatik düzenlendi."
        
        if hatalar:
            hata_metni = "\n".join(hatalar[:10])
            if len(hatalar) > 10: hata_metni += "\n... (daha fazla)"
            embed.add_field(name="⚠️ Bazı Uyarılar (Botun Yetkisinin Yetmediği Roller)", value=f"```\n{hata_metni}\n```")
            
        await msg.edit(content=None, embed=embed)

async def setup(bot):
    await bot.add_cog(RoleManagerCog(bot))
