import os
import re
import time
import asyncio
from datetime import datetime, timezone

import aiohttp
import discord
from discord.ext import commands, tasks
from discord import app_commands

from utils.storage import load_json, async_save_json

# =====================================================================
# KANAL / ROL / ROBLOX AYARLARI
# =====================================================================
GUILD_ID = 1529545898294509589

KAYIT_KANAL_ID = 1532831582753128530          # Kayıt paneli + kişiye özel gizli thread'ler
ONAY_KANAL_ID = 1532828473972752555           # Yetkililerin önüne düşen başvuru / karakter kartları
KAYIT_LOG_KANAL_ID = 1552306929571733635      # Kaydı tamamlanan üyelerin duyurusu
GRUP_KANAL_ID = 1554038042157654016           # "PRP | Hesap Onaylama" paneli
UYE_DOSYASI_KANAL_ID = 1554853823447703623    # Canlı üye dosyaları
CK_PANEL_KANAL_ID = 1556759241614688369       # PRP | CK Başvurusu paneli
CK_ONAY_KANAL_ID = 1556754470526783518        # CK başvurularının yetkili onayına düştüğü kanal
MEVCUT_UYE_KANAL_ID = 1556759358883373096     # Mevcut Üye Grup Eşleme paneli
DESTEK_KANAL_LINK = "https://discord.com/channels/1529545898294509589/1534770099179884564"

UYE_ROL_ID = 1533919249985437706              # Üye
WHITELIST_ROL_ID = 1533908873772273715        # Whitelist
ERKEK_ROL_ID = 1534736940904218755            # Erkek
KIZ_ROL_ID = 1534736941600342016              # Kız
KAYITSIZ_ROL_ID = 1542271426386591894         # Kayıtsız (final onayda alınır)
GRUP_ONAY_BEKLIYOR_ROL_ID = 1556628657878081546  # 1. onaydan sonra verilir, final onayda alınır
ONAYLANMIS_BIREY_ROL_ID = 1534741499726663690        # Onaylanmış birey
WHITELIST_YETKILISI_ROL_ID = 1551242344190189718  # Bildirim için etiketlenir
KURUCU_ROL_ID = 1529546007635824680

YETKILI_ROL_IDLERI = [
    1529546007635824680,  # KURUCU
    1539167256246747186,  # ÜST YÖNETİM
    1534798061845483694,  # YÖNETİCİ
    1537934087166369812,  # YÖNETİM EKİBİ
    1551242344190189718,  # WHITELIST YETKILISI
]

ROBLOX_GRUP_ID = 860635623
ROBLOX_GRUP_LINK = "https://www.roblox.com/share/g/860635623"
ROBLOX_API_KEY = os.getenv("ROBLOX_API_KEY", "").strip()

THREAD_SILME_SURESI = 300        # Kayıt bitince / reddedilince thread kaç saniye sonra silinsin
HESAP_ONAY_COOLDOWN = 30         # "Hesabımı Onayla" butonu bekleme süresi (sn)
CK_COOLDOWN_SANIYE = 3 * 86400   # 3 gün (onaylanan CK sonrası bekleme süresi)

TEMA_RENK = discord.Colour(0x2B8CFF)
TURUNCU_RENK = discord.Colour(0xFF8A1F)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RED_BANNER_PATH = os.path.join(BASE_DIR, "assets", "roblox_red_banner.png")
PANEL_BANNER_PATH = os.path.join(BASE_DIR, "assets", "yeni_banner.png")
GRUP_PANEL_BANNER_PATH = os.path.join(BASE_DIR, "assets", "grup_panel_banner.jpg")
CK_PANEL_BANNER_PATH = os.path.join(BASE_DIR, "assets", "ck_panel_banner.jpg")
DATA_PATH = os.path.join(BASE_DIR, "data", "kayit_data.json")

GRUP_KANAL_LINK = f"https://discord.com/channels/{GUILD_ID}/{GRUP_KANAL_ID}"
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=8)

# =====================================================================
# AŞAMALAR
# =====================================================================
AKTIF_ASAMALAR = {"basvuru_bekliyor", "grup_bekliyor", "karakter_bekliyor", "karakter_inceleniyor"}

ASAMA_BILGI = {
    "basvuru_bekliyor":     ("🟡 1. Başvuru İnceleniyor",        1, discord.Colour.gold()),
    "grup_bekliyor":        ("🔵 Roblox Grup Doğrulaması Bekleniyor", 2, discord.Colour.blue()),
    "karakter_bekliyor":    ("🟣 Karakter Formu Bekleniyor",      3, discord.Colour.purple()),
    "karakter_inceleniyor": ("🟠 Karakter Formu İnceleniyor",     4, discord.Colour.orange()),
    "tamamlandi":           ("🟢 Kayıt Tamamlandı",               5, discord.Colour.green()),
    "reddedildi":           ("🔴 Başvuru Reddedildi",             0, discord.Colour.red()),
    "ayrildi":              ("⚫ Sunucudan Ayrıldı",              0, discord.Colour.dark_grey()),
}

# =====================================================================
# VERİ KATMANI (data/kayit_data.json)
# =====================================================================
_VERI: dict | None = None
_KILITLER: dict[int, asyncio.Lock] = {}
_ONAY_COOLDOWN: dict[int, float] = {}
_SON_API_UYARISI = 0.0


def _veri() -> dict:
    global _VERI
    if _VERI is None:
        _VERI = load_json(DATA_PATH, {})
        _VERI.setdefault("kullanicilar", {})
        _VERI.setdefault("roblox_index", {})
        _VERI.setdefault("silinecek_threadler", {})
        _VERI.setdefault("kullanilan_karakterler", {})
        _VERI.setdefault("ck_basvurulari", {})
        _VERI.setdefault("ck_gecmisi", {})
    return _VERI


async def _kaydet():
    await async_save_json(DATA_PATH, _veri())


def kayit_al(uid: int) -> dict | None:
    return _veri()["kullanicilar"].get(str(uid))


def _kilit(uid: int) -> asyncio.Lock:
    if uid not in _KILITLER:
        _KILITLER[uid] = asyncio.Lock()
    return _KILITLER[uid]


def _roblox_baglantisini_birak(kayit: dict):
    rid = str(kayit.get("roblox_id") or "")
    idx = _veri()["roblox_index"]
    if rid and idx.get(rid) == str(kayit.get("discord_id")):
        idx.pop(rid, None)


def _thread_silme_planla(kayit: dict, gecikme: int = THREAD_SILME_SURESI):
    tid = kayit.get("thread_id")
    if tid:
        _veri()["silinecek_threadler"][str(tid)] = _simdi() + gecikme
        kayit["thread_id"] = None


# =====================================================================
# YARDIMCI FONKSİYONLAR
# =====================================================================
def _simdi() -> int:
    return int(time.time())


def _ts(unix: int | None, fmt: str = "f") -> str:
    return f"<t:{int(unix)}:{fmt}>" if unix else "—"


def yetkili_mi(member: discord.Member) -> bool:
    if not isinstance(member, discord.Member):
        return False
    if member.guild_permissions.administrator:
        return True
    return any(rol.id in YETKILI_ROL_IDLERI for rol in member.roles)


def _cinsiyet_normalize(metin: str) -> str:
    m = (metin or "").strip().lower()
    if m.startswith("k") or "kız" in m or "kiz" in m or "kadın" in m:
        return "Kız"
    if m.startswith("e") or "erkek" in m:
        return "Erkek"
    return metin.strip() or "Belirtilmedi"


def _nick_olustur(karakter_ad: str, roblox_ad: str) -> str:
    ek = f" | {roblox_ad}"
    kalan = 32 - len(ek)
    if kalan < 3:
        return karakter_ad[:32]
    return f"{karakter_ad[:kalan]}{ek}"


def karakter_adi_kullanildi_mi(guild: discord.Guild | None, ad: str, haric_uid: int | None = None) -> tuple[bool, str | None]:
    """
    Karakter adının sunucuda daha önce kullanılıp kullanılmadığını kontrol eder.
    Dönüş: (kullanildi_mi: bool, aciklama: str | None)
    """
    temiz_ad = re.sub(r"\s+", " ", ad).strip().lower()
    if not temiz_ad:
        return True, "Geçersiz karakter adı."

    kullanim = _veri()["kullanilan_karakterler"].get(temiz_ad)
    if kullanim:
        sahip_uid = kullanim.get("uid")
        if haric_uid is None or sahip_uid != haric_uid:
            return True, f"Bu isim daha önce kullanılmış."

    if guild:
        for member in guild.members:
            if haric_uid and member.id == haric_uid:
                continue
            nick = member.nick or member.display_name or ""
            if "|" in nick:
                kr_parca = nick.split("|")[0].strip().lower()
                if kr_parca == temiz_ad:
                    return True, f"Bu isim şu anda aktif bir üye ({member.mention}) tarafından kullanılıyor."

    return False, None


def karakter_adi_kaydet(ad: str, uid: int):
    """Karakter adını kalıcı olarak 'kullanılan karakterler' arşivine işler."""
    temiz = re.sub(r"\s+", " ", ad).strip()
    if temiz:
        _veri()["kullanilan_karakterler"][temiz.lower()] = {
            "ad": temiz,
            "uid": uid,
            "tarih": _simdi(),
        }


