import discord
from discord.ext import commands, tasks
from discord import app_commands
import json
import os
import random
import string
from datetime import datetime, timedelta

# ==================== KANAL & ROL ID'LERİ ====================
UYARILAR_KANAL_ID = 1532828434739368149   # Uyarı kayıtlarının gönderileceği kanal
SICIL_LOG_KANAL_ID = 1532828404347437287  # Sicil log kanalı

# Katılımcı Uyarı Rolleri
UYARI_1_ROL = 1534715251323572315   # Uyarı 1 (3 puan)
UYARI_2_ROL = 1534715383507058749   # Uyarı 2 (6 puan)
UYARI_3_ROL = 1534715488716853278   # Uyarı 3 (9 puan)
UYARI_4_ROL = 1553054768388374620   # Uyarı 4 (12 puan)
UYARI_5_ROL = 1553055210073497710   # Uyarı 5 (15 puan)
JAIL_ROL    = 1553053929087172768   # Jail rolü
YASAKLI_ROL = 1534715583826759790   # Yasaklı rolü (M9 özel)

UYARI_KADEME_ROLLERI = {
    1: UYARI_1_ROL,    # 3+ puan
    2: UYARI_2_ROL,    # 6+ puan
    3: UYARI_3_ROL,    # 9+ puan
    4: UYARI_4_ROL,    # 12+ puan
    5: UYARI_5_ROL,    # 15+ puan
}
TUM_UYARI_ROLLERI = list(UYARI_KADEME_ROLLERI.values())

# Yetkili Uyarı Rolleri
YETKILI_UYARI_1 = 1551287340444549191
YETKILI_UYARI_2 = 1551287502667776130
YETKILI_UYARI_3 = 1551287599983755405
TUM_YETKILI_UYARI_ROLLERI = [YETKILI_UYARI_1, YETKILI_UYARI_2, YETKILI_UYARI_3]

# Yetkili rolleri
YETKILI_ROLLERI = [
    1551241753137254611,  # Senior Staff
    1551241634094645288,  # Staff
    1551241468985737376,  # Trial Staff
    1529546007635824680,  # Kurucu
    1539167256246747186,  # Üst Yönetim
    1534798061845483694,  # Yönetici
    1537934087166369812,  # Yönetim ekibi
    1542249243702726796,  # Mesaj Denetimcisi
    1547526649459777556,  # Ses Kanalı yetkilisi
    1543075759508164659,  # Takma Ad Yetkilisi
    1551242344190189718,  # Whitelist Yetkilisi
]

# Yönetim rolleri (uyarı panelini kullanabilecekler)
YONETIM_ROLLERI = [1529546007635824680, 1539167256246747186]

# ==================== KURAL SİSTEMİ ====================

# Katılımcı Kuralları - Kategori 1: Genel Kurallar
# Katılımcı Kuralları - Kategori 2: Sunucu Düzeni
MADDELER = {
    # Kategori 1: Genel Kurallar
    "M1":  {"puan": 2,  "aciklama": "Sunucumuzda küfür/hakarete başvurmak.", "ozel": None},
    "M2":  {"puan": 0,  "aciklama": "Reklam yapmak, hesap/oyun satışı gibi ticari faaliyetlerde bulunmak (Özel mesajda dahil).", "ozel": "ban"},
    "M3":  {"puan": 1,  "aciklama": "Etkinliklerde veya kapışmalarda karşı taraf rahatsız olduğu halde kendini abartı şekilde övmek.", "ozel": None},
    "M4":  {"puan": 0,  "aciklama": "Cinsiyet fark etmeksizin taciz içeren davranışlarda bulunmak.", "ozel": "timeout_2gun"},
    "M5":  {"puan": 3,  "aciklama": "Kanalları amacı dışında kullanmak (Örn: #bot-komut'da sohbet etmek).", "ozel": None},
    "M6":  {"puan": 8,  "aciklama": "Cinsel içerikli herhangi bir paylaşım (görsel, yazı, link) yapmak.", "ozel": None},
    "M7":  {"puan": 4,  "aciklama": "Bir kişiye muhatap olmak istemediği sürece ya da kasten kavga ortamı yaratmak.", "ozel": None},
    "M8":  {"puan": 5,  "aciklama": "Zorbalık yapmak, başka bir üyeyi sunucudan soğutacak davranışlarda bulunmak.", "ozel": None},
    "M9":  {"puan": 0,  "aciklama": "Kurucu ve Üst Yönetim'in bilgisi dışında sunucu üyelerini kendi sunucunuza veya grubunuza davet etmek.", "ozel": "yasakli"},
    "M10": {"puan": 0,  "aciklama": "+18, cinsel taciz, ırkçılık, cinsiyet/yaş ayrımcılığı içeren içerik paylaşmak.", "ozel": "timeout_1gun"},
    "M11": {"puan": 0,  "aciklama": "Irkçılık ve her türlü ayrımcılık yapmak.", "ozel": "timeout_1gun"},
    "M12": {"puan": 2,  "aciklama": "Sunucuda bulunan kişilerin psikolojisini etkileyecek argo, küçümseme ve dalga geçme gibi faaliyetler yapmak.", "ozel": None},
    "M13": {"puan": 0,  "aciklama": "Sunucuda yapılan etkinliklerde ve kapışmalarda 3. Taraf yazılım kullanmak.", "ozel": "timeout_1gun"},
    # Kategori 2: Sunucu Düzeni
    "D1":  {"puan": 3,  "aciklama": "Önemli kanallara (duyuru vb.) anlamsız, boş mesajlar atmak.", "ozel": None},
    "D2":  {"puan": 3,  "aciklama": "Ses kanallarında ses panelini veya sohbet kanallarında sohbeti gereksiz yere çağırmak (spawnlamak).", "ozel": None},
    "D3":  {"puan": 3,  "aciklama": "Önemli ses kanallarında sürekli yolculuk yaparak gereksiz bildirim yağmuruna sebep olmak.", "ozel": None},

    # Kategori 3: Roleplay (RM) Kuralları
    "RM1":  {"puan": 3, "aciklama": "Fail RP (FRP)", "ozel": None},
    "RM2":  {"puan": 3, "aciklama": "Fear Roleplay (Korku Rolü Yapmama)", "ozel": None},
    "RM3":  {"puan": 2, "aciklama": "Cop Trigger (Cop-Bait)", "ozel": None},
    "RM4":  {"puan": 4, "aciklama": "New Life Rule (NLR) İhlali", "ozel": None},
    "RM5":  {"puan": 2, "aciklama": "Non-RP Driving", "ozel": None},
    "RM6":  {"puan": 3, "aciklama": "Combat LOG (CL)", "ozel": None},
    "RM7":  {"puan": 4, "aciklama": "Meta Gaming (MG)", "ozel": None},
    "RM8":  {"puan": 3, "aciklama": "Power Gaming (PG)", "ozel": None},
    "RM9":  {"puan": 0, "aciklama": "Erotik Roleplay (ERP) Dayatması/İhlali", "ozel": "timeout_4gun"},
    "RM10": {"puan": 4, "aciklama": "Random Shooting", "ozel": None},
    "RM11": {"puan": 3, "aciklama": "Vehicle Death Match (VDM)", "ozel": None},
    "RM12": {"puan": 2, "aciklama": "GOOA (Silah Çıkarma Kuralı İhlali)", "ozel": None},
    "RM13": {"puan": 4, "aciklama": "Trash Talk (TT)", "ozel": None},
    "RM14": {"puan": 3, "aciklama": "Random Death Match (RDM)", "ozel": None},
    "RM15": {"puan": 1, "aciklama": "Kaza RP Yapmama", "ozel": None},
    "RM16": {"puan": 2, "aciklama": "Refuse RP (Rolü Reddetmek)", "ozel": None},
    "RM17": {"puan": 5, "aciklama": "Abuse (Oyun Açığı Suistimali)", "ozel": None},
}

