import discord
from discord.ext import commands, tasks
import aiohttp
import os
import json
from datetime import datetime, timezone, timedelta
from utils.storage import load_json, save_json_atomic

RADAR_KANAL_ID = 1553721461389266974
RDM_LOG_KANAL_ID = 1554099605837185044

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
BOLGELER_FILE = os.path.join(DATA_DIR, "bolgeler.json")
KILLER_FILE = os.path.join(DATA_DIR, "gunluk_killer.json")
DASHBOARD_FILE = os.path.join(DATA_DIR, "radar_dashboard.json")

# Dosya okunamasa bile Safezone kontrolünün asla aksamaması için yedek tanımlar (4 Köşe Poligon)
TANIMLI_BOLGELER = {
    "gun_shop": {
        "name": "Gunshop Etkileşimli Bölge (Safezone)",
        "postal_codes": ["227"],
        "points": [
            {"x": 1095.33, "z": 3411.18},
            {"x": 1118.24, "z": 3408.05},
            {"x": 1129.06, "z": 3388.36},
            {"x": 1110.77, "z": 3395.14}
        ]
    },
    "police_department": {
        "name": "Polis Departmanı (Safezone)",
        "postal_codes": ["310", "316", "317"],
        "points": [
            {"x": 2946.46, "z": 3474.49},
            {"x": 2945.49, "z": 3559.07},
            {"x": 2809.82, "z": 3562.42},
            {"x": 2811.28, "z": 3473.87}
        ]
    },
    "fire_department": {
        "name": "Fire Departman (Safezone)",
        "postal_codes": ["228", "229"],
        "points": [
            {"x": 1358.66, "z": 3370.96},
            {"x": 1284.1, "z": 3306.45},
            {"x": 1207.34, "z": 3440.44},
            {"x": 1317.57, "z": 3459.93}
        ]
    },
    "city_spawn": {
        "name": "City Spawn (Safezone)",
        "postal_codes": ["210", "211"],
        "points": [
            {"x": 1465.45, "z": 3935.5},
            {"x": 1616.43, "z": 3933.91},
            {"x": 1615.94, "z": 3845.71},
            {"x": 1464.1, "z": 3843.23}
        ]
    }
}

def point_in_polygon(x: float, z: float, polygon: list) -> bool:
    """
    Ray-Casting Algoritması:
    (x, z) koordinatının verilen 4 noktalı çokgen (safezone sınırları) içinde
    olup olmadığını milimetrik kesinlikle hesaplar.
    """
    if not polygon or len(polygon) < 3:
        return False

    pts = []
    for p in polygon:
        if isinstance(p, dict):
            pts.append((float(p["x"]), float(p["z"])))
        elif isinstance(p, (list, tuple)):
            pts.append((float(p[0]), float(p[1])))

    n = len(pts)
    inside = False
    p1x, p1z = pts[0]
    for i in range(n + 1):
        p2x, p2z = pts[i % n]
        if min(p1z, p2z) < z <= max(p1z, p2z):
            if x <= max(p1x, p2x):
                if p1z != p2z:
                    xinters = (z - p1z) * (p2x - p1x) / (p2z - p1z) + p1x
                if p1x == p2x or x <= xinters:
                    inside = not inside
        p1x, p1z = p2x, p2z
    return inside

def bolge_kontrol(x, z, postal, bolgeler):
    """
    Oyuncunun (x, z) koordinatlarının tam olarak hangi Safezone poligonu içinde olduğunu belirler.
    NOT: Posta kodları yüzlerce metrelik geniş sokakları kapsadığı için Safezone tespitinde
    kullanılmaz; yalnızca poligon (X, Z) koordinat kontrolü esastır.
    """
    if not isinstance(x, (int, float)) or not isinstance(z, (int, float)):
        return None

    for b_id, b_info in bolgeler.items():
        # 1. Kesin Poligon Kontrolü (4 Köşe Noktası)
        points = b_info.get("points")
        if points and len(points) >= 3:
            if point_in_polygon(float(x), float(z), points):
                return b_info.get("name", b_id)
            continue

        # 2. Yedek: Sadece points yoksa katı bounds kontrolü (tampon payı olmadan)
        bounds = b_info.get("bounds")
        if bounds:
            min_x = bounds.get("min_x")
            max_x = bounds.get("max_x")
            min_z = bounds.get("min_z")
            max_z = bounds.get("max_z")
            if min_x is not None and max_x is not None and min_z is not None and max_z is not None:
                if min_x <= x <= max_x and min_z <= z <= max_z:
                    return b_info.get("name", b_id)

    return None