def _iso_to_unix(deger: str | None) -> int | None:
    if not deger:
        return None
    try:
        dt = datetime.strptime(deger[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def _profil_link(rid) -> str:
    return f"https://www.roblox.com/users/{rid}/profile"


def _guild_icon(guild: discord.Guild | None) -> str | None:
    return guild.icon.url if guild and guild.icon else None


async def _uye_getir(guild: discord.Guild, uid: int) -> discord.Member | None:
    uye = guild.get_member(uid)
    if uye is None:
        try:
            uye = await guild.fetch_member(uid)
        except Exception:
            uye = None
    return uye


async def _kanal_getir(client: discord.Client, kanal_id: int):
    kanal = client.get_channel(kanal_id)
    if kanal is None:
        try:
            kanal = await client.fetch_channel(kanal_id)
        except Exception:
            kanal = None
    return kanal


async def _dm(uye: discord.abc.User, **kwargs) -> bool:
    try:
        await uye.send(**kwargs)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


async def _kart_kapat(mesaj: discord.Message | None, sonuc: str, renk: discord.Colour):
    """Onay kanalındaki başvuru/karakter kartına sonuç ekler ve butonları kaldırır."""
    if mesaj is None:
        return
    try:
        if mesaj.embeds:
            yeni = mesaj.embeds[0].copy()
            yeni.add_field(name="Sonuç", value=sonuc[:1024], inline=False)
            yeni.colour = renk
            await mesaj.edit(embed=yeni, view=None)
        else:
            await mesaj.edit(view=None)
    except Exception:
        pass


async def _rolleri_duzenle(uye: discord.Member, ekle: list[int], cikar: list[int], sebep: str) -> bool:
    """Rolleri ekler/çıkarır. Yetki hatası olursa False döner."""
    guild = uye.guild
    basarili = True
    eklenecek = [guild.get_role(r) for r in ekle]
    eklenecek = [r for r in eklenecek if r and r not in uye.roles]
    cikarilacak = [guild.get_role(r) for r in cikar]
    cikarilacak = [r for r in cikarilacak if r and r in uye.roles]
    try:
        if eklenecek:
            await uye.add_roles(*eklenecek, reason=sebep)
    except (discord.Forbidden, discord.HTTPException):
        basarili = False
    try:
        if cikarilacak:
            await uye.remove_roles(*cikarilacak, reason=sebep)
    except (discord.Forbidden, discord.HTTPException):
        basarili = False
    return basarili


# =====================================================================
# ROBLOX API
# =====================================================================
async def roblox_profil_getir(bilgi: str) -> dict | None:
    """Link / ID / kullanıcı adından detaylı Roblox profili döndürür. Bulunamazsa None."""
    bilgi = (bilgi or "").strip()
    user_id = None
    eslesme = re.search(r"/users/(\d+)", bilgi)
    if eslesme:
        user_id = eslesme.group(1)
    elif bilgi.isdigit():
        user_id = bilgi
    else:
        bilgi = bilgi.lstrip("@").strip()

    async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
        if not user_id:
            if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", bilgi):
                return None
            try:
                async with session.post(
                    "https://users.roblox.com/v1/usernames/users",
                    json={"usernames": [bilgi], "excludeBannedUsers": False},
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("data"):
                            user_id = str(data["data"][0]["id"])
            except Exception:
                return None
        if not user_id:
            return None

        profil = None
        try:
            async with session.get(f"https://users.roblox.com/v1/users/{user_id}") as resp:
                if resp.status == 200:
                    profil = await resp.json()
        except Exception:
            return None
        if not profil or not profil.get("name"):
            return None

        avatar_url = None
        try:
            async with session.get(
                "https://thumbnails.roblox.com/v1/users/avatar-headshot",
                params={"userIds": user_id, "size": "420x420", "format": "Png", "isCircular": "false"},
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("data"):
                        avatar_url = data["data"][0].get("imageUrl")
        except Exception:
            pass

    return {
        "id": str(profil.get("id", user_id)),
        "name": profil.get("name"),
        "display_name": profil.get("displayName") or profil.get("name"),
        "created": _iso_to_unix(profil.get("created")),
        "is_banned": bool(profil.get("isBanned")),
        "verified": bool(profil.get("hasVerifiedBadge")),
        "avatar": avatar_url,
    }


async def roblox_grup_rutbesi(roblox_id: str) -> str | None:
    """Kullanıcı grubun üyesiyse rütbe adını, değilse None döndürür (herkese açık API)."""
    try:
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            async with session.get(f"https://groups.roblox.com/v2/users/{roblox_id}/groups/roles") as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        for kayit in data.get("data", []):
            if int(kayit.get("group", {}).get("id", 0)) == ROBLOX_GRUP_ID:
                return kayit.get("role", {}).get("name") or "Member"
    except Exception:
        pass
    return None


async def roblox_katilma_istegi_bul(roblox_id: str) -> tuple[str, str | None]:
    """Open Cloud ile gruba bekleyen katılma isteğini arar.
    Dönüş: ("var", path) | ("yok", None) | ("anahtar_yok"|"yetki_hatasi"|"hata", None)"""
    if not ROBLOX_API_KEY:
        return "anahtar_yok", None
    url = f"https://apis.roblox.com/cloud/v2/groups/{ROBLOX_GRUP_ID}/join-requests"
    params = {"filter": f"user == 'users/{roblox_id}'", "maxPageSize": "10"}
    try:
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            async with session.get(url, params=params, headers={"x-api-key": ROBLOX_API_KEY}) as resp:
                if resp.status in (401, 403):
                    print(f"[KAYIT] Open Cloud yetki hatası: {resp.status} {await resp.text()}", flush=True)
                    return "yetki_hatasi", None
                if resp.status == 404:
                    # Roblox Open Cloud v2, kullanıcının bekleyen katılma isteği yoksa 404 NOT_FOUND döner:
                    # {"code": "NOT_FOUND", "message": "The join request with identifier ... was not found."}
                    return "yok", None
                if resp.status != 200:
                    print(f"[KAYIT] Open Cloud hata: {resp.status} {await resp.text()}", flush=True)
                    return "hata", None
                data = await resp.json()
        for istek in data.get("groupJoinRequests", []):
            if istek.get("user") == f"users/{roblox_id}":
                return "var", istek.get("path")
        return "yok", None
    except Exception as e:
        print(f"[KAYIT] Open Cloud istek hatası: {e}", flush=True)
        return "hata", None


async def roblox_istegi_kabul_et(path: str | None) -> bool:
    if not path or not ROBLOX_API_KEY:
        return False
    clean_path = path.lstrip("/")
    try:
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            async with session.post(
                f"https://apis.roblox.com/cloud/v2/{clean_path}:accept",
                json={},
                headers={"x-api-key": ROBLOX_API_KEY, "Content-Type": "application/json"},
            ) as resp:
                if resp.status == 200:
                    return True
                print(f"[KAYIT] İstek kabul edilemedi: {resp.status} {await resp.text()}", flush=True)
    except Exception as e:
        print(f"[KAYIT] İstek kabul hatası: {e}", flush=True)
    return False


# =====================================================================
# ÜYE DOSYASI (canlı mesaj)
# =====================================================================
def dosya_embed(kayit: dict) -> discord.Embed:
    asama = kayit.get("asama", "basvuru_bekliyor")
    etiket, adim, renk = ASAMA_BILGI.get(asama, ASAMA_BILGI["basvuru_bekliyor"])
    bar = "▰" * adim + "▱" * (5 - adim)
    uid = kayit.get("discord_id")
    rid = kayit.get("roblox_id")

    embed = discord.Embed(
        title=f"📁 Üye Dosyası • {kayit.get('roblox_ad', 'Bilinmiyor')}",
        description=(
            f"**Durum:** {etiket}\n"
            f"`{bar}`  **Aşama {adim}/5**\n"
            f"**Kullanıcı:** <@{uid}> (`{uid}`)"
        ),
        colour=renk,
    )

    embed.add_field(
        name="🪪 Discord Kimliği",
        value=(
            f"**Kullanıcı Adı:** `{kayit.get('discord_ad', '—')}`\n"
            f"**Hesap Oluşturma:** {_ts(kayit.get('discord_olusturma'), 'D')}\n"
            f"**Sunucuya Katılım:** {_ts(kayit.get('sunucu_katilim'), 'D')}"
        ),
        inline=False,
    )

    r_yas = ""
    if kayit.get("roblox_olusturma"):
        gun = max(0, (_simdi() - kayit["roblox_olusturma"]) // 86400)
        r_yas = f" (**{gun}** gün)" + (" ⚠️ *Yeni hesap*" if gun < 30 else "")
    embed.add_field(
        name="🎮 Roblox Profili",
        value=(
            f"**Kullanıcı Adı:** `{kayit.get('roblox_ad', '—')}`\n"
            f"**Görünen Ad:** `{kayit.get('roblox_gorunen_ad', '—')}`\n"
            f"**Roblox ID:** `{rid or '—'}`\n"
            f"**Profil:** [Roblox Profiline Git]({_profil_link(rid)})\n"
            f"**Hesap Oluşturma:** {_ts(kayit.get('roblox_olusturma'), 'D')}{r_yas}\n"
            f"**Hesap Durumu:** {'⛔ Yasaklı' if kayit.get('roblox_banli') else '✅ Aktif'}"
        ),
        inline=False,
    )

    embed.add_field(
        name="📝 1. Anket — Kayıt Formu",
        value=(
            f"**Gerçek Ad:** {kayit.get('gercek_ad', '—')}\n"
            f"**Cinsiyet:** {kayit.get('cinsiyet', '—')}\n"
            f"**Gönderim:** {_ts(kayit.get('basvuru_tarihi'))}"
            + (f"\n**Önceki Reddedilen Başvuru:** {kayit['onceki_red_sayisi']}" if kayit.get("onceki_red_sayisi") else "")
        ),
        inline=False,
    )

    if kayit.get("basvuru_karar"):
        k = kayit["basvuru_karar"]
        if k.get("sonuc") == "onay":
            deger = f"✅ **Onaylandı** — <@{k.get('yetkili_id')}>\n**Tarih:** {_ts(k.get('tarih'))}"
        else:
            deger = (f"❌ **Reddedildi** — <@{k.get('yetkili_id')}>\n**Tarih:** {_ts(k.get('tarih'))}\n"
                     f"**Sebep:** {k.get('sebep', '—')}")
        embed.add_field(name="🛡️ 1. Aşama Kararı", value=deger[:1024], inline=False)
    else:
        embed.add_field(name="🛡️ 1. Aşama Kararı", value="⏳ Yetkili incelemesi bekleniyor", inline=False)

    if kayit.get("grup_dogrulama"):
        g = kayit["grup_dogrulama"]
        yontem = {
            "istek_kabul": "📨 Katılma isteği bulundu ve **bot tarafından otomatik kabul edildi**",
            "istek_bulundu": "⚠️ Katılma isteği bulundu ama **otomatik kabul edilemedi** — grupta elle kabul edin!",
            "zaten_uye": "👥 Kullanıcı zaten grubun üyesi",
        }.get(g.get("yontem"), g.get("yontem", "—"))
        embed.add_field(
            name="🔗 Roblox Grup Doğrulaması",
            value=(f"{yontem}\n**Tarih:** {_ts(g.get('tarih'))}\n"
                   f"**Grup Rütbesi:** {g.get('rutbe') or '—'}"),
            inline=False,
        )
    elif asama in AKTIF_ASAMALAR or asama == "tamamlandi":
        embed.add_field(name="🔗 Roblox Grup Doğrulaması", value="⏳ Bekleniyor", inline=False)

    if kayit.get("karakter"):
        kr = kayit["karakter"]
        yas = kr.get("yas", "—")
        yas_uyari = " ⚠️ *18 yaş altı*" if str(yas).isdigit() and int(yas) < 18 else ""
        deger = (f"**Karakter Adı:** {kr.get('ad', '—')}\n"
                 f"**Karakter Yaşı:** {yas}{yas_uyari}\n"
                 f"**Gönderim:** {_ts(kr.get('tarih'))}")
        redler = kayit.get("karakter_red_gecmisi", [])
        if redler:
            deger += f"\n**Reddedilen Formlar ({len(redler)}):**"
            for r in redler[-3:]:
                deger += f"\n> `{r.get('ad')}` ({r.get('yas')}) — {r.get('sebep', '')[:80]} — <@{r.get('yetkili_id')}>"
        embed.add_field(name="🎭 2. Anket — Karakter Formu", value=deger[:1024], inline=False)
    elif asama in AKTIF_ASAMALAR or asama == "tamamlandi":
        embed.add_field(name="🎭 2. Anket — Karakter Formu", value="⏳ Bekleniyor", inline=False)

    if kayit.get("final"):
        f = kayit["final"]
        embed.add_field(
            name="🏁 Final Onayı",
            value=(f"✅ **Onaylayan:** <@{f.get('yetkili_id')}>\n"
                   f"**Tarih:** {_ts(f.get('tarih'))}\n"
                   f"**Sunucu İsmi:** `{f.get('nick', '—')}`\n"
                   f"**Verilen Roller:** {f.get('roller', '—')}"),
            inline=False,
        )

    if kayit.get("roblox_avatar"):
        embed.set_thumbnail(url=kayit["roblox_avatar"])
    embed.set_footer(text=f"Discord ID: {uid} • Roblox ID: {rid}")
    embed.timestamp = discord.utils.utcnow()
    return embed


async def dosya_guncelle(client: discord.Client, kayit: dict):
    kanal = await _kanal_getir(client, UYE_DOSYASI_KANAL_ID)
    if kanal is None:
        return
    embed = dosya_embed(kayit)
    mid = kayit.get("dosya_mesaj_id")
    if mid:
        try:
            await kanal.get_partial_message(int(mid)).edit(embed=embed)
            return
        except discord.NotFound:
            pass
        except Exception as e:
            print(f"[KAYIT] Üye dosyası düzenlenemedi: {e}", flush=True)
            return
    try:
        mesaj = await kanal.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        kayit["dosya_mesaj_id"] = mesaj.id
        await _kaydet()
    except Exception as e:
        print(f"[KAYIT] Üye dosyası gönderilemedi: {e}", flush=True)


# =====================================================================
# KİŞİYE ÖZEL GİZLİ THREAD
# =====================================================================
async def thread_hazirla(guild: discord.Guild, uye: discord.Member, kayit: dict) -> tuple[discord.Thread | None, bool]:
    """Kullanıcının gizli thread'ini döndürür, yoksa oluşturur. (thread, yeni_mi)"""
    tid = kayit.get("thread_id")
    if tid:
        th = guild.get_thread(int(tid))
        if th is None:
            try:
                th = await guild.fetch_channel(int(tid))
            except Exception:
                th = None
        if isinstance(th, discord.Thread):
            if th.archived:
                try:
                    await th.edit(archived=False)
                except Exception:
                    pass
            return th, False

    kanal = guild.get_channel(KAYIT_KANAL_ID)
    if not isinstance(kanal, discord.TextChannel):
        return None, False
    try:
        th = await kanal.create_thread(
            name=f"📋・kayıt-{uye.name}"[:100],
            type=discord.ChannelType.private_thread,
            invitable=False,
            auto_archive_duration=10080,
            reason=f"{uye} için kişiye özel kayıt odası",
        )
        await th.add_user(uye)
    except (discord.Forbidden, discord.HTTPException) as e:
        print(f"[KAYIT] Gizli thread oluşturulamadı: {e}", flush=True)
        return None, False
    kayit["thread_id"] = th.id
    return th, True


def _inceleniyor_embed(uye: discord.Member, kayit: dict) -> discord.Embed:
    embed = discord.Embed(
        title="📨 Başvurun Bize Ulaştı!",
        description=(
            f"Merhaba {uye.mention}, **Piyade RP | Los Angeles** ailesine gösterdiğin ilgi için içtenlikle teşekkür ederiz! 💙\n\n"
            "Kayıt başvurun yetkili ekibimize iletildi ve şu anda **özenle inceleniyor.** "
            "Ekibimiz her başvuruyu tek tek değerlendirdiği için bu süreç kısa bir zaman alabilir; "
            "anlayışın ve sabrın için şimdiden teşekkür ederiz. 🙏\n\n"
            "**📋 Başvuru Özetin**\n"
            f"> 👤 **Ad:** {kayit.get('gercek_ad')}\n"
            f"> ⚧ **Cinsiyet:** {kayit.get('cinsiyet')}\n"
            f"> 🎮 **Roblox:** [{kayit.get('roblox_ad')}]({_profil_link(kayit.get('roblox_id'))}) (`{kayit.get('roblox_id')}`)\n\n"
            "**⏳ Sırada Ne Var?**\n"
            "> Başvurun sonuçlandığında **bu odaya** bilgilendirme mesajı gelecek ve seni bir sonraki adıma yönlendireceğiz.\n\n"
            "-# 🔒 Bu oda yalnızca sana ve yetkili ekibimize özeldir."
        ),
        colour=discord.Colour.gold(),
    )
    if kayit.get("roblox_avatar"):
        embed.set_thumbnail(url=kayit["roblox_avatar"])
    embed.set_footer(text="Piyade RP • Kayıt Sistemi")
    embed.timestamp = discord.utils.utcnow()
    return embed


def _grup_adimi_embed(uye: discord.Member, kayit: dict) -> discord.Embed:
    karar = kayit.get("basvuru_karar") or {}
    yetkili = f"<@{karar['yetkili_id']}>" if karar.get("yetkili_id") else "yetkili ekibimiz"
    embed = discord.Embed(
        title="✅ İlk Başvurun Onaylandı!",
        description=(
            f"Tebrikler {uye.mention}! 🎉 Kayıt başvurun {yetkili} tarafından incelendi ve **onaylandı.**\n\n"
            "> **Başvurunuz onaylanmıştır, Rolplay sunucumuza giriş yapabilmeniz için aşağıdaki butona "
            "tıklayarak Roblox grubumuza katılın!**\n\n"
            "### 🎮 Sıradaki Adım: Roblox Grubumuz\n"
            "ER:LC rolplay sunucumuza erişebilmen için Roblox hesabının **Piyade RP | Los Angeles** grubunda olması gerekiyor. "
            "Bu adım, Roblox kimliğini doğrulamamızı ve sunucu erişimini sana tanımlamamızı sağlar.\n\n"
            "**🧭 Nasıl İlerlerim?**\n"
            f"> **1.** Aşağıdaki **Gruba Kaydol!** butonuna bas, <#{GRUP_KANAL_ID}> kanalına yönlendirileceksin.\n"
            "> **2.** Oradaki paneldeki bağlantıdan Roblox grubumuza **katılma isteği** gönder.\n"
            f"> **3.** Discord'a dönüp aynı kanaldaki **✅ Hesabımı Onayla** butonuna bas.\n"
            "> **4.** Hesabın doğrulanınca karakter oluşturma paneli **bu odaya** gelecek.\n\n"
            f"-# ⚠️ Gruba, kayıtta belirttiğin **{kayit.get('roblox_ad')}** hesabıyla istek göndermelisin."
        ),
        colour=discord.Colour.green(),
    )
    if kayit.get("roblox_avatar"):
        embed.set_thumbnail(url=kayit["roblox_avatar"])
    embed.set_footer(text="Piyade RP • Kayıt Sistemi")
    embed.timestamp = discord.utils.utcnow()
    return embed


def _gruba_kaydol_view() -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    v.add_item(discord.ui.Button(label="Gruba Kaydol!", emoji="🚀", style=discord.ButtonStyle.link, url=GRUP_KANAL_LINK))
    return v


def _karakter_inceleniyor_embed(uye: discord.Member, kayit: dict) -> discord.Embed:
    kr = kayit.get("karakter") or {}
    return discord.Embed(
        title="🕵️ Karakter Formun İnceleniyor",
        description=(
            f"{uye.mention}, karakter formun yetkili ekibimize ulaştı! 🙌\n\n"
            f"> 🎭 **Karakter Adı:** {kr.get('ad', '—')}\n"
            f"> 🎂 **Karakter Yaşı:** {kr.get('yas', '—')}\n\n"
            "Yetkililerimiz isim ve yaş kurallarına uygunluğunu kontrol ettikten sonra sonucu **bu odaya** ve DM kutuna ileteceğiz. "
            "Az kaldı, sabrın için teşekkürler! ✨"
        ),
        colour=discord.Colour.orange(),
    ).set_footer(text="Piyade RP • Kayıt Sistemi")


async def asama_mesaji_gonder(thread: discord.Thread, uye: discord.Member, kayit: dict):
    """Kullanıcının bulunduğu aşamaya uygun mesajı thread'e gönderir (thread yeniden oluşturulduğunda)."""
    asama = kayit.get("asama")
    try:
        if asama == "basvuru_bekliyor":
            await thread.send(content=uye.mention, embed=_inceleniyor_embed(uye, kayit))
        elif asama == "grup_bekliyor":
            await thread.send(content=uye.mention, embed=_grup_adimi_embed(uye, kayit), view=_gruba_kaydol_view())
        elif asama == "karakter_bekliyor":
            await thread.send(view=KarakterPanelView(uye.mention))
        elif asama == "karakter_inceleniyor":
            await thread.send(content=uye.mention, embed=_karakter_inceleniyor_embed(uye, kayit))
    except Exception as e:
        print(f"[KAYIT] Aşama mesajı gönderilemedi: {e}", flush=True)


# =====================================================================
# 1. AŞAMA — KAYIT FORMU
# =====================================================================
async def _otomatik_red(interaction: discord.Interaction, gerekce: str, cozum: str, log_baslik: str, log_aciklama: str, avatar: str | None = None):
    guild = interaction.guild
    red_embed = discord.Embed(
        title="❌ Kayıt Başvurunuz Otomatik Olarak Reddedildi",
        description=(
            f"Merhaba {interaction.user.mention},\n\n"
            "**Piyade RP** sunucumuza yaptığınız kayıt başvurusu **otomatik olarak reddedilmiştir.**\n\n"
            f"### 📌 Reddedilme Gerekçesi:\n{gerekce}\n\n"
            f"### 💡 Çözüm ve Tekrar Başvuru Rehberi:\n{cozum}"
        ),
        colour=discord.Colour.red(),
    )
    red_embed.set_footer(text="Piyade RP Kayıt Yönetimi", icon_url=_guild_icon(guild))
    red_embed.timestamp = discord.utils.utcnow()

    def _dosyali():
        if os.path.exists(RED_BANNER_PATH):
            red_embed.set_image(url="attachment://roblox_red_banner.png")
            return {"embed": red_embed, "file": discord.File(RED_BANNER_PATH, filename="roblox_red_banner.png")}
        return {"embed": red_embed}

    if await _dm(interaction.user, **_dosyali()):
        await interaction.followup.send(
            "❌ Başvurunuz **otomatik olarak reddedildi.** Gerekçe ve çözüm adımları **DM kutunuza iletildi.**",
            ephemeral=True,
        )
    else:
        await interaction.followup.send(
            content="⚠️ DM kutunuz kapalı olduğu için mesaj özelinize iletilemedi. Lütfen aşağıdaki adımları inceleyiniz:",
            ephemeral=True,
            **_dosyali(),
        )

    onay_kanal = guild.get_channel(ONAY_KANAL_ID)
    if onay_kanal:
        log = discord.Embed(title=f"🤖 Otomatik Red • {log_baslik}", description=log_aciklama, colour=discord.Colour.red())
        log.add_field(name="Discord Kullanıcı", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
        if avatar:
            log.set_thumbnail(url=avatar)
        log.set_footer(text="Bu başvuru yetkili onayına düşmedi • Sadece bilgilendirme")
        log.timestamp = discord.utils.utcnow()
        try:
            await onay_kanal.send(embed=log, allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            pass


def _basvuru_karti(uye: discord.Member, kayit: dict) -> discord.Embed:
    embed = discord.Embed(title="🆕 Yeni Kayıt Başvurusu • 1. Aşama", colour=discord.Colour.blurple())
    rid = kayit["roblox_id"]
    # Alan sırası eski kartlarla uyumludur (0: Discord, 1: Ad, 2: Cinsiyet, 3: Roblox Adı, 4: Profil)
    embed.add_field(name="Discord Kullanıcı", value=f"{uye.mention} (`{uye.id}`)", inline=False)
    embed.add_field(name="Gerçek Adı", value=kayit["gercek_ad"], inline=True)
    embed.add_field(name="Cinsiyet", value=kayit["cinsiyet"], inline=True)
    embed.add_field(name="Roblox Adı (Doğrulandı ✅)", value=f"**{kayit['roblox_ad']}**", inline=False)
    embed.add_field(name="Roblox Profil Linki", value=f"[{kayit['roblox_ad']} Profili]({_profil_link(rid)}) (ID: `{rid}`)", inline=False)

    detay = f"**Görünen Ad:** `{kayit.get('roblox_gorunen_ad')}`\n"
    if kayit.get("roblox_olusturma"):
        gun = max(0, (_simdi() - kayit["roblox_olusturma"]) // 86400)
        detay += f"**Hesap Yaşı:** {gun} gün ({_ts(kayit['roblox_olusturma'], 'D')})" + (" ⚠️" if gun < 30 else "") + "\n"
    detay += f"**Discord Hesap Yaşı:** {_ts(kayit.get('discord_olusturma'), 'R')}"
    embed.add_field(name="🔎 Hesap Detayları", value=detay, inline=False)
    if kayit.get("onceki_red_sayisi"):
        embed.add_field(name="⚠️ Geçmiş", value=f"Daha önce **{kayit['onceki_red_sayisi']}** kez reddedilmiş.", inline=False)

    embed.set_thumbnail(url=kayit.get("roblox_avatar") or uye.display_avatar.url)
    embed.set_footer(text=f"Başvuran ID: {uye.id}")
    embed.timestamp = discord.utils.utcnow()
    return embed


class KayitModal(discord.ui.Modal, title="📋 Kayıt Formu"):
    def __init__(self):
        super().__init__(timeout=600)
        self.gercek_ad = discord.ui.TextInput(
            label="Gerçek adın nedir?", placeholder="Örn: Ahmet Yılmaz", max_length=50, required=True,
        )
        self.roblox_link = discord.ui.TextInput(
            label="Roblox Adı, ID'si veya Profil Linki",
            placeholder="Örn: Builderman, 156 veya https://www.roblox.com/users/156/profile",
            max_length=200, required=True,
        )
        self.cinsiyet_secim = discord.ui.Select(
            placeholder="Cinsiyetini seç",
            options=[
                discord.SelectOption(label="Erkek", value="Erkek", emoji="👨"),
                discord.SelectOption(label="Kız", value="Kız", emoji="👩"),
            ],
        )
        self.add_item(self.gercek_ad)
        self.add_item(self.roblox_link)
        self.add_item(discord.ui.Label(text="Cinsiyetin nedir?", component=self.cinsiyet_secim))

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        uye = interaction.user
        uid = uye.id

        onay_kanal = guild.get_channel(ONAY_KANAL_ID)
        if onay_kanal is None:
            return await interaction.followup.send("❌ Onay kanalı bulunamadı, lütfen yöneticilere haber veriniz.", ephemeral=True)

        async with _kilit(uid):
            mevcut = kayit_al(uid)
            if mevcut and mevcut.get("asama") in AKTIF_ASAMALAR:
                return await interaction.followup.send("ℹ️ Zaten aktif bir başvurun var. Kayıt panelindeki butona tekrar basarak odana ulaşabilirsin.", ephemeral=True)

            girdi = self.roblox_link.value
            profil = await roblox_profil_getir(girdi)

            if not profil:
                return await _otomatik_red(
                    interaction,
                    gerekce=f"Formda belirttiğiniz `{girdi[:100]}` bilgisi Roblox sistemlerinde bulunamadı veya geçersiz bir format girildi.",
                    cozum=(
                        "• **Doğru Kullanıcı Adı:** Görünen adınızı (Display Name) değil, `@` ile başlayan asıl kullanıcı adınızı yazınız.\n"
                        "• **Profil Linki:** Roblox profilinize girip linki kopyalayabilirsiniz (Örn: `https://www.roblox.com/users/12345678/profile`).\n"
                        "• **Sayısal ID:** Profil linkinizdeki sayısal ID numarasını doğrudan yazabilirsiniz.\n"
                        "• **Yazım Kontrolü:** Harf ve rakamları kontrol ettikten sonra kayıt kanalından tekrar başvurabilirsiniz."
                    ),
                    log_baslik="Roblox Hesabı Bulunamadı",
                    log_aciklama=f"Girilen bilgi: `{girdi[:200]}`",
                )

            rid = profil["id"]
            if profil["is_banned"]:
                return await _otomatik_red(
                    interaction,
                    gerekce=f"Belirttiğiniz **{profil['name']}** (`{rid}`) Roblox hesabı Roblox tarafından **yasaklanmış (banned)** görünüyor.",
                    cozum="• Aktif ve yasaklı olmayan Roblox hesabınızla tekrar başvurunuz.\n• Bir hata olduğunu düşünüyorsanız destek bileti açınız.",
                    log_baslik="Yasaklı Roblox Hesabı",
                    log_aciklama=f"Roblox: [{profil['name']}]({_profil_link(rid)}) (`{rid}`)",
                    avatar=profil.get("avatar"),
                )

            # Kimlik kuralı: 1 Roblox hesabı = 1 Discord hesabı
            sahip = _veri()["roblox_index"].get(rid)
            if sahip and sahip != str(uid):
                sahip_kayit = kayit_al(int(sahip))
                if sahip_kayit and sahip_kayit.get("asama") not in ("reddedildi", "ayrildi"):
                    return await _otomatik_red(
                        interaction,
                        gerekce=f"Belirttiğiniz **{profil['name']}** (`{rid}`) Roblox hesabı sunucumuzda **başka bir Discord hesabına bağlı.** "
                                "Her Roblox hesabı yalnızca bir Discord hesabıyla kayıt olabilir.",
                        cozum="• Kendinize ait Roblox hesabınızla tekrar başvurunuz.\n• Bu hesap size aitse ve bir yanlışlık olduğunu düşünüyorsanız destek bileti açınız.",
                        log_baslik="⚠️ Kimlik Çakışması",
                        log_aciklama=(f"Roblox: [{profil['name']}]({_profil_link(rid)}) (`{rid}`)\n"
                                      f"Bu hesap zaten <@{sahip}> (`{sahip}`) kullanıcısına bağlı! (Durum: {ASAMA_BILGI.get(sahip_kayit.get('asama'), ('?',))[0]})"),
                        avatar=profil.get("avatar"),
                    )

            onceki_red = 0
            if mevcut:
                onceki_red = int(mevcut.get("onceki_red_sayisi", 0)) + (1 if mevcut.get("asama") == "reddedildi" else 0)
                _roblox_baglantisini_birak(mevcut)

            cinsiyet = self.cinsiyet_secim.values[0] if self.cinsiyet_secim.values else "Belirtilmedi"
            kayit = {
                "discord_id": uid,
                "discord_ad": str(uye),
                "discord_olusturma": int(uye.created_at.timestamp()),
                "sunucu_katilim": int(uye.joined_at.timestamp()) if getattr(uye, "joined_at", None) else None,
                "gercek_ad": self.gercek_ad.value.strip(),
                "cinsiyet": cinsiyet,
                "roblox_id": rid,
                "roblox_ad": profil["name"],
                "roblox_gorunen_ad": profil["display_name"],
                "roblox_olusturma": profil["created"],
                "roblox_banli": profil["is_banned"],
                "roblox_avatar": profil["avatar"],
                "asama": "basvuru_bekliyor",
                "basvuru_tarihi": _simdi(),
                "onceki_red_sayisi": onceki_red,
                "thread_id": None,
                "dosya_mesaj_id": mevcut.get("dosya_mesaj_id") if mevcut else None,
            }
            _veri()["kullanicilar"][str(uid)] = kayit
            _veri()["roblox_index"][rid] = str(uid)

            thread, _ = await thread_hazirla(guild, uye, kayit)
            if thread:
                try:
                    await thread.send(content=uye.mention, embed=_inceleniyor_embed(uye, kayit))
                except Exception:
                    pass

            kart = await onay_kanal.send(
                content=f"<@&{WHITELIST_YETKILISI_ROL_ID}>",
                embed=_basvuru_karti(uye, kayit),
                view=kayit_karar_view(uid),
            )
            kayit["basvuru_kart_id"] = kart.id
            await _kaydet()

        await dosya_guncelle(interaction.client, kayit)
        mesaj = f"✅ Roblox hesabın doğrulandı (**{profil['name']}**)! Başvurun yetkililere iletildi."
        if thread:
            mesaj += f"\n🔒 Sana özel kayıt odan açıldı: {thread.mention} — tüm gelişmeler oraya gelecek."
        await interaction.followup.send(mesaj, ephemeral=True)


class KayitButonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="✅ Kayıt Ol", style=discord.ButtonStyle.green, custom_id="kayit_ol_buton")
    async def kayit_ol(self, interaction: discord.Interaction, button: discord.ui.Button):
        uye = interaction.user
        if UYE_ROL_ID in [rol.id for rol in uye.roles]:
            return await interaction.response.send_message("❌ Zaten sunucumuza kayıtlısınız!", ephemeral=True)

        kayit = kayit_al(uye.id)
        if kayit and kayit.get("asama") in AKTIF_ASAMALAR:
            await interaction.response.defer(ephemeral=True, thinking=True)
            async with _kilit(uye.id):
                thread, yeni = await thread_hazirla(interaction.guild, uye, kayit)
                if thread and yeni:
                    await asama_mesaji_gonder(thread, uye, kayit)
                    await _kaydet()
            etiket = ASAMA_BILGI[kayit["asama"]][0]
            hedef = f"\n🔒 Kayıt odan: {thread.mention}" if thread else ""
            return await interaction.followup.send(f"ℹ️ Zaten aktif bir başvurun var.\n**Durum:** {etiket}{hedef}", ephemeral=True)

        await interaction.response.send_modal(KayitModal())


# =====================================================================
# 1. AŞAMA — YETKİLİ KARARI (DynamicItem: restart sonrası da çalışır)
# =====================================================================
def _hedef_id_coz(uid: int, mesaj: discord.Message | None) -> int | None:
    if uid:
        return uid
    if mesaj and mesaj.embeds:
        m = re.search(r"\d{15,}", mesaj.embeds[0].footer.text or "")
        if m:
            return int(m.group())
    return None


async def _eski_karttan_kayit(mesaj: discord.Message, uye: discord.Member) -> tuple[dict | None, str | None]:
    """Eski sistemden kalan (JSON kaydı olmayan) kartlardan kayıt oluşturur."""
    if not mesaj.embeds:
        return None, "Kart içeriği okunamadı."
    alanlar = mesaj.embeds[0].fields
    gercek_ad = alanlar[1].value if len(alanlar) > 1 else uye.display_name
    cinsiyet = _cinsiyet_normalize(alanlar[2].value if len(alanlar) > 2 else "")
    roblox_girdi = None
    for f in alanlar:
        m = re.search(r"/users/(\d+)", f.value) or re.search(r"ID: `(\d+)`", f.value)
        if m:
            roblox_girdi = m.group(1)
            break
    if not roblox_girdi and len(alanlar) > 3:
        roblox_girdi = alanlar[3].value.replace("*", "").strip()
    profil = await roblox_profil_getir(roblox_girdi or "")
    if not profil:
        return None, "Karttaki Roblox hesabı doğrulanamadı."
    sahip = _veri()["roblox_index"].get(profil["id"])
    if sahip and sahip != str(uye.id):
        sk = kayit_al(int(sahip))
        if sk and sk.get("asama") not in ("reddedildi", "ayrildi"):
            return None, f"Bu Roblox hesabı zaten <@{sahip}> kullanıcısına bağlı."
    kayit = {
        "discord_id": uye.id,
        "discord_ad": str(uye),
        "discord_olusturma": int(uye.created_at.timestamp()),
        "sunucu_katilim": int(uye.joined_at.timestamp()) if uye.joined_at else None,
        "gercek_ad": gercek_ad,
        "cinsiyet": cinsiyet,
        "roblox_id": profil["id"],
        "roblox_ad": profil["name"],
        "roblox_gorunen_ad": profil["display_name"],
        "roblox_olusturma": profil["created"],
        "roblox_banli": profil["is_banned"],
        "roblox_avatar": profil["avatar"],
        "asama": "basvuru_bekliyor",
        "basvuru_tarihi": int(mesaj.created_at.timestamp()),
        "onceki_red_sayisi": 0,
        "thread_id": None,
        "dosya_mesaj_id": None,
        "basvuru_kart_id": mesaj.id,
        "eski_sistem": True,
    }
    _veri()["kullanicilar"][str(uye.id)] = kayit
    _veri()["roblox_index"][profil["id"]] = str(uye.id)
    return kayit, None


class KayitKararButonu(discord.ui.DynamicItem[discord.ui.Button], template=r"kayit_(?P<islem>onayla|reddet)_(?P<uid>\d+)"):
    def __init__(self, islem: str, uid: int):
        onay = islem == "onayla"
        super().__init__(
            discord.ui.Button(
                label="ONAYLA" if onay else "REDDET",
                emoji="✅" if onay else "✖️",
                style=discord.ButtonStyle.green if onay else discord.ButtonStyle.red,
                custom_id=f"kayit_{islem}_{uid}",
            )
        )
        self.islem = islem
        self.uid = uid

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str], /):
        return cls(match["islem"], int(match["uid"]))

    async def callback(self, interaction: discord.Interaction):
        if not yetkili_mi(interaction.user):
            return await interaction.response.send_message("❌ Bu işlemi yapma yetkiniz yok.", ephemeral=True)
        hedef_id = _hedef_id_coz(self.uid, interaction.message)
        if not hedef_id:
            return await interaction.response.send_message("❌ Kullanıcı ID okunamadı.", ephemeral=True)

        kayit = kayit_al(hedef_id)
        if kayit and kayit.get("asama") != "basvuru_bekliyor" and kayit.get("basvuru_kart_id") == interaction.message.id:
            etiket = ASAMA_BILGI.get(kayit.get("asama"), ("?",))[0]
            return await interaction.response.send_message(f"ℹ️ Bu başvuru zaten işlenmiş. Güncel durum: **{etiket}**", ephemeral=True)

        if self.islem == "reddet":
            return await interaction.response.send_modal(KayitRedModal(hedef_id, interaction.message))
        await kayit_onayla(interaction, hedef_id)


def kayit_karar_view(uid: int) -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    v.add_item(KayitKararButonu("onayla", uid))
    v.add_item(KayitKararButonu("reddet", uid))
    return v


class OnayView(discord.ui.View):
    """Eski kayıtlarla geriye dönük uyumluluk için View sarmalayıcısı."""
    def __init__(self, *, user_id: int | None = None):
        super().__init__(timeout=None)
        uid = user_id or 0
        self.add_item(KayitKararButonu("onayla", uid))
        self.add_item(KayitKararButonu("reddet", uid))



async def kayit_onayla(interaction: discord.Interaction, uid: int):
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild
    uye = await _uye_getir(guild, uid)
    if uye is None:
        await _kart_kapat(interaction.message, "⚫ Kullanıcı sunucudan ayrılmış.", discord.Colour.dark_grey())
        return await interaction.followup.send("❌ Kullanıcı sunucuda bulunamadı (ayrılmış olabilir).", ephemeral=True)

    if UYE_ROL_ID in [r.id for r in uye.roles]:
        await _kart_kapat(interaction.message, f"ℹ️ Kullanıcı zaten kayıtlı üye — işlem yapılmadı ({interaction.user.mention})", discord.Colour.dark_grey())
        return await interaction.followup.send("ℹ️ Bu kullanıcı zaten **Üye**. Herhangi bir işlem yapılmadı.", ephemeral=True)

    async with _kilit(uid):
        kayit = kayit_al(uid)
        if kayit is None or kayit.get("asama") not in AKTIF_ASAMALAR and kayit.get("basvuru_kart_id") != interaction.message.id:
            kayit, hata = await _eski_karttan_kayit(interaction.message, uye)
            if hata:
                return await interaction.followup.send(f"❌ {hata}", ephemeral=True)
        if kayit.get("asama") != "basvuru_bekliyor":
            etiket = ASAMA_BILGI.get(kayit.get("asama"), ("?",))[0]
            await _kart_kapat(interaction.message, f"ℹ️ Zaten işlenmiş — {etiket}", discord.Colour.dark_grey())
            return await interaction.followup.send(f"ℹ️ Bu başvuru zaten işlenmiş. Güncel durum: **{etiket}**", ephemeral=True)

        rol_ok = await _rolleri_duzenle(uye, [GRUP_ONAY_BEKLIYOR_ROL_ID], [], "Kayıt 1. aşama onaylandı")
        kayit["asama"] = "grup_bekliyor"
        kayit["basvuru_karar"] = {"sonuc": "onay", "yetkili_id": interaction.user.id, "tarih": _simdi()}

        thread, _ = await thread_hazirla(guild, uye, kayit)
        if thread:
            try:
                await thread.send(content=uye.mention, embed=_grup_adimi_embed(uye, kayit), view=_gruba_kaydol_view())
            except Exception:
                pass
        await _kaydet()

    dm = discord.Embed(
        title="✅ İlk Başvurun Onaylandı!",
        description=(
            f"**{guild.name}** sunucusundaki kayıt başvurun onaylandı! 🎉\n\n"
            "Rolplay sunucumuza giriş yapabilmen için Roblox grubumuza katılman gerekiyor. "
            + (f"Detaylar kayıt odanda seni bekliyor: {thread.jump_url}" if thread else f"Detaylar için: {GRUP_KANAL_LINK}")
        ),
        colour=discord.Colour.green(),
    ).set_footer(text=guild.name, icon_url=_guild_icon(guild))
    await _dm(uye, embed=dm, view=_gruba_kaydol_view())

    await dosya_guncelle(interaction.client, kayit)
    await _kart_kapat(
        interaction.message,
        f"✅ **1. Aşama Onaylandı** — {interaction.user.mention}\n🔵 Roblox grup doğrulaması bekleniyor.",
        discord.Colour.green(),
    )
    uyari = "" if rol_ok else "\n⚠️ **Grup Onayı Bekliyor** rolü verilemedi — botun rolünü hiyerarşide yukarı taşıyın."
    await interaction.followup.send(f"✅ {uye.mention} ilk aşamadan geçti, Roblox grup adımına yönlendirildi.{uyari}", ephemeral=True)


class KayitRedModal(discord.ui.Modal, title="❌ Başvuru Reddetme"):
    sebep = discord.ui.TextInput(
        label="Reddetme Sebebi",
        style=discord.TextStyle.paragraph,
        placeholder="Örn: Roblox hesabı uygun değil / isim kural dışı.",
        max_length=400,
        required=True,
    )

    def __init__(self, hedef_id: int, orijinal_mesaj: discord.Message):
        super().__init__()
        self.hedef_id = hedef_id
        self.orijinal_mesaj = orijinal_mesaj

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        uye = await _uye_getir(guild, self.hedef_id)
        sebep = self.sebep.value

        kayit = None
        async with _kilit(self.hedef_id):
            kayit = kayit_al(self.hedef_id)
            if kayit and kayit.get("basvuru_kart_id") == self.orijinal_mesaj.id:
                if kayit.get("asama") != "basvuru_bekliyor":
                    return await interaction.followup.send("ℹ️ Bu başvuru zaten işlenmiş.", ephemeral=True)
                kayit["asama"] = "reddedildi"
                kayit["basvuru_karar"] = {"sonuc": "red", "yetkili_id": interaction.user.id, "tarih": _simdi(), "sebep": sebep}
                _roblox_baglantisini_birak(kayit)
                if kayit.get("thread_id"):
                    th = guild.get_thread(int(kayit["thread_id"]))
                    if th and uye:
                        try:
                            await th.send(
                                content=uye.mention,
                                embed=discord.Embed(
                                    title="❌ Başvurun Reddedildi",
                                    description=(
                                        f"{uye.mention}, kayıt başvurun yetkili ekibimiz tarafından incelendi ve maalesef **reddedildi.**\n\n"
                                        f"**📌 Sebep:**\n```{sebep}```\n"
                                        f"Eksikleri giderdikten sonra <#{KAYIT_KANAL_ID}> kanalındaki panelden **tekrar başvurabilirsin.**\n\n"
                                        f"-# 🗑️ Bu oda {THREAD_SILME_SURESI // 60} dakika içinde otomatik olarak silinecektir."
                                    ),
                                    colour=discord.Colour.red(),
                                ),
                            )
                        except Exception:
                            pass
                    _thread_silme_planla(kayit)
                await _kaydet()
            else:
                kayit = None  # Eski sistem kartı: sadece DM + kart güncelleme

        dm_embed = discord.Embed(
            title="❌ Kayıt Başvurunuz Reddedildi",
            description=(
                f"Merhaba {uye.mention if uye else 'Kullanıcı'},\n\n"
                f"**{guild.name}** sunucusundaki kayıt başvurunuz yetkili ekip tarafından incelenmiş ve **reddedilmiştir.**\n\n"
                f"**Reddedilme Sebebi:**\n```{sebep}```\n"
                "Eksikleri giderdikten sonra kayıt kanalından tekrar başvurabilir, sorularınız için yetkili ekibimizle iletişime geçebilirsiniz."
            ),
            colour=discord.Colour.red(),
        )
        dm_embed.set_footer(text=f"İnceleyen Yetkili: {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        dm_embed.timestamp = discord.utils.utcnow()
        dm_ok = False
        if uye:
            if os.path.exists(RED_BANNER_PATH):
                dm_embed.set_image(url="attachment://roblox_red_banner.png")
                dm_ok = await _dm(uye, embed=dm_embed, file=discord.File(RED_BANNER_PATH, filename="roblox_red_banner.png"))
            else:
                dm_ok = await _dm(uye, embed=dm_embed)

        if kayit:
            await dosya_guncelle(interaction.client, kayit)
        await _kart_kapat(self.orijinal_mesaj, f"❌ **Reddedildi** — {interaction.user.mention}\n**Sebep:** {sebep}", discord.Colour.red())
        ek = "" if dm_ok else "\n⚠️ Kullanıcıya DM gönderilemedi."
        await interaction.followup.send(f"✅ Başvuru reddedildi.{ek}", ephemeral=True)


# =====================================================================
# 2. AŞAMA — ROBLOX GRUP PANELİ ("Hesabımı Onayla")
# =====================================================================
def _grup_bulunamadi_embed(kayit: dict) -> discord.Embed:
    return discord.Embed(
        title="🔍 Hesap Bulunamadı",
        description=(
            f"Roblox grubumuza gelen istekler arasında **{kayit.get('roblox_ad')}** (`{kayit.get('roblox_id')}`) hesabına ait bir istek bulunamadı.\n\n"
            "**Lütfen şunları kontrol et:**\n"
            f"> **1.** [Roblox grubumuza]({ROBLOX_GRUP_LINK}) gidip **Join Community / Topluluğa Katıl** butonuna bastın mı?\n"
            f"> **2.** İsteği kayıtta belirttiğin **{kayit.get('roblox_ad')}** hesabıyla mı gönderdin?\n"
            "> **3.** İsteğin Roblox'ta *Pending / Beklemede* görünüyor mu?\n"
            "> **4.** İsteği yeni gönderdiysen birkaç saniye bekleyip tekrar dene.\n\n"
            f"-# ⏳ Butonu {HESAP_ONAY_COOLDOWN} saniye sonra tekrar kullanabilirsin. Sorun devam ederse [destek bileti]({DESTEK_KANAL_LINK}) aç."
        ),
        colour=discord.Colour.red(),
    )


async def _yetkililere_api_uyarisi(client: discord.Client, durum: str):
    global _SON_API_UYARISI
    if time.monotonic() - _SON_API_UYARISI < 600:
        return
    _SON_API_UYARISI = time.monotonic()
    kanal = await _kanal_getir(client, ONAY_KANAL_ID)
    if kanal:
        aciklama = {
            "anahtar_yok": "`ROBLOX_API_KEY` ortam değişkeni tanımlı değil!",
            "yetki_hatasi": "Roblox API anahtarı reddedildi (401/403). Anahtarın **groups** izni (`group:read`, `group:write`), grup seçimi ve IP kısıtlaması (`0.0.0.0/0`) kontrol edilmeli.",
        }.get(durum, "Roblox Open Cloud API'sine ulaşılamadı (geçici olabilir).")
        try:
            await kanal.send(embed=discord.Embed(title="⚠️ Roblox Grup Doğrulama Hatası", description=aciklama, colour=discord.Colour.orange()))
        except Exception:
            pass


async def hesabimi_onayla(interaction: discord.Interaction):
    uye = interaction.user
    uid = uye.id
    kalan = HESAP_ONAY_COOLDOWN - (time.monotonic() - _ONAY_COOLDOWN.get(uid, 0))
    if kalan > 0:
        return await interaction.response.send_message(f"⏳ Lütfen **{int(kalan) + 1} saniye** sonra tekrar dene.", ephemeral=True)

    kayit = kayit_al(uid)
    asama = kayit.get("asama") if kayit else None
    if not kayit or asama in ("reddedildi", "ayrildi"):
        if UYE_ROL_ID in [r.id for r in uye.roles]:
            return await interaction.response.send_message("ℹ️ Sistemde yeni kayıt akışına ait bir kaydın bulunmuyor. Zaten üyeysen grup için yetkililerle iletişime geç.", ephemeral=True)
        return await interaction.response.send_message(f"❌ Önce <#{KAYIT_KANAL_ID}> kanalından kayıt başvurusu yapmalısın.", ephemeral=True)
    if asama == "basvuru_bekliyor":
        return await interaction.response.send_message("⏳ İlk başvurun hâlâ yetkililer tarafından inceleniyor. Onaylandığında kayıt odana bildirim gelecek.", ephemeral=True)
    if asama in ("karakter_bekliyor", "karakter_inceleniyor"):
        hedef = f" <#{kayit['thread_id']}>" if kayit.get("thread_id") else f" <#{KAYIT_KANAL_ID}>"
        return await interaction.response.send_message(f"✅ Hesabın zaten doğrulandı! Karakter adımı için kayıt odana git:{hedef}", ephemeral=True)
    if asama == "tamamlandi":
        return await interaction.response.send_message("✅ Kaydın zaten tamamlanmış. İyi roller! 🎮", ephemeral=True)

    _ONAY_COOLDOWN[uid] = time.monotonic()
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild

    async with _kilit(uid):
        kayit = kayit_al(uid)
        if not kayit or kayit.get("asama") != "grup_bekliyor":
            return await interaction.followup.send("ℹ️ Kaydın bu adımda değil, lütfen tekrar dene.", ephemeral=True)

        rid = str(kayit["roblox_id"])
        profil = await roblox_profil_getir(rid)
        if not profil:
            _ONAY_COOLDOWN.pop(uid, None)
            return await interaction.followup.send("⚠️ Roblox profiline şu an ulaşılamıyor. Lütfen biraz sonra tekrar dene.", ephemeral=True)
        if profil["is_banned"]:
            return await interaction.followup.send("⛔ Kayıtlı Roblox hesabın yasaklı görünüyor. Lütfen yetkililerle iletişime geç.", ephemeral=True)
        kayit.update({
            "roblox_ad": profil["name"],
            "roblox_gorunen_ad": profil["display_name"],
            "roblox_avatar": profil["avatar"] or kayit.get("roblox_avatar"),
            "roblox_banli": profil["is_banned"],
        })

        rutbe = await roblox_grup_rutbesi(rid)
        if rutbe:
            yontem = "zaten_uye"
        else:
            durum, path = await roblox_katilma_istegi_bul(rid)
            if durum == "yok":
                await _kaydet()
                v = discord.ui.View()
                v.add_item(discord.ui.Button(label="Roblox Grubumuz", emoji="🔗", style=discord.ButtonStyle.link, url=ROBLOX_GRUP_LINK))
                return await interaction.followup.send(embed=_grup_bulunamadi_embed(kayit), view=v, ephemeral=True)
            if durum != "var":
                _ONAY_COOLDOWN.pop(uid, None)
                await _yetkililere_api_uyarisi(interaction.client, durum)
                return await interaction.followup.send("⚠️ Şu anda grup isteklerini kontrol edemiyoruz. Yetkililer bilgilendirildi, lütfen biraz sonra tekrar dene.", ephemeral=True)
            kabul = await roblox_istegi_kabul_et(path)
            yontem = "istek_kabul" if kabul else "istek_bulundu"
            if kabul:
                rutbe = await roblox_grup_rutbesi(rid) or "Member"

        kayit["asama"] = "karakter_bekliyor"
        kayit["grup_dogrulama"] = {"yontem": yontem, "tarih": _simdi(), "rutbe": rutbe}
        await _rolleri_duzenle(uye, [ONAYLANMIS_BIREY_ROL_ID], [], "Roblox hesabı onaylandı")

        thread, _ = await thread_hazirla(guild, uye, kayit)
        if thread:
            try:
                await thread.send(view=KarakterPanelView(uye.mention))
            except Exception as e:
                print(f"[KAYIT] Karakter paneli gönderilemedi: {e}", flush=True)
        await _kaydet()

    await dosya_guncelle(interaction.client, kayit)

    basari = discord.Embed(
        title="✅ Hesabın Doğrulandı!",
        description=(
            f"**{kayit['roblox_ad']}** hesabın Roblox grubumuzda bulundu"
            + (" ve isteğin **kabul edildi!** 🎉" if yontem == "istek_kabul" else "! 🎉")
            + "\n\nSon adım: **karakterini oluşturmak.** Karakter oluşturma paneli kayıt odana gönderildi."
        ),
        colour=discord.Colour.green(),
    )
    if kayit.get("roblox_avatar"):
        basari.set_thumbnail(url=kayit["roblox_avatar"])
    v = discord.ui.View()
    if thread:
        v.add_item(discord.ui.Button(label="Kayıt Odama Git", emoji="🎭", style=discord.ButtonStyle.link, url=thread.jump_url))
    await interaction.followup.send(embed=basari, view=v, ephemeral=True)


class GrupPanelView(discord.ui.LayoutView):
    """PRP | Hesap Onaylama paneli (Components V2 — ince ayraçlar + büyük görsel)."""

    def __init__(self):
        super().__init__(timeout=None)
        onay_btn = discord.ui.Button(label="Hesabımı Onayla!", emoji="✅", style=discord.ButtonStyle.success, custom_id="grup_hesap_onayla")
        onay_btn.callback = hesabimi_onayla
        grup_btn = discord.ui.Button(label="Roblox Grubumuz", emoji="🔗", style=discord.ButtonStyle.link, url=ROBLOX_GRUP_LINK)

        ayrac = lambda: discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.large)

        c = discord.ui.Container(accent_colour=TEMA_RENK)
        c.add_item(discord.ui.TextDisplay(
            "# 🛡️ PRP | Hesap Onaylama\n"
            "**Piyade RP | Los Angeles** ER:LC sunucumuzda rol yapabilmek için Roblox hesabının grubumuzda olması gerekiyor. "
            "Aşağıdaki adımları **sırasıyla** takip et; birkaç dakika içinde aramızdasın! 🚓"
        ))
        c.add_item(ayrac())
        c.add_item(discord.ui.TextDisplay(
            "## 1️⃣ Roblox Grubumuza Nasıl Katılırım?\n"
            f"**1.** Bağlantıya tıkla ➜ **[Piyade RP | Los Angeles]({ROBLOX_GRUP_LINK})**\n"
            "**2.** Roblox'a, kayıt formunda yazdığın **aynı hesapla** giriş yaptığından emin ol.\n"
            "**3.** Grup sayfasındaki **Join Community / Topluluğa Katıl** butonuna bas.\n"
            "**4.** Grubumuz onaylı giriş kullandığı için bir **katılma isteği** gönderilir. "
            "İsteğin *Pending / Beklemede* görünmesi tamamen normaldir."
        ))
        c.add_item(ayrac())
        c.add_item(discord.ui.TextDisplay(
            "## 2️⃣ Hesabımı Nasıl Onaylarım?\n"
            "**1.** İsteği gönderdikten sonra Discord'a, **bu kanala** geri dön.\n"
            "**2.** Aşağıdaki **✅ Hesabımı Onayla!** butonuna bas.\n"
            "**3.** Bot, kayıtta verdiğin Roblox profilini inceler ve grubumuza gelen istekler arasında **Roblox ID'ni** arar.\n"
            "**4.** İsteğin bulunursa **otomatik olarak kabul edilir** ve kayıt odana karakter oluşturma paneli gönderilir.\n"
            f"**5.** *Hesap bulunamadı* uyarısı alırsan doğru hesapla istek attığını kontrol et ve **{HESAP_ONAY_COOLDOWN} saniye** sonra tekrar dene."
        ))
        c.add_item(ayrac())
        c.add_item(discord.ui.TextDisplay(
            "## 3️⃣ Karakterimi Nasıl Oluştururum?\n"
            f"**1.** Hesabın onaylanınca <#{KAYIT_KANAL_ID}> kanalında **sana özel açılan odaya** git.\n"
            "**2.** **🎭 Karakter Oluştur** butonuna bas ve açılan formu doldur.\n"
            "**3.** Karakter adı **yabancı** bir isim olmalı ve **ünlü ismi olmamalı.** *(Örn: John Carter)*\n"
            "**4.** Karakterin **18 yaşından büyük** olmalı.\n"
            "**5.** Formun onaylanınca rollerin verilir, ismin `Karakter Adı | Roblox Adı` olarak düzenlenir ve sunucumuzun kapıları sana açılır! 🎉"
        ))
        c.add_item(ayrac())
        c.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem("attachment://grup_panel_banner.jpg")))
        c.add_item(discord.ui.TextDisplay(
            f"-# ⚠️ Bir sorun yaşarsan [Destek Bileti]({DESTEK_KANAL_LINK}) kanalından talep oluşturabilirsin."
        ))
        c.add_item(discord.ui.ActionRow(onay_btn, grup_btn))
        self.add_item(c)


# =====================================================================
# 3. AŞAMA — KARAKTER OLUŞTURMA
# =====================================================================
async def karakter_olustur_tiklandi(interaction: discord.Interaction):
    kayit = kayit_al(interaction.user.id)
    asama = kayit.get("asama") if kayit else None
    if asama == "karakter_bekliyor":
        return await interaction.response.send_modal(KarakterModal())
    if asama == "karakter_inceleniyor":
        return await interaction.response.send_message("⏳ Karakter formun şu anda yetkililer tarafından inceleniyor.", ephemeral=True)
    if asama == "tamamlandi":
        return await interaction.response.send_message("✅ Kaydın zaten tamamlandı.", ephemeral=True)
    if asama == "grup_bekliyor":
        return await interaction.response.send_message(f"🔗 Önce <#{GRUP_KANAL_ID}> kanalından Roblox hesabını onaylamalısın.", ephemeral=True)
    return await interaction.response.send_message("❌ Bu panel sana ait değil ya da henüz bu adıma gelmedin.", ephemeral=True)


class KarakterPanelView(discord.ui.LayoutView):
    def __init__(self, mention: str | None = None):
        super().__init__(timeout=None)
        btn = discord.ui.Button(label="Karakter Oluştur", emoji="🎭", style=discord.ButtonStyle.primary, custom_id="karakter_olustur_buton")
        btn.callback = karakter_olustur_tiklandi

        ayrac = lambda: discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.large)
        c = discord.ui.Container(accent_colour=discord.Colour.purple())
        c.add_item(discord.ui.TextDisplay(
            (f"{mention}\n" if mention else "")
            + "# 🎭 Karakter Oluşturma\n"
            "Hesabın doğrulandı ve Roblox grubumuza kabul edildin, tebrikler! 🎉 "
            "Şimdi son adımdasın: **rolplay karakterini oluşturmak.**"
        ))
        c.add_item(ayrac())
        c.add_item(discord.ui.TextDisplay(
            "## 📋 Nasıl Karakter Oluştururum?\n"
            "**1.** Aşağıdaki **🎭 Karakter Oluştur** butonuna bas.\n"
            "**2.** **Karakter Adı** kısmına karakterinin **adını ve soyadını** yaz.\n"
            "**3.** **Karakter Yaşı** kısmına yalnızca **sayı** yaz.\n"
            "**4.** **Gönder**'e bas; formun yetkililere iletilir.\n"
            "**5.** Sonuç **bu odaya** ve DM kutuna bildirilir. Onaylanınca rollerin otomatik verilir!"
        ))
        c.add_item(ayrac())
        c.add_item(discord.ui.TextDisplay(
            "## 📜 Karakter Kuralları\n"
            "• İsim **yabancı** olmalı. *(Örn: Michael Turner, Emily Johnson)*\n"
            "• **Ünlü / tanınmış kişi** ya da kurgusal karakter isimleri kullanılamaz. *(Örn: Elon Musk, Tony Stark)*\n"
            "• Karakter **18 yaşından büyük** olmalı.\n"
            "• Troll, argo veya anlamsız isimler reddedilir.\n"
            "-# İsim ve yaş, yetkililer tarafından manuel olarak kontrol edilir."
        ))
        c.add_item(discord.ui.ActionRow(btn))
        self.add_item(c)


class KarakterModal(discord.ui.Modal, title="🎭 Karakter Oluştur"):
    def __init__(self):
        super().__init__(timeout=600)
        self.karakter_ad = discord.ui.TextInput(
            label="Karakterin adı ve soyadı nedir?",
            placeholder="Yabancı bir isim, ünlü ismi olmamalı. Örn: John Carter",
            min_length=3, max_length=28, required=True,
        )
        self.karakter_yas = discord.ui.TextInput(
            label="Karakterinin yaşı kaç?",
            placeholder="18 veya üzeri olmalı. Örn: 24",
            min_length=1, max_length=3, required=True,
        )
        self.add_item(self.karakter_ad)
        self.add_item(self.karakter_yas)

    async def on_submit(self, interaction: discord.Interaction):
        ad = re.sub(r"\s+", " ", self.karakter_ad.value).strip()
        yas = self.karakter_yas.value.strip()
        if not yas.isdigit() or not (1 <= int(yas) <= 120):
            return await interaction.response.send_message("❌ Karakter yaşı yalnızca **sayı** olmalı (Örn: `24`). Lütfen butona tekrar basıp formu doldur.", ephemeral=True)

        kullanildi, _ = karakter_adi_kullanildi_mi(interaction.guild, ad, interaction.user.id)
        if kullanildi:
            return await interaction.response.send_message(
                f"❌ **{ad}** karakter adı sunucumuzda daha önce kullanılmış veya şu an aktif bir üyeye ait.\n"
                "Sunucumuzda her karakter adı benzersiz olmalıdır. Lütfen butona tekrar basıp başka bir isim seçiniz.",
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        uye = interaction.user
        uid = uye.id
        onay_kanal = guild.get_channel(ONAY_KANAL_ID)
        if onay_kanal is None:
            return await interaction.followup.send("❌ Onay kanalı bulunamadı, lütfen yöneticilere haber veriniz.", ephemeral=True)

        async with _kilit(uid):
            kayit = kayit_al(uid)
            if not kayit or kayit.get("asama") != "karakter_bekliyor":
                return await interaction.followup.send("ℹ️ Şu anda karakter formu gönderemezsin.", ephemeral=True)

            kayit["karakter"] = {"ad": ad, "yas": int(yas), "tarih": _simdi()}
            kayit["asama"] = "karakter_inceleniyor"

            redler = kayit.get("karakter_red_gecmisi", [])
            embed = discord.Embed(title="🎭 Karakter Onay Başvurusu • 2. Aşama", colour=discord.Colour.purple())
            embed.add_field(name="Discord Kullanıcı", value=f"{uye.mention} (`{uid}`)", inline=False)
            embed.add_field(name="🎭 Karakter Adı", value=f"**{ad}**", inline=True)
            embed.add_field(name="🎂 Karakter Yaşı", value=f"**{yas}**" + (" ⚠️ *18 yaş altı!*" if int(yas) < 18 else ""), inline=True)
            embed.add_field(name="🎮 Roblox", value=f"[{kayit['roblox_ad']}]({_profil_link(kayit['roblox_id'])}) (`{kayit['roblox_id']}`)", inline=False)
            embed.add_field(name="📝 1. Anket", value=f"**Gerçek Ad:** {kayit.get('gercek_ad')}\n**Cinsiyet:** {kayit.get('cinsiyet')}", inline=False)
            onizleme = _nick_olustur(ad, kayit["roblox_ad"])
            embed.add_field(name="🏷️ Onaylanınca Sunucu İsmi", value=f"`{onizleme}`", inline=False)
            if redler:
                embed.add_field(name="⚠️ Geçmiş", value=f"Daha önce **{len(redler)}** karakter formu reddedildi.\nSon: `{redler[-1].get('ad')}` — {redler[-1].get('sebep', '')[:150]}", inline=False)
            embed.add_field(name="🔎 Manuel Kontrol", value="• İsim yabancı mı?\n• Ünlü / kurgusal karakter ismi mi?\n• Yaş 18 ve üzeri mi?", inline=False)
            if kayit.get("roblox_avatar"):
                embed.set_thumbnail(url=kayit["roblox_avatar"])
            embed.set_footer(text=f"Başvuran ID: {uid}")
            embed.timestamp = discord.utils.utcnow()

            kart = await onay_kanal.send(content=f"<@&{WHITELIST_YETKILISI_ROL_ID}>", embed=embed, view=karakter_karar_view(uid))
            kayit["karakter_kart_id"] = kart.id

            thread, _ = await thread_hazirla(guild, uye, kayit)
            if thread:
                try:
                    await thread.send(content=uye.mention, embed=_karakter_inceleniyor_embed(uye, kayit))
                except Exception:
                    pass
            await _kaydet()

        await dosya_guncelle(interaction.client, kayit)
        await interaction.followup.send("✅ Karakter formun yetkililere iletildi! Sonuç kayıt odana ve DM kutuna gelecek.", ephemeral=True)


class KarakterKararButonu(discord.ui.DynamicItem[discord.ui.Button], template=r"karakter_(?P<islem>onayla|reddet)_(?P<uid>\d+)"):
    def __init__(self, islem: str, uid: int):
        onay = islem == "onayla"
        super().__init__(
            discord.ui.Button(
                label="KARAKTERİ ONAYLA" if onay else "REDDET",
                emoji="✅" if onay else "✖️",
                style=discord.ButtonStyle.green if onay else discord.ButtonStyle.red,
                custom_id=f"karakter_{islem}_{uid}",
            )
        )
        self.islem = islem
        self.uid = uid

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str], /):
        return cls(match["islem"], int(match["uid"]))

    async def callback(self, interaction: discord.Interaction):
        if not yetkili_mi(interaction.user):
            return await interaction.response.send_message("❌ Bu işlemi yapma yetkiniz yok.", ephemeral=True)
        kayit = kayit_al(self.uid)
        if not kayit or kayit.get("asama") != "karakter_inceleniyor" or kayit.get("karakter_kart_id") != interaction.message.id:
            etiket = ASAMA_BILGI.get(kayit.get("asama"), ("?",))[0] if kayit else "Kayıt bulunamadı"
            return await interaction.response.send_message(f"ℹ️ Bu karakter formu zaten işlenmiş. Güncel durum: **{etiket}**", ephemeral=True)
        if self.islem == "reddet":
            return await interaction.response.send_modal(KarakterRedModal(self.uid, interaction.message))
        await karakter_onayla(interaction, self.uid)


def karakter_karar_view(uid: int) -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    v.add_item(KarakterKararButonu("onayla", uid))
    v.add_item(KarakterKararButonu("reddet", uid))
    return v


async def karakter_onayla(interaction: discord.Interaction, uid: int):
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild
    uye = await _uye_getir(guild, uid)
    if uye is None:
        await _kart_kapat(interaction.message, "⚫ Kullanıcı sunucudan ayrılmış.", discord.Colour.dark_grey())
        return await interaction.followup.send("❌ Kullanıcı sunucuda bulunamadı.", ephemeral=True)

    async with _kilit(uid):
        kayit = kayit_al(uid)
        if not kayit or kayit.get("asama") != "karakter_inceleniyor":
            return await interaction.followup.send("ℹ️ Bu karakter formu zaten işlenmiş.", ephemeral=True)

        kr = kayit["karakter"]
        karakter_adi_kaydet(kr["ad"], uid)
        cinsiyet_rol = KIZ_ROL_ID if kayit.get("cinsiyet") == "Kız" else ERKEK_ROL_ID if kayit.get("cinsiyet") == "Erkek" else None
        ekle = [UYE_ROL_ID, WHITELIST_ROL_ID, ONAYLANMIS_BIREY_ROL_ID] + ([cinsiyet_rol] if cinsiyet_rol else [])
        rol_ok = await _rolleri_duzenle(uye, ekle, [KAYITSIZ_ROL_ID, GRUP_ONAY_BEKLIYOR_ROL_ID], "Kayıt tamamlandı (karakter onaylandı)")

        nick = _nick_olustur(kr["ad"], kayit["roblox_ad"])
        nick_ok = True
        try:
            await uye.edit(nick=nick, reason="Kayıt tamamlandı")
        except (discord.Forbidden, discord.HTTPException):
            nick_ok = False

        rol_adlari = ", ".join(f"<@&{r}>" for r in ekle)
        kayit["asama"] = "tamamlandi"
        kayit["final"] = {"yetkili_id": interaction.user.id, "tarih": _simdi(), "nick": nick, "roller": rol_adlari}

        if kayit.get("thread_id"):
            th = guild.get_thread(int(kayit["thread_id"]))
            if th:
                try:
                    await th.send(
                        content=uye.mention,
                        embed=discord.Embed(
                            title="🎉 Kaydın Tamamlandı — Aramıza Hoş Geldin!",
                            description=(
                                f"Tebrikler {uye.mention}! Karakterin **onaylandı** ve kaydın başarıyla tamamlandı. 🥳\n\n"
                                f"> 🏷️ **Sunucu İsmin:** `{nick}`\n"
                                f"> 🎭 **Karakterin:** {kr['ad']} ({kr['yas']})\n"
                                f"> 🎮 **Roblox:** {kayit['roblox_ad']}\n"
                                f"> 🎖️ **Rollerin:** {rol_adlari}\n\n"
                                "Artık sunucumuzun tüm kanalları sana açık. Keyifli ve kaliteli roller dileriz! 🚓✨\n\n"
                                f"-# 🗑️ Bu oda {THREAD_SILME_SURESI // 60} dakika içinde otomatik olarak silinecektir."
                            ),
                            colour=discord.Colour.green(),
                        ),
                        allowed_mentions=discord.AllowedMentions(users=True, roles=False),
                    )
                except Exception:
                    pass
            _thread_silme_planla(kayit)
        await _kaydet()

    tebrik = discord.Embed(
        title="🎉 Kaydınız Tamamlandı!",
        description=(
            f"Merhaba {uye.mention},\n\n**{guild.name}** sunucumuza kaydınız tamamlandı!\n\n"
            f"• **Sunucu İçi İsminiz:** `{nick}`\n"
            f"• **Karakteriniz:** {kr['ad']} ({kr['yas']})\n"
            f"• **Roblox Hesabınız:** `{kayit['roblox_ad']}`\n\n"
            "Aramıza hoş geldiniz, keyifli oyunlar dileriz! 🎮✨"
        ),
        colour=discord.Colour.green(),
    )
    tebrik.set_footer(text=guild.name, icon_url=_guild_icon(guild))
    tebrik.timestamp = discord.utils.utcnow()
    await _dm(uye, embed=tebrik)

    log_kanal = await _kanal_getir(interaction.client, KAYIT_LOG_KANAL_ID)
    if log_kanal:
        log = discord.Embed(title="🎉 Yeni Üye Kaydı", description=f"{uye.mention} başarıyla kayıt oldu ve aramıza katıldı!", colour=discord.Colour.green())
        log.add_field(name="👤 Roblox Adı", value=f"**{kayit['roblox_ad']}**", inline=True)
        log.add_field(name="🆔 Roblox ID", value=f"`{kayit['roblox_id']}`", inline=True)
        log.add_field(name="🎭 Karakter", value=f"{kr['ad']} ({kr['yas']})", inline=True)
        log.add_field(name="🔗 Profil Linki", value=f"[Roblox Profiline Git]({_profil_link(kayit['roblox_id'])})", inline=False)
        log.add_field(name="🛡️ Onaylayan Yetkili", value=interaction.user.mention, inline=True)
        if kayit.get("roblox_avatar"):
            log.set_thumbnail(url=kayit["roblox_avatar"])
        log.set_footer(text=f"Üye ID: {uye.id}")
        log.timestamp = discord.utils.utcnow()
        try:
            await log_kanal.send(content=uye.mention, embed=log)
        except Exception:
            pass

    await dosya_guncelle(interaction.client, kayit)
    await _kart_kapat(interaction.message, f"✅ **Karakter Onaylandı — Kayıt Tamamlandı** — {interaction.user.mention}\n🏷️ `{nick}`", discord.Colour.green())

    uyarilar = []
    if not rol_ok:
        uyarilar.append("⚠️ Bazı roller verilemedi/alınamadı — botun rolünü `Üye`, `Whitelist`, `Kayıtsız` ve `Grup Onayı Bekliyor` rollerinin ÜSTÜNE taşıyın.")
    if not nick_ok:
        uyarilar.append("⚠️ İsim değiştirilemedi (kullanıcı sunucu sahibi olabilir ya da bot yetkisi yetersiz).")
    await interaction.followup.send(f"✅ {uye.mention} kaydı tamamlandı. İsim: `{nick}`\n" + "\n".join(uyarilar), ephemeral=True)


class KarakterRedModal(discord.ui.Modal, title="❌ Karakter Formunu Reddet"):
    sebep = discord.ui.TextInput(
        label="Reddetme Sebebi",
        style=discord.TextStyle.paragraph,
        placeholder="Örn: Ünlü ismi kullanılamaz / yaş 18'den küçük.",
        max_length=400,
        required=True,
    )

    def __init__(self, hedef_id: int, orijinal_mesaj: discord.Message):
        super().__init__()
        self.hedef_id = hedef_id
        self.orijinal_mesaj = orijinal_mesaj

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        uye = await _uye_getir(guild, self.hedef_id)
        sebep = self.sebep.value

        async with _kilit(self.hedef_id):
            kayit = kayit_al(self.hedef_id)
            if not kayit or kayit.get("asama") != "karakter_inceleniyor":
                return await interaction.followup.send("ℹ️ Bu karakter formu zaten işlenmiş.", ephemeral=True)
            kr = kayit.get("karakter") or {}
            kayit.setdefault("karakter_red_gecmisi", []).append({
                "ad": kr.get("ad"), "yas": kr.get("yas"), "sebep": sebep,
                "yetkili_id": interaction.user.id, "tarih": _simdi(),
            })
            kayit["asama"] = "karakter_bekliyor"

            if uye:
                thread, _ = await thread_hazirla(guild, uye, kayit)
                if thread:
                    try:
                        await thread.send(
                            content=uye.mention,
                            embed=discord.Embed(
                                title="❌ Karakter Formun Reddedildi",
                                description=(
                                    f"{uye.mention}, **{kr.get('ad')}** ({kr.get('yas')}) karakter formun yetkililer tarafından reddedildi.\n\n"
                                    f"**📌 Sebep:**\n```{sebep}```\n"
                                    "Endişelenme, formu **tekrar doldurabilirsin!** Kuralları gözden geçirip aşağıdaki panelden yeniden gönder. 💪"
                                ),
                                colour=discord.Colour.red(),
                            ),
                        )
                        await thread.send(view=KarakterPanelView())
                    except Exception:
                        pass
            await _kaydet()

        if uye:
            await _dm(uye, embed=discord.Embed(
                title="❌ Karakter Formunuz Reddedildi",
                description=(f"**{guild.name}** sunucusundaki karakter formunuz reddedildi.\n\n**Sebep:**\n```{sebep}```\n"
                             "Kayıt odanızdan formu tekrar doldurabilirsiniz."),
                colour=discord.Colour.red(),
            ).set_footer(text=f"İnceleyen Yetkili: {interaction.user.display_name}"))

        await dosya_guncelle(interaction.client, kayit)
        await _kart_kapat(self.orijinal_mesaj, f"❌ **Karakter Reddedildi** — {interaction.user.mention}\n**Sebep:** {sebep}", discord.Colour.red())
        await interaction.followup.send("✅ Karakter formu reddedildi, kullanıcı formu tekrar doldurabilecek.", ephemeral=True)


# =====================================================================
# 4. AŞAMA — CK (ROLSEL KARAKTER YENİLEME) SİSTEMİ
# =====================================================================
async def ck_dosyasi_gonder(client: discord.Client, uye: discord.Member, kayit: dict, ck_data: dict, yetkili: discord.Member | None):
    """
    Onaylanan CK işlemi için UYE_DOSYASI_KANAL_ID kanalına tamamen yeni,
    detaylı bir arşiv belgesi gönderir.
    """
    kanal = await _kanal_getir(client, UYE_DOSYASI_KANAL_ID)
    if kanal is None:
        return

    embed = discord.Embed(
        title="📋 Üye Dosyası • Rolsel Karakter Yenileme (CK) Belgesi",
        description=f"{uye.mention} kullanıcısı için onaylanan CK ve karakter yenileme kaydı aşağıdadır.",
        colour=discord.Colour(0x9B59B6),
    )

    # 1. Kullanıcı
    embed.add_field(
        name="👤 Discord Kullanıcısı",
        value=f"{uye.mention} (`{uye.id}`)\n**Sunucu İsmi:** `{uye.display_name}`",
        inline=False,
    )

    # 2. 1. Anket Bilgisi (Geçmişe yönelik kayıt bilgisi)
    gercek_ad = kayit.get("gercek_ad") or "Eski sistem kaydı — bilgi yok"
    cinsiyet = kayit.get("cinsiyet") or "Belirtilmedi"
    basvuru_ts = _ts(kayit.get("basvuru_tarihi"))
    embed.add_field(
        name="📝 İlk Kayıt Arşivi (1. Anket)",
        value=f"• **Gerçek Adı:** {gercek_ad}\n• **Cinsiyet:** {cinsiyet}\n• **İlk Kayıt / Başvuru Tarihi:** {basvuru_ts}",
        inline=False,
    )

    # 3. Karakter Değişimi
    eski_kr = ck_data.get("eski_karakter", "—")
    yeni_kr = ck_data.get("yeni_karakter", "—")
    yeni_yas = ck_data.get("yeni_yas", "—")
    embed.add_field(
        name="🎭 Karakter Bilgileri",
        value=f"• **Eski Karakter:** `{eski_kr}`\n• **Yeni Karakter:** `{yeni_kr}`\n• **Yeni Karakter Yaşı:** `{yeni_yas}`",
        inline=True,
    )

    # 4. Roblox Hesap Bilgisi
    eski_r_ad = ck_data.get("eski_roblox_ad", "—")
    eski_r_id = ck_data.get("eski_roblox_id", "")
    yeni_r_ad = ck_data.get("yeni_roblox_ad", "—")
    yeni_r_id = ck_data.get("yeni_roblox_id", "")
    if ck_data.get("hesap_degisti"):
        r_metin = (
            f"⚠️ **Roblox Hesabı Değişti**\n"
            f"• **Eski:** [{eski_r_ad}]({_profil_link(eski_r_id)}) (`{eski_r_id}`)\n"
            f"• **Yeni:** [{yeni_r_ad}]({_profil_link(yeni_r_id)}) (`{yeni_r_id}`)\n"
            f"• **Grup Durumu:** ✅ Yeni hesap gruba bağlandı"
        )
    else:
        r_metin = (
            f"✅ **Aynı Roblox Hesabı**\n"
            f"• **Hesap:** [{yeni_r_ad}]({_profil_link(yeni_r_id)}) (`{yeni_r_id}`)"
        )
    embed.add_field(name="🎮 Roblox Durumu", value=r_metin, inline=True)

    # 5. CK Sebebi
    sebep = ck_data.get("sebep", "Belirtilmedi")
    embed.add_field(name="💀 CK (Rolsel Karakter Yenileme) Gerekçesi", value=f"```{sebep[:950]}```", inline=False)

    # 6. Yetkili & Onay Detayları
    yetkili_str = yetkili.mention if yetkili else (f"<@{ck_data.get('onaylayan_id')}>" if ck_data.get("onaylayan_id") else "Bilinmiyor")
    onay_ts = _ts(ck_data.get("onay_tarihi") or _simdi())
    embed.add_field(
        name="🛡️ İşlem & Onay Bilgileri",
        value=f"• **Onaylayan Yetkili:** {yetkili_str}\n• **Onay Tarihi:** {onay_ts}\n• **Güncel Sunucu İsmi:** `{uye.nick or uye.display_name}`",
        inline=False,
    )

    avatar = ck_data.get("yeni_roblox_avatar") or kayit.get("roblox_avatar") or uye.display_avatar.url
    if avatar:
        embed.set_thumbnail(url=avatar)
    embed.set_footer(text=f"Belge No: CK-{uye.id}-{_simdi()} • Discord ID: {uye.id}")
    embed.timestamp = discord.utils.utcnow()

    try:
        await kanal.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except Exception as e:
        print(f"[CK] Detaylı CK dosyası gönderilemedi: {e}", flush=True)


class CKModal(discord.ui.Modal, title="💀 PRP | CK Başvuru Formu"):
    def __init__(self, mevcut_roblox_ad: str = ""):
        super().__init__(timeout=600)
        self.yeni_karakter_ad = discord.ui.TextInput(
            label="Yeni Karakterinizin Adı ve Soyadı",
            placeholder="Yabancı isim, ünlü ismi olmamalı. Örn: John Carter",
            min_length=3,
            max_length=28,
            required=True,
        )
        self.yeni_karakter_yas = discord.ui.TextInput(
            label="Yeni Karakterinizin Yaşı",
            placeholder="18 veya üzeri olmalı. Örn: 24",
            min_length=1,
            max_length=3,
            required=True,
        )
        self.roblox_hesap = discord.ui.TextInput(
            label="Roblox Profil Linki veya Kullanıcı Adı",
            placeholder="Aynı kalacaksa mevcut adınız, değişecekse yeni hesap",
            default=mevcut_roblox_ad,
            max_length=200,
            required=True,
        )
        self.ck_sebep = discord.ui.TextInput(
            label="CK Atma (Karakter Değişimi) Sebebi",
            style=discord.TextStyle.paragraph,
            placeholder="Rolsel ölüm detayları, yeni karakter hikayesi ve sebebi açıklayınız...",
            min_length=10,
            max_length=600,
            required=True,
        )
        self.add_item(self.yeni_karakter_ad)
        self.add_item(self.yeni_karakter_yas)
        self.add_item(self.roblox_hesap)
        self.add_item(self.ck_sebep)

    async def on_submit(self, interaction: discord.Interaction):
        ad = re.sub(r"\s+", " ", self.yeni_karakter_ad.value).strip()
        yas = self.yeni_karakter_yas.value.strip()
        if not yas.isdigit() or not (18 <= int(yas) <= 120):
            return await interaction.response.send_message("❌ Karakter yaşı en az **18** ve geçerli bir sayı olmalıdır.", ephemeral=True)

        kullanildi, _ = karakter_adi_kullanildi_mi(interaction.guild, ad, interaction.user.id)
        if kullanildi:
            return await interaction.response.send_message(
                f"❌ **{ad}** karakter adı sunucumuzda daha önce kullanılmış veya şu an aktif bir üyeye ait.\n"
                "Sunucumuzda her karakter adı benzersiz olmalıdır. Lütfen başka bir karakter adı seçiniz.",
                ephemeral=True,
            )

        uye = interaction.user
        uid = uye.id
        kayit = kayit_al(uid)

        eski_kr = ""
        if kayit and kayit.get("karakter", {}).get("ad"):
            eski_kr = kayit["karakter"]["ad"]
        elif "|" in uye.display_name:
            eski_kr = uye.display_name.split("|")[0].strip()
        else:
            eski_kr = uye.display_name

        if ad.lower() == eski_kr.lower():
            return await interaction.response.send_message(
                f"❌ Yeni karakter adı eski karakterinizle (**{eski_kr}**) aynı olamaz! Karakter yenilemek için farklı bir isim seçmelisiniz.",
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        ck_onay_kanal = guild.get_channel(CK_ONAY_KANAL_ID)
        if ck_onay_kanal is None:
            return await interaction.followup.send("❌ CK onay kanalı bulunamadı, lütfen yöneticilere haber veriniz.", ephemeral=True)

        girdi = self.roblox_hesap.value.strip()
        profil = await roblox_profil_getir(girdi)
        if not profil:
            return await interaction.followup.send(f"❌ Belirttiğiniz Roblox hesabı (`{girdi[:100]}`) bulunamadı.", ephemeral=True)
        if profil["is_banned"]:
            return await interaction.followup.send(f"❌ Belirttiğiniz Roblox hesabı (**{profil['name']}**) yasaklıdır (banned).", ephemeral=True)

        rid = profil["id"]
        mevcut_rid = str(kayit.get("roblox_id") or "") if kayit else ""
        hesap_degisti = bool(mevcut_rid and rid != mevcut_rid)

        if hesap_degisti:
            sahip = _veri()["roblox_index"].get(rid)
            if sahip and sahip != str(uid):
                sahip_kayit = kayit_al(int(sahip))
                if sahip_kayit and sahip_kayit.get("asama") not in ("reddedildi", "ayrildi"):
                    return await interaction.followup.send(
                        f"❌ Belirttiğiniz yeni Roblox hesabı (**{profil['name']}**) sunucumuzda zaten başka bir kullanıcıya (<@{sahip}>) bağlıdır.",
                        ephemeral=True,
                    )

        async with _kilit(uid):
            ck_data = {
                "discord_id": uid,
                "eski_karakter": eski_kr,
                "yeni_karakter": ad,
                "yeni_yas": int(yas),
                "eski_roblox_id": mevcut_rid or rid,
                "eski_roblox_ad": kayit.get("roblox_ad") if kayit else (uye.display_name.split("|")[-1].strip() if "|" in uye.display_name else profil["name"]),
                "yeni_roblox_id": rid,
                "yeni_roblox_ad": profil["name"],
                "yeni_roblox_avatar": profil["avatar"],
                "hesap_degisti": hesap_degisti,
                "sebep": self.ck_sebep.value.strip(),
                "tarih": _simdi(),
                "durum": "onay_bekliyor",
                "onaylayan_id": None,
                "onay_tarihi": None,
                "kart_mesaj_id": None,
            }
            _veri()["ck_basvurulari"][str(uid)] = ck_data

            embed = discord.Embed(title="💀 Yeni CK (Karakter Değişimi) Başvurusu", colour=discord.Colour(0x9B59B6))
            embed.add_field(name="Discord Kullanıcı", value=f"{uye.mention} (`{uid}`)", inline=False)
            embed.add_field(name="Mevcut Sunucu İsmi", value=f"`{uye.display_name}`", inline=True)
            embed.add_field(name="Eski Karakter", value=f"**{eski_kr}**", inline=True)
            embed.add_field(name="🎭 Yeni Karakter & Yaş", value=f"**{ad}** ({yas})", inline=False)
            if hesap_degisti:
                embed.add_field(
                    name="🎮 Roblox Hesabı",
                    value=(f"⚠️ **HESAP DEĞİŞECEK!**\n"
                           f"• Eski: [{ck_data['eski_roblox_ad']}]({_profil_link(ck_data['eski_roblox_id'])}) (`{ck_data['eski_roblox_id']}`)\n"
                           f"• Yeni: [{profil['name']}]({_profil_link(rid)}) (`{rid}`)"),
                    inline=False,
                )
            else:
                embed.add_field(
                    name="🎮 Roblox Hesabı",
                    value=f"✅ **Aynı Hesap:** [{profil['name']}]({_profil_link(rid)}) (`{rid}`)",
                    inline=False,
                )
            gercek = kayit.get("gercek_ad", "Eski sistem kaydı — bilgi yok") if kayit else "Eski sistem kaydı — bilgi yok"
            embed.add_field(name="📝 1. Anket Bilgisi", value=f"**Gerçek Ad:** {gercek}", inline=True)
            onizleme = _nick_olustur(ad, profil["name"])
            embed.add_field(name="🏷️ Yeni İsim Önizleme", value=f"`{onizleme}`", inline=True)
            embed.add_field(name="💀 CK / Değişim Sebebi", value=f"```{self.ck_sebep.value.strip()[:900]}```", inline=False)
            if profil.get("avatar"):
                embed.set_thumbnail(url=profil["avatar"])
            embed.set_footer(text=f"Başvuran ID: {uid}")
            embed.timestamp = discord.utils.utcnow()

            kart = await ck_onay_kanal.send(
                content=f"<@&{WHITELIST_YETKILISI_ROL_ID}>",
                embed=embed,
                view=ck_karar_view(uid),
            )
            ck_data["kart_mesaj_id"] = kart.id
            await _kaydet()

        await interaction.followup.send("✅ CK başvurunuz yetkililere iletildi! Başvurunuz sonuçlandığında DM kutunuza bilgilendirme gelecektir.", ephemeral=True)


async def ck_basvur_tiklandi(interaction: discord.Interaction):
    uye = interaction.user
    uid = uye.id
    if UYE_ROL_ID not in [r.id for r in uye.roles]:
        return await interaction.response.send_message("❌ CK başvurusu yapabilmek için sunucumuzda kayıtlı bir **Üye** olmalısınız.", ephemeral=True)

    ck_data = _veri()["ck_basvurulari"].get(str(uid))
    if ck_data:
        durum = ck_data.get("durum")
        if durum == "grup_bekliyor":
            return await interaction.response.send_message(
                "⏳ CK başvurunuz ön onay aldı! Yeni hesabınızla gruba katılma isteği attıktan sonra paneldeki **'Yeni Hesabımı Onayla'** butonuna basınız.",
                ephemeral=True,
            )
        elif durum == "onay_bekliyor":
            return await interaction.response.send_message(
                "⏳ Yetkililer tarafından incelenmekte olan aktif bir CK başvurunuz bulunuyor.",
                ephemeral=True,
            )
        else:
            # Durum 'reddedildi' veya 'tamamlandi' kalmışsa aktif başvurulardan temizle
            _veri()["ck_basvurulari"].pop(str(uid), None)
            await _kaydet()

    # 3 GÜN BEKLEME KURALI:
    # Cooldown YALNIZCA ONAYLANAN (TAMAMLANAN) CK işlemleri için geçerlidir!
    # Başvuru reddedildiyse kullanıcı beklemeden anında tekrar anket doldurabilir.
    son_onayli_ck = None
    gecmis = _veri()["ck_gecmisi"].get(str(uid), [])
    for item in reversed(gecmis):
        if item.get("durum") in ("tamamlandi", "onaylandi") and item.get("durum") != "reddedildi":
            t = item.get("onay_tarihi") or item.get("tamamlanma_tarihi")
            if not t and isinstance(item.get("grup_dogrulama"), dict):
                t = item["grup_dogrulama"].get("tarih")
            if t:
                son_onayli_ck = t
                break

    # Geçmiş listesinde onaylı başvuru yoksa kayıt profilindeki son_ck_tarihi alanına bak
    if not son_onayli_ck:
        kayit = kayit_al(uid)
        if kayit and kayit.get("son_ck_tarihi"):
            son_onayli_ck = kayit["son_ck_tarihi"]

    if son_onayli_ck:
        fark = _simdi() - son_onayli_ck
        if fark < CK_COOLDOWN_SANIYE:
            kalan_saniye = CK_COOLDOWN_SANIYE - fark
            kalan_saat = kalan_saniye // 3600
            kalan_dakika = (kalan_saniye % 3600) // 60
            return await interaction.response.send_message(
                f"⏳ Son onaylanan CK işleminizin üzerinden 3 gün geçmeden yeni başvuru yapamazsınız.\n"
                f"Kalan bekleme süresi: **{kalan_saat} saat {kalan_dakika} dakika**.\n"
                "-# (Not: Bu bekleme süresi sadece onaylanmış karakter değişimleri için geçerlidir. Reddedilen başvurularda bekleme süresi uygulanmaz.)",
                ephemeral=True,
            )

    kayit = kayit_al(uid)
    mevcut_roblox = kayit.get("roblox_ad") if kayit else ""
    if not mevcut_roblox and "|" in uye.display_name:
        mevcut_roblox = uye.display_name.split("|")[-1].strip()

    await interaction.response.send_modal(CKModal(mevcut_roblox_ad=mevcut_roblox))


async def ck_yeni_hesap_onayla_tiklandi(interaction: discord.Interaction):
    uye = interaction.user
    uid = uye.id
    ck_data = _veri()["ck_basvurulari"].get(str(uid))
    if not ck_data or ck_data.get("durum") != "grup_bekliyor":
        return await interaction.response.send_message("ℹ️ Grup doğrulaması bekleyen aktif bir CK başvurunuz bulunmuyor. Yeni bir karakter oluşturmak istiyorsanız önce **CK Başvur** butonuna basınız.", ephemeral=True)

    kalan = HESAP_ONAY_COOLDOWN - (time.monotonic() - _ONAY_COOLDOWN.get(uid, 0))
    if kalan > 0:
        return await interaction.response.send_message(f"⏳ Lütfen **{int(kalan) + 1} saniye** sonra tekrar deneyiniz.", ephemeral=True)

    _ONAY_COOLDOWN[uid] = time.monotonic()
    await interaction.response.defer(ephemeral=True, thinking=True)

    rid = str(ck_data["yeni_roblox_id"])
    profil = await roblox_profil_getir(rid)
    if not profil:
        _ONAY_COOLDOWN.pop(uid, None)
        return await interaction.followup.send("⚠️ Roblox profiline şu anda ulaşılamıyor. Lütfen biraz sonra tekrar deneyin.", ephemeral=True)
    if profil["is_banned"]:
        return await interaction.followup.send("⛔ Yeni Roblox hesabınız yasaklı görünüyor. Lütfen yetkililerle iletişime geçin.", ephemeral=True)

    rutbe = await roblox_grup_rutbesi(rid)
    if rutbe:
        yontem = "zaten_uye"
    else:
        durum, path = await roblox_katilma_istegi_bul(rid)
        if durum == "yok":
            v = discord.ui.View()
            v.add_item(discord.ui.Button(label="Roblox Grubumuz", emoji="🔗", style=discord.ButtonStyle.link, url=ROBLOX_GRUP_LINK))
            return await interaction.followup.send(
                embed=_grup_bulunamadi_embed({"roblox_ad": ck_data["yeni_roblox_ad"], "roblox_id": rid, "roblox_avatar": ck_data.get("yeni_roblox_avatar")}),
                view=v,
                ephemeral=True,
            )
        if durum != "var":
            _ONAY_COOLDOWN.pop(uid, None)
            return await interaction.followup.send("⚠️ Şu anda grup isteklerini kontrol edemiyoruz. Lütfen biraz sonra tekrar deneyiniz.", ephemeral=True)
        kabul = await roblox_istegi_kabul_et(path)
        yontem = "istek_kabul" if kabul else "istek_bulundu"
        if kabul:
            rutbe = await roblox_grup_rutbesi(rid) or "Member"

    async with _kilit(uid):
        # Eski Roblox bağlantısını bırak, yenisini bağla
        eski_rid = str(ck_data.get("eski_roblox_id") or "")
        if eski_rid and _veri()["roblox_index"].get(eski_rid) == str(uid):
            _veri()["roblox_index"].pop(eski_rid, None)
        _veri()["roblox_index"][rid] = str(uid)

        karakter_adi_kaydet(ck_data["yeni_karakter"], uid)

        yeni_nick = _nick_olustur(ck_data["yeni_karakter"], profil["name"])
        try:
            await uye.edit(nick=yeni_nick, reason="CK tamamlandı (Yeni Roblox hesabı bağlandı)")
        except Exception:
            pass

        kayit = kayit_al(uid)
        if not kayit:
            kayit = {
                "discord_id": uid,
                "discord_ad": str(uye),
                "discord_olusturma": int(uye.created_at.timestamp()),
                "sunucu_katilim": int(uye.joined_at.timestamp()) if getattr(uye, "joined_at", None) else None,
                "gercek_ad": "Eski sistem kaydı — bilgi yok",
                "cinsiyet": "Belirtilmedi",
                "asama": "tamamlandi",
                "dosya_mesaj_id": None,
            }
            _veri()["kullanicilar"][str(uid)] = kayit

        kayit.update({
            "roblox_id": rid,
            "roblox_ad": profil["name"],
            "roblox_gorunen_ad": profil["display_name"],
            "roblox_avatar": profil["avatar"],
            "karakter": {"ad": ck_data["yeni_karakter"], "yas": ck_data["yeni_yas"], "tarih": _simdi()},
            "son_ck_tarihi": _simdi(),
            "asama": "tamamlandi",
        })

        ck_data["durum"] = "tamamlandi"
        ck_data["grup_dogrulama"] = {"yontem": yontem, "rutbe": rutbe, "tarih": _simdi()}
        _veri()["ck_gecmisi"].setdefault(str(uid), []).append(ck_data)
        _veri()["ck_basvurulari"].pop(str(uid), None)
        await _rolleri_duzenle(uye, [ONAYLANMIS_BIREY_ROL_ID], [], "CK yeni Roblox hesabı onaylandı")
        await _kaydet()

    yetkili = await _uye_getir(interaction.guild, ck_data.get("onaylayan_id"))
    await ck_dosyasi_gonder(interaction.client, uye, kayit, ck_data, yetkili)

    embed = discord.Embed(
        title="🎉 Yeni Hesabınız Onaylandı & CK Tamamlandı!",
        description=(
            f"Tebrikler {uye.mention}! Yeni Roblox hesabınız (**{profil['name']}**) grubumuzda doğrulandı "
            + ("ve katılma isteğiniz **otomatik kabul edildi!** 🎉\n\n" if yontem == "istek_kabul" else "! 🎉\n\n")
            + f"• **Yeni Karakteriniz:** {ck_data['yeni_karakter']} ({ck_data['yeni_yas']})\n"
            + f"• **Sunucu İsminiz:** `{yeni_nick}`\n\n"
            + "Yeni karakterinizle keyifli ve kaliteli roller dileriz! 🚓✨"
        ),
        colour=discord.Colour.green(),
    )
    if profil.get("avatar"):
        embed.set_thumbnail(url=profil["avatar"])
    await interaction.followup.send(embed=embed, ephemeral=True)


class CKKararButonu(discord.ui.DynamicItem[discord.ui.Button], template=r"ck_(?P<islem>onayla|reddet)_(?P<uid>\d+)"):
    def __init__(self, islem: str, uid: int):
        onay = islem == "onayla"
        super().__init__(
            discord.ui.Button(
                label="CK'YI ONAYLA" if onay else "REDDET",
                emoji="✅" if onay else "✖️",
                style=discord.ButtonStyle.green if onay else discord.ButtonStyle.red,
                custom_id=f"ck_{islem}_{uid}",
            )
        )
        self.islem = islem
        self.uid = uid

    @classmethod
    async def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str], /):
        return cls(match["islem"], int(match["uid"]))

    async def callback(self, interaction: discord.Interaction):
        if not yetkili_mi(interaction.user):
            return await interaction.response.send_message("❌ Bu işlemi yapma yetkiniz yok.", ephemeral=True)
        ck_data = _veri()["ck_basvurulari"].get(str(self.uid))
        if not ck_data or ck_data.get("durum") != "onay_bekliyor":
            return await interaction.response.send_message("ℹ️ Bu CK başvurusu zaten işlenmiş.", ephemeral=True)
        if self.islem == "reddet":
            return await interaction.response.send_modal(CKRedModal(self.uid, interaction.message))
        await ck_onayla(interaction, self.uid)