# Yetkili Kuralları (puan sistemi yok, uyarı sayısı bazlı)
YETKILI_MADDELER = {
    "Y1": {"aciklama": "Yetkisini kendi lehine kullanmak.", "ozel": "yetki_al"},
    "Y2": {"aciklama": "Sunucudaki katılımcıyı yanlış yönlendirmek.", "ozel": None},
    "Y3": {"aciklama": "Yanlış işlem yapmak. (Örn: Yanlış uyarı vermek)", "ozel": None},
    "Y4": {"aciklama": "Sunucuda kendini üstün görmek.", "ozel": None},
    "Y5": {"aciklama": "Kendinden üst kademeli yetkililerin yönlendirmesini dinlememek/takmamak.", "ozel": None},
}

# ==================== VERİ YÖNETİMİ ====================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
UYARI_DATA_FILE = os.path.join(DATA_DIR, "uyari_data.json")
SICIL_DATA_FILE = os.path.join(DATA_DIR, "sicil_data.json")

os.makedirs(DATA_DIR, exist_ok=True)

def load_data(filepath):
    if not os.path.exists(filepath):
        return {}
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def save_data(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def generate_uyari_id():
    """4 haneli benzersiz uyarı ID'si üretir."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

def get_user_data(uid: str):
    """Kullanıcının uyarı verisini döndürür, yoksa oluşturur."""
    data = load_data(UYARI_DATA_FILE)
    if uid not in data:
        data[uid] = {
            "uyarilar": [],
            "toplam_puan": 0,
            "kademe": 0,
            "son_uyari_tarihi": None,
            "jail_bitis": None
        }
        save_data(UYARI_DATA_FILE, data)
    return data[uid]

def save_user_data(uid: str, user_data: dict):
    """Kullanıcı verisini kaydeder."""
    data = load_data(UYARI_DATA_FILE)
    data[uid] = user_data
    save_data(UYARI_DATA_FILE, data)

def hesapla_kademe(toplam_puan: int) -> int:
    """Toplam puana göre uyarı kademesini hesaplar."""
    if toplam_puan >= 15:
        return 5
    elif toplam_puan >= 12:
        return 4
    elif toplam_puan >= 9:
        return 3
    elif toplam_puan >= 6:
        return 2
    elif toplam_puan >= 3:
        return 1
    return 0

def add_sicil_record(user_id: int, madde: str, aciklama: str, yetkili_id: int, sonuc: str):
    """Sicil dosyasına kayıt ekler."""
    data = load_data(SICIL_DATA_FILE)
    uid = str(user_id)
    if uid not in data:
        data[uid] = []
    data[uid].append({
        "tarih": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "madde": madde,
        "aciklama": aciklama,
        "yetkili_id": yetkili_id,
        "sonuc": sonuc
    })
    save_data(SICIL_DATA_FILE, data)

# ==================== YARDIMCI FONKSİYONLAR ====================

def yetkili_rolunu_bul(member: discord.Member) -> str:
    """Yetkilinin en yüksek rütbesini metin olarak döndürür."""
    rol_isimleri = {
        1529546007635824680: "Kurucu",
        1539167256246747186: "Üst Yönetim",
        1534798061845483694: "Yönetici",
        1537934087166369812: "Yönetim Ekibi",
        1551241753137254611: "Senior Staff",
        1551241634094645288: "Staff",
        1551241468985737376: "Trial Staff",
        1542249243702726796: "Mesaj Denetimcisi",
        1547526649459777556: "Ses Kanalı Yetkilisi",
        1543075759508164659: "Takma Ad Yetkilisi",
        1551242344190189718: "Whitelist Yetkilisi",
    }
    # Öncelik sırası: en yüksekten en düşüğe
    for rol_id, isim in rol_isimleri.items():
        if any(r.id == rol_id for r in member.roles):
            return isim
    return "Yetkili"

def kullanici_yetkili_mi(member: discord.Member) -> bool:
    """Kullanıcının yetkili olup olmadığını kontrol eder."""
    return any(r.id in YETKILI_ROLLERI for r in member.roles)

def yonetim_mi(member: discord.Member) -> bool:
    """Yönetim rolü var mı kontrol eder."""
    if member.guild_permissions.administrator:
        return True
    return any(r.id in YONETIM_ROLLERI for r in member.roles)

# ==================== KANIT GÖRSEL SİSTEMİ ====================

class KanitGorselView(discord.ui.View):
    """Uyarı verdikten sonra kanıt görseli yükleme seçeneği sunar."""
    def __init__(self, uyari_id: str, hedef_id: int, kanal_id: int):
        super().__init__(timeout=120)
        self.uyari_id = uyari_id
        self.hedef_id = hedef_id
        self.kanal_id = kanal_id
        self.gorsel_url = None

    @discord.ui.button(label="📎 Görsel Yükle", style=discord.ButtonStyle.primary, custom_id="kanit_yukle_btn")
    async def gorsel_yukle(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "📎 Lütfen **30 saniye** içinde kanıt görselini bu kanala gönderin.\n"
            "*(Sadece resim dosyası kabul edilir)*",
            ephemeral=True
        )
        
        def check(m):
            return (m.author.id == interaction.user.id 
                    and m.channel.id == interaction.channel.id 
                    and len(m.attachments) > 0
                    and any(m.attachments[0].filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']))
        
        try:
            msg = await interaction.client.wait_for('message', check=check, timeout=30.0)
            gorsel_url = msg.attachments[0].url
            
            # Uyarı kaydına görseli ekle
            data = load_data(UYARI_DATA_FILE)
            uid = str(self.hedef_id)
            if uid in data:
                for uyari in data[uid]["uyarilar"]:
                    if uyari["id"] == self.uyari_id:
                        uyari["kanit_url"] = gorsel_url
                        break
                save_data(UYARI_DATA_FILE, data)
            
            # Log kanalındaki uyarı mesajını güncelle
            log_kanal = interaction.guild.get_channel(self.kanal_id)
            if log_kanal:
                async for log_msg in log_kanal.history(limit=30):
                    if log_msg.author == interaction.client.user and log_msg.embeds:
                        embed = log_msg.embeds[0]
                        if embed.footer and embed.footer.text and self.uyari_id in embed.footer.text:
                            new_embed = embed.copy()
                            new_embed.set_image(url=gorsel_url)
                            if new_embed.description and "Görsel Kanıtı: *Eklenmedi*" in new_embed.description:
                                new_embed.description = new_embed.description.replace(
                                    "Görsel Kanıtı: *Eklenmedi*", 
                                    f"Görsel Kanıtı: [Resim]({gorsel_url})"
                                )
                            await log_msg.edit(embed=new_embed)
                            break
            
            await msg.delete()
            await interaction.followup.send(f"✅ Kanıt görseli **#{self.uyari_id}** numaralı uyarıya eklendi.", ephemeral=True)
            self.stop()
            
        except Exception:
            await interaction.followup.send("⏰ Süre doldu veya geçersiz dosya. Kanıt eklenmedi.", ephemeral=True)
            self.stop()

    @discord.ui.button(label="⏩ Pas Geç", style=discord.ButtonStyle.secondary, custom_id="kanit_pasla_btn")
    async def pas_gec(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("✅ Kanıt görseli eklenmeden devam edildi.", ephemeral=True)
        self.stop()

# ==================== UYARI MODAL ====================

class ResmiUyariModal(discord.ui.Modal, title="Uyarı - Madde Numarası"):
    madde = discord.ui.TextInput(
        label="Madde Numarası (Örn: M1, D1, Y2)",
        style=discord.TextStyle.short,
        placeholder="M1",
        required=True,
        max_length=5
    )

    def __init__(self, hedef_kullanici: discord.Member):
        super().__init__()
        self.hedef_kullanici = hedef_kullanici

    async def on_submit(self, interaction: discord.Interaction):
        madde_kodu = self.madde.value.strip().upper()
        guild = interaction.guild
        hedef = self.hedef_kullanici
        yetkili = interaction.user
        
        # Hedef yetkili mi kontrol et
        hedef_yetkili = kullanici_yetkili_mi(hedef)
        
        # Yetkili maddeleri (Y1-Y5) ve RM maddeleri yetkili tarafından yapılırsa
        if madde_kodu in YETKILI_MADDELER or (hedef_yetkili and madde_kodu.startswith("RM")):
            if not hedef_yetkili:
                return await interaction.response.send_message(
                    f"❌ **{madde_kodu}** yetkili kuralıdır. {hedef.mention} yetkili değil!", ephemeral=True)
            await self._yetkili_uyari_isle(interaction, madde_kodu, hedef, yetkili, guild)
            return
        
        # Normal maddeler (M1-M12, D1-D3)
        if madde_kodu not in MADDELER:
            return await interaction.response.send_message(
                "❌ Geçersiz madde numarası! Geçerli maddeler: M1-M13, D1-D3, RM1-RM17, Y1-Y5", ephemeral=True)
        
        if hedef_yetkili and madde_kodu not in YETKILI_MADDELER:
            # Yetkililere normal madde uygulanabilir (M kuralları onlar için de geçerli)
            pass
        
        await self._katilimci_uyari_isle(interaction, madde_kodu, hedef, yetkili, guild)

    async def _katilimci_uyari_isle(self, interaction, madde_kodu, hedef, yetkili, guild):
        """Katılımcı uyarı işlemi — puanlı sistem."""
        bilgi = MADDELER[madde_kodu]
        ozel = bilgi["ozel"]
        
        # === ÖZEL DURUMLAR ===
        
        # M2: Doğrudan BAN
        if ozel == "ban":
            sonuc = "Kalıcı Yasak (Permanent Ban)"
            uyari_id = generate_uyari_id()
            
            add_sicil_record(hedef.id, madde_kodu, bilgi["aciklama"], yetkili.id, sonuc)
            msg_id = await self._uyari_log_gonder(interaction, uyari_id, madde_kodu, bilgi, hedef, yetkili, 0, 0, 0, sonuc, guild)
            
            try:
                await hedef.send(f"🚫 **{guild.name}** sunucusundan **kalıcı olarak yasaklandınız.**\n📌 Sebep: **{madde_kodu}** — {bilgi['aciklama']}")
            except discord.Forbidden:
                pass
            
            try:
                await hedef.ban(reason=f"{madde_kodu} - {bilgi['aciklama']}")
            except discord.Forbidden:
                await interaction.response.send_message("❌ Bu kullanıcıyı banlama yetkim yok!", ephemeral=True)
                return
            
            await interaction.response.send_message(f"✅ **{hedef.display_name}** kalıcı olarak yasaklandı. (M2)", ephemeral=True)
            return
        
        # M9: Doğrudan Yasaklı rolü
        if ozel == "yasakli":
            yasakli_rol = guild.get_role(YASAKLI_ROL)
            sonuc = "Doğrudan Yasaklı rolü verildi"
            uyari_id = generate_uyari_id()
            
            if yasakli_rol:
                # Tüm rolleri al, yasaklı ver
                silinecek = [r for r in hedef.roles if r.id != guild.id and not r.is_integration() and not r.is_premium_subscriber()]
                try:
                    await hedef.remove_roles(*silinecek, reason=f"{madde_kodu} ihlali")
                    await hedef.add_roles(yasakli_rol, reason=f"{madde_kodu} ihlali")
                except discord.Forbidden:
                    pass
            
            add_sicil_record(hedef.id, madde_kodu, bilgi["aciklama"], yetkili.id, sonuc)
            msg_id = await self._uyari_log_gonder(interaction, uyari_id, madde_kodu, bilgi, hedef, yetkili, 0, 0, 0, sonuc, guild)
            await interaction.response.send_message(f"✅ **{hedef.display_name}** doğrudan Yasaklı rolü aldı. (M9)", ephemeral=True)
            return
        
        # M4: 2 Gün Timeout
        if ozel == "timeout_2gun":
            sonuc = "2 Gün Timeout"
            uyari_id = generate_uyari_id()
            try:
                await hedef.timeout(timedelta(days=2), reason=f"{madde_kodu} - {bilgi['aciklama']}")
            except discord.Forbidden:
                pass
            add_sicil_record(hedef.id, madde_kodu, bilgi["aciklama"], yetkili.id, sonuc)
            msg_id = await self._uyari_log_gonder(interaction, uyari_id, madde_kodu, bilgi, hedef, yetkili, 0, 0, 0, sonuc, guild)
            await interaction.response.send_message(f"✅ **{hedef.display_name}** 2 gün timeout aldı. (M4)", ephemeral=True)
            return
        
        
        # RM9: 4 Gün Timeout
        if ozel == "timeout_4gun":
            sonuc = "4 Gün Timeout"
            uyari_id = generate_uyari_id()
            try:
                await hedef.timeout(timedelta(days=4), reason=f"{madde_kodu} - {bilgi['aciklama']}")
            except discord.Forbidden:
                pass
            add_sicil_record(hedef.id, madde_kodu, bilgi["aciklama"], yetkili.id, sonuc)
            msg_id = await self._uyari_log_gonder(interaction, uyari_id, madde_kodu, bilgi, hedef, yetkili, 0, 0, 0, sonuc, guild)
            await interaction.response.send_message(f"✅  **{hedef.display_name}** 4 gün timeout aldı. ({madde_kodu})", ephemeral=True)
            return

        # M10, M11: 1 Gün Timeout
        if ozel == "timeout_1gun":
            sonuc = "1 Gün Timeout"
            uyari_id = generate_uyari_id()
            try:
                await hedef.timeout(timedelta(days=1), reason=f"{madde_kodu} - {bilgi['aciklama']}")
            except discord.Forbidden:
                pass
            add_sicil_record(hedef.id, madde_kodu, bilgi["aciklama"], yetkili.id, sonuc)
            msg_id = await self._uyari_log_gonder(interaction, uyari_id, madde_kodu, bilgi, hedef, yetkili, 0, 0, 0, sonuc, guild)
            await interaction.response.send_message(f"✅ **{hedef.display_name}** 1 gün timeout aldı. ({madde_kodu})", ephemeral=True)
            return
        
        # === PUANLI SİSTEM ===
        eklenen_puan = bilgi["puan"]
        uid = str(hedef.id)
        user_data = get_user_data(uid)
        
        # Uyarı ekle
        uyari_id = generate_uyari_id()
        simdi = datetime.now()
        bitis_tarihi = simdi + timedelta(days=30)
        
        user_data["uyarilar"].append({
            "id": uyari_id,
            "madde": madde_kodu,
            "puan": eklenen_puan,
            "aciklama": bilgi["aciklama"],
            "yetkili_id": yetkili.id,
            "tarih": simdi.strftime("%d/%m/%Y %H:%M"),
            "bitis_tarihi": bitis_tarihi.strftime("%d/%m/%Y"),
            "kanit_url": None,
            "aktif": True
        })
        
        eski_puan = user_data["toplam_puan"]
        user_data["toplam_puan"] = eski_puan + eklenen_puan
        yeni_puan = user_data["toplam_puan"]
        user_data["son_uyari_tarihi"] = simdi.isoformat()
        
        yeni_kademe = hesapla_kademe(yeni_puan)
        user_data["kademe"] = yeni_kademe
        
        # Uyarı rollerini güncelle
        silinecek_roller = [guild.get_role(r) for r in TUM_UYARI_ROLLERI if guild.get_role(r) and guild.get_role(r) in hedef.roles]
        if silinecek_roller:
            try:
                await hedef.remove_roles(*silinecek_roller, reason="Uyarı kademesi güncelleniyor")
            except discord.Forbidden:
                pass
        
        # Yeni kademe rolünü ver
        sonuc_metni = ""
        if yeni_kademe > 0:
            yeni_rol = guild.get_role(UYARI_KADEME_ROLLERI[yeni_kademe])
            if yeni_rol:
                try:
                    await hedef.add_roles(yeni_rol, reason=f"Uyarı Kademe {yeni_kademe}")
                except discord.Forbidden:
                    pass
            sonuc_metni = f"Uyarı {yeni_kademe} rolü verildi."
        
        # 10 puan = 3 gün timeout (ek ceza)
        if eski_puan < 10 <= yeni_puan:
            try:
                await hedef.timeout(timedelta(days=3), reason="10 uyarı puanına ulaşıldı - 3 gün timeout")
            except discord.Forbidden:
                pass
            sonuc_metni += " + 3 Gün Timeout (10 puan)"
        
        # 15+ puan = Jail rolü (1 hafta)
        if yeni_kademe >= 5:
            jail_rol = guild.get_role(JAIL_ROL)
            if jail_rol:
                try:
                    await hedef.add_roles(jail_rol, reason="15+ uyarı puanı - 1 hafta Jail")
                except discord.Forbidden:
                    pass
            user_data["jail_bitis"] = (simdi + timedelta(weeks=1)).isoformat()
            sonuc_metni += " + 1 Hafta Jail"
        
        save_user_data(uid, user_data)
        
        # Sicil kaydı
        add_sicil_record(hedef.id, madde_kodu, bilgi["aciklama"], yetkili.id, sonuc_metni)
        
        # Log mesajı gönder
        aktif_uyari_sayisi = len([u for u in user_data["uyarilar"] if u.get("aktif", True)])
        msg_id = await self._uyari_log_gonder(
            interaction, uyari_id, madde_kodu, bilgi, hedef, yetkili,
            eklenen_puan, yeni_puan, yeni_kademe, sonuc_metni, guild,
            bitis_tarihi_str=bitis_tarihi.strftime("%d/%m/%Y"),
            toplam_uyari=aktif_uyari_sayisi
        )
        user_data["uyarilar"][-1]["log_msg_id"] = msg_id
        save_user_data(uid, user_data)
        
        # Kanıt görsel seçeneği
        kanit_view = KanitGorselView(uyari_id, hedef.id, UYARILAR_KANAL_ID)
        await interaction.response.send_message(
            f"✅ **{hedef.display_name}** kişisine **{madde_kodu}** uyarısı verildi. (+{eklenen_puan} puan → Toplam: {yeni_puan})\n"
            f"📌 {sonuc_metni}\n\n"
            f"Kanıt görseli eklemek ister misiniz?",
            view=kanit_view,
            ephemeral=True
        )

    async def _yetkili_uyari_isle(self, interaction, madde_kodu, hedef, yetkili, guild):
        """Yetkili uyarı işlemi — puan yok, uyarı sayısı bazlı."""
        bilgi = YETKILI_MADDELER.get(madde_kodu) or MADDELER.get(madde_kodu)
        ozel = bilgi["ozel"]
        
        # Y1: Direkt yetkileri alınır
        if ozel == "yetki_al":
            silinecek_yetki_rolleri = [guild.get_role(r) for r in YETKILI_ROLLERI if guild.get_role(r)]
            gecerli_silinecekler = [r for r in silinecek_yetki_rolleri if r is not None and r in hedef.roles]
            
            sonuc = "TÜM YETKİLERİ ALINDI (Y1 - Direkt)"
            if gecerli_silinecekler:
                try:
                    await hedef.remove_roles(*gecerli_silinecekler, reason="Y1 - Yetkisini kendi lehine kullanmak")
                except discord.Forbidden:
                    sonuc = "Yetkiler alınacaktı fakat botun rolü yeterli değil!"
            
            uyari_id = generate_uyari_id()
            add_sicil_record(hedef.id, madde_kodu, bilgi["aciklama"], yetkili.id, sonuc)
            msg_id = await self._uyari_log_gonder(interaction, uyari_id, madde_kodu, {"puan": 0, "aciklama": bilgi["aciklama"]}, hedef, yetkili, 0, 0, 0, sonuc, guild, yetkili_uyari=True)
            
            # Sicil log kanalına özel mesaj
            sicil_kanal = guild.get_channel(SICIL_LOG_KANAL_ID)
            if sicil_kanal:
                sicil_embed = discord.Embed(title="📜 Yetkili Siciline İşlendi — YETKİSİ ALINDI", color=discord.Color.dark_red())
                sicil_embed.add_field(name="Eski Yetkili", value=hedef.mention, inline=True)
                sicil_embed.add_field(name="İşlem Yapan", value=yetkili.mention, inline=True)
                sicil_embed.add_field(name="İhlal", value=f"**{madde_kodu}** — {bilgi['aciklama']}", inline=False)
                sicil_embed.timestamp = discord.utils.utcnow()
                await sicil_kanal.send(embed=sicil_embed)
            
            kanit_view = KanitGorselView(uyari_id, hedef.id, UYARILAR_KANAL_ID)
            await interaction.response.send_message(f"✅ **{hedef.display_name}** — {sonuc}", view=kanit_view, ephemeral=True)
            return
        
        if ozel == "timeout_4gun":
            try:
                await hedef.timeout(timedelta(days=4), reason=f"{madde_kodu} - {bilgi['aciklama']}")
            except:
                pass

        # Y2-Y5, RM1-RM17: Yetkili uyarı sayısı +1
        roller = [r.id for r in hedef.roles]
        mevcut_seviye = 0
        if YETKILI_UYARI_3 in roller: mevcut_seviye = 3
        elif YETKILI_UYARI_2 in roller: mevcut_seviye = 2
        elif YETKILI_UYARI_1 in roller: mevcut_seviye = 1
        
        yeni_seviye = mevcut_seviye + 1
        
        # Eski uyarı rollerini sil
        silinecek = [guild.get_role(r) for r in TUM_YETKILI_UYARI_ROLLERI if guild.get_role(r) and guild.get_role(r) in hedef.roles]
        if silinecek:
            try:
                await hedef.remove_roles(*silinecek)
            except discord.Forbidden:
                pass
        
        sonuc = ""
        if yeni_seviye <= 3:
            # Yeni uyarı rolü ver
            uyari_rolleri_map = {1: YETKILI_UYARI_1, 2: YETKILI_UYARI_2, 3: YETKILI_UYARI_3}
            verilecek_rol = guild.get_role(uyari_rolleri_map[yeni_seviye])
            if verilecek_rol:
                try:
                    await hedef.add_roles(verilecek_rol)
                except discord.Forbidden:
                    pass
            sonuc = f"Yetkili Uyarı {yeni_seviye} rolü verildi."
        else:
            # Sınırı aştı: tüm yetkileri al
            silinecek_yetki_rolleri = [guild.get_role(r) for r in YETKILI_ROLLERI if guild.get_role(r)]
            gecerli_silinecekler = [r for r in silinecek_yetki_rolleri if r is not None and r in hedef.roles]
            if gecerli_silinecekler:
                try:
                    await hedef.remove_roles(*gecerli_silinecekler, reason="Yetkili uyarı sınırı aşıldı")
                except discord.Forbidden:
                    pass
            sonuc = "Yetkili uyarı sınırı aşıldı — TÜM YETKİLERİ ALINDI."
            
            # Sicil log
            sicil_kanal = guild.get_channel(SICIL_LOG_KANAL_ID)
            if sicil_kanal:
                sicil_embed = discord.Embed(title="📜 Yetkili Siciline İşlendi — SINIR AŞILDI", color=discord.Color.dark_red())
                sicil_embed.add_field(name="Eski Yetkili", value=hedef.mention, inline=True)
                sicil_embed.add_field(name="İşlem Yapan", value=yetkili.mention, inline=True)
                sicil_embed.add_field(name="Son İhlal", value=f"**{madde_kodu}** — {bilgi['aciklama']}", inline=False)
                sicil_embed.add_field(name="Detay", value=f"Yetkili uyarı sınırını aştı (Seviye {yeni_seviye}). Tüm yetkileri alındı.", inline=False)
                sicil_embed.timestamp = discord.utils.utcnow()
                await sicil_kanal.send(embed=sicil_embed)
        
        uyari_id = generate_uyari_id()
        add_sicil_record(hedef.id, madde_kodu, bilgi["aciklama"], yetkili.id, sonuc)
        msg_id = await self._uyari_log_gonder(interaction, uyari_id, madde_kodu, {"puan": 0, "aciklama": bilgi["aciklama"]}, hedef, yetkili, 0, 0, yeni_seviye, sonuc, guild, yetkili_uyari=True)
        # Note: yetkili warnings are not stored in UYARI_DATA_FILE in the same way, 
        # they are stored in sicil. But we don't need to auto-delete yetkili warnings after 1 month (they are manual).
        
        kanit_view = KanitGorselView(uyari_id, hedef.id, UYARILAR_KANAL_ID)
        await interaction.response.send_message(f"✅ **{hedef.display_name}** — {sonuc}", view=kanit_view, ephemeral=True)

    async def _uyari_log_gonder(self, interaction, uyari_id, madde_kodu, bilgi, hedef, yetkili, eklenen_puan, toplam_puan, kademe, sonuc, guild, bitis_tarihi_str=None, toplam_uyari=0, yetkili_uyari=False):
        """Uyarı log embed'ini oluşturup kanala gönderir."""
        kanal = guild.get_channel(UYARILAR_KANAL_ID)
        if not kanal:
            return
        
        yetkili_rutbe = yetkili_rolunu_bul(yetkili)
        
        embed = discord.Embed(
            title="⚠️ Uyarı Var!!!",
            color=discord.Color.red() if not yetkili_uyari else discord.Color.dark_red()
        )
        
        # Logo thumbnail (sağ üst)
        logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "uyari_logo.png")
        dosya = None
        if os.path.exists(logo_path):
            dosya = discord.File(logo_path, filename="uyari_logo.png")
            embed.set_thumbnail(url="attachment://uyari_logo.png")
        
        # Değişkenleri hazırla
        bitis = bitis_tarihi_str or "—"
        if bilgi.get("ozel") in ("ban", "yasakli"):
            bitis = "Kalıcı"
        
        kademe_str = f"{kademe}" if kademe > 0 else "—"
        if yetkili_uyari:
            kademe_str = f"Yetkili Uyarı {kademe}" if kademe > 0 else "—"
            
        kullanici_rolleri = ", ".join([r.mention for r in hedef.roles if r.id != guild.id][:15]) or "Rol yok"
        
        puan_metni = ""
        if not yetkili_uyari and eklenen_puan > 0:
            puan_metni = (
                f"### 🚨 Verilen Uyarı Puanı:\n"
                f"**+{eklenen_puan} Puan (Toplam: {toplam_puan})**\n\n"
            )
            
        # Description olarak derle
        desc = (
            f"## 👤 Taraflar\n"
            f"**Ceza Yiyen Kişi:** {hedef.mention}\n"
            f"**Yetkili:** {yetkili.mention} | {yetkili_rutbe}\n\n"
            f"***\n\n"
            f"## 📌 Kayıt Özet\n"
            f"**Uyarı ID:** #{uyari_id}\n"
            f"**Yetkili:** {yetkili.mention} | {yetkili_rutbe}\n"
            f"**Ceza Yiyen Kişi:** {hedef.mention}\n"
            f"**Uyarı Bitiş Tarihi:** {bitis}\n"
            f"**Toplam Uyarı:** {toplam_uyari if toplam_uyari > 0 else kademe_str}\n\n"
            f"***\n\n"
            f"{puan_metni}"
            f"### 📝 Uyarı Sebebi:\n"
            f"**{madde_kodu} — {bilgi['aciklama']}**\n\n"
            f"***\n\n"
            f"### 🏷️ Rolleri:\n"
            f"**{kullanici_rolleri}**\n\n"
            f"***\n\n"
            f"📎 **Kanıt**\n"
            f"Görsel Kanıtı: *Eklenmedi*"
        )
        embed.description = desc
        
        # Sonuç
        if sonuc:
            embed.add_field(name="⚡ Uygulanan İşlem", value=f"**{sonuc}**", inline=False)
        
        embed.set_footer(text=f"Uyarı ID: #{uyari_id} • © 2026 PRP")
        embed.timestamp = discord.utils.utcnow()
        
        if dosya:
            msg = await kanal.send(content=f"{hedef.mention}", embed=embed, file=dosya)
        else:
            msg = await kanal.send(content=f"{hedef.mention}", embed=embed)
        return msg.id

