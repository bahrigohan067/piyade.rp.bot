import discord
from discord.ext import commands
from discord import app_commands
import os

KURUCU_ROL_ID = 1529546007635824680
ILLEGAL_ROL_ID = 1539249508314259567
LEGAL_ROL_ID = 1539318613498929193

CIVILIAN_VEHICLES = [
    "Arrow Phoenix Nationals 1977",
    "Averon Anodic 2024",
    "Averon Bremen VS Garde 2023",
    "Averon LM 2020",
    "Averon LM R 2020",
    "Averon Q8 2022",
    "Averon RS3 2020",
    "Averon S5 2010",
    "BKM Munich 2020",
    "BKM Risen Roadster 2020",
    "Bullhorn BH15 2009",
    "Bullhorn Determinator 2008",
    "Bullhorn Determinator C-T 2022",
    "Bullhorn Determinator SFP Blackjack Widebody 2022",
    "Bullhorn Determinator SFP Fury 2022",
    "Bullhorn Foreman 1988",
    "Bullhorn Prancer 1969",
    "Bullhorn Prancer C-T 2020",
    "Bullhorn Prancer Colonel Fields 1969",
    "Bullhorn Prancer Fury Widebody 2020",
    "Bullhorn Prancer Hotrod 1969",
    "Bullhorn Prancer S 2011",
    "Bullhorn Prancer Talladega 1969",
    "Bullhorn Pueblo SFP Fury 2022",
    "Bullhorn Pueblo V6 2022",
    "Celestial Truckatron 2024",
    "Celestial Type-5 2022",
    "Celestial Type-6 2024",
    "Celestial Type-7 2022",
    "Chevlon Amigo LZR 2011",
    "Chevlon Amigo LZR 2016",
    "Chevlon Amigo S 2011",
    "Chevlon Amigo S 2016",
    "Chevlon Camion 2008",
    "Chevlon Camion 2018",
    "Chevlon Camion 2021",
    "Chevlon Camion GMT 800 LTS 2002",
    "Chevlon Camion GMT 800 LT 2002",
    "Chevlon Camion GMT 800 S 2002",
    "Chevlon Captain 1992",
    "Chevlon Captain 2009",
    "Chevlon Captain Antelope SS 1994",
    "Chevlon Captain LTZ 1994",
    "Chevlon Commuter Van 2006",
    "Chevlon Corbeta 1M Edition 2014",
    "Chevlon Corbeta 8 2023",
    "Chevlon Corbeta C2 1967",
    "Chevlon Corbeta RZR 2014",
    "Chevlon Corbeta X08 2014",
    "Chevlon Inferno 1981",
    "Chevlon L-15 1981",
    "Chevlon L-15 Side Step 1981",
    "Chevlon L-35 Extended 1981",
    "Chevlon Landslide 2007",
    "Chevlon Platoro 2019",
    "Chevlon Revver 2005",
    "Chryslus Champion 2005",
    "Elysion Slick 2014",
    "Falcon Advance 100 1956",
    "Falcon Advance 100 Holiday Edition 1956",
    "Falcon Advance 350 2020",
    "Falcon Advance 350 Royal Ranch 2020",
    "Falcon Advance 450 2020",
    "Falcon Advance 450 Royal Ranch 2020",
    "Falcon Aquarius STP 2017",
    "Falcon Heritage 2021",
    "Falcon Heritage Track 2022",
    "Falcon Prime Eques 2003",
    "Falcon Rampage Beast 2021",
    "Falcon Rampage Bigfoot 2-Door 2021",
    "Falcon Rampage Prairie 2021",
    "Falcon Scavenger 2013",
    "Falcon Scavenger 2016",
    "Falcon Scavenger Royal Ranch 2024",
    "Falcon Stallion 350 1969",
    "Falcon Stallion 350 2015",
    "Falcon Traveller 2022",
    "Falcon eStallion 2024",
    "Ferdinand Jalapeno Turbo 2022",
    "Kovac Heladera 2023",
    "Leland Birchwood Hearse 1995",
    "Leland LTS5-V Blackwing 2023",
    "Leland LTS 2010",
    "Leland Series 67 Skyview 1959",
    "Leland Vault 2020",
    "Navara Boundary 2022",
    "Navara Horizon 2013",
    "Navara Imperium 2020",
    "Overland Apache 1995",
    "Overland Apache 2011",
    "Overland Apache SFP 2020",
    "Overland Buckaroo 2018",
    "Pea Car 2025",
    "Sentinel Platinum 1968",
    "Strugatti Ettore 2020",
    "Stuttgart Executive 2021",
    "Stuttgart Landschaft 2022",
    "Stuttgart Vierturig 2021",
    "Sumo Reflexion 2022",
    "Surrey 650S 2016",
    "Takeo Experience 2021",
    "Terrain Traveller 2022",
    "Vellfire Everest VRD Max 2023",
    "Vellfire Evertt Extended Cab 1995",
    "Vellfire Pioneer 2019",
    "Vellfire Pioneer Targa 2019",
    "Vellfire Prairie 2022",
    "Vellfire Prima 2009",
    "Vellfire Riptide 2020",
    "Vellfire Runabout 1984",
]