def ck_karar_view(uid: int) -> discord.ui.View:
    v = discord.ui.View(timeout=None)
    v.add_item(CKKararButonu("onayla", uid))
    v.add_item(CKKararButonu("reddet", uid))
    return v


async def ck_onayla(interaction: discord.Interaction, uid: int):
    await interaction.response.defer(ephemeral=True, thinking=True)
    guild = interaction.guild
    uye = await _uye_getir(guild, uid)
    if uye is None:
        await _kart_kapat(interaction.message, "⚫ Kullanıcı sunucudan ayrılmış.", discord.Colour.dark_grey())
        return await interaction.followup.send("❌ Kullanıcı sunucuda bulunamadı.", ephemeral=True)

    async with _kilit(uid):
        ck_data = _veri()["ck_basvurulari"].get(str(uid))
        if not ck_data or ck_data.get("durum") != "onay_bekliyor":
            return await interaction.followup.send("ℹ️ Bu CK başvurusu zaten işlenmiş.", ephemeral=True)

        kayit = kayit_al(uid)
        if not kayit:
            kayit = {
                "discord_id": uid,
                "discord_ad": str(uye),
                "discord_olusturma": int(uye.created_at.timestamp()),
                "sunucu_katilim": int(uye.joined_at.timestamp()) if getattr(uye, "joined_at", None) else None,
                "gercek_ad": "Eski sistem kaydı — bilgi yok",
                "cinsiyet": "Belirtilmedi",
                "roblox_id": ck_data["yeni_roblox_id"],
                "roblox_ad": ck_data["yeni_roblox_ad"],
                "roblox_avatar": ck_data.get("yeni_roblox_avatar"),
                "asama": "tamamlandi",
                "dosya_mesaj_id": None,
            }
            _veri()["kullanicilar"][str(uid)] = kayit

        if not ck_data.get("hesap_degisti"):
            # A) Aynı Roblox hesabı: Karakter adı kaydedilir, isim hemen güncellenir
            karakter_adi_kaydet(ck_data["yeni_karakter"], uid)
            yeni_nick = _nick_olustur(ck_data["yeni_karakter"], ck_data["yeni_roblox_ad"])
            try:
                await uye.edit(nick=yeni_nick, reason=f"CK onaylandı ({interaction.user})")
            except Exception:
                pass

            kayit["karakter"] = {"ad": ck_data["yeni_karakter"], "yas": ck_data["yeni_yas"], "tarih": _simdi()}
            kayit["son_ck_tarihi"] = _simdi()
            ck_data["durum"] = "tamamlandi"
            ck_data["onaylayan_id"] = interaction.user.id
            ck_data["onay_tarihi"] = _simdi()
            _veri()["ck_gecmisi"].setdefault(str(uid), []).append(ck_data)
            _veri()["ck_basvurulari"].pop(str(uid), None)
            await _rolleri_duzenle(uye, [ONAYLANMIS_BIREY_ROL_ID], [], "CK onaylandı")
            await _kaydet()

            if uye:
                await _dm(
                    uye,
                    embed=discord.Embed(
                        title="🎉 CK Başvurunuz Onaylandı!",
                        description=(
                            f"Merhaba {uye.mention},\n\n"
                            f"**{guild.name}** sunucusundaki CK başvurunuz **onaylanmıştır!** 🥳\n\n"
                            f"• **Yeni Karakteriniz:** {ck_data['yeni_karakter']} ({ck_data['yeni_yas']})\n"
                            f"• **Sunucu İçi İsminiz:** `{yeni_nick}`\n"
                            f"• **Roblox Hesabınız:** `{ck_data['yeni_roblox_ad']}`\n\n"
                            "Yeni karakterinizle keyifli ve kaliteli roller dileriz! 🚓✨"
                        ),
                        colour=discord.Colour.green(),
                    ).set_footer(text=f"Onaylayan Yetkili: {interaction.user.display_name}")
                )

            await ck_dosyasi_gonder(interaction.client, uye, kayit, ck_data, interaction.user)
            await _kart_kapat(interaction.message, f"✅ **CK Onaylandı** — {interaction.user.mention}\n🏷️ `{yeni_nick}`", discord.Colour.green())
            await interaction.followup.send(f"✅ {uye.mention} CK başvurusu onaylandı. Sunucu takma adı güncellendi: `{yeni_nick}`", ephemeral=True)
        else:
            # B) Yeni Roblox hesabı: Ön onay verilir, grup katılımı beklenir
            ck_data["durum"] = "grup_bekliyor"
            ck_data["onaylayan_id"] = interaction.user.id
            ck_data["onay_tarihi"] = _simdi()
            await _kaydet()

            if uye:
                await _dm(
                    uye,
                    embed=discord.Embed(
                        title="🟡 CK Başvurunuz Ön Onay Aldı!",
                        description=(
                            f"Merhaba {uye.mention},\n\n"
                            f"**{ck_data['yeni_karakter']}** karakteri için yaptığınız CK başvurusu yetkililer tarafından **kabul edildi!** 🎉\n\n"
                            f"Yeni Roblox hesabınız (**{ck_data['yeni_roblox_ad']}**) için son bir adım kaldı:\n"
                            f"1. [Roblox Grubumuza]({ROBLOX_GRUP_LINK}) yeni hesabınızla katılma isteği gönderin.\n"
                            f"2. <#{CK_PANEL_KANAL_ID}> kanalındaki **'Yeni Hesabımı Onayla'** butonuna basınız.\n\n"
                            "İsteğiniz doğrulandığında yeni sunucu isminiz otomatik tanımlanacaktır."
                        ),
                        colour=discord.Colour.gold(),
                    ).set_footer(text=f"Onaylayan Yetkili: {interaction.user.display_name}")
                )

            await _kart_kapat(
                interaction.message,
                f"🟡 **CK Karakteri Onaylandı (Grup Bekleniyor)** — {interaction.user.mention}\nKullanıcının yeni Roblox hesabıyla gruba katılıp paneldeki **Yeni Hesabımı Onayla** butonuna basması bekleniyor.",
                discord.Colour.gold(),
            )
            await interaction.followup.send(f"✅ {uye.mention} CK başvurusu onaylandı. Kullanıcı gruba katılıp 'Yeni Hesabımı Onayla' butonuna bastığında süreç tamamlanacak.", ephemeral=True)