# ==================== SEÇİM MENÜLERİ ====================

class KullaniciSecView_Resmi(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
    
    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Uyarı verilecek kişiyi seçin")
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        kullanici = select.values[0]
        if isinstance(kullanici, discord.Member):
            await interaction.response.send_modal(ResmiUyariModal(kullanici))
        else:
            await interaction.response.send_message("Lütfen sunucudaki bir üyeyi seçin.", ephemeral=True)

# ==================== SÖZLÜ UYARI ====================

class SozluUyariModal(discord.ui.Modal, title="Sözlü Uyarı Sebebi"):
    sebep = discord.ui.TextInput(
        label="Uyarı Sebebini Yazın",
        style=discord.TextStyle.paragraph,
        placeholder="Örn: Ses kanalında yüksek sesle konuşmak...",
        required=True
    )
    
    def __init__(self, hedef_kullanici: discord.Member):
        super().__init__()
        self.hedef_kullanici = hedef_kullanici

    async def on_submit(self, interaction: discord.Interaction):
        kanal = interaction.guild.get_channel(UYARILAR_KANAL_ID)
        embed = discord.Embed(title="⚠️ Sözlü Uyarı!", color=discord.Color.orange())
        embed.add_field(name="Uyarı Alan", value=self.hedef_kullanici.mention, inline=True)
        embed.add_field(name="İşlem Yapan", value=interaction.user.mention, inline=True)
        embed.add_field(name="İhlal / Sebep", value=self.sebep.value, inline=False)
        embed.set_footer(text="© 2026 PRP")
        embed.timestamp = discord.utils.utcnow()
        
        if kanal:
            await kanal.send(content=f"{self.hedef_kullanici.mention}", embed=embed)
        
        add_sicil_record(
            user_id=self.hedef_kullanici.id,
            madde="SÖZLÜ",
            aciklama=self.sebep.value,
            yetkili_id=interaction.user.id,
            sonuc="Sözlü uyarı verildi (Rol işlemi yok)."
        )
        
        await interaction.response.send_message(f"✅ Sözlü uyarı {self.hedef_kullanici.mention} kişisine başarıyla verildi.", ephemeral=True)


class KullaniciSecView_Sozlu(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
    
    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Sözlü uyarı verilecek kişiyi seçin")
    async def select_user(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        kullanici = select.values[0]
        if isinstance(kullanici, discord.Member):
            await interaction.response.send_modal(SozluUyariModal(kullanici))
        else:
            await interaction.response.send_message("Lütfen sunucudaki bir üyeyi seçin.", ephemeral=True)


# ==================== KALICI PANEL ====================

class UyariPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Sözlü Uyarı Ver", style=discord.ButtonStyle.secondary, custom_id="sozlu_uyari_btn", emoji="🗣️")
    async def sozlu_uyari(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Kimi uyarmak istiyorsunuz?", view=KullaniciSecView_Sozlu(), ephemeral=True)

    @discord.ui.button(label="Uyarı Ver", style=discord.ButtonStyle.danger, custom_id="resmi_uyari_btn", emoji="⚠️")
    async def resmi_uyari(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Kime uyarı vermek istiyorsunuz?", view=KullaniciSecView_Resmi(), ephemeral=True)


# ==================== COG SINIFI ====================

class UyariSistemi(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.uyari_temizle.start()
        self.jail_kontrol.start()

    def cog_unload(self):
        self.uyari_temizle.cancel()
        self.jail_kontrol.cancel()

    # --- 1 Ay Kuralı: Her saat kontrol et ---
    @tasks.loop(hours=1)
    async def uyari_temizle(self):
        """1 ay boyunca uyarı almayan kullanıcıların uyarılarını sıfırlar."""
        data = load_data(UYARI_DATA_FILE)
        simdi = datetime.now()
        degisti = False
        
        for uid, user_data in data.items():
            son_tarih_str = user_data.get("son_uyari_tarihi")
            if not son_tarih_str:
                continue
            
            try:
                son_tarih = datetime.fromisoformat(son_tarih_str)
            except Exception:
                continue
            
            # 30 günden fazla geçmişse sıfırla
            if (simdi - son_tarih).days >= 30 and user_data.get("toplam_puan", 0) > 0:
                uyari_kanali = self.bot.get_channel(UYARILAR_KANAL_ID)
                if uyari_kanali:
                    for uyari in user_data.get("uyarilar", []):
                        log_msg_id = uyari.get("log_msg_id")
                        if log_msg_id:
                            try:
                                msg = await uyari_kanali.fetch_message(log_msg_id)
                                await msg.delete()
                            except Exception:
                                pass
                user_data["uyarilar"] = []
                user_data["toplam_puan"] = 0
                user_data["kademe"] = 0
                user_data["son_uyari_tarihi"] = None
                degisti = True
                
                # Uyarı rollerini kaldır
                for guild in self.bot.guilds:
                    member = guild.get_member(int(uid))
                    if member:
                        silinecek = [guild.get_role(r) for r in TUM_UYARI_ROLLERI if guild.get_role(r) and guild.get_role(r) in member.roles]
                        if silinecek:
                            try:
                                await member.remove_roles(*silinecek, reason="1 ay uyarı almadı — uyarılar sıfırlandı")
                            except discord.Forbidden:
                                pass
        
        if degisti:
            save_data(UYARI_DATA_FILE, data)

    @uyari_temizle.before_loop
    async def before_uyari_temizle(self):
        await self.bot.wait_until_ready()

    # --- Jail süresi kontrol ---
    @tasks.loop(minutes=30)
    async def jail_kontrol(self):
        """Jail süresi dolan kullanıcıların Jail rolünü kaldırır."""
        data = load_data(UYARI_DATA_FILE)
        simdi = datetime.now()
        degisti = False
        
        for uid, user_data in data.items():
            jail_bitis_str = user_data.get("jail_bitis")
            if not jail_bitis_str:
                continue
            
            try:
                jail_bitis = datetime.fromisoformat(jail_bitis_str)
            except Exception:
                continue
            
            if simdi >= jail_bitis:
                for guild in self.bot.guilds:
                    member = guild.get_member(int(uid))
                    if member is None:
                        try:
                            member = await guild.fetch_member(int(uid))
                        except discord.NotFound:
                            # Üye sunucuda değil → cezayı veritabanında BIRAK, affetme!
                            continue
                        except Exception:
                            continue
                    if member:
                        jail_rol = guild.get_role(JAIL_ROL)
                        if jail_rol and jail_rol in member.roles:
                            try:
                                await member.remove_roles(jail_rol, reason="Jail süresi doldu")
                            except discord.Forbidden:
                                pass
                        # Rol başarıyla kaldırıldı (veya zaten yoktu) → cezayı sıfırla
                        user_data["jail_bitis"] = None
                        degisti = True
        
        if degisti:
            save_data(UYARI_DATA_FILE, data)

    @jail_kontrol.before_loop
    async def before_jail_kontrol(self):
        await self.bot.wait_until_ready()

    # --- Yönetim Kontrol ---
    def yonetim_mi(self, member: discord.Member) -> bool:
        if member.guild_permissions.administrator:
            return True
        return any(rol.id in YONETIM_ROLLERI for rol in member.roles)

    # --- Komutlar ---
    @app_commands.command(name="uyari-panel", description="Uyarı panelini kanala gönderir.")
    @app_commands.default_permissions(administrator=True)
    async def uyari_panel(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚠️ Sunucu Uyarı Paneli",
            description=(
                "**Yapmanız Gerekenler:**\n"
                "→ Uyarı alacak kişiyi seç.\n"
                "→ Karşına çıkan madde numarasını doldur.\n"
                "→ Kanıt görseli varsa yükle.\n\n"
                "**Katılımcı Maddeleri:** M1-M13, D1-D3, RM1-RM17\n"
                "**Yetkili Maddeleri:** Y1-Y5"
            ),
            color=discord.Color.red()
        )
        embed.set_footer(text="© 2026 PRP")
        embed.timestamp = discord.utils.utcnow()
        
        await interaction.channel.send(embed=embed, view=UyariPanel())
        await interaction.response.send_message("✅ Uyarı paneli kuruldu.", ephemeral=True)

    @app_commands.command(name="sicil-gor", description="Bir kullanıcının geçmiş uyarı sicilini gösterir.")
    @app_commands.describe(kisi="Sicili görüntülenecek kişi")
    async def sicil_gor(self, interaction: discord.Interaction, kisi: discord.Member):
        if not self.yonetim_mi(interaction.user):
            return await interaction.response.send_message("❌ Bu komutu sadece Kurucu veya Üst Yönetim kullanabilir.", ephemeral=True)
        
        # Sicil verisinden çek
        sicil_data = load_data(SICIL_DATA_FILE)
        uid = str(kisi.id)
        
        if uid not in sicil_data or len(sicil_data[uid]) == 0:
            return await interaction.response.send_message(f"✅ {kisi.mention} kişisinin sicili tamamen temiz.", ephemeral=True)
        
        kayitlar = sicil_data[uid]
        
        embed = discord.Embed(
            title=f"📜 {kisi.display_name} — Sicil Kaydı",
            description=f"Toplam **{len(kayitlar)}** adet ihlal kaydı bulunuyor.",
            color=discord.Color.dark_theme()
        )
        embed.set_thumbnail(url=kisi.display_avatar.url)
        
        # Aktif uyarı durumu
        uyari_data = get_user_data(uid)
        embed.add_field(
            name="📊 Mevcut Durum",
            value=(
                f"**Toplam Puan:** {uyari_data['toplam_puan']}\n"
                f"**Kademe:** {uyari_data['kademe']}\n"
                f"**Aktif Uyarı:** {len([u for u in uyari_data.get('uyarilar', []) if u.get('aktif', True)])}"
            ),
            inline=False
        )
        
        # Son 10 kayıt göster
        for idx, kayit in enumerate(kayitlar[-10:], 1):
            tarih = kayit.get("tarih", "?")
            madde = kayit.get("madde", "?")
            aciklama = kayit.get("aciklama", "Belirtilmemiş")
            yetkili_id = kayit.get("yetkili_id", 0)
            sonuc = kayit.get("sonuc", "Bilinmiyor")
            
            detay = (
                f"**Tarih:** {tarih}\n"
                f"**Yetkili:** <@{yetkili_id}>\n"
                f"**Açıklama:** {aciklama}\n"
                f"**Sonuç:** {sonuc}"
            )
            embed.add_field(name=f"{idx}. İhlal (Madde: {madde})", value=detay, inline=False)
        
        embed.set_footer(text="© 2026 PRP")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="uyari-sifirla", description="Bir kullanıcının tüm uyarılarını sıfırlar.")
    @app_commands.describe(kisi="Uyarıları sıfırlanacak kişi")
    @app_commands.default_permissions(administrator=True)
    async def uyari_sifirla(self, interaction: discord.Interaction, kisi: discord.Member):
        kurucu_rol_id = 1529546007635824680
        if kurucu_rol_id not in [r.id for r in interaction.user.roles] and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Bu komutu sadece **Kurucu** kullanabilir!", ephemeral=True)
            
        await interaction.response.defer(ephemeral=True)
        
        uid = str(kisi.id)
        data = load_data(UYARI_DATA_FILE)
        
        silinen = 0
        if uid in data:
            # Delete warning messages from channel
            uyari_kanali = self.bot.get_channel(UYARILAR_KANAL_ID)
            if uyari_kanali:
                for uyari in data[uid].get("uyarilar", []):
                    log_msg_id = uyari.get("log_msg_id")
                    if log_msg_id:
                        try:
                            msg = await uyari_kanali.fetch_message(int(log_msg_id))
                            await msg.delete()
                            silinen += 1
                        except:
                            pass
                            
            data[uid]["uyarilar"] = []
            data[uid]["toplam_puan"] = 0
            data[uid]["kademe"] = 0
            data[uid]["son_uyari_tarihi"] = None
            data[uid]["jail_bitis"] = None
            save_data(UYARI_DATA_FILE, data)
        
        # Tüm uyarı + jail rollerini kaldır
        silinecek = [interaction.guild.get_role(r) for r in TUM_UYARI_ROLLERI + [JAIL_ROL] 
                     if interaction.guild.get_role(r) and interaction.guild.get_role(r) in kisi.roles]
        if silinecek:
            try:
                await kisi.remove_roles(*silinecek, reason=f"Uyarılar sıfırlandı - {interaction.user}")
            except discord.Forbidden:
                pass
        
        await interaction.followup.send(f"✅ {kisi.mention} kişisinin tüm uyarıları sıfırlandı ve kanaldaki {silinen} adet uyarı log mesajı silindi.", ephemeral=True)

        
        uid = str(kisi.id)
        data = load_data(UYARI_DATA_FILE)
        
        if uid in data:
            data[uid] = {
                "uyarilar": [],
                "toplam_puan": 0,
                "kademe": 0,
                "son_uyari_tarihi": None,
                "jail_bitis": None
            }
            save_data(UYARI_DATA_FILE, data)
        
        # Tüm uyarı + jail rollerini kaldır
        silinecek = [interaction.guild.get_role(r) for r in TUM_UYARI_ROLLERI + [JAIL_ROL] 
                     if interaction.guild.get_role(r) and interaction.guild.get_role(r) in kisi.roles]
        if silinecek:
            try:
                await kisi.remove_roles(*silinecek, reason=f"Uyarılar sıfırlandı — {interaction.user}")
            except discord.Forbidden:
                pass
        
        await interaction.response.send_message(f"✅ {kisi.mention} kişisinin tüm uyarıları sıfırlandı.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(UyariSistemi(bot))
