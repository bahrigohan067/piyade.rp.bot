import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import time

OLU_ROL_ID = 1544777693030125720
ARANAN_ROL_ID = 1549155694714953870
ARANANLAR_KANAL_ID = 1540128889307922452

def truncate_label(text, limit=80):
    if len(text) > limit:
        return text[:limit-3] + "..."
    return text

SORULAR = [
    {
        "q": "Isı aniden fırladı ve karışım şiddetle fokurdamaya başladı. Saniyelerin var, ne yaparsın?",
        "options": [
            "Üstüne soğuk su dökerim.",
            "Kapağını tüm gücümle kapatıp bastırırım.",
            "Isıtıcıyı anında kapatır ve güvenli mesafeye çekilirim.",
            "Eğilip var gücümle kaba üflerim."
        ],
        "ans": 2
    },
    {
        "q": "Tezgahtaki asit şişesi devrildi, yere doğru hızla akıyor. İlk hamlen nedir?",
        "options": [
            "Çıplak elimle şişeyi hemen dikeltirim.",
            "Bezi alıp asidi silmeye çalışırım.",
            "Asit eldivenimi takıp şişeyi düzeltir, üstüne karbonat/kum dökerim.",
            "Suyun altına tutup asidi yıkamaya çalışırım."
        ],
        "ans": 2
    },
    {
        "q": "Karbon filtren tıkandı, odaya inanılmaz yoğun bir kimyasal kokusu dolmaya başladı. Ne yaparsın?",
        "options": [
            "Sokağa bakan tüm camları sonuna kadar açarım.",
            "İçeride parfüm veya deodorant sıkarım.",
            "İşlemi derhal durdurur ve maskemi takıp filtreyi değiştiririm.",
            "Kokuyu içime çekmemeye çalışıp işe devam ederim."
        ],
        "ans": 2
    },
    {
        "q": "Tam kritik bir sıvıyı (milimetrik) damlatıyorsun, kapı alacaklı gibi çalmaya başladı. Ne yaparsın?",
        "options": [
            "Elimi bırakır koşarak kapıya bakarım.",
            "Kapıdakine 'Kim o, bekle geliyorum!' diye bağırırım.",
            "Kapıyı umursamam, sessizce işlemi bitirmeye odaklanırım.",
            "Sıvının hepsini birden kaba boşaltıp kapıya koşarım."
        ],
        "ans": 2
    },
    {
        "q": "İçinde kimyasal olan cam tüp elinden kaydı ve çatladı, sıvı sızdırıyor. Ne yaparsın?",
        "options": [
            "Çatlağı parmağımla kapatıp bastırırım.",
            "Koli bandıyla etrafını hızlıca sararım.",
            "Tüpü dikkatlice daha büyük ve sağlam bir plastik/cam kaba oturturum.",
            "Tüpü olduğu gibi çöpe fırlatırım."
        ],
        "ans": 2
    },
    {
        "q": "Üretimin ortasındasın. Camdan baktın, evin önünde bir polis arabası yavaşladı ve durdu. Ne yaparsın?",
        "options": [
            "Silahımı çeker camın önünde beklerim.",
            "Tüm ışıkları ve ses yapan makineleri kapatıp karanlıkta beklerim.",
            "Pencereyi açıp 'Birine mi baktınız?' diye bağırırım.",
            "Bütün malzemeleri hızlıca tuvalete dökmeye başlarım."
        ],
        "ans": 1
    },
    {
        "q": "Ocakta ufak bir parlama (alev) oldu. Büyümeden nasıl söndürürsün?",
        "options": [
            "Üstüne bir kova su dökerim.",
            "Ocağı kapatıp alevin üstüne ıslak havlu veya kapak kapatırım.",
            "Rüzgar yapsın diye üstüne bez sallarım.",
            "Üfleyerek söndürmeye çalışırım."
        ],
        "ans": 1
    },
    {
        "q": "Tüpün basınç vanası sıkıştı, ibre hızla kırmızıya (patlama noktasına) yükseliyor. Ne yaparsın?",
        "options": [
            "Vanayı çekiçle vurarak açmaya çalışırım.",
            "Sistemi derhal fişten çeker ve koşarak odadan çıkarım.",
            "Üstüne tüm ağırlığımla abanıp patlamasını engellerim.",
            "Tüpü kucaklayıp camdan aşağı atarım."
        ],
        "ans": 1
    },
    {
        "q": "Mikser inanılmaz bir gürültüyle titremeye başladı, alt komşu tavana vuruyor. Ne yaparsın?",
        "options": [
            "Mikseri durdurur, altına kalın sünger veya kauçuk paspas koyarım.",
            "Komşu duymasın diye son ses müzik açarım.",
            "Hızını daha da artırıp işlemin çabuk bitmesini sağlarım.",
            "Yere ayağımla vurup komşuya karşılık veririm."
        ],
        "ans": 0
    },
    {
        "q": "Yüzündeki gaz maskesinin filtresi doldu, nefes almakta zorlanıyorsun. Ne yaparsın?",
        "options": [
            "Maskeyi çıkarıp derin bir nefes alırım.",
            "Maskeyi hafif aralayıp işe öyle devam ederim.",
            "Yüzümü tişörtümle kapatırım.",
            "Temiz havanın olduğu odaya geçer, filtreyi yenilerim."
        ],
        "ans": 3
    },
    {
        "q": "Soğutucu motor durdu. Sistem aşırı ısınıyor ve sular da kesik. Acil soğutma lazım! Nereden bulursun?",
        "options": [
            "Hortumla karışıma üflerim.",
            "Suların gelmesini beklerim.",
            "Buzdolabındaki buzları veya donmuş gıdaları (et/sebze) kullanırım.",
            "Sıcak malzemeyi buzdolabının içine koyarım."
        ],
        "ans": 2
    },
    {
        "q": "Çatı katındasın. Tam havalandırmanın oraya bir drone yaklaştı, içeri bakıyor. Ne yaparsın?",
        "options": [
            "Drone'a el sallar, doğal davranırım.",
            "Perdeyi hızla çeker, kritik malzemeleri kutulara kaldırırım.",
            "Drone'u vurmak için ateş ederim.",
            "Işık tutarak kamerasını bozmaya çalışırım."
        ],
        "ans": 1
    },
    {
        "q": "Karışım renk değiştiriyor, müdahale için saniyen var. O sırada patronun (veya çete liderin) arıyor. Ne yaparsın?",
        "options": [
            "Telefonu omuzuma sıkıştırıp konuşarak işlemi yaparım.",
            "İşlemi bırakır, telefonu 'Efendim' diyerek açarım.",
            "Telefonu umursamam, karışıma odaklanırım, sonra geri ararım.",
            "Ortağıma 'Sen şu kimyasalı dök, ben konuşayım' derim."
        ],
        "ans": 2
    },
    {
        "q": "Ortağın eldivensiz asite dokundu, 'ellerim yanıyor!' diye panikle bağırıyor. İlk hamlen?",
        "options": [
            "Onu hızlıca lavaboya itip ellerini dakikalarca soğuk suyla yıkamasını söylerim.",
            "Hemen yara bandı ve krem sürerim.",
            "'Sessiz ol polis duyacak' diye ağzını kapatırım.",
            "Asidin üstüne kolonya dökerek dezenfekte ederim."
        ],
        "ans": 0
    },
    {
        "q": "İçerisi buhar altı oldu, sokağa bakan pencerenin perdesi aralanmış. Dışarıdan biri baksa görecek. Ne yaparsın?",
        "options": [
            "Işıkları daha da açar, gölgemi saklarım.",
            "Camın önüne geçip dışarıyı kapatacak şekilde dururum.",
            "Sürünerek veya eğilerek camın altına yaklaşır, perdeyi sıkıca çekerim.",
            "Bir şey olmaz diyerek işime devam ederim."
        ],
        "ans": 2
    },
    {
        "q": "14 saattir ayaktasın, gözlerin kapanıyor ama son ve en tehlikeli aşamadasın. Ne yaparsın?",
        "options": [
            "Gözümü açık tutmak için işlemi hızlandırırım.",
            "Hemen ocağın başında kısa bir şekerleme yaparım.",
            "Sistemi güvenli moda (standby) alıp hava alır, yüzümü yıkarım.",
            "Uyku açsın diye ürettiğim maldan biraz kullanırım."
        ],
        "ans": 2
    },
    {
        "q": "Yanlışlıkla A sıvısı yerine B sıvısını döktün. İkisi tepkimeye girmeye başladı. Ne yaparsın?",
        "options": [
            "İçinden B sıvısını kaşıkla geri toplamaya çalışırım.",
            "Üstüne bolca A sıvısı döküp dengelemeye çalışırım.",
            "Kabı güvenli alana alıp geri çekilir, tepkimenin bitmesini beklerim.",
            "Karışımı hemen lavaboya dökerim."
        ],
        "ans": 2
    },
    {
        "q": "Alt katta yangın alarmı çaldı, apartman boşalıyor. Senin kaynayan sistemin çalışıyor. Ne yaparsın?",
        "options": [
            "İşleme devam ederim, bana gelene kadar zamanım var.",
            "Sistemi çalışır halde bırakıp aşağı inip kalabalığa karışırım.",
            "Ocağı ve fişleri kapatır, kilitleri vurup binayı terk ederim.",
            "İtfaiye gelir diye bütün düzeneği camdan aşağı atarım."
        ],
        "ans": 2
    },
    {
        "q": "Ürün bitti ama hala ıslak. Acil kurutman lazım, fırın bozuldu. Nereye koyarsın?",
        "options": [
            "Sokak kapısının önüne, rüzgar alan bir yere.",
            "Rutubetli ama karanlık banyoya.",
            "Sıcak ve kuru çatı katına veya nem alıcı cihazın önüne.",
            "Kurusun diye doğrudan sobanın alevine tutarım."
        ],
        "ans": 2
    },
    {
        "q": "Kalan tehlikeli atık sıvıyı hemen yok etmen lazım. Nereye dökersin?",
        "options": [
            "Kendi tuvaletime döker sifonu çekerim.",
            "Evin arka bahçesindeki toprağa dökerim.",
            "Ağzı kapalı plastik bidonlara koyar, sonra sanayideki atık varillerine atarım.",
            "Gece sokağa çıkıp rögar kapağından dökerim."
        ],
        "ans": 2
    },
    {
        "q": "Narkotik köpeği olan bir devriye ekibi sokaktan geçiyor. Evin camları açık ve rüzgar dışarı esiyor. İlk hamlen?",
        "options": [
            "Camdan kafamı uzatıp köpeklere bakarım.",
            "Köpeklerin dikkatini dağıtmak için sokağa sosis atarım.",
            "Camları hızla kapatır, havalandırmayı iptal edip içeride koku hapsi yaparım.",
            "Kokuyu bastırmak için evde ateş yakarım."
        ],
        "ans": 2
    },
    {
        "q": "Ortağın panikle içeri girdi, 'Bizi izliyorlar, çıkmamız lazım!' diye bağırıyor. Ocağın üstünde mal var. Ne yaparsın?",
        "options": [
            "Ortağıma inanmam, iş bitene kadar kalmaya zorlarım.",
            "Sıcak malı poşete koyup kaçmaya çalışırım.",
            "Güvenlik için ısıyı kapatır, maskeleri çıkarır ve tahliye planına uyarım.",
            "Silahımı alıp bizi izleyenleri bulmak için dışarı fırlarım."
        ],
        "ans": 2
    },
    {
        "q": "İşlem sırasında sülfürik asit kokusu odaya yayıldı, başın dönmeye başladı. İlk hamlen?",
        "options": [
            "Kokuyu bastırmak için derin derin ağızdan nefes alırım.",
            "Yere (aşağıya) çömelirim, temiz hava alanına emekleyerek çıkarım.",
            "Koşarak etrafta pencere ararım.",
            "Odaya oda parfümü sıkarım."
        ],
        "ans": 1
    },
    {
        "q": "Malları paketledin ama dış kapının önünde komşular sohbet ediyor, gitmiyorlar. Malı evden nasıl çıkarırsın?",
        "options": [
            "Komşuların arasına girip onlarla sohbet ederek malı çıkarırım.",
            "Bağırıp çağırarak komşuları kapıdan kovarım.",
            "Spor çantasına veya alet çantasına koyup, sıradan biri gibi oradan geçerim.",
            "Beklemek istemem, arka camdan çantayı sokağa fırlatırım."
        ],
        "ans": 2
    }
]

