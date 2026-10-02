import discord
from discord.ext import commands

AKTIF_ROL_ID = 1534736941973504032
SES_KANALLARI = [
    1551196392138215434, # Sohbet Odası 1
    1551196508664242186, # Sohbet Odası 2
    1551196598472540190, # Sohbet Odası 3
    1551196973590249552, # İn The Game 1
    1551197003529199727, # İn The Game 2
    1551197027617079417  # İn The Game 3
]

class SesOdasi(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        aktif_rol = member.guild.get_role(AKTIF_ROL_ID)
        if not aktif_rol:
            return

        joined_target = after.channel and after.channel.id in SES_KANALLARI
        left_target = before.channel and before.channel.id in SES_KANALLARI and (not after.channel or after.channel.id not in SES_KANALLARI)

        if joined_target and aktif_rol not in member.roles:
            try:
                await member.add_roles(aktif_rol, reason="Belirlenen ses kanalına katıldı.")
            except discord.Forbidden:
                pass
        elif left_target and aktif_rol in member.roles:
            try:
                await member.remove_roles(aktif_rol, reason="Belirlenen ses kanalından ayrıldı.")
            except discord.Forbidden:
                pass

async def setup(bot):
    await bot.add_cog(SesOdasi(bot))