class CKRedModal(discord.ui.Modal, title="❌ CK Başvurusunu Reddet"):
    sebep = discord.ui.TextInput(
        label="Reddetme Sebebi",
        style=discord.TextStyle.paragraph,
        placeholder="Örn: Karakter adı uygunsuz / CK hikayesi yetersiz...",
        max_length=400,
        required=True,
    )

    def __init__(self, hedef_id: int, orijinal_mesaj: discord.Message):
        super().__init__()
        self.hedef_id = hedef_id
        self.orijinal_mesaj = orijinal_mesaj

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        uye = await _uye_getir(guild, self.hedef_id)
        sebep = self.sebep.value.strip()

        async with _kilit(self.hedef_id):
            ck_data = _veri()["ck_basvurulari"].get(str(self.hedef_id))
            if not ck_data or ck_data.get("durum") != "onay_bekliyor":
                return await interaction.followup.send("ℹ️ Bu CK başvurusu zaten işlenmiş.", ephemeral=True)

            ck_data["durum"] = "reddedildi"
            ck_data["red_sebebi"] = sebep
            ck_data["reddeden_id"] = interaction.user.id
            ck_data["red_tarihi"] = _simdi()
            _veri()["ck_gecmisi"].setdefault(str(self.hedef_id), []).append(ck_data)
            _veri()["ck_basvurulari"].pop(str(self.hedef_id), None)
            await _kaydet()

        if uye:
            await _dm(
                uye,
                embed=discord.Embed(
                    title="❌ CK Başvurunuz Reddedildi",
                    description=(
                        f"Merhaba {uye.mention},\n\n"
                        f"**{guild.name}** sunucusundaki **{ck_data.get('yeni_karakter')}** karakteri için yaptığınız CK başvurusu yetkililer tarafından reddedildi.\n\n"
                        f"**📌 Reddetme Gerekçesi:**\n```{sebep}```\n"
                        "Gerekçeyi inceleyip eksikleri düzelterek tekrar başvurabilirsiniz."
                    ),
                    colour=discord.Colour.red(),
                ).set_footer(text=f"İnceleyen Yetkili: {interaction.user.display_name}")
            )

        await _kart_kapat(self.orijinal_mesaj, f"❌ **CK Reddedildi** — {interaction.user.mention}\n**Sebep:** {sebep}", discord.Colour.red())
        await interaction.followup.send(f"✅ {uye.mention if uye else self.hedef_id} kullanıcısının CK başvurusu reddedildi.", ephemeral=True)