OFFICIAL_VEHICLES = [
    "Averon Q8 2022",
    "BKM Munich 2020",
    "Bullhorn BH15 SSV 2009",
    "Bullhorn Determinator C-T 2022",
    "Bullhorn Determinator SFP Fury 2022",
    "Bullhorn Determinator SFP Fury Blackjack Widebody 2022",
    "Bullhorn Foreman 1988",
    "Bullhorn Prancer Fury Widebody Pursuit 2020",
    "Bullhorn Prancer Pursuit 2011",
    "Bullhorn Prancer Pursuit 2015",
    "Bullhorn Pueblo Pursuit 2022",
    "Celestial Truckatron 2024",
    "Chevlon Amigo LZR 2011",
    "Chevlon Antelope SS 1994",
    "Chevlon Camion PPV 2000",
    "Chevlon Camion PPV 2008",
    "Chevlon Camion PPV 2018",
    "Chevlon Camion PPV 2021",
    "Chevlon Captain PPV 2009",
    "Chevlon Commuter Van 2006",
    "Chevlon Corbeta RZR 2014",
    "Chevlon Inferno 1981",
    "Chevlon Platoro PPV 2019",
    "Emergency Services Falcon Advance+ 2020",
    "Falcon Advance 350 2020",
    "Falcon Advance XET 2022",
    "Falcon Global 350 2013",
    "Falcon Interceptor Sedan 2017",
    "Falcon Interceptor Utility 2013",
    "Falcon Interceptor Utility 2019",
    "Falcon Interceptor Utility 2024",
    "Falcon Prime Eques Interceptor 2015",
    "Falcon Rampage Interceptor 2021",
    "Falcon Stallion 350 2015",
    "Falcon Traveller 2002",
    "Falcon Traveller PPV 2022",
    "Falcon eStallion 2024",
    "Mobile Command 2005",
    "SWAT Armored Truck 2011",
    "Stuttgart Runner Prisoner Transport 2020",
]

def check_civilian_permissions(member: discord.Member) -> bool:
    if member.guild_permissions.administrator: return True
    return any(r.id in [KURUCU_ROL_ID, ILLEGAL_ROL_ID, LEGAL_ROL_ID] for r in member.roles)

def check_official_permissions(member: discord.Member) -> bool:
    if member.guild_permissions.administrator: return True
    return any(r.id in [KURUCU_ROL_ID, LEGAL_ROL_ID] for r in member.roles)

def _build_asset_cache() -> dict[str, str]:
    """
    Bot başlarken assets/ klasöründeki tüm dosyaları bir kez tarar ve
    lowercase isim → gerçek yol eşlemesini döndürür.
    Bu sayede her autocomplete tuşuna basışta disk I/O yapılmaz.
    """
    cache: dict[str, str] = {}
    assets_dir = os.path.join(os.path.dirname(__file__), "..", "assets")
    if not os.path.isdir(assets_dir):
        return cache
    for fname in os.listdir(assets_dir):
        fpath = os.path.join(assets_dir, fname)
        if os.path.isfile(fpath):
            # Uzantısız küçük harf ismi → gerçek yol
            name_no_ext = os.path.splitext(fname)[0].lower()
            cache[name_no_ext] = fpath
    return cache

# Modül yüklendiğinde bir kez çalışır
_ASSET_CACHE: dict[str, str] = _build_asset_cache()


def find_asset_image(base_name: str, is_official: bool = False) -> str | None:
    """
    Cache üzerinden arama yapar — disk I/O yok.
    """
    name_underscored = base_name.replace(" ", "_")
    prefix_under = "(LEO)_" if is_official else ""
    prefix_space = "(LEO) "  if is_official else ""

    candidates = [
        base_name,
        f"{base_name}_Original",
        name_underscored,
        f"{name_underscored}_Original",
    ]
    if is_official:
        candidates += [
            f"{prefix_space}{base_name}",
            f"{prefix_space}{base_name}_Original",
            f"{prefix_under}{name_underscored}",
            f"{prefix_under}{name_underscored}_Original",
        ]

    for candidate in candidates:
        path = _ASSET_CACHE.get(candidate.lower())
        if path:
            return path
    return None

