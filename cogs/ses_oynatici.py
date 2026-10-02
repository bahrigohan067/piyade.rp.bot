import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os

MUSIC_ROLE_ID = 1547589732937240627

class MusicControlView(discord.ui.View):
    def __init__(self, cog, guild_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    async def update_panel(self, interaction: discord.Interaction):
        state = self.cog.get_state(self.guild_id)
        embed = discord.Embed(title="🎶 Müzik Kuyruğu", color=discord.Color.blue())
        if not state["queue"]:
            embed.description = "Sıra boş."
        else:
            liste_metni = ""
            for i, sarki in enumerate(state["queue"]):
                prefix = "▶️ " if i == state["index"] else "▫️ "
                liste_metni += f"{prefix} **{i+1}.** {sarki['filename']}\n"
            embed.description = liste_metni
        
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary, custom_id="btn_prev")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        state = self.cog.get_state(self.guild_id)
        if not (vc and state["index"] > 0):
            return await interaction.response.send_message("❌ Önceki şarkı yok.", ephemeral=True)

        # Önceki şarkıya geç:
        # play_next her çağrılışta index += 1 yapar, bu yüzden hedef - 1'e ayarlıyoruz.
        # Önce durduruyoruz; after callback play_next'i tetikler ve index'i hedefimize getirir.
        state["index"] = max(-1, state["index"] - 2)

        # Mevcut sesi durdur; after callback otomatik play_next'i çağırır.
        # Güvenli bekleme: interaction'ı hemen cevaplayıp ardından paneli güncelliyoruz.
        await interaction.response.defer()
        vc.stop()
        # play_next senkron olarak loop'a schedule edilir; bir tick sonra hazır.
        await asyncio.sleep(0.1)
        await self.update_panel(interaction)

    @discord.ui.button(emoji="⏯️", style=discord.ButtonStyle.primary, custom_id="btn_pause_resume")
    async def pause_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            if vc.is_paused():
                vc.resume()
                await interaction.response.send_message("▶️ Müzik devam ettiriliyor.", ephemeral=True)
            elif vc.is_playing():
                vc.pause()
                await interaction.response.send_message("⏸️ Müzik duraklatıldı.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Çalan bir şey yok.", ephemeral=True)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary, custom_id="btn_next")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        state = self.cog.get_state(self.guild_id)
        if vc and state["index"] < len(state["queue"]) - 1:
            await interaction.response.defer()
            vc.stop()  # Mevcut şarkıyı durdurduğumuz an sonrakine geçer
            await asyncio.sleep(0.1)
            await self.update_panel(interaction)
        else:
            await interaction.response.send_message("❌ Sırada başka şarkı yok.", ephemeral=True)
            
    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="btn_stop")
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            self.cog.states[self.guild_id] = {"queue": [], "index": -1}
            await vc.disconnect()
            await self.update_panel(interaction)
        else:
            await interaction.response.send_message("❌ Zaten seste değilim.", ephemeral=True)

class LocalMusicStartView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="▶️ Listeyi Başlat", style=discord.ButtonStyle.success, custom_id="btn_start_local")
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Önce bir ses kanalına girmelisiniz!", ephemeral=True)

        await interaction.response.defer()

        vc = interaction.guild.voice_client
        if not vc:
            try:
                vc = await interaction.user.voice.channel.connect()
            except Exception as e:
                return await interaction.followup.send(f"❌ Ses kanalına bağlanılamadı: {e}", ephemeral=True)
        elif vc.channel != interaction.user.voice.channel:
            await vc.move_to(interaction.user.voice.channel)

        music_dir = os.path.join(os.path.dirname(__file__), '..', 'Music')
        if not os.path.exists(music_dir):
            return await interaction.followup.send("❌ Music klasörü bulunamadı.", ephemeral=True)

        files = [f for f in sorted(os.listdir(music_dir)) if f.endswith(('.mp3', '.mp4', '.wav', '.m4a'))]
        if not files:
            return await interaction.followup.send("❌ Hazır müzik bulunamadı.", ephemeral=True)

        state = self.cog.get_state(interaction.guild_id)
        # Kuyruğu temizleyip hazır listeyi ekliyoruz
        state["queue"] = [{"url": os.path.join(music_dir, f), "filename": f, "is_local": True} for f in files]
        state["index"] = -1

        if vc.is_playing() or vc.is_paused():
            vc.stop() # stop edince otomatik sonrakini (index 0) çalar
        else:
            self.cog.play_next(interaction.guild_id)

        view = MusicControlView(self.cog, interaction.guild_id)
        embed = discord.Embed(title="🎶 Müzik Kuyruğu (Hazır Liste)", color=discord.Color.blue())
        liste_metni = ""
        for i, sarki in enumerate(state["queue"]):
            prefix = "▶️ " if i == 0 else "▫️ "
            liste_metni += f"{prefix} **{i+1}.** {sarki['filename']}\n"
        embed.description = liste_metni

        await interaction.followup.send("✅ Hazır müzik listesi başlatıldı!", embed=embed, view=view)


