import discord
from discord.ext import commands
from discord import app_commands

class RolSecim(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(placeholder="🎭 İşlem yapmak istediğiniz rolü seçin...", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        embed = discord.Embed(
            title=f"🎭 {role.name} Rolü İzinleri",
            description="Aşağıdaki butonları kullanarak bu role ait genel sunucu izinlerini açıp kapatabilirsiniz.",
            color=role.color
        )
        await interaction.response.send_message(embed=embed, view=RolIzinView(role), ephemeral=True)

class KanalSecim(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(placeholder="📁 İzinlerini ayarlamak istediğiniz kanalı seçin...", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        # AppCommandChannel'ı tam kanal objesine çeviriyoruz
        channel = interaction.guild.get_channel(self.values[0].id) or self.values[0]
        # Kanal seçildikten sonra hangi rol için ayarlanacağını sormak adına rol seçimine yönlendirelim
        view = discord.ui.View()
        view.add_item(KanalRolSecim(channel))
        await interaction.response.send_message(f"**{channel.mention}** kanalı için hangi rolün/kişinin izinlerini düzenlemek istiyorsunuz?", view=view, ephemeral=True)

class KanalRolSecim(discord.ui.RoleSelect):
    def __init__(self, channel):
        super().__init__(placeholder="Kanal izni ayarlanacak rolü seçin...", min_values=1, max_values=1)
        self.channel = channel

    async def callback(self, interaction: discord.Interaction):
        role = self.values[0]
        embed = discord.Embed(
            title=f"📁 {self.channel.name} Kanalı İzinleri",
            description=f"**{role.name}** rolünün bu kanaldaki izinlerini aşağıdan yönetebilirsiniz.",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, view=KanalIzinView(self.channel, role), ephemeral=True)


class RolIzinView(discord.ui.View):
    def __init__(self, role: discord.Role):
        super().__init__(timeout=None)
        self.role = role

    async def toggle_perm(self, interaction: discord.Interaction, perm_name: str, display_name: str):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Sadece yöneticiler izinleri değiştirebilir.", ephemeral=True)
            
        perms = self.role.permissions
        current_val = getattr(perms, perm_name)
        setattr(perms, perm_name, not current_val)
        
        try:
            await self.role.edit(permissions=perms, reason=f"{interaction.user} tarafından değiştirildi.")
            durum = "✅ Açıldı" if not current_val else "❌ Kapatıldı"
            await interaction.response.send_message(f"**{self.role.name}** rolü için **{display_name}** izni **{durum}**.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Yetkim yetmiyor veya bir hata oluştu: {e}", ephemeral=True)

    @discord.ui.button(label="Yönetici", emoji="👑", style=discord.ButtonStyle.danger)
    async def btn_admin(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_perm(interaction, "administrator", "Yönetici")

    @discord.ui.button(label="Kanalları Yönet", emoji="📁", style=discord.ButtonStyle.primary)
    async def btn_manage_channels(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_perm(interaction, "manage_channels", "Kanalları Yönet")

    @discord.ui.button(label="Rolleri Yönet", emoji="🎭", style=discord.ButtonStyle.primary)
    async def btn_manage_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_perm(interaction, "manage_roles", "Rolleri Yönet")

    @discord.ui.button(label="Mesajları Yönet", emoji="🗑️", style=discord.ButtonStyle.primary)
    async def btn_manage_messages(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_perm(interaction, "manage_messages", "Mesajları Yönet")
        
    @discord.ui.button(label="Üyeleri At", emoji="🥾", style=discord.ButtonStyle.secondary)
    async def btn_kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_perm(interaction, "kick_members", "Üyeleri At")
        
    @discord.ui.button(label="Üyeleri Yasakla", emoji="🔨", style=discord.ButtonStyle.secondary)
    async def btn_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_perm(interaction, "ban_members", "Üyeleri Yasakla")


class KanalIzinView(discord.ui.View):
    def __init__(self, channel, role):
        super().__init__(timeout=None)
        self.channel = channel
        self.role = role

    async def toggle_channel_perm(self, interaction: discord.Interaction, perm_name: str, display_name: str):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Sadece yöneticiler izinleri değiştirebilir.", ephemeral=True)
            
        overwrites = self.channel.overwrites_for(self.role)
        # 3 state: True, False, None
        current_val = getattr(overwrites, perm_name)
        
        if current_val is None:
            yeni_deger = True
        elif current_val is True:
            yeni_deger = False
        else:
            yeni_deger = None
            
        setattr(overwrites, perm_name, yeni_deger)
        
        try:
            await self.channel.set_permissions(self.role, overwrite=overwrites, reason=f"{interaction.user} tarafından değiştirildi.")
            durum = "✅ Açık" if yeni_deger is True else ("❌ Kapalı" if yeni_deger is False else "🔄 Nötr (Varsayılan)")
            await interaction.response.send_message(f"**{self.channel.name}** kanalında **{self.role.name}** rolü için **{display_name}** izni **{durum}** olarak ayarlandı.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Yetkim yetmiyor veya bir hata oluştu: {e}", ephemeral=True)

    @discord.ui.button(label="Kanalı Görüntüle", emoji="👁️", style=discord.ButtonStyle.primary)
    async def btn_view(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_channel_perm(interaction, "view_channel", "Kanalı Görüntüle")

    @discord.ui.button(label="Mesaj Gönder / Konuş", emoji="💬", style=discord.ButtonStyle.primary)
    async def btn_send(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Sesli veya Sahne kanalıysa speak, metin kanalıysa send_messages
        if isinstance(self.channel, (discord.VoiceChannel, discord.StageChannel)):
            await self.toggle_channel_perm(interaction, "speak", "Konuşma")
        else:
            await self.toggle_channel_perm(interaction, "send_messages", "Mesaj Gönderme")

    @discord.ui.button(label="Bağlan (Ses)", emoji="🔊", style=discord.ButtonStyle.primary)
    async def btn_connect(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_channel_perm(interaction, "connect", "Bağlanma")


class AnaIzinPaneli(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎭 Rol İzinlerini Düzenle", style=discord.ButtonStyle.success, custom_id="panel_rol_izinleri")
    async def rol_izinleri_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = discord.ui.View()
        view.add_item(RolSecim())
        await interaction.response.send_message("Lütfen düzenlemek istediğiniz rolü seçin:", view=view, ephemeral=True)

    @discord.ui.button(label="📁 Kanal İzinlerini Düzenle", style=discord.ButtonStyle.primary, custom_id="panel_kanal_izinleri")
    async def kanal_izinleri_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = discord.ui.View()
        view.add_item(KanalSecim())
        await interaction.response.send_message("Lütfen düzenlemek istediğiniz kanalı seçin:", view=view, ephemeral=True)

class IzinYonetimi(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="izin-paneli-kur", description="Sunucu izinlerini hızlıca ayarlayabileceğiniz sabit paneli kurar.")
    @app_commands.default_permissions(administrator=True)
    async def izin_paneli_kur(self, interaction: discord.Interaction):
        if not discord.utils.get(interaction.user.roles, id=1529546007635824680):
            return await interaction.response.send_message("❌ Bu komutu sadece **Kurucu** kullanabilir!", ephemeral=True)

        embed = discord.Embed(
            title="⚙️ Sunucu İzin Yönetim Merkezi",
            description="Aşağıdaki butonları kullanarak sunucudaki rollerin genel izinlerini veya belirli kanallardaki izinlerini hızlıca düzenleyebilirsiniz.\n\n"
                        "🎭 **Rol İzinleri:** Yöneticilik, Kanalları Yönetme, Üye Atma vb.\n"
                        "📁 **Kanal İzinleri:** Kanalları görme, mesaj atma, sese bağlanma vb.",
            color=discord.Color.dark_theme()
        )
        embed.set_footer(text="Bu panele sadece yöneticiler müdahale edebilir.")
        
        await interaction.channel.send(embed=embed, view=AnaIzinPaneli())
        await interaction.response.send_message("✅ İzin yönetim paneli başarıyla kuruldu.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(IzinYonetimi(bot))