IHBAR_SORUSU = {
    "q": "Her şey bitti. Baskın ihbarı aldın, evi 5 dakikada terk etmen lazım. İlk neyi yok edersin/alırsın?",
    "options": [
        "Üretilmiş malı ve içinde ismim olan/bana ait olan her türlü kişisel eşyayı alıp çıkarım.",
        "Makineleri balyozla kırarak 5 dakikamı harcarım.",
        "Evi tamamen ateşe verir öyle çıkarım.",
        "Boş kimyasal şişelerini çantama doldururum."
    ],
    "ans": 0
}

class SoruView(discord.ui.View):
    def __init__(self, correct_ans, user_id, options):
        super().__init__(timeout=10)
        self.correct_ans = correct_ans
        self.user_id = user_id
        self.result = None

        for idx, option_text in enumerate(options):
            btn = discord.ui.Button(label=truncate_label(option_text), style=discord.ButtonStyle.primary, custom_id=f"soru_btn_{idx}")
            btn.callback = self.make_callback(idx)
            self.add_item(btn)

    def make_callback(self, idx):
        async def callback(interaction: discord.Interaction):
            await interaction.response.edit_message(embed=discord.Embed(description="🔄 Sonraki aşamaya geçiliyor...", color=discord.Color.light_grey()), view=None)
            self.result = (idx == self.correct_ans)
            self.stop()
        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Bu butonlar senin için değil!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        self.result = None