class LiveRadar(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = None  # Kalıcı ClientSession (Socket sızıntılarını önler)
        self.son_konumlar = {}  # Katil takibi ve son bilinen konumlar
        self.last_radar_state = None  # Dirty-checking için son durum önbelleği

        # Kalıcı dashboard mesaj kimliği
        dashboard_data = load_json(DASHBOARD_FILE, {})
        self.dashboard_msg_id = dashboard_data.get("message_id")

        # İşlenen kill logları
        kill_data = load_json(KILLER_FILE, {"islenen_killer": [], "gunluk_safezone_ihlalleri": {}})
        self.islenen_killer = set(kill_data.get("islenen_killer", []))

        self.radar_loop.start()

    def cog_unload(self):
        self.radar_loop.cancel()
        if self.session and not self.session.closed:
            self.bot.loop.create_task(self.session.close())

    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    def olustur_dashboard_embed(self, aktif_oyuncular: dict, total_count: any, bolgeler: dict) -> discord.Embed:
        tz_tr = timezone(timedelta(hours=3))
        now_tr = datetime.now(tz_tr)
        zaman_str = now_tr.strftime("%H:%M:%S")
        ts_unix = int(now_tr.timestamp())

        oyuncu_sayisi = len(aktif_oyuncular)
        renk = discord.Color.green() if oyuncu_sayisi > 0 else discord.Color.dark_theme()

        embed = discord.Embed(
            title="📡 PİYADE RP • CANLI OYUNCU RADARI & TERMİNALİ",
            color=renk,
            timestamp=now_tr
        )

        embed.description = (
            f"**👥 Çevrimiçi Oyuncular:** `{oyuncu_sayisi}` / `{total_count}`\n"
            f"**⏱️ Son Tarama:** `{zaman_str}` (<t:{ts_unix}:R>)\n"
            f"**🛡️ Safezone Koruması:** `Aktif (Otomatik İhlal Tespiti)`\n"
            "──────────────────────────────────────────"
        )

        if not aktif_oyuncular:
            embed.add_field(
                name="🔍 Şehir Durumu",
                value="*Şu anda ER:LC sunucusunda aktif oyuncu bulunmamaktadır.*",
                inline=False
            )
        else:
            # Oyuncuları listele (Görsel ve düzenli gruplama)
            # En fazla 24 oyuncuyu ayrı alan veya bloklar halinde göster
            oyuncu_listesi = list(aktif_oyuncular.items())
            
            # Sayfa aşımını önlemek için bloklar halinde ekle
            chunk_size = 6
            for i in range(0, len(oyuncu_listesi), chunk_size):
                chunk = oyuncu_listesi[i:i + chunk_size]
                satirlar = []
                for isim, loc in chunk:
                    bolge = bolge_kontrol(loc["x"], loc["z"], loc["postal"], bolgeler)
                    bolge_metin = f"🛡️ **{bolge}**" if bolge else f"🛣️ {loc['street']} (No: {loc['building']})"
                    satir = (
                        f"🟢 **{isim}** [Posta: `{loc['postal']}`]\n"
                        f"└ 📍 `X: {loc['x']} | Z: {loc['z']}` • {bolge_metin}"
                    )
                    satirlar.append(satir)
                
                embed.add_field(
                    name=f"📋 Oyuncular ({i + 1} - {min(i + chunk_size, len(oyuncu_listesi))})",
                    value="\n\n".join(satirlar),
                    inline=False
                )

        embed.set_footer(text="Piyade RP Canlı Radar • Tek Panel Dashboard Modu")
        return embed

    @tasks.loop(seconds=15)
    async def radar_loop(self):
        if not self.bot.is_ready():
            return

        api_key = os.getenv("ERLC_API_KEY")
        if not api_key:
            return

        kanal = self.bot.get_channel(RADAR_KANAL_ID)
        if not kanal:
            try:
                kanal = await self.bot.fetch_channel(RADAR_KANAL_ID)
            except Exception:
                return

        # 1. ER:LC API Verisini Çek
        try:
            session = await self.get_session()
            headers = {'Server-Key': api_key}
            async with session.get('https://api.erlc.gg/v2/server?Players=true&KillLogs=true', headers=headers, timeout=6) as resp:
                if resp.status != 200:
                    return
                data = await resp.json()
                players = data.get("Players", [])
                kill_logs = data.get("KillLogs", [])
                current_players_count = data.get("CurrentPlayers", len(players))
        except Exception as e:
            print(f"[RADAR HATA] API isteği başarısız: {e}", flush=True)
            return

        # 2. Oyuncu Konumlarını Ayrıştır
        aktif_oyuncular = {}
        for p in players:
            player_str = p.get("Player", "")
            if not player_str:
                continue

            isim = player_str.split(':')[0]
            loc = p.get("Location", {})
            x = loc.get("LocationX", 0)
            y = loc.get("LocationY", loc.get("Y", "-"))
            z = loc.get("LocationZ", 0)
            posta_kodu = loc.get("PostalCode", "-")
            sokak = loc.get("StreetName", "-")
            bina = loc.get("BuildingNumber", "-")

            aktif_oyuncular[isim] = {
                "x": round(x, 1) if isinstance(x, (int, float)) else x,
                "y": round(y, 1) if isinstance(y, (int, float)) else y,
                "z": round(z, 1) if isinstance(z, (int, float)) else z,
                "postal": posta_kodu,
                "street": sokak,
                "building": bina
            }

        self.son_konumlar.update(aktif_oyuncular)

        # 3. Dirty Checking: Oyuncu durumunda değişiklik yoksa Discord edit isteği atma (0 Rate Limit!)
        state_repr = tuple(sorted((k, v["x"], v["z"], v["postal"]) for k, v in aktif_oyuncular.items()))
        bolgeler_data = load_json(BOLGELER_FILE, TANIMLI_BOLGELER) or TANIMLI_BOLGELER

        if state_repr != self.last_radar_state or not self.dashboard_msg_id:
            embed = self.olustur_dashboard_embed(aktif_oyuncular, current_players_count, bolgeler_data)
            dashboard_msg = None

            if self.dashboard_msg_id:
                try:
                    dashboard_msg = await kanal.fetch_message(self.dashboard_msg_id)
                except Exception:
                    dashboard_msg = None

            if dashboard_msg:
                try:
                    await dashboard_msg.edit(embed=embed)
                except Exception as e:
                    print(f"[RADAR HATA] Dashboard düzenlenemedi: {e}", flush=True)
                    dashboard_msg = None

            if not dashboard_msg:
                # Mesaj yoksa kanalı temizleyip sıfır master mesajı gönder
                try:
                    await kanal.purge(limit=20)
                except Exception:
                    pass
                try:
                    new_msg = await kanal.send(embed=embed)
                    self.dashboard_msg_id = new_msg.id
                    save_json_atomic(DASHBOARD_FILE, {"message_id": new_msg.id})
                    print(f"[RADAR BAŞARILI] Yeni Master Dashboard oluşturuldu: {new_msg.id}", flush=True)
                except Exception as e:
                    print(f"[RADAR HATA] Master dashboard gönderilemedi: {e}", flush=True)

            self.last_radar_state = state_repr

        # 4. ER:LC Kill Loglarını ve Safezone İhlallerini Kontrol Et
        if kill_logs:
            rdm_kanal = self.bot.get_channel(RDM_LOG_KANAL_ID)
            if not rdm_kanal:
                try:
                    rdm_kanal = await self.bot.fetch_channel(RDM_LOG_KANAL_ID)
                except Exception:
                    rdm_kanal = None

            kill_tracker = load_json(KILLER_FILE, {"islenen_killer": [], "gunluk_safezone_ihlalleri": {}})
            tz_tr = timezone(timedelta(hours=3))
            bugun = datetime.now(tz_tr).strftime("%Y-%m-%d")

            for k in kill_logs:
                ts = k.get("Timestamp", 0)
                killer_raw = str(k.get("Killer", "Bilinmiyor:0"))
                victim_raw = str(k.get("Killed", "Bilinmiyor:0"))
                kill_id = f"{killer_raw}_{victim_raw}_{ts}"

                if kill_id in self.islenen_killer:
                    continue

                self.islenen_killer.add(kill_id)

                killer_name = killer_raw.split(':')[0]
                killer_id = killer_raw.split(':')[1] if ':' in killer_raw else "0"
                victim_name = victim_raw.split(':')[0]
                victim_id = victim_raw.split(':')[1] if ':' in victim_raw else "0"

                pos_info = self.son_konumlar.get(killer_name, {})
                x_val = pos_info.get("x", "-")
                z_val = pos_info.get("z", "-")
                postal = pos_info.get("postal", "-")
                street = pos_info.get("street", "-")
                bina = pos_info.get("building", "-")
                silah = k.get("Weapon", "Bilinmiyor")

                safezone = bolge_kontrol(x_val, z_val, postal, bolgeler_data)
                if not safezone:
                    continue

                gunluk_sozluk = kill_tracker.setdefault("gunluk_safezone_ihlalleri", {}).setdefault(bugun, {})
                ihlal_sayi = gunluk_sozluk.get(killer_name, 0) + 1
                gunluk_sozluk[killer_name] = ihlal_sayi

                embed = discord.Embed(
                    title="🚨 SAFEZONE İHLALİ TESPİT EDİLDİ",
                    description=f"**{killer_name}**, korumalı bölge olan **{safezone}** sınırları içerisinde saldırı/cinayet gerçekleştirdi!",
                    color=discord.Color.red(),
                    timestamp=datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(tz_tr)
                )
                embed.add_field(name="👤 İhlal Eden (Saldırgan)", value=f"**{killer_name}** `(ID: {killer_id})`", inline=True)
                embed.add_field(name="🎯 Mağdur (Kurban)", value=f"**{victim_name}** `(ID: {victim_id})`", inline=True)
                embed.add_field(name="🔫 Kullanılan Silah", value=f"`{silah}`", inline=True)

                konum_metni = (
                    f"**🛡️ İhlal Bölgesi:** `{safezone}`\n"
                    f"**📍 Koordinatlar:** X: `{x_val}` | Z: `{z_val}`\n"
                    f"**📮 Posta Kodu:** `{postal}`\n"
                    f"**🛣️ Cadde / Bina:** `{street}` (No: `{bina}`)"
                )
                embed.add_field(name="📍 Olay Yeri Detayları", value=konum_metni, inline=False)
                embed.add_field(name="📊 Günlük Safezone İhlali", value=f"Bugün **{ihlal_sayi}.** kez tekrarladı", inline=True)
                embed.set_footer(text="ER-LC Piyadeleri • Safezone Güvenlik Takip Sistemi")

                if rdm_kanal:
                    try:
                        await rdm_kanal.send(embed=embed)
                        print(f"[SAFEZONE İHLALİ] {killer_name} -> {victim_name} ({safezone}) logu iletildi.", flush=True)
                    except Exception as e:
                        print(f"[SAFEZONE HATA] Log iletilemedi: {e}", flush=True)

            kill_tracker["islenen_killer"] = list(self.islenen_killer)[-200:]
            save_json_atomic(KILLER_FILE, kill_tracker)

async def setup(bot: commands.Bot):
    await bot.add_cog(LiveRadar(bot))