class CKPanelView(discord.ui.LayoutView):
    """PRP | CK Başvurusu Paneli (Components V2 LayoutView)."""

    def __init__(self):
        super().__init__(timeout=None)
        ck_btn = discord.ui.Button(label="CK Başvur", emoji="💀", style=discord.ButtonStyle.primary, custom_id="ck_basvur_buton")
        ck_btn.callback = ck_basvur_tiklandi

        onay_btn = discord.ui.Button(label="Yeni Hesabımı Onayla", emoji="✅", style=discord.ButtonStyle.success, custom_id="ck_yeni_hesap_onayla")
        onay_btn.callback = ck_yeni_hesap_onayla_tiklandi

        grup_btn = discord.ui.Button(label="Roblox Grubumuz", emoji="🔗", style=discord.ButtonStyle.link, url=ROBLOX_GRUP_LINK)

        ayrac = lambda: discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.large)

        c = discord.ui.Container(accent_colour=discord.Colour(0x9B59B6))
        c.add_item(discord.ui.TextDisplay(
            "# 💀 PRP | CK Başvurusu\n"
            "**Piyade RP | Los Angeles** sunucumuzda rol gereği karakterinizin hikayesi sona erdiğinde "
            "(CK - Character Kill) veya yeni bir karaktere geçiş yapmak istediğinizde bu panel üzerinden başvurunuzu gerçekleştirebilirsiniz.\n\n"
            "Aşağıdaki iki farklı geçiş seçeneğini inceleyerek size uygun adımlarla ilerleyiniz:"
        ))
        c.add_item(ayrac())
        c.add_item(discord.ui.TextDisplay(
            "## 🎭 1. Seçenek: Aynı Roblox Hesabı ile İsim Değişimi\n"
            "Eğer katılımcı rolsel olarak öldüyse ve mevcut Roblox hesabını değiştirmeden yalnızca karakter adını değiştirmek istiyorsa:\n"
            "• **Karakter Adı:** Karakteriniz için yeni bir yabancı isim ve soyad belirleyiniz *(Örn: John Carter)*.\n"
            "• **Yaş Kuralı:** Karakteriniz en az **18 yaşında** olmalıdır.\n"
            "• **İsim Tekilliği:** Sunucuda daha önce kullanılmış veya eski karakter adınız seçilemez (Otomatik kontrol edilir).\n"
            "• **Roblox Alanı:** Formdaki Roblox kısmına mevcut Roblox kullanıcı adınızı aynen yazınız.\n"
            "• **Sonuç:** Yetkili onayının ardından takma adınız `{Yeni Karakter} | {Roblox}` olarak güncellenir."
        ))
        c.add_item(ayrac())
        c.add_item(discord.ui.TextDisplay(
            "## 🔄 2. Seçenek: Roblox Hesabı ve Karakter Değişimi\n"
            "Eğer katılımcı rol yapacağı Roblox hesabını da değiştirecekse:\n"
            "• **Kullanıcı Adı Zorunluluğu:** Roblox profilini değiştiren üyeler karakter adını da değiştirmek zorundadır.\n"
            "• **Formu Doldurma:** Aşağıdaki **💀 CK Başvur** butonuna basıp yeni karakter adını ve **yeni Roblox profil linkini** yazınız.\n"
            "• **İsim Tekilliği:** Kullanıcı önceden kullandığı karakter adını bir daha kullanamaz (Otomatik kontrol edilir).\n"
            "• **Yetkili Onayı:** Başvuru incelenip yetkili ekibi tarafından ön onay verilir.\n"
            "• **Gruba Katılma & Doğrulama:** Ön onay sonrası **[Roblox Grubumuza]({ROBLOX_GRUP_LINK})** yeni hesabınızla istek gönderiniz ve ardından bu paneldeki **✅ Yeni Hesabımı Onayla** butonuna basınız!"
        ))
        c.add_item(ayrac())
        c.add_item(discord.ui.TextDisplay(
            "## 📜 Önemli Kurallar & Maddeler\n"
            "• **3 Günlük Cooldown:** Onaylanan bir CK işleminden sonra tekrar başvuru yapabilmek için **3 gün** beklemeniz gerekir.\n"
            "• **Geçmiş Arşivi:** İlk kayıt bilgileriniz (1. Anket gerçek adınız) sunucu dosyalarımızda kalıcı olarak saklanır.\n"
            "• **Troll İsim Yasağı:** Ünlü, kurgusal ya da troll isimlerle yapılan başvurular reddedilir."
        ))
        c.add_item(ayrac())
        c.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem("attachment://ck_panel_banner.jpg")))
        c.add_item(discord.ui.ActionRow(ck_btn, onay_btn, grup_btn))
        self.add_item(c)