class IhbarView(discord.ui.View):
    def __init__(self, user_id, options, correct_ans):
        super().__init__(timeout=15)
        self.correct_ans = correct_ans
        self.user_id = user_id
        self.result = None
        
        for idx, option_text in enumerate(options):
            btn = discord.ui.Button(label=truncate_label(option_text), style=discord.ButtonStyle.danger, custom_id=f"ihbar_btn_{idx}")
            btn.callback = self.make_callback(idx)
            self.add_item(btn)

    def make_callback(self, idx):
        async def callback(interaction: discord.Interaction):
            await interaction.response.edit_message(embed=discord.Embed(description="🚨 Sonuçlar değerlendiriliyor...", color=discord.Color.dark_grey()), view=None)
            self.result = (idx == self.correct_ans)
            self.stop()
        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Bu ihbar seninle ilgili değil!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        self.result = None

class MethUretimi(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldowns = {}

    @app_commands.command(name="madde-uret", description="Karanlık laboratuvarında üretime başla. Riskli ve tehlikelidir!")
    async def madde_uret(self, interaction: discord.Interaction):
        # Cooldown check
        now = time.time()
        cooldown_suresi = 900 # 15 dakika = 900 saniye
        son_kullanim = self.cooldowns.get(interaction.user.id, 0)
        
        if now - son_kullanim < cooldown_suresi:
            kalan_sure = int(cooldown_suresi - (now - son_kullanim))
            dakika = kalan_sure // 60
            saniye = kalan_sure % 60
            return await interaction.response.send_message(f"⏳ Çok yoruldun, polisler de civarda geziyor! Yeni bir üretim yapabilmek için **{dakika} dakika {saniye} saniye** beklemelisin.", ephemeral=True)

        if any(r.id == OLU_ROL_ID for r in interaction.user.roles):
            return await interaction.response.send_message("💀 Ölüler/Mahkumlar işlem yapamaz!", ephemeral=True)
        
        market_cog = self.bot.get_cog("Market")
        if not market_cog:
            return await interaction.response.send_message("Market sistemi aktif değil.", ephemeral=True)

        if not market_cog.esya_sahibi_mi(interaction.user.id, "meth"):
            return await interaction.response.send_message("🛢️ Bunu yapmak için önce marketten **Meth Malzemeleri** satın almalısın!", ephemeral=True)

        # Üretime başarılı şekilde başlanıyor, süreyi başlat:
        self.cooldowns[interaction.user.id] = now

        # ⚠️ Ürün henüz SİLİNMİYOR — oyun bitmeden tüketim yapılmaz.
        # Eğer oyun başarıyla tamamlanırsa aşağıda silinecek.

        await interaction.response.send_message("🧪 **Üretim Başlıyor!** Karşına çıkacak 8 acil duruma 10 saniye içinde doğru tepkiyi vermelisin. Gözünü kırpma!", ephemeral=True)
        await asyncio.sleep(2)
        
        # Select 8 random questions
        secilen_sorular = random.sample(SORULAR, 8)
        
        dogru_sayisi = 0
        zaman_asimi = False

        for i, soru in enumerate(secilen_sorular):
            secenekler = list(enumerate(soru["options"]))
            random.shuffle(secenekler)
            yeni_dogru = None
            view_options = []
            
            for index, (orj_idx, text) in enumerate(secenekler):
                view_options.append(text)
                if orj_idx == soru["ans"]:
                    yeni_dogru = index

            view = SoruView(correct_ans=yeni_dogru, user_id=interaction.user.id, options=view_options)
            metin = f"{soru['q'].replace('[@kullanıcı]', interaction.user.mention)}"
            embed = discord.Embed(title=f"⚠️ ACİL DURUM! (Soru {i+1}/8)", description=metin, color=discord.Color.yellow())
            
            await interaction.edit_original_response(content=None, embed=embed, view=view)
            await view.wait()
            
            if view.result is None: # Timeout
                await interaction.edit_original_response(content="⏰ Süren doldu, çok yavaşsın!", embed=None, view=None)
                await asyncio.sleep(2)
                zaman_asimi = True
                break
            elif view.result:
                dogru_sayisi += 1

        if not zaman_asimi and dogru_sayisi >= 4:
            # Başarılı — ürünü şimdi tüket
            market_cog.esya_sil(interaction.user.id, "meth", 1)

            if dogru_sayisi == 4:
                kazanc = random.randint(300, 500)
            elif dogru_sayisi == 5:
                kazanc = random.randint(500, 800)
            elif dogru_sayisi == 6:
                kazanc = random.randint(800, 1000)
            elif dogru_sayisi == 7:
                kazanc = random.randint(1000, 1200)
            else:
                kazanc = random.randint(1200, 1400)
            
            market_cog.bakiye_ayarla(interaction.user.id, market_cog.bakiye_al(interaction.user.id) + kazanc)
            
            sonuc_embed = discord.Embed(title="✅ Üretim Tamamlandı!", color=discord.Color.green())
            sonuc_embed.description = f"🎉 {interaction.user.mention} muhteşem bir iş çıkardın!\n\n🧪 **Skor:** {dogru_sayisi}/8\n💵 **Kazanılan:** {f'{kazanc:,}'.replace(',', '.')}₺"
            
            await interaction.edit_original_response(content=None, embed=sonuc_embed, view=None)
            
            try:
                await interaction.user.send(embed=sonuc_embed)
            except discord.Forbidden:
                pass  # DM kapalı — sessizce devam et

        else:
            # Başarısız -> İhbar
            secenekler = list(enumerate(IHBAR_SORUSU["options"]))
            random.shuffle(secenekler)
            yeni_dogru = None
            view_options = []
            
            for index, (orj_idx, text) in enumerate(secenekler):
                view_options.append(text)
                if orj_idx == IHBAR_SORUSU["ans"]:
                    yeni_dogru = index
                    
            view = IhbarView(user_id=interaction.user.id, options=view_options, correct_ans=yeni_dogru)
            
            ihbar_embed = discord.Embed(title="🚨 POLİS BASKINI!", color=discord.Color.red())
            ihbar_embed.description = f"Hatalar yaptın ve polis kokuyu aldı! Kapı kırılmak üzere!\nKaçmak için son bir şansın var. 15 saniyen başladı!\n\n**{IHBAR_SORUSU['q']}**"
            
            await interaction.edit_original_response(content=None, embed=ihbar_embed, view=view)
            await view.wait()
            
            if view.result:
                # Başarılı kaçış
                aranan_rol = interaction.guild.get_role(ARANAN_ROL_ID)
                if aranan_rol:
                    try:
                        await interaction.user.add_roles(aranan_rol, reason="Meth üretiminden kaçtı")
                    except:
                        pass
                
                # Arananlar kanalına mesaj
                kanal = interaction.guild.get_channel(ARANANLAR_KANAL_ID)
                if kanal:
                    duyuru = discord.Embed(title="⚠️ YENİ ARANAN ŞAHIS", color=discord.Color.dark_red())
                    duyuru.description = f"🚨 **ŞÜPHELİ:** {interaction.user.mention}\n📜 **SUÇ:** Yasadışı kimyasal üretim ve polisten kaçış.\n\nBu şahsı görenlerin derhal yetkililere bildirmesi rica olunur!"
                    duyuru.set_thumbnail(url=interaction.user.display_avatar.url)
                    await kanal.send(embed=duyuru)
                
                await interaction.edit_original_response(content="🏃‍♂️ Kıl payı kaçtın ama artık **En Çok Aranan** listesindesin. DM kutunu kontrol et.", embed=None, view=None)
                try:
                    await interaction.user.send("🏃‍♂️ Polislerden kurtuldun ancak artık tüm şehir seni arıyor. Başarısız olduğun için para kazanamadın.")
                except:
                    pass
            else:
                # Yakalandı veya öldü
                olu_rol = interaction.guild.get_role(OLU_ROL_ID)
                if olu_rol:
                    try:
                        # Varsa aranan rolünü al
                        aranan_rol = interaction.guild.get_role(ARANAN_ROL_ID)
                        if aranan_rol and aranan_rol in interaction.user.roles:
                            await interaction.user.remove_roles(aranan_rol)
                            
                        await interaction.user.add_roles(olu_rol, reason="Polis baskınında yakalandı/öldü")
                    except:
                        pass
                
                await interaction.edit_original_response(content="☠️ Hatalı hamle! Polis seni kıskıvrak yakaladı. Artık **ÖLÜ/MAHKUM** statüsündesin.", embed=None, view=None)

async def setup(bot):
    await bot.add_cog(MethUretimi(bot))
