import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import discord
from discord.ext import commands
from discord import app_commands
from config import TOKEN, GUILD_ID
import os

intents = discord.Intents.all()

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # __file__ ile göreceli yol — farklı dizinden çalıştırılınca da bozulmaz
        cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
        for filename in sorted(os.listdir(cogs_dir)):
            if filename.endswith(".py"):
                try:
                    await self.load_extension(f"cogs.{filename[:-3]}")
                    print(f"Yüklendi: {filename}")
                except Exception as e:
                    print(f"Hata: {filename} → {e}")

        # ── Kalıcı (persistent) buton kayıtları ──
        # Bot yeniden başlasa bile eski panellerdeki butonlar çalışır.
        from cogs.registration import (
            KayitButonView,
            GrupPanelView,
            KarakterPanelView,
            CKPanelView,
            MevcutUyePanelView,
            KayitKararButonu,
            KarakterKararButonu,
            CKKararButonu,
            OnayView,
        )
        from cogs.tickets import TicketPanelView, CloseTicketView
        from cogs.vs_talep import VSSetupView, VSChannelView
        from cogs.uyari_sistemi import UyariPanel
        from cogs.rol_secim import RolSecimView
        from cogs.izin_yonetimi import AnaIzinPaneli
        from cogs.yonetim_paneli import YonetimButonView
        from cogs.cete_sistemi import GangPanelView, AdminGangPanelView
        from cogs.rp_oylama import RPOylamaView
        from cogs.yardim_bekleme import DevralView, DestekAktifView
        from cogs.mod_cagri import ModCagriView

        self.add_view(KayitButonView())
        self.add_view(GrupPanelView())
        self.add_view(KarakterPanelView())
        self.add_view(CKPanelView())
        self.add_view(MevcutUyePanelView())
        self.add_view(OnayView(user_id=None))
        self.add_dynamic_items(KayitKararButonu, KarakterKararButonu, CKKararButonu)
        self.add_view(TicketPanelView())
        self.add_view(CloseTicketView())
        self.add_view(UyariPanel())
        self.add_view(VSSetupView())
        self.add_view(VSChannelView())
        self.add_view(RolSecimView())
        self.add_view(AnaIzinPaneli())
        self.add_view(YonetimButonView())
        self.add_view(GangPanelView())
        self.add_view(AdminGangPanelView())
        self.add_view(RPOylamaView())
        self.add_view(DevralView())
        self.add_view(DestekAktifView())
        self.add_view(ModCagriView())

        # ── Akıllı Otomatik Slash Komut Senkronizasyonu ──
        # Discord'a kayıtlı komut adlarını çekip yerel komutlarla karşılaştırır.
        # İsimlerde veya sayıda herhangi bir fark varsa sync yapar.
        try:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)

            yerel_komutlar = self.tree.get_commands(guild=guild)
            kayitli_komutlar = await self.tree.fetch_commands(guild=guild)

            yerel_adlar = {c.name for c in yerel_komutlar}
            kayitli_adlar = {c.name for c in kayitli_komutlar}

            if yerel_adlar != kayitli_adlar:
                synced = await self.tree.sync(guild=guild)
                fark_eklenen = yerel_adlar - kayitli_adlar
                fark_silinen = kayitli_adlar - yerel_adlar
                print(f"[SYNC] Komut listesi güncellendi! Toplam: {len(synced)}. Eklenen: {fark_eklenen or 'Yok'}, Silinen: {fark_silinen or 'Yok'}", flush=True)
            else:
                print(f"[SYNC] Komutlar güncel ({len(kayitli_adlar)} komut). Sync atlandı.", flush=True)
        except Exception as e:
            print(f"[SYNC] Senkronizasyon hatası: {e}", flush=True)

bot = MyBot()

@bot.command(name="sync")
async def sync_komutu(ctx: commands.Context):
    """Kurucu veya Yönetici yetkisine sahip kişilerin zorla komut senkronizasyonu yapmasını sağlar."""
    KURUCU_ROL_ID = 1529546007635824680
    if not (ctx.author.guild_permissions.administrator or any(r.id == KURUCU_ROL_ID for r in getattr(ctx.author, "roles", []))):
        return await ctx.reply("❌ Bu komutu yalnızca **Kurucu** kullanabilir.")

    mesaj = await ctx.reply("🔄 Slash komutları Discord'a senkronize ediliyor, lütfen bekleyiniz...")
    try:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        await mesaj.edit(content=f"✅ **{len(synced)} adet** slash komutu sunucuya başarıyla senkronize edildi! (Discord'unuzu `Ctrl + R` yaparak yenileyebilirsiniz.)")
    except Exception as e:
        await mesaj.edit(content=f"❌ Senkronizasyon hatası: `{e}`")

@bot.event
async def on_ready():
    print(f"Bot basariyla giris yapti: {bot.user}", flush=True)
    print("------", flush=True)

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    import traceback
    traceback.print_exception(type(error), error, error.__traceback__)
    
    if isinstance(error, app_commands.CommandOnCooldown):
        kalan_dakika = int(error.retry_after / 60)
        if kalan_dakika > 0:
            msg = f"⏳ Bu komutu tekrar kullanabilmek için **{kalan_dakika} dakika** beklemelisiniz."
        else:
            msg = f"⏳ Bu komutu tekrar kullanabilmek için **{int(error.retry_after)} saniye** beklemelisiniz."
    else:
        msg = "Komut çalışırken bir hata oluştu."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        pass

if __name__ == "__main__":
    if not TOKEN:
        print("❌ HATA: Discord Bot TOKEN tanımlı değil!")
        print("Lütfen Railway panelinden veya .env dosyasından TOKEN değişkenini tanımlayın.")
        sys.exit(1)
        
    bot.run(TOKEN)