# =====================================================================
# 5. AŞAMA — MEVCUT ÜYE ROBLOX EŞLEME SİSTEMİ
# =====================================================================
class MevcutUyeModal(discord.ui.Modal, title="🛡️ Mevcut Üye Roblox Eşleme"):
    def __init__(self):
        super().__init__(timeout=600)
        self.roblox_girdi = discord.ui.TextInput(
            label="Roblox Adınız veya Profil Linkiniz",
            placeholder="Örn: Builderman, 156 veya https://www.roblox.com/users/156/profile",
            max_length=200,
            required=True,
        )
        self.add_item(self.roblox_girdi)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        uye = interaction.user
        uid = uye.id

        girdi = self.roblox_girdi.value.strip()
        profil = await roblox_profil_getir(girdi)
        if not profil:
            return await interaction.followup.send(f"❌ Belirttiğiniz Roblox hesabı (`{girdi[:100]}`) bulunamadı.", ephemeral=True)
        if profil["is_banned"]:
            return await interaction.followup.send(f"❌ Belirttiğiniz Roblox hesabı (**{profil['name']}**) yasaklıdır (banned).", ephemeral=True)

        rid = profil["id"]
        sahip = _veri()["roblox_index"].get(rid)
        if sahip and sahip != str(uid):
            sahip_kayit = kayit_al(int(sahip))
            if sahip_kayit and sahip_kayit.get("asama") not in ("reddedildi", "ayrildi"):
                return await interaction.followup.send(
                    f"❌ Belirttiğiniz Roblox hesabı (**{profil['name']}**) sunucumuzda başka bir üyeye (<@{sahip}>) bağlıdır.",
                    ephemeral=True,
                )

        rutbe = await roblox_grup_rutbesi(rid)
        if rutbe:
            yontem = "zaten_uye"
        else:
            durum, path = await roblox_katilma_istegi_bul(rid)
            if durum == "yok":
                v = discord.ui.View()
                v.add_item(discord.ui.Button(label="Roblox Grubumuz", emoji="🔗", style=discord.ButtonStyle.link, url=ROBLOX_GRUP_LINK))
                return await interaction.followup.send(
                    embed=_grup_bulunamadi_embed({"roblox_ad": profil["name"], "roblox_id": rid, "roblox_avatar": profil.get("avatar")}),
                    view=v,
                    ephemeral=True,
                )
            if durum != "var":
                return await interaction.followup.send("⚠️ Şu anda grup isteklerini kontrol edemiyoruz. Yetkililer bilgilendirildi, lütfen biraz sonra tekrar deneyiniz.", ephemeral=True)
            kabul = await roblox_istegi_kabul_et(path)
            yontem = "istek_kabul" if kabul else "istek_bulundu"
            if kabul:
                rutbe = await roblox_grup_rutbesi(rid) or "Member"

        async with _kilit(uid):
            kayit = kayit_al(uid)
            display = uye.display_name
            kr_ad = display.split("|")[0].strip() if "|" in display else display

            if not kayit:
                kayit = {
                    "discord_id": uid,
                    "discord_ad": str(uye),
                    "discord_olusturma": int(uye.created_at.timestamp()),
                    "sunucu_katilim": int(uye.joined_at.timestamp()) if getattr(uye, "joined_at", None) else None,
                    "gercek_ad": "Eski sistem kaydı — bilgi yok",
                    "cinsiyet": "Belirtilmedi",
                    "roblox_id": rid,
                    "roblox_ad": profil["name"],
                    "roblox_gorunen_ad": profil["display_name"],
                    "roblox_olusturma": profil["created"],
                    "roblox_banli": profil["is_banned"],
                    "roblox_avatar": profil["avatar"],
                    "asama": "tamamlandi",
                    "basvuru_tarihi": _simdi(),
                    "onceki_red_sayisi": 0,
                    "thread_id": None,
                    "dosya_mesaj_id": None,
                    "karakter": {"ad": kr_ad, "yas": 20, "tarih": _simdi()},
                    "grup_dogrulama": {"yontem": yontem, "tarih": _simdi(), "rutbe": rutbe},
                    "final": {"yetkili_id": interaction.client.user.id, "tarih": _simdi(), "nick": uye.display_name, "roller": "Mevcut Üye Eşleme"},
                    "mevcut_uye_esleme": True,
                }
                _veri()["kullanicilar"][str(uid)] = kayit
            else:
                kayit.update({
                    "roblox_id": rid,
                    "roblox_ad": profil["name"],
                    "roblox_gorunen_ad": profil["display_name"],
                    "roblox_avatar": profil["avatar"],
                    "roblox_banli": profil["is_banned"],
                    "asama": "tamamlandi",
                    "grup_dogrulama": {"yontem": yontem, "tarih": _simdi(), "rutbe": rutbe},
                })
            _veri()["roblox_index"][rid] = str(uid)
            karakter_adi_kaydet(kr_ad, uid)
            await _kaydet()

        await _rolleri_duzenle(uye, [ONAYLANMIS_BIREY_ROL_ID], [], "Mevcut üye Roblox hesabı onaylandı")
        await dosya_guncelle(interaction.client, kayit)

        await interaction.followup.send(
            f"✅ Tebrikler {uye.mention}! **{profil['name']}** Roblox hesabınız grubumuza başarıyla eşlendi "
            + ("ve katılma isteğiniz **otomatik kabul edildi!** 🎉" if yontem == "istek_kabul" else "! 🎉")
            + "\nRollerinize, karakterinize veya takma adınıza dokunulmadı. İyi roller dileriz! 🚓✨",
            ephemeral=True,
        )


