import discord
from discord.ext import commands
from discord import app_commands

# ==================== AYARLAR ====================
HEDEF_KANAL_ID = 1554924155927924776

# Rol ID'leri
ROLE_DRIVER = 1534736940279005326
ROLE_PVP = 1534736939675160637
ROLE_TEMEL_KADEME = 1541213765410754640
ROLE_BUILDER = 1534756885016871083
ROLE_LEGAL = 1539318613498929193
ROLE_ILLEGAL = 1539249508314259567
ROLE_SICAK_KANLI = 1534757047919317172
ROLE_MUZIK_IZNI = 1547589732937240627
# =================================================

class RolSecimView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def toggle_roles(self, interaction: discord.Interaction, role_ids: list, label: str, conflicts: list = None):
        guild = interaction.guild
        member = interaction.user
        
        verilenler = []
        alinanlar = []
        
        # Üyede vereceğimiz ana rol halihazırda var mı? (Birden fazla rol veriliyorsa ilkine bakalım)
        ilk_rol = guild.get_role(role_ids[0])
        has_primary = ilk_rol in member.roles if ilk_rol else False

        # Eğer rolü VERECEKSEK ve bir zıtlık kuralı (conflicts) belirtilmişse:
        if not has_primary and conflicts:
            for c_id in conflicts:
                c_rol = guild.get_role(c_id)
                if c_rol and c_rol in member.roles:
                    try:
                        await member.remove_roles(c_rol, reason=f"{label} rolü seçildiği için zıt rol çıkarıldı")
                        alinanlar.append(c_rol.name)
                    except discord.Forbidden:
                        pass
        
        for r_id in role_ids:
            rol = guild.get_role(r_id)
            if not rol:
                continue
                
            if rol in member.roles:
                try:
                    await member.remove_roles(rol, reason=f"{label} butonu kullanıldı")
                    alinanlar.append(rol.name)
                except discord.Forbidden:
                    return await interaction.response.send_message("❌ Bu rolü yönetmek için yetkim yok!", ephemeral=True)
            else:
                try:
                    await member.add_roles(rol, reason=f"{label} butonu kullanıldı")
                    verilenler.append(rol.name)
                except discord.Forbidden:
                    return await interaction.response.send_message("❌ Bu rolü yönetmek için yetkim yok!", ephemeral=True)
                    
        mesaj = ""
        if verilenler:
            mesaj += f"✅ **{', '.join(verilenler)}** rolü verildi.\n"
        if alinanlar:
            mesaj += f"❌ **{', '.join(alinanlar)}** rolü alındı.\n"
            
        if not mesaj:
            mesaj = "Rol bulunamadı, sunucu ayarlarını kontrol edin."
            
        await interaction.response.send_message(mesaj, ephemeral=True)

    # 1. DRİVER
    @discord.ui.button(label="DRİVER", emoji="🚐", style=discord.ButtonStyle.secondary, custom_id="rs_driver")
    async def btn_driver(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_roles(interaction, [ROLE_DRIVER], "DRİVER")

    # 2. PVP (İki rol birden)
    @discord.ui.button(label="PVP", emoji="⚔️", style=discord.ButtonStyle.secondary, custom_id="rs_pvp")
    async def btn_pvp(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_roles(interaction, [ROLE_PVP, ROLE_TEMEL_KADEME], "PVP")

    # 3. BUİLDER
    @discord.ui.button(label="BUİLDER", emoji="🔨", style=discord.ButtonStyle.secondary, custom_id="rs_builder")
    async def btn_builder(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_roles(interaction, [ROLE_BUILDER], "BUİLDER")

    # 4. LEGAL (ILLEGAL ile zıt - biri varken diğeri alınamaz/otomatik çıkarılır)
    @discord.ui.button(label="LEGAL", emoji="👮", style=discord.ButtonStyle.secondary, custom_id="rs_legal")
    async def btn_legal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_roles(interaction, [ROLE_LEGAL], "LEGAL", conflicts=[ROLE_ILLEGAL])

    # 5. İLLEGAL (LEGAL ile zıt - biri varken diğeri alınamaz/otomatik çıkarılır)
    @discord.ui.button(label="İLLEGAL", emoji="🥷", style=discord.ButtonStyle.secondary, custom_id="rs_illegal")
    async def btn_illegal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_roles(interaction, [ROLE_ILLEGAL], "İLLEGAL", conflicts=[ROLE_LEGAL])

    # 6. SICAK KANLI
    @discord.ui.button(label="SICAK KANLI", emoji="❤️", style=discord.ButtonStyle.secondary, custom_id="rs_sicakkanli")
    async def btn_sicakkanli(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_roles(interaction, [ROLE_SICAK_KANLI], "SICAK KANLI")

    # 7. Müzik İzni
    @discord.ui.button(label="Müzik İzni", emoji="🎵", style=discord.ButtonStyle.secondary, custom_id="rs_muzik")
    async def btn_muzik(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.toggle_roles(interaction, [ROLE_MUZIK_IZNI], "Müzik İzni")


class RolSecim(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="rol-paneli-kur", description="[YÖNETİM] Rol seçim panelini gönderir.")
    @app_commands.default_permissions(administrator=True)
    async def rol_paneli_kur(self, interaction: discord.Interaction):
        if not discord.utils.get(interaction.user.roles, id=1529546007635824680):
            return await interaction.response.send_message("❌ Bu komutu sadece **Kurucu** kullanabilir!", ephemeral=True)

        kanal = self.bot.get_channel(HEDEF_KANAL_ID)
        if not kanal:
            try:
                kanal = await self.bot.fetch_channel(HEDEF_KANAL_ID)
            except Exception:
                kanal = None

        if not kanal:
            return await interaction.response.send_message("❌ Hedef kanal bulunamadı. ID'yi kontrol edin.", ephemeral=True)

        embed = discord.Embed(
            title="İstek ile rol Alma",
            description="Rolleri tuşlarla al !\n\n-------------------------\n\nCANSIN❤️",
            color=discord.Color.red()
        )
        embed.set_author(
            name="~ Polat", 
            icon_url=interaction.user.display_avatar.url 
        )
        embed.set_footer(text="--- işimiz herzaman kolay ---")
        embed.timestamp = discord.utils.utcnow()

        await kanal.send(embed=embed, view=RolSecimView())
        await interaction.response.send_message(f"✅ Panel {kanal.mention} kanalına başarıyla gönderildi.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(RolSecim(bot))