class MapView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def send_map(self, interaction: discord.Interaction, map_name: str, fallback_file: str = None):
        img_path = find_asset_image(map_name)
        if not img_path and fallback_file:
            img_path = find_asset_image(fallback_file)
            
        embed = discord.Embed(title=f"🗺️ {map_name}", color=discord.Color.blue())
        if img_path:
            dosya = discord.File(img_path, filename="map.png")
            embed.set_image(url="attachment://map.png")
            await interaction.response.send_message(embed=embed, file=dosya, ephemeral=True)
        else:
            embed.description = "*(Resim bulunamadı)*"
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Harita 2025", style=discord.ButtonStyle.primary, custom_id="map_2025")
    async def btn_2025(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.send_map(interaction, "Harita 2025", fallback_file="In-Game Map December 23 2025")

    @discord.ui.button(label="Harita 2026", style=discord.ButtonStyle.primary, custom_id="map_2026")
    async def btn_2026(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.send_map(interaction, "Harita 2026", fallback_file="Street Map v3 March 22 2026")

class AssetsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="civilian-vehicles", description="Sivil araçların listesini ve detaylarını gösterir.")
    @app_commands.describe(arac="Görmek istediğiniz araç")
    async def civilian_vehicles(self, interaction: discord.Interaction, arac: str):
        if not check_civilian_permissions(interaction.user):
            return await interaction.response.send_message("❌ Bu komutu kullanma yetkin yok. (Legal/İllegal rolleri gerektirir)", ephemeral=True)
            
        if arac not in CIVILIAN_VEHICLES:
            return await interaction.response.send_message("❌ Belirtilen sivil araç bulunamadı. Lütfen listeden geçerli bir araç seçin.", ephemeral=True)

        img_path = find_asset_image(arac, is_official=False)
        embed = discord.Embed(title=f"🚗 {arac}", description="Bu sivil araçla ilgili özellikler:\n*(Buraya araç özellikleri eklenebilir)*", color=discord.Color.green())
        
        if img_path:
            dosya = discord.File(img_path, filename="vehicle.png")
            embed.set_thumbnail(url="attachment://vehicle.png")
            await interaction.response.send_message(embed=embed, file=dosya)
        else:
            embed.description += "\n\n*(Resim bulunamadı)*"
            await interaction.response.send_message(embed=embed)

    @civilian_vehicles.autocomplete("arac")
    async def civilian_autocomplete(self, interaction: discord.Interaction, current: str):
        return [
            app_commands.Choice(name=car, value=car)
            for car in CIVILIAN_VEHICLES if current.lower() in car.lower()
        ][:25]

    @app_commands.command(name="official-vehicles", description="Resmi (Polis/LEO) araçların listesini ve detaylarını gösterir.")
    @app_commands.describe(arac="Görmek istediğiniz araç")
    async def official_vehicles(self, interaction: discord.Interaction, arac: str):
        if not check_official_permissions(interaction.user):
            return await interaction.response.send_message("❌ Bu komutu kullanma yetkin yok. (Sadece Legal rolü gerektirir)", ephemeral=True)
            
        if arac not in OFFICIAL_VEHICLES:
            return await interaction.response.send_message("❌ Belirtilen resmi araç bulunamadı. Lütfen listeden geçerli bir araç seçin.", ephemeral=True)

        img_path = find_asset_image(arac, is_official=True)
        embed = discord.Embed(title=f"🚓 {arac}", description="Bu resmi araçla ilgili özellikler:\n*(Buraya polis aracı özellikleri eklenebilir)*", color=discord.Color.blue())
        
        if img_path:
            dosya = discord.File(img_path, filename="vehicle.png")
            embed.set_thumbnail(url="attachment://vehicle.png")
            await interaction.response.send_message(embed=embed, file=dosya)
        else:
            embed.description += "\n\n*(Resim bulunamadı)*"
            await interaction.response.send_message(embed=embed)

    @official_vehicles.autocomplete("arac")
    async def official_autocomplete(self, interaction: discord.Interaction, current: str):
        return [
            app_commands.Choice(name=car, value=car)
            for car in OFFICIAL_VEHICLES if current.lower() in car.lower()
        ][:25]

    @app_commands.command(name="maps", description="Sunucu haritalarını gösterir.")
    async def maps(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🗺️ Harita Seçimi", description="Lütfen görmek istediğiniz haritayı seçin:", color=discord.Color.dark_theme())
        await interaction.response.send_message(embed=embed, view=MapView())

async def setup(bot):
    await bot.add_cog(AssetsCog(bot))
    # MapView panelini bot restart sonrası da aktif tut
    bot.add_view(MapView())