async def mevcut_uye_esle_tiklandi(interaction: discord.Interaction):
    uye = interaction.user
    if UYE_ROL_ID not in [r.id for r in uye.roles]:
        return await interaction.response.send_message(
            "❌ Bu panel yalnızca sunucumuzda halihazırda **Üye** rolü olan eski katılımcılar içindir. "
            f"Henüz kayıt olmadıysanız lütfen <#{KAYIT_KANAL_ID}> kanalından başvurunuz.",
            ephemeral=True,
        )
    await interaction.response.send_modal(MevcutUyeModal())


class MevcutUyePanelView(discord.ui.LayoutView):
    """PRP | Mevcut Üye Roblox Eşleme Paneli (Components V2 LayoutView)."""

    def __init__(self):
        super().__init__(timeout=None)
        esle_btn = discord.ui.Button(label="Hesabımı Gruba Eşle", emoji="🛡️", style=discord.ButtonStyle.success, custom_id="mevcut_uye_esle_buton")
        esle_btn.callback = mevcut_uye_esle_tiklandi

        grup_btn = discord.ui.Button(label="Roblox Grubumuz", emoji="🔗", style=discord.ButtonStyle.link, url=ROBLOX_GRUP_LINK)

        ayrac = lambda: discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.large)

        c = discord.ui.Container(accent_colour=TEMA_RENK)
        c.add_item(discord.ui.TextDisplay(
            "# 🛡️ PRP | Mevcut Üye Roblox Eşleme\n"
            "Bu panel, sunucumuzda halihazırda **Üye** rolü bulunan eski katılımcılarımızın Roblox hesaplarını "
            "grubumuzla eşleştirmesi ve katılma isteklerinin otomatik kabul edilmesi için hazırlanmıştır."
        ))
        c.add_item(ayrac())
        c.add_item(discord.ui.TextDisplay(
            "## 📋 Nasıl Çalışır?\n"
            f"**1.** Önce **[Piyade RP | Los Angeles]({ROBLOX_GRUP_LINK})** Roblox grubumuza katılma isteği gönderiniz.\n"
            "**2.** Aşağıdaki **🛡️ Hesabımı Gruba Eşle** butonuna basınız.\n"
            "**3.** Açılan forma Roblox kullanıcı adınızı veya profil linkinizi yazınız.\n"
            "**4.** Bot isteğinizi otomatik olarak kabul eder ve üye dosyanızı sisteme işler.\n\n"
            "-# ⚠️ Bu işlem mevcut rollerinizi, karakterinizi veya sunucu içi takma adınızı DEĞİŞTİRMEZ."
        ))
        c.add_item(ayrac())
        c.add_item(discord.ui.ActionRow(esle_btn, grup_btn))
        self.add_item(c)