class SesOynatici(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.states = {}

    def get_state(self, guild_id):
        if guild_id not in self.states:
            self.states[guild_id] = {"queue": [], "index": -1}
        return self.states[guild_id]

    def play_next(self, guild_id):
        state = self.get_state(guild_id)
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
            
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            return
            
        state["index"] += 1
        if state["index"] >= len(state["queue"]):
            state["index"] = len(state["queue"]) - 1
            return
            
        item = state["queue"][state["index"]]
        
        if item.get("is_local"):
            # Yerel dosyalarda reconnect opsiyonlarına gerek yok
            FFMPEG_OPTIONS = {'options': '-vn'}
        else:
            FFMPEG_OPTIONS = {
                'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                'options': '-vn'
            }
        
        source = discord.FFmpegPCMAudio(executable="ffmpeg", source=item["url"], **FFMPEG_OPTIONS)
        vc.play(source, after=lambda e: self.bot.loop.call_soon_threadsafe(self.play_next, guild_id))

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingRole):
            await interaction.response.send_message("❌ Bu komutu kullanmak için **Müzik Açma İzni** rolüne sahip olmalısın!", ephemeral=True)
        else:
            # Diğer hataları da loglayabiliriz ama genelde botun ana error handlerı da çalışır
            pass

    @app_commands.command(name="play-file", description="Ses kanalında mp3 dosyası oynatır")
    @app_commands.describe(dosya="Oynatılacak ses dosyası (mp3, wav vb.)")
    @app_commands.checks.has_role(MUSIC_ROLE_ID)
    async def play_file(self, interaction: discord.Interaction, dosya: discord.Attachment):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Önce bir ses kanalına girmelisiniz!", ephemeral=True)
            
        if not dosya.content_type or not dosya.content_type.startswith(('audio/', 'video/')):
            return await interaction.response.send_message("❌ Lütfen geçerli bir ses dosyası (örneğin .mp3) yükleyin.", ephemeral=True)

        await interaction.response.defer()

        vc = interaction.guild.voice_client
        if not vc:
            try:
                vc = await interaction.user.voice.channel.connect()
            except Exception as e:
                return await interaction.followup.send(f"❌ Ses kanalına bağlanılamadı: {e}", ephemeral=True)
        elif vc.channel != interaction.user.voice.channel:
            await vc.move_to(interaction.user.voice.channel)

        state = self.get_state(interaction.guild_id)
        state["queue"].append({"url": dosya.url, "filename": dosya.filename, "is_local": False})

        if not vc.is_playing() and not vc.is_paused():
            state["index"] = len(state["queue"]) - 2 
            await interaction.followup.send(f"🎵 **{dosya.filename}** oynatılıyor!")
            self.play_next(interaction.guild_id)
        else:
            await interaction.followup.send(f"✅ **{dosya.filename}** sıraya eklendi. (Sıra: {len(state['queue'])})")

    @app_commands.command(name="stop", description="Müziği durdurur ve botu sesten çıkarır")
    @app_commands.checks.has_role(MUSIC_ROLE_ID)
    async def stop(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc:
            self.states[interaction.guild_id] = {"queue": [], "index": -1}
            await vc.disconnect()
            await interaction.response.send_message("🛑 Müzik durduruldu ve sesten çıkıldı.")
        else:
            await interaction.response.send_message("❌ Bot şu an bir ses kanalında değil.", ephemeral=True)

    @app_commands.command(name="lists", description="Müzik kuyruğunu ve kontrol panelini gösterir")
    @app_commands.checks.has_role(MUSIC_ROLE_ID)
    async def lists(self, interaction: discord.Interaction):
        state = self.get_state(interaction.guild_id)
        if not state["queue"]:
            return await interaction.response.send_message("❌ Sırada hiç şarkı yok.", ephemeral=True)
            
        embed = discord.Embed(title="🎶 Müzik Kuyruğu", color=discord.Color.blue())
        liste_metni = ""
        for i, sarki in enumerate(state["queue"]):
            prefix = "▶️ " if i == state["index"] else "▫️ "
            liste_metni += f"{prefix} **{i+1}.** {sarki['filename']}\n"
            
        embed.description = liste_metni
        
        view = MusicControlView(self, interaction.guild_id)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="list-nos", description="Hazır müzik listesini gösterir ve başlatma paneli sunar")
    @app_commands.checks.has_role(MUSIC_ROLE_ID)
    async def list_nos(self, interaction: discord.Interaction):
        music_dir = os.path.join(os.path.dirname(__file__), '..', 'Music')
        if not os.path.exists(music_dir):
            return await interaction.response.send_message("❌ Sunucuda 'Music' klasörü bulunamadı.", ephemeral=True)

        files = [f for f in sorted(os.listdir(music_dir)) if f.endswith(('.mp3', '.mp4', '.wav', '.m4a'))]
        if not files:
            return await interaction.response.send_message("❌ 'Music' klasörünün içinde hiç hazır şarkı yok.", ephemeral=True)

        embed = discord.Embed(title="📂 Hazır Müzik Listesi", description="Aşağıdaki şarkılar listeye eklenecek:\n\n", color=discord.Color.green())
        liste_metni = ""
        for i, f in enumerate(files):
            liste_metni += f"**{i+1}.** {f}\n"
        embed.description += liste_metni

        view = LocalMusicStartView(self)
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(SesOynatici(bot))