# =====================================================================
# COG
# =====================================================================
class Registration(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        _veri()

    async def cog_load(self):
        self.thread_temizleyici.start()

    async def cog_unload(self):
        self.thread_temizleyici.cancel()

    @tasks.loop(seconds=30)
    async def thread_temizleyici(self):
        silinecek = _veri()["silinecek_threadler"]
        simdi = _simdi()
        degisti = False
        for tid, zaman in list(silinecek.items()):
            if zaman > simdi:
                continue
            kanal = self.bot.get_channel(int(tid))
            if kanal is None:
                try:
                    kanal = await self.bot.fetch_channel(int(tid))
                except discord.NotFound:
                    kanal = None
                except Exception:
                    continue
            if kanal is not None:
                try:
                    await kanal.delete(reason="Kayıt süreci sona erdi")
                except discord.NotFound:
                    pass
                except Exception as e:
                    print(f"[KAYIT] Thread silinemedi ({tid}): {e}", flush=True)
                    continue
            silinecek.pop(tid, None)
            degisti = True
        if degisti:
            await _kaydet()

    @thread_temizleyici.before_loop
    async def _temizleyici_bekle(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.guild.id != GUILD_ID:
            return
        async with _kilit(member.id):
            kayit = kayit_al(member.id)
            if not kayit or kayit.get("asama") not in AKTIF_ASAMALAR:
                return
            onceki_asama = kayit["asama"]
            kayit["asama"] = "ayrildi"
            kayit["ayrilma_tarihi"] = _simdi()
            _roblox_baglantisini_birak(kayit)
            _thread_silme_planla(kayit, gecikme=0)
            await _kaydet()
        onay_kanal = member.guild.get_channel(ONAY_KANAL_ID)
        kart_id = kayit.get("basvuru_kart_id") if onceki_asama == "basvuru_bekliyor" else kayit.get("karakter_kart_id") if onceki_asama == "karakter_inceleniyor" else None
        if onay_kanal and kart_id:
            try:
                mesaj = await onay_kanal.fetch_message(int(kart_id))
                await _kart_kapat(mesaj, "⚫ Kullanıcı sunucudan ayrıldı — başvuru iptal edildi.", discord.Colour.dark_grey())
            except Exception:
                pass
        await dosya_guncelle(self.bot, kayit)

    @app_commands.command(name="kayit-panel", description="Kayıt panelini bu kanala kurar.")
    async def kayit_panel(self, interaction: discord.Interaction):
        if not discord.utils.get(interaction.user.roles, id=KURUCU_ROL_ID):
            return await interaction.response.send_message("❌ Bu komutu sadece **Kurucu** kullanabilir!", ephemeral=True)

        desc = (
            "> 📜 **Kural & Düzen:** Kayıt olmadan önce kuralları okumayı unutmayınız. Sunucu düzenini ve rol kalitesini bozacak davranışlar yasaktır.\n> \n"
            "> 👁️ **Kanal Erişimi:** Sunucu adının üstüne tıklayarak **Tüm Kanalları Göster** seçeneğini mutlaka aktif edin!\n> \n"
            "> 🔗 **Roblox Doğrulaması:** Başvuru sırasında geçerli **Roblox Profil Linkiniz** gereklidir.\n> \n"
            "> 👤 **İsim Tercihi:** Formda gerçek isminizi belirtmek istemiyorsanız takma ad kullanabilirsiniz.\n> \n"
            "> 🧭 **Kayıt Süreci:** Başvuru ➜ Yetkili Onayı ➜ Roblox Grup Doğrulaması ➜ Karakter Oluşturma ➜ Aramızdasın! 🎉\n> \n"
            "> 🎫 **Yardım & Destek:** Kayıt olmakta sorun yaşıyorsanız [Destek Bileti](" + DESTEK_KANAL_LINK + ") kanalından talep oluşturabilirsiniz.\n\n"
            "Aşağıdaki **Kayıt Ol** butonuna basarak başvurunuzu başlatabilirsiniz! 🥳"
        )
        embed = discord.Embed(title="🏛️ PİYADE RP | Kayıt Rehberi & Sistemi", description=desc, colour=discord.Colour.green())
        embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

        await interaction.response.defer(ephemeral=True)
        if os.path.exists(PANEL_BANNER_PATH):
            embed.set_image(url="attachment://yeni_banner.png")
            await interaction.channel.send(embed=embed, file=discord.File(PANEL_BANNER_PATH, filename="yeni_banner.png"), view=KayitButonView())
        else:
            await interaction.channel.send(embed=embed, view=KayitButonView())
        await interaction.followup.send("✅ Panel başarıyla gönderildi.", ephemeral=True)

    @app_commands.command(name="grup-panel", description="PRP | Hesap Onaylama (Roblox grup) panelini bu kanala kurar.")
    async def grup_panel(self, interaction: discord.Interaction):
        if not discord.utils.get(interaction.user.roles, id=KURUCU_ROL_ID):
            return await interaction.response.send_message("❌ Bu komutu sadece **Kurucu** kullanabilir!", ephemeral=True)
        if not os.path.exists(GRUP_PANEL_BANNER_PATH):
            return await interaction.response.send_message("❌ `assets/grup_panel_banner.jpg` bulunamadı.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.send(
            view=GrupPanelView(),
            file=discord.File(GRUP_PANEL_BANNER_PATH, filename="grup_panel_banner.jpg"),
        )
        uyari = "" if ROBLOX_API_KEY else "\n⚠️ `ROBLOX_API_KEY` tanımlı değil! Grup isteği kontrolü çalışmayacak."
        await interaction.followup.send(f"✅ Grup paneli gönderildi.{uyari}", ephemeral=True)

    @app_commands.command(name="ck-panel-kur", description="PRP | CK Başvurusu panelini bu kanala kurar.")
    async def ck_panel_kur(self, interaction: discord.Interaction):
        if not discord.utils.get(interaction.user.roles, id=KURUCU_ROL_ID):
            return await interaction.response.send_message("❌ Bu komutu sadece **Kurucu** kullanabilir!", ephemeral=True)
        if not os.path.exists(CK_PANEL_BANNER_PATH):
            return await interaction.response.send_message("❌ `assets/ck_panel_banner.jpg` bulunamadı.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.send(
            view=CKPanelView(),
            file=discord.File(CK_PANEL_BANNER_PATH, filename="ck_panel_banner.jpg"),
        )
        await interaction.followup.send("✅ CK paneli başarıyla gönderildi.", ephemeral=True)

    @app_commands.command(name="mevcut-uye-panel", description="PRP | Mevcut Üye Roblox Grup Eşleme panelini bu kanala kurar.")
    async def mevcut_uye_panel(self, interaction: discord.Interaction):
        if not discord.utils.get(interaction.user.roles, id=KURUCU_ROL_ID):
            return await interaction.response.send_message("❌ Bu komutu sadece **Kurucu** kullanabilir!", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.send(view=MevcutUyePanelView())
        await interaction.followup.send("✅ Mevcut üye paneli başarıyla gönderildi.", ephemeral=True)

    @app_commands.command(name="kayit-sifirla", description="Bir kullanıcının kayıt sürecini ve Roblox kimlik bağlantısını sıfırlar.")
    @app_commands.describe(kullanici="Kaydı sıfırlanacak kullanıcı (ID de yazılabilir)")
    async def kayit_sifirla(self, interaction: discord.Interaction, kullanici: discord.User):
        if not yetkili_mi(interaction.user):
            return await interaction.response.send_message("❌ Yetkiniz bulunmuyor.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        async with _kilit(kullanici.id):
            kayit = kayit_al(kullanici.id)
            if not kayit:
                return await interaction.followup.send("ℹ️ Bu kullanıcıya ait kayıt verisi yok.", ephemeral=True)
            _roblox_baglantisini_birak(kayit)
            _thread_silme_planla(kayit, gecikme=0)
            _veri()["kullanicilar"].pop(str(kullanici.id), None)
            _veri()["ck_basvurulari"].pop(str(kullanici.id), None)
            _veri()["ck_gecmisi"].pop(str(kullanici.id), None)
            await _kaydet()
        uye = await _uye_getir(interaction.guild, kullanici.id)
        if uye:
            await _rolleri_duzenle(uye, [], [GRUP_ONAY_BEKLIYOR_ROL_ID, ONAYLANMIS_BIREY_ROL_ID], f"Kayıt sıfırlandı ({interaction.user})")
        await interaction.followup.send(
            f"✅ {kullanici.mention} kaydı sıfırlandı. Roblox bağlantısı (`{kayit.get('roblox_ad')}`) serbest bırakıldı; kullanıcı yeniden başvurabilir.",
            ephemeral=True,
        )

    @app_commands.command(name="ck-sifirla", description="Bir kullanıcının CK bekleme süresini (cooldown) ve bekleyen CK başvurusunu sıfırlar.")
    @app_commands.describe(kullanici="CK süresi sıfırlanacak kullanıcı")
    async def ck_sifirla(self, interaction: discord.Interaction, kullanici: discord.Member):
        if not yetkili_mi(interaction.user):
            return await interaction.response.send_message("❌ Yetkiniz bulunmuyor.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        uid_str = str(kullanici.id)
        async with _kilit(kullanici.id):
            _veri()["ck_basvurulari"].pop(uid_str, None)
            kayit = kayit_al(kullanici.id)
            if kayit and "son_ck_tarihi" in kayit:
                kayit.pop("son_ck_tarihi", None)
            if uid_str in _veri()["ck_gecmisi"]:
                for item in _veri()["ck_gecmisi"][uid_str]:
                    if item.get("durum") in ("tamamlandi", "onaylandi"):
                        item["durum"] = "sifirlandi"
            await _kaydet()

        await interaction.followup.send(
            f"✅ {kullanici.mention} kullanıcısının CK bekleme süresi ve başvuruları sıfırlandı. Kullanıcı hemen yeni CK başvurusu yapabilir.",
            ephemeral=True,
        )


async def setup(bot):
    await bot.add_cog(Registration(bot))
