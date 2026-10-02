import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import random
from datetime import datetime, timedelta
from utils.storage import load_json, save_json_atomic as save_json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, "data", "cete_data.json")
PENDING_FILE = os.path.join(BASE_DIR, "data", "cete_pending.json")
COLORS_FILE = os.path.join(BASE_DIR, "data", "colors.json")

BOSS_ROLE_ID = 1551552841716334592
UNDERBOSS_ROLE_ID = 1551553107492601876
INFAZ_ROLE_ID = 1544777693030125720
LOG_CHANNEL_ID = 1551547117024190474
BOT_KOMUT_CHANNEL_ID = 1544809399296589885
CETE_BILDIRIM_CHANNEL_ID = 1551964863725838346
GANG_PANEL_CHANNEL_ID = 1551345902868889671
ADMIN_GANG_PANEL_CHANNEL_ID = 1551996894597750897
GANG_WARNING_CHANNEL_ID = 1551369739878539364

VALID_PARSELLER = ["700", "701", "702", "703", "1104", "1108", "1101", "601", "602", "600", "805", "807", "809", "1003", "1004", "1005", "1006", "1007", "1008", "1009", "403", "404", "405", "406", "407", "409", "410", "411"]


COOLDOWNS_FILE = os.path.join(BASE_DIR, "data", "cete_cooldowns.json")
JOIN_REQUESTS_FILE = os.path.join(BASE_DIR, "data", "cete_join_requests.json")
DETAILED_LOG_CHANNEL_ID = 1554830631408504842
DETAILED_LOG_MENTION = "<@&1551546608305573989> | <@&1551545853141983232>"

def is_user_on_cooldown(user_id):
    cooldowns = load_json(COOLDOWNS_FILE)
    uid = str(user_id)
    if uid in cooldowns:
        cooldown_time = datetime.fromisoformat(cooldowns[uid])
        if datetime.utcnow() < cooldown_time:
            return True
        else:
            del cooldowns[uid]
            save_json(COOLDOWNS_FILE, cooldowns)
    return False
    
def set_cooldown(user_id):
    cooldowns = load_json(COOLDOWNS_FILE)
    cooldowns[str(user_id)] = (datetime.utcnow() + timedelta(days=7)).isoformat()
    save_json(COOLDOWNS_FILE, cooldowns)

async def send_detailed_log(bot, action_text, color=discord.Color.blue(), cete_id=None):
    channel = bot.get_channel(DETAILED_LOG_CHANNEL_ID)
    if not channel:
        return
    embed = discord.Embed(title="Çete Log", description=action_text, color=color, timestamp=datetime.utcnow())
    try:
        msg = await channel.send(content=DETAILED_LOG_MENTION, embed=embed)
        if cete_id:
            cete_data = load_json(DATA_FILE)
            if cete_id in cete_data:
                if "log_msg_ids" not in cete_data[cete_id]:
                    cete_data[cete_id]["log_msg_ids"] = []
                cete_data[cete_id]["log_msg_ids"].append(str(msg.id))
                save_json(DATA_FILE, cete_data)

    except:
        pass

async def get_or_fetch_channel(client_or_guild, channel_id: int):
    if not channel_id:
        return None
    ch = client_or_guild.get_channel(channel_id)
    if ch:
        return ch
    try:
        return await client_or_guild.fetch_channel(channel_id)
    except Exception:
        return None

def hex_to_discord_color(hex_str):
    hex_str = hex_str.strip().lstrip('#')
    return discord.Color(int(hex_str, 16))

def is_user_in_any_gang(user_id):
    cete_data = load_json(DATA_FILE)
    uid = str(user_id)
    for cete_id, cete in cete_data.items():
        if str(cete["boss"]) == uid or uid in cete.get("underbosses", []) or uid in cete.get("members", []):
            return True
    return False

# --- GANG CREATION VIEWS & MODALS ---

class AdminRejectModal(discord.ui.Modal, title="Çete Reddetme Sebebi"):
    sebep = discord.ui.TextInput(
        label="Reddedilme Sebebi",
        style=discord.TextStyle.paragraph,
        placeholder="Neden reddedildiğini yazınız...",
        required=True
    )

    def __init__(self, request_id: str):
        super().__init__()
        self.request_id = request_id

    async def on_submit(self, interaction: discord.Interaction):
        pending = load_json(PENDING_FILE)
        if self.request_id not in pending:
            return await interaction.response.send_message("Talebin süresi dolmuş veya zaten işlem yapılmış.", ephemeral=True)
        
        req = pending[self.request_id]
        boss_id = req["boss"]
        
        # Log mesajını güncelle
        try:
            log_channel = interaction.client.get_channel(LOG_CHANNEL_ID)
            msg = await log_channel.fetch_message(req["log_msg_id"])
            embed = msg.embeds[0]
            embed.color = discord.Color.red()
            embed.title = f"❌ REDDEDİLDİ: {req['name']}"
            embed.add_field(name="Reddeden Yetkili", value=interaction.user.mention, inline=False)
            embed.add_field(name="Sebep", value=self.sebep.value, inline=False)
            await msg.edit(embed=embed, view=None)
        except:
            pass

        # Boss'a bildir
        try:
            komut_kanal = interaction.client.get_channel(CETE_BILDIRIM_CHANNEL_ID)
            await komut_kanal.send(f"❌ <@{boss_id}>, **{req['name']}** adlı çete kurma talebiniz yetkililer tarafından reddedildi.\n**Sebep:** {self.sebep.value}")
        except:
            pass

        del pending[self.request_id]
        save_json(PENDING_FILE, pending)
        await interaction.response.send_message("Talep başarıyla reddedildi.", ephemeral=True)


class AdminApprovalView(discord.ui.View):
    def __init__(self, request_id: str):
        super().__init__(timeout=None)
        self.request_id = request_id

    @discord.ui.button(label="Onayla", style=discord.ButtonStyle.green, custom_id="admin_gang_approve")
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if getattr(self, "processing", False):
            return await interaction.response.send_message("Şu anda işleniyor, lütfen bekleyin...", ephemeral=True)
        self.processing = True
        pending = load_json(PENDING_FILE)
        if self.request_id not in pending:
            return await interaction.response.send_message("Bu talep artık geçerli değil.", ephemeral=True)
        
        req = pending[self.request_id]
        boss_id = int(req["boss"])
        guild = interaction.guild
        
        # Kabul edenleri al
        accepted_members = []
        for uid_str, status in req["invited"].items():
            if status == "accepted":
                accepted_members.append(int(uid_str))
        
        await interaction.response.defer()

        # Kategori 48 kanal sınır kontrolü
        text_category = discord.utils.get(guild.categories, name="Çeteler Sınırsız Ticket")
        voice_category = discord.utils.get(guild.categories, name="Çete Ses kanalları")
        if (text_category and len(text_category.channels) >= 48) or (voice_category and len(voice_category.channels) >= 48):
            return await interaction.followup.send("❌ Kategori kanal kapasitesi sınırına (48 kanal) ulaşıldığı için yeni çete onaylanamaz!", ephemeral=True)

        # 1. Rolü Oluştur
        colors_data = load_json(COLORS_FILE)
        hex_color = "#ffffff"
        for c in colors_data:
            if str(c["ID"]) == str(req["color_id"]):
                hex_color = c["Hex (Web RGB)"]
                break
        
        new_role = await guild.create_role(
            name=req["name"],
            color=hex_to_discord_color(hex_color),
            reason="Çete sistemi otomatik kurulum"
        )
        
        boss_role = guild.get_role(BOSS_ROLE_ID)

        # 2. Üyelere Rolleri Ver
        members_to_add = [boss_id] + accepted_members
        for uid in members_to_add:
            member = guild.get_member(uid)
            if not member:
                # Üye sunucudan ayrılmış; atlıyoruz
                continue
            await member.add_roles(new_role)
            if uid == boss_id and boss_role:
                await member.add_roles(boss_role)
        
        # 3. Kategorileri Bul / Oluştur
        illegal_role = guild.get_role(1539249508314259567)
        base_cat_overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False)
        }
        if illegal_role:
            base_cat_overwrites[illegal_role] = discord.PermissionOverwrite(view_channel=True, send_messages=False, connect=False)
            
        text_category = discord.utils.get(guild.categories, name="Çeteler Sınırsız Ticket")
        if not text_category:
            text_category = await guild.create_category("Çeteler Sınırsız Ticket", overwrites=base_cat_overwrites)
            
        voice_category = discord.utils.get(guild.categories, name="Çete Ses kanalları")
        if not voice_category:
            voice_category = await guild.create_category("Çete Ses kanalları", overwrites=base_cat_overwrites)

        # İzinler
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            new_role: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True)
        }
        if illegal_role:
            overwrites[illegal_role] = discord.PermissionOverwrite(view_channel=True, send_messages=False, connect=False)

        # 4. Kanalları Oluştur
        text_channel_name = f"{req['name'].replace(' ', '-').lower()}_sınırsız_ticket"
        text_channel = await guild.create_text_channel(text_channel_name, category=text_category, overwrites=overwrites)
        
        freq_code = random.randint(100, 999)
        voice_channel_name = f"{req['name']} 📻{freq_code}"
        voice_channel = await guild.create_voice_channel(voice_channel_name, category=voice_category, overwrites=overwrites)

        # 5. Mesaj Gönder
        info_embed = discord.Embed(title=f"🛡️ {req['name']} Çetesi Kuruldu!", color=new_role.color)
        info_embed.add_field(name="Boss", value=f"<@{boss_id}>", inline=False)
        info_embed.add_field(name="Üyeler", value=" ".join([f"<@{u}>" for u in accepted_members]), inline=False)
        info_embed.add_field(name="Parsel", value=req["parsel"], inline=False)
        story_text = req["story"][:1021] + "..." if len(req["story"]) > 1024 else req["story"]
        info_embed.add_field(name="Hikaye", value=story_text, inline=False)
        info_embed.set_footer(text="Bu mesaj çeteye yeni üyeler eklendikçe güncellenecektir.")
        info_msg = await text_channel.send(embed=info_embed, view=GangJoinButtonView())

        # 6. JSON'a Kaydet
        cete_data = load_json(DATA_FILE)
        gang_id = str(new_role.id)
        cete_data[gang_id] = {
            "name": req["name"],
            "color_id": req["color_id"],
            "boss": str(boss_id),
            "underbosses": [],
            "members": [str(u) for u in accepted_members],
            "parsel": req["parsel"],
            "text_channel": str(text_channel.id),
            "voice_channel": str(voice_channel.id),
            "role_id": str(new_role.id),
            "info_msg_id": str(info_msg.id)
        }
        save_json(DATA_FILE, cete_data)
        await send_detailed_log(interaction.client, f"**{req['name']}** çetesi <@{boss_id}> önderliğinde kuruldu! Onaylayan: <@{interaction.user.id}>", discord.Color.green(), str(new_role.id))

        
        # 7. Log Mesajını Güncelle
        try:
            log_channel = guild.get_channel(LOG_CHANNEL_ID)
            msg = await log_channel.fetch_message(req["log_msg_id"])
            embed = msg.embeds[0]
            embed.color = discord.Color.green()
            embed.title = f"✅ ONAYLANDI: {req['name']}"
            embed.add_field(name="Onaylayan Yetkili", value=interaction.user.mention, inline=False)
            await msg.edit(embed=embed, view=None)
        except:
            pass

        del pending[self.request_id]
        save_json(PENDING_FILE, pending)

        komut_kanal = guild.get_channel(CETE_BILDIRIM_CHANNEL_ID)
        await komut_kanal.send(f"🎉 <@{boss_id}>, **{req['name']}** çeteniz başarıyla onaylandı ve kuruldu! Kanallarınıza göz atabilirsiniz.", delete_after=15)
        await update_admin_gang_panel(interaction.client)

    @discord.ui.button(label="Reddet", style=discord.ButtonStyle.red, custom_id="admin_gang_reject")
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminRejectModal(self.request_id))


class GangInviteView(discord.ui.View):
    def __init__(self, request_id: str, invited_user_id: str):
        super().__init__(timeout=None)
        self.request_id = request_id
        self.invited_user_id = str(invited_user_id)

    async def handle_response(self, interaction: discord.Interaction, accepted: bool):
        if str(interaction.user.id) != self.invited_user_id:
            return await interaction.response.send_message("Bu davet sizin için değil!", ephemeral=True)
            
        pending = load_json(PENDING_FILE)
        if self.request_id not in pending:
            return await interaction.response.send_message("Bu çete talebi artık geçerli değil (zaman aşımı veya onaylandı).", ephemeral=True)
            
        req = pending[self.request_id]
        if req["invited"].get(self.invited_user_id) != "pending":
            return await interaction.response.send_message("Bu davete zaten yanıt verdiniz.", ephemeral=True)
            
        req["invited"][self.invited_user_id] = "accepted" if accepted else "rejected"
        save_json(PENDING_FILE, pending)
        
        try:
            await interaction.message.delete()
        except:
            pass
        await interaction.response.send_message(f"Yanıtınız kaydedildi: {'✅ Kabul Edildi' if accepted else '❌ Reddedildi'}", ephemeral=True)
        
        await self.update_log_message(interaction, req)

    @discord.ui.button(label="Onaylıyorum", style=discord.ButtonStyle.green, custom_id="invite_accept")
    async def accept_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_response(interaction, True)

    @discord.ui.button(label="Onaylamıyorum", style=discord.ButtonStyle.red, custom_id="invite_reject")
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_response(interaction, False)

    async def update_log_message(self, interaction, req):
        accepted_count = sum(1 for status in req["invited"].values() if status == "accepted")
        rejected_count = sum(1 for status in req["invited"].values() if status == "rejected")
        total_invited = len(req["invited"])
        
        try:
            log_channel = interaction.client.get_channel(LOG_CHANNEL_ID)
            msg = await log_channel.fetch_message(req["log_msg_id"])
            
            embed = discord.Embed(title=f"Çete Başvurusu: {req['name']}", color=discord.Color.yellow())
            if accepted_count >= 3:
                embed.color = discord.Color.default() # Beyaz
            
            embed.add_field(name="Boss", value=f"<@{req['boss']}>", inline=False)
            embed.add_field(name="Çete Rengi (ID)", value=req['color_id'], inline=True)
            embed.add_field(name="Parsel", value=req['parsel'], inline=True)
            embed.add_field(name="Davet Edilen", value=str(total_invited), inline=True)
            embed.add_field(name="Onaylayan", value=str(accepted_count), inline=True)
            embed.add_field(name="Reddeden", value=str(rejected_count), inline=True)
            
            if accepted_count >= 3:
                embed.description = "✅ Yeterli onaya ulaşıldı. Yetkili onayı bekleniyor."
                view = AdminApprovalView(self.request_id)
                await msg.edit(embed=embed, view=view)
            elif (total_invited - rejected_count) < 3:
                # İptal et
                embed.color = discord.Color.red()
                embed.description = "❌ Yeterli kişi onaylamadığı için sistem tarafından otomatik reddedildi."
                await msg.edit(embed=embed, view=None)
                
                pending = load_json(PENDING_FILE)
                del pending[self.request_id]
                save_json(PENDING_FILE, pending)
                
                komut_kanal = interaction.client.get_channel(CETE_BILDIRIM_CHANNEL_ID)
                await komut_kanal.send(f"❌ <@{req['boss']}>, **{req['name']}** çeteniz için yeterli onay alınamadığından başvuru iptal edildi.")
            else:
                embed.description = "⏳ Üyelerin onayı bekleniyor..."
                await msg.edit(embed=embed)
        except Exception as e:
            print(f"Log message update error: {e}")

class GangMemberSelectView(discord.ui.View):
    def __init__(self, cete_adi, cete_rengi, parsel_kodu, hikaye):
        super().__init__(timeout=300)
        self.cete_adi = cete_adi
        self.cete_rengi = cete_rengi
        self.parsel_kodu = parsel_kodu
        self.hikaye = hikaye

    @discord.ui.select(cls=discord.ui.UserSelect, placeholder="Başlangıç Üyelerini Seç (En az 3)", min_values=3, max_values=15)
    async def select_members(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        unique_members = []
        for user in select.values:
            if user.id == interaction.user.id:
                return await interaction.response.send_message("❌ Kendinizi başlangıç üyesi olarak seçemezsiniz!", ephemeral=True)
            if user.bot:
                return await interaction.response.send_message("❌ Botları çetenize ekleyemezsiniz!", ephemeral=True)
            if is_user_in_any_gang(user.id):
                return await interaction.response.send_message(f"❌ Seçtiğiniz üyelerden biri (<@{user.id}>) zaten bir çetede!", ephemeral=True)
            if is_user_on_cooldown(user.id):
                return await interaction.response.send_message(f"❌ Seçtiğiniz üyelerden biri (<@{user.id}>) son 1 hafta içinde bir çeteden ayrılmış/atılmış!", ephemeral=True)
            unique_members.append(str(user.id))
            
        if len(unique_members) < 3:
            return await interaction.response.send_message("❌ Lütfen en az 3 geçerli kişi seçin.", ephemeral=True)
            
        request_id = str(interaction.id)
        pending_data = load_json(PENDING_FILE)
        
        log_channel = interaction.client.get_channel(LOG_CHANNEL_ID)
        if not log_channel:
            return await interaction.response.send_message("❌ Log kanalı bulunamadı. Lütfen yetkililere bildirin.", ephemeral=True)

        embed = discord.Embed(title=f"Çete Başvurusu: {self.cete_adi}", description="⏳ Üyelerin onayı bekleniyor...", color=discord.Color.yellow())
        embed.add_field(name="Boss", value=f"<@{interaction.user.id}>", inline=False)
        embed.add_field(name="Çete Rengi (ID)", value=self.cete_rengi, inline=True)
        embed.add_field(name="Parsel", value=self.parsel_kodu, inline=True)
        embed.add_field(name="Davet Edilen", value=str(len(unique_members)), inline=True)
        embed.add_field(name="Onaylayan", value="0", inline=True)
        embed.add_field(name="Reddeden", value="0", inline=True)
        
        log_msg = await log_channel.send(embed=embed)
        
        pending_data[request_id] = {
            "name": self.cete_adi,
            "color_id": self.cete_rengi,
            "parsel": self.parsel_kodu,
            "boss": str(interaction.user.id),
            "story": self.hikaye,
            "log_msg_id": log_msg.id,
            "invited": {uid: "pending" for uid in unique_members},
            "expires_at": (datetime.utcnow() + timedelta(hours=24)).isoformat()
        }
        save_json(PENDING_FILE, pending_data)
        
        bot_komut = interaction.client.get_channel(CETE_BILDIRIM_CHANNEL_ID)
        for uid in unique_members:
            view = GangInviteView(request_id, uid)
            await bot_komut.send(content=f"🔔 Merhaba <@{uid}>! **{self.cete_adi}** çetesi lideri <@{interaction.user.id}> sizi çetesine başlangıç üyesi olarak davet ediyor. Katılmayı kabul ediyor musunuz?", view=view)
            
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="✅ Başvuru süreci başlatıldı! Seçtiğiniz üyelere davetiyeler gönderildi.", view=self)


class GangCreateModal(discord.ui.Modal, title="Yeni Çete Oluştur"):
    cete_adi = discord.ui.TextInput(label="Çetenizin Adı", max_length=50, required=True)
    cete_rengi = discord.ui.TextInput(label="Çetenizin Rengi (Sayı ID giriniz)", max_length=5, placeholder="Örn: 27", required=True)
    parsel_kodu = discord.ui.TextInput(label="Çetenizin Parsel Kodu", max_length=10, placeholder="Örn: 700", required=True)
    hikaye = discord.ui.TextInput(label="Oluşma Hikayesi", style=discord.TextStyle.paragraph, placeholder="Kısa bir hikaye...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            if is_user_in_any_gang(interaction.user.id):
                return await interaction.response.send_message("❌ Zaten bir çetedesiniz veya başka bir çetenin boss'usunuz!", ephemeral=True)
            
            parsel = self.parsel_kodu.value.strip()
            if parsel not in VALID_PARSELLER:
                parsel_listesi = ", ".join(VALID_PARSELLER)
                return await interaction.response.send_message(f"❌ Geçersiz parsel kodu! Geçerli kodlar: {parsel_listesi}", ephemeral=True)
            
            colors_data = load_json(COLORS_FILE)
            valid_color = False
            user_input_color = self.cete_rengi.value.strip()
            try:
                normalized_color_id = str(int(user_input_color))
            except ValueError:
                normalized_color_id = user_input_color
                
            for c in colors_data:
                if str(c.get("ID", "")).strip() == normalized_color_id:
                    valid_color = True
                    user_input_color = normalized_color_id 
                    break
                    
            if not valid_color:
                return await interaction.response.send_message("❌ Geçersiz Renk ID girdiniz. Lütfen görseldeki numaralardan birini yazın.", ephemeral=True)

            view = GangMemberSelectView(
                cete_adi=self.cete_adi.value.strip(),
                cete_rengi=user_input_color,
                parsel_kodu=parsel,
                hikaye=self.hikaye.value.strip()
            )
            
            await interaction.response.send_message("Lütfen çetenizin başlangıç üyelerini (En az 3 kişi) aşağıdaki menüden seçiniz:", view=view, ephemeral=True)
        except Exception as e:
            import traceback
            print("GANG CREATE MODAL ERROR:", traceback.format_exc())
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(f"❌ Sistem Hatası: {e}", ephemeral=True)
                else:
                    await interaction.response.send_message(f"❌ Sistem Hatası: {e}", ephemeral=True)
            except Exception:
                pass
class GangPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Çete Oluştur", style=discord.ButtonStyle.primary, custom_id="gang_create_btn")
    async def create_gang(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GangCreateModal())

# --- GANG MEMBER ADD VIEWS ---

class NewMemberInviteView(discord.ui.View):
    def __init__(self, cete_id: str, cete_adi: str, boss_id: str, invited_user_id: str):
        super().__init__(timeout=None)
        self.cete_id = cete_id
        self.cete_adi = cete_adi
        self.boss_id = boss_id
        self.invited_user_id = str(invited_user_id)

    async def handle_response(self, interaction: discord.Interaction, accepted: bool):
        if str(interaction.user.id) != self.invited_user_id:
            return await interaction.response.send_message("Bu davet sizin için değil!", ephemeral=True)

        komut_kanal = interaction.client.get_channel(CETE_BILDIRIM_CHANNEL_ID)
        
        if not accepted:
            try:
                await interaction.message.delete()
            except:
                pass
            await interaction.response.send_message("Daveti reddettiniz.", ephemeral=True)
            await komut_kanal.send(f"❌ <@{self.boss_id}>, <@{self.invited_user_id}> çeteye davetinizi **reddetti**.")
            return

        # Kabul edildi
        cete_data = load_json(DATA_FILE)
        if self.cete_id not in cete_data:
            return await interaction.response.send_message("Çete artık mevcut değil.", ephemeral=True)

        if is_user_in_any_gang(self.invited_user_id):
            try:
                await interaction.message.delete()
            except:
                pass
            await interaction.response.send_message("Zaten bir çetedesiniz, davet iptal edildi.", ephemeral=True)
            return await komut_kanal.send(f"❌ <@{self.boss_id}>, <@{self.invited_user_id}> zaten bir çetede olduğu için eklenemedi.")

        cete = cete_data[self.cete_id]
        cete["members"].append(self.invited_user_id)
        save_json(DATA_FILE, cete_data)


        # Rol ver
        role = interaction.guild.get_role(int(cete["role_id"]))
        if role:
            await interaction.user.add_roles(role)

        await interaction.response.edit_message(content=f"{interaction.message.content}\n**Yanıtınız:** ✅ Kabul Edildi", view=self)
        await komut_kanal.send(f"🎉 <@{self.boss_id}>, <@{self.invited_user_id}> başarıyla **{self.cete_adi}** çetesine katıldı!")

        # Info mesajını güncelle
        try:
            text_channel = interaction.guild.get_channel(int(cete["text_channel"]))
            msg = await text_channel.fetch_message(int(cete["info_msg_id"]))
            embed = msg.embeds[0]
            
            # Üyeler field'ını bul ve güncelle
            for i, field in enumerate(embed.fields):
                if field.name == "Üyeler":
                    embed.set_field_at(i, name="Üyeler", value=" ".join([f"<@{u}>" for u in cete["members"]]), inline=False)
                    break
            await msg.edit(embed=embed)
        except:
            pass

    @discord.ui.button(label="Onaylıyorum", style=discord.ButtonStyle.green, custom_id="new_invite_accept")
    async def accept_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_response(interaction, True)

    @discord.ui.button(label="Onaylamıyorum", style=discord.ButtonStyle.red, custom_id="new_invite_reject")
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_response(interaction, False)


class UyeCikarView(discord.ui.View):
    def __init__(self, cete_id, target_member):
        super().__init__(timeout=300)
        self.cete_id = cete_id
        self.target_member = target_member
        
    async def remove_user_from_gang(self, interaction: discord.Interaction, infaz: bool):
        cete_data = load_json(DATA_FILE)
        if self.cete_id not in cete_data:
            return await interaction.response.send_message("❌ Çete bulunamadı.", ephemeral=True)
            
        cete = cete_data[self.cete_id]
        if str(self.target_member.id) not in cete["members"]:
            return await interaction.response.send_message("❌ Bu kişi çetede değil.", ephemeral=True)
            
        cete["members"].remove(str(self.target_member.id))
        if str(self.target_member.id) in cete.get("underbosses", []):
            cete["underbosses"].remove(str(self.target_member.id))
        save_json(DATA_FILE, cete_data)

        
        try:
            gang_role = interaction.guild.get_role(int(cete["role_id"]))
            if gang_role:
                await self.target_member.remove_roles(gang_role)
                
            underboss_role = interaction.guild.get_role(UNDERBOSS_ROLE_ID)
            if underboss_role:
                await self.target_member.remove_roles(underboss_role)
                
            if infaz:
                infaz_role = interaction.guild.get_role(INFAZ_ROLE_ID)
                if infaz_role:
                    await self.target_member.add_roles(infaz_role)
        except Exception as e:
            print("Rol düzenleme hatası:", e)
            
        try:
            text_channel = interaction.guild.get_channel(int(cete["text_channel"]))
            msg = await text_channel.fetch_message(int(cete["info_msg_id"]))
            embed = msg.embeds[0]
            for i, field in enumerate(embed.fields):
                if field.name == "Üyeler":
                    embed.set_field_at(i, name="Üyeler", value=" ".join([f"<@{u}>" for u in cete["members"]]), inline=False)
                    break
            await msg.edit(embed=embed)
        except:
            pass
            
        for child in self.children:
            child.disabled = True
        
        action_text = "İnfaz edildi!" if infaz else "Sokağa fırlatıldı!"
        await interaction.response.edit_message(content=f"✅ {self.target_member.mention} başarıyla {action_text}", view=self)

    @discord.ui.button(label="İnfaz Et", style=discord.ButtonStyle.danger)
    async def infaz_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.remove_user_from_gang(interaction, True)
        
    @discord.ui.button(label="Sokağa Fırlat", style=discord.ButtonStyle.secondary)
    async def sokak_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.remove_user_from_gang(interaction, False)

class AyrilmaView(discord.ui.View):
    def __init__(self, cete_id: str, target_member_id: int):
        super().__init__(timeout=86400)
        self.cete_id = cete_id
        self.target_member_id = target_member_id
        
    async def process_leave(self, interaction: discord.Interaction, infaz: bool):
        cete_data = load_json(DATA_FILE)
        if self.cete_id not in cete_data:
            return await interaction.response.send_message("❌ Çete artık mevcut değil.", ephemeral=True)
            
        cete = cete_data[self.cete_id]
        if str(interaction.user.id) != cete["boss"]:
            return await interaction.response.send_message("❌ Bu işlemi yalnızca çetenin Boss'u yapabilir!", ephemeral=True)
            
        if str(self.target_member_id) not in cete["members"]:
            return await interaction.response.send_message("❌ Bu kişi zaten çetede değil.", ephemeral=True)
            
        cete["members"].remove(str(self.target_member_id))
        set_cooldown(self.target_member_id)
        await send_detailed_log(interaction.client, f"<@{self.target_member_id}>, **{cete['name']}** çetesinden ayrıldı.", discord.Color.orange(), self.cete_id)
        if str(self.target_member_id) in cete.get("underbosses", []):
            cete["underbosses"].remove(str(self.target_member_id))
        save_json(DATA_FILE, cete_data)

        
        target_member = interaction.guild.get_member(self.target_member_id)
        if target_member:
            try:
                gang_role = interaction.guild.get_role(int(cete["role_id"]))
                if gang_role:
                    await target_member.remove_roles(gang_role)
                    
                underboss_role = interaction.guild.get_role(UNDERBOSS_ROLE_ID)
                if underboss_role:
                    await target_member.remove_roles(underboss_role)
                    
                if infaz:
                    infaz_role = interaction.guild.get_role(INFAZ_ROLE_ID)
                    if infaz_role:
                        await target_member.add_roles(infaz_role)
            except Exception as e:
                print("Rol düzenleme hatası:", e)
                
        try:
            text_channel = interaction.guild.get_channel(int(cete["text_channel"]))
            msg = await text_channel.fetch_message(int(cete["info_msg_id"]))
            embed = msg.embeds[0]
            for i, field in enumerate(embed.fields):
                if field.name == "Üyeler":
                    embed.set_field_at(i, name="Üyeler", value=" ".join([f"<@{u}>" for u in cete["members"]]), inline=False)
                    break
            await msg.edit(embed=embed)
        except:
            pass
            
        for child in self.children:
            child.disabled = True
            
        action_text = "İnfaz edildi!" if infaz else "Serbest bırakıldı!"
        await interaction.response.edit_message(content=f"{interaction.message.content}\n\n✅ İşlem tamamlandı: **{action_text}**", view=self)

    @discord.ui.button(label="İnfaz Et", emoji="🩸", style=discord.ButtonStyle.danger)
    async def infaz_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_leave(interaction, True)
        
    @discord.ui.button(label="Bırak Gitsin", emoji="🚪", style=discord.ButtonStyle.secondary)
    async def sokak_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_leave(interaction, False)
class WarningModal(discord.ui.Modal, title="Çete Uyarı Sebebi"):
    sebep = discord.ui.TextInput(
        label="Uyarı Sebebi",
        style=discord.TextStyle.paragraph,
        placeholder="Hangi kuralı ihlal ettiler?",
        required=True
    )

    def __init__(self, cete_id: str, cete_adi: str, cete_role_id: str):
        super().__init__()
        self.cete_id = cete_id
        self.cete_adi = cete_adi
        self.cete_role_id = cete_role_id

    async def on_submit(self, interaction: discord.Interaction):
        cete_data = load_json(DATA_FILE)
        if self.cete_id not in cete_data:
            return await interaction.response.send_message("❌ Çete artık mevcut değil.", ephemeral=True)
            
        cete = cete_data[self.cete_id]
        current_warnings = cete.get("warnings", 0) + 1
        cete["warnings"] = current_warnings
        save_json(DATA_FILE, cete_data)

        
        warning_channel = interaction.client.get_channel(GANG_WARNING_CHANNEL_ID)
        
        # Message format requested: "@[seçilen çetenin rolü] [yetkilinin yazdığı uyarı sebebi] kuralını toplu bir şekilde çiğnediği için **[Çete adı]** Çetesi [Uyarı kadamesi] almıştır."
        if warning_channel:
            msg = f"<@&{self.cete_role_id}>, **{self.sebep.value}** kuralını toplu bir şekilde çiğnediğiniz için **{self.cete_adi}** Çetesi {current_warnings}/3 uyarı kademesi almıştır."
            await warning_channel.send(msg)
            
        if current_warnings >= 3:
            # 3. uyarıyı aldı, çeteyi kapat.
            await close_gang_logic(interaction.guild, self.cete_id, cete_data)
            await interaction.response.send_message(f"✅ **{self.cete_adi}** çetesi 3. uyarısını aldığı için kapatıldı.", ephemeral=True)
        else:
            await interaction.response.send_message(f"✅ **{self.cete_adi}** çetesine {current_warnings}. uyarı verildi.", ephemeral=True)
            
        # Refresh the admin panel
        await update_admin_gang_panel(interaction.client)


async def close_gang_logic(guild, cete_id, cete_data):
    if cete_id not in cete_data:
        return
    cete = cete_data[cete_id]
    
    # Kanallari sil
    try:
        tc = guild.get_channel(int(cete["text_channel"]))
        if tc: await tc.delete()
    except: pass
    
    try:
        vc = guild.get_channel(int(cete["voice_channel"]))
        if vc: await vc.delete()
    except: pass
    
    # Rolu sil
    try:
        role = guild.get_role(int(cete["role_id"]))
        if role: await role.delete()
    except: pass
    
    # Boss / Underboss global rollerini temizle
    boss_role = guild.get_role(BOSS_ROLE_ID)
    underboss_role = guild.get_role(UNDERBOSS_ROLE_ID)
    
    if boss_role:
        try:
            b_member = guild.get_member(int(cete["boss"]))
            if b_member: await b_member.remove_roles(boss_role)
        except: pass
        
    if underboss_role:
        for ub_id in cete.get("underbosses", []):
            try:
                ub_member = guild.get_member(int(ub_id))
                if ub_member: await ub_member.remove_roles(underboss_role)
            except: pass
    
    # JSON'dan kaldir
    try:
        log_channel = guild.get_channel(DETAILED_LOG_CHANNEL_ID)
        if log_channel and "log_msg_ids" in cete:
            for msg_id in cete["log_msg_ids"]:
                try:
                    m = await log_channel.fetch_message(int(msg_id))
                    await m.delete()
                except: pass
    except: pass
    
    del cete_data[cete_id]
    save_json(DATA_FILE, cete_data)
    
    try:
        if log_channel:
            embed = discord.Embed(title="Çete Log", description=f"**{cete['name']}** çetesi kapatıldı/silindi ve tüm geçmiş logları temizlendi.", color=discord.Color.red(), timestamp=datetime.utcnow())
            await log_channel.send(content=DETAILED_LOG_MENTION, embed=embed)
    except: pass



class AdminGangPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
        cete_data = load_json(DATA_FILE)
        options = []
        for cid, c in list(cete_data.items())[:25]:
            warns = c.get('warnings', 0)
            options.append(discord.SelectOption(label=c['name'][:25], description=f"Boss: {c['boss']} | Uyarı: {warns}/3", value=cid))
            
        if not options:
            options.append(discord.SelectOption(label="Aktif çete yok", value="none"))
            
        self.select_menu = discord.ui.Select(placeholder="İşlem yapmak için bir çete seçin", min_values=1, max_values=1, options=options, custom_id="admin_gang_select")
        self.select_menu.callback = self.select_callback
        self.add_item(self.select_menu)
        
        self.selected_gang = None

    async def select_callback(self, interaction: discord.Interaction):
        if self.select_menu.values[0] == "none":
            return await interaction.response.send_message("❌ İşlem yapılabilecek aktif çete yok.", ephemeral=True)
            
        self.selected_gang = self.select_menu.values[0]
        await interaction.response.defer()

    @discord.ui.button(label="Çeteye Uyarı Ver", style=discord.ButtonStyle.danger, emoji="⚠️", custom_id="admin_gang_warn", row=1)
    async def warn_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_gang or self.selected_gang == "none":
            return await interaction.response.send_message("❌ Lütfen önce menüden bir çete seçin.", ephemeral=True)
            
        cete_data = load_json(DATA_FILE)
        if self.selected_gang not in cete_data:
            return await interaction.response.send_message("❌ Çete artık mevcut değil.", ephemeral=True)
            
        cete = cete_data[self.selected_gang]
        await interaction.response.send_modal(WarningModal(self.selected_gang, cete["name"], str(cete["role_id"])))

    @discord.ui.button(label="Çeteyi Kapat", style=discord.ButtonStyle.danger, emoji="🚫", custom_id="admin_gang_close", row=1)
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_gang or self.selected_gang == "none":
            return await interaction.response.send_message("❌ Lütfen önce menüden bir çete seçin.", ephemeral=True)
            
        cete_data = load_json(DATA_FILE)
        if self.selected_gang not in cete_data:
            return await interaction.response.send_message("❌ Çete artık mevcut değil.", ephemeral=True)
            
        cete_adi = cete_data[self.selected_gang]["name"]
        await close_gang_logic(interaction.guild, self.selected_gang, cete_data)
        
        await interaction.response.send_message(f"✅ **{cete_adi}** çetesi başarıyla kapatıldı! Kanalları ve rolleri silindi.", ephemeral=True)
        await update_admin_gang_panel(interaction.client)


async def update_admin_gang_panel(client):
    try:
        channel = client.get_channel(ADMIN_GANG_PANEL_CHANNEL_ID)
        if not channel:
            return
            
        # Clear old panel messages
        async for msg in channel.history(limit=10):
            if msg.author == client.user:
                await msg.delete()
                
        cete_data = load_json(DATA_FILE)
        
        embed = discord.Embed(title="🛡️ Yetkili Çete Yönetim Paneli", description="Aşağıdaki menüden bir çete seçerek işlem yapabilirsiniz.", color=discord.Color.dark_red())
        
        if cete_data:
            cete_list = ""
            for cid, c in cete_data.items():
                warns = c.get('warnings', 0)
                cete_list += f"**{c['name']}**\nBoss: <@{c['boss']}> | Parsel: {c['parsel']} | Üye Sayısı: {len(c['members'])} | Uyarılar: {warns}/3\n\n"
            embed.add_field(name="Aktif Çeteler", value=cete_list[:1024], inline=False)
        else:
            embed.add_field(name="Aktif Çeteler", value="Şu anda aktif hiçbir çete bulunmuyor.", inline=False)
            
        await channel.send(embed=embed, view=AdminGangPanelView())
    except Exception as e:
        print(f"Update admin panel error: {e}")



class GangJoinRequestApproveView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Onayla", style=discord.ButtonStyle.green, custom_id="join_req_approve_btn")
    async def approve_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_req(interaction, True)
        
    @discord.ui.button(label="Reddet", style=discord.ButtonStyle.red, custom_id="join_req_reject_btn")
    async def reject_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_req(interaction, False)
        
    async def handle_req(self, interaction: discord.Interaction, approved: bool):
        msg_id = str(interaction.message.id)
        join_reqs = load_json(JOIN_REQUESTS_FILE)
        
        if msg_id not in join_reqs:
            return await interaction.response.send_message("Bu istek artık geçerli değil.", ephemeral=True)
            
        req = join_reqs[msg_id]
        if req["status"] != "pending":
            return await interaction.response.send_message("Bu istek zaten yanıtlanmış.", ephemeral=True)
            
        cete_id = req["cete_id"]
        user_id = req["user_id"]
        
        cete_data = load_json(DATA_FILE)
        if cete_id not in cete_data:
            return await interaction.response.send_message("Çete bulunamadı (silinmiş olabilir).", ephemeral=True)
            
        cete = cete_data[cete_id]
        boss_id = cete["boss"]
        underbosses = cete.get("underbosses", [])
        
        uid = str(interaction.user.id)
        if uid != boss_id and uid not in underbosses and not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Bunu sadece bu çetenin Boss'u veya Underboss'u yapabilir!", ephemeral=True)
            
        req["status"] = "approved" if approved else "rejected"
        save_json(JOIN_REQUESTS_FILE, join_reqs)
        
        target_member = interaction.guild.get_member(int(user_id))
        
        for child in self.children:
            child.disabled = True
            
        if approved:
            cete["members"].append(user_id)
            save_json(DATA_FILE, cete_data)

            
            role = interaction.guild.get_role(int(cete["role_id"]))
            if role and target_member:
                await target_member.add_roles(role)
                
            await interaction.response.edit_message(content=f"✅ <@{user_id}> kullanıcısının isteği <@{uid}> tarafından **ONAYLANDI**.", embed=interaction.message.embeds[0], view=self)
            
            try:
                text_channel = interaction.guild.get_channel(int(cete["text_channel"]))
                info_msg = await text_channel.fetch_message(int(cete["info_msg_id"]))
                embed = info_msg.embeds[0]
                for i, field in enumerate(embed.fields):
                    if field.name == "Üyeler":
                        embed.set_field_at(i, name="Üyeler", value=" ".join([f"<@{u}>" for u in cete["members"]]), inline=False)
                        break
                await info_msg.edit(embed=embed)
            except:
                pass
                
            await send_detailed_log(interaction.client, f"<@{user_id}>, **{cete['name']}** çetesine katıldı. Onaylayan: <@{uid}>", discord.Color.green(), cete_id)
        else:
            await interaction.response.edit_message(content=f"❌ <@{user_id}> kullanıcısının isteği <@{uid}> tarafından **REDDEDİLDİ**.", embed=interaction.message.embeds[0], view=self)
            bildirim_kanal = interaction.guild.get_channel(1551964863725838346)
            if bildirim_kanal:
                await bildirim_kanal.send(f"❌ <@{user_id}>, **{cete['name']}** çetesine katılım isteğiniz reddedildi.")
            
            await send_detailed_log(interaction.client, f"<@{user_id}> kullanıcısının **{cete['name']}** çetesine katılım isteği <@{uid}> tarafından reddedildi.", discord.Color.red(), cete_id)


class GangJoinButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Bu Çeteye Katıl", style=discord.ButtonStyle.blurple, custom_id="gang_join_btn")
    async def join_gang(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        if is_user_in_any_gang(user_id):
            return await interaction.response.send_message("❌ Zaten bir çetedesiniz veya başka bir çetenin boss'usunuz!", ephemeral=True)
            
        if is_user_on_cooldown(user_id):
            return await interaction.response.send_message("❌ Çeteden ayrıldıktan sonra yeni bir çeteye katılmak için 1 hafta beklemelisiniz!", ephemeral=True)
            
        cete_data = load_json(DATA_FILE)
        cete_id = None
        for cid, c in cete_data.items():
            if c.get("info_msg_id") == str(interaction.message.id):
                cete_id = cid
                break
                
        if not cete_id:
            return await interaction.response.send_message("❌ Çete bilgisi bulunamadı.", ephemeral=True)
            
        cete = cete_data[cete_id]
        cete_adi = cete["name"]
        
        join_reqs = load_json(JOIN_REQUESTS_FILE)
        for req_id, req in join_reqs.items():
            if req["user_id"] == user_id and req["cete_id"] == cete_id and req["status"] == "pending":
                return await interaction.response.send_message("❌ Bu çeteye zaten bir katılım isteği gönderdiniz. Onaylanmasını bekleyin.", ephemeral=True)
                
        await interaction.response.defer(ephemeral=True)
        
        bildirim_kanal = interaction.guild.get_channel(1551964863725838346)
        boss_id = cete["boss"]
        underbosses = cete.get("underbosses", [])
        
        tags = [f"<@{boss_id}>"] + [f"<@{u}>" for u in underbosses]
        tag_str = " ".join(tags)
        
        embed = discord.Embed(
            title="Yeni Çete Katılım İsteği",
            description=f"<@{user_id}> kullanıcısı **{cete_adi}** çetesine katılmak istiyor.",
            color=discord.Color.gold()
        )
        
        if bildirim_kanal:
            req_msg = await bildirim_kanal.send(content=tag_str, embed=embed, view=GangJoinRequestApproveView())
            
            join_reqs[str(req_msg.id)] = {
                "user_id": user_id,
                "cete_id": cete_id,
                "status": "pending"
            }
            save_json(JOIN_REQUESTS_FILE, join_reqs)
            
            await interaction.followup.send(f"✅ **{cete_adi}** çetesine katılma isteğiniz yetkililere iletildi.", ephemeral=True)
            await send_detailed_log(interaction.client, f"<@{user_id}>, **{cete_adi}** çetesine katılma isteği gönderdi.", discord.Color.gold(), cete_id)
        else:
            await interaction.followup.send("❌ Bildirim kanalı bulunamadı.", ephemeral=True)

class CeteSistemi(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        data_dir = os.path.join(BASE_DIR, "data")
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        if not os.path.exists(DATA_FILE):
            save_json(DATA_FILE, {})
        if not os.path.exists(PENDING_FILE):
            save_json(PENDING_FILE, {})
            
        if not os.path.exists(COLORS_FILE):
            default_colors = [
               {"ID":"0", "Description":"Metallic Black", "Hex (Web RGB)":"#0d1116"},
               {"ID":"1", "Description":"Metallic Graphite Black", "Hex (Web RGB)":"#1c1d21"},
               {"ID":"2", "Description":"Metallic Black Steal", "Hex (Web RGB)":"#32383d"},
               {"ID":"3", "Description":"Metallic Dark Silver", "Hex (Web RGB)":"#454b4f"},
               {"ID":"4", "Description":"Metallic Silver", "Hex (Web RGB)":"#999da0"},
               {"ID":"5", "Description":"Metallic Blue Silver", "Hex (Web RGB)":"#c2c4c6"},
               {"ID":"6", "Description":"Metallic Steel Gray", "Hex (Web RGB)":"#979a97"},
               {"ID":"7", "Description":"Metallic Shadow Silver", "Hex (Web RGB)":"#637380"},
               {"ID":"8", "Description":"Metallic Stone Silver", "Hex (Web RGB)":"#63625c"},
               {"ID":"9", "Description":"Metallic Midnight Silver", "Hex (Web RGB)":"#3c3f47"},
               {"ID":"10", "Description":"Metallic Gun Metal", "Hex (Web RGB)":"#444e54"},
               {"ID":"11", "Description":"Metallic Anthracite Grey", "Hex (Web RGB)":"#1d2129"},
               {"ID":"12", "Description":"Matte Black", "Hex (Web RGB)":"#13181f"},
               {"ID":"13", "Description":"Matte Gray", "Hex (Web RGB)":"#26282a"},
               {"ID":"14", "Description":"Matte Light Grey", "Hex (Web RGB)":"#515554"},
               {"ID":"15", "Description":"Util Black", "Hex (Web RGB)":"#151921"},
               {"ID":"16", "Description":"Util Black Poly", "Hex (Web RGB)":"#1e2429"},
               {"ID":"17", "Description":"Util Dark silver", "Hex (Web RGB)":"#333a3c"},
               {"ID":"18", "Description":"Util Silver", "Hex (Web RGB)":"#8c9095"},
               {"ID":"19", "Description":"Util Gun Metal", "Hex (Web RGB)":"#39434d"},
               {"ID":"20", "Description":"Util Shadow Silver", "Hex (Web RGB)":"#506272"},
               {"ID":"21", "Description":"Worn Black", "Hex (Web RGB)":"#1e232f"},
               {"ID":"22", "Description":"Worn Graphite", "Hex (Web RGB)":"#363a3f"},
               {"ID":"23", "Description":"Worn Silver Grey", "Hex (Web RGB)":"#a0a199"},
               {"ID":"24", "Description":"Worn Silver", "Hex (Web RGB)":"#d3d3d3"},
               {"ID":"25", "Description":"Worn Blue Silver", "Hex (Web RGB)":"#b7bfca"},
               {"ID":"26", "Description":"Worn Shadow Silver", "Hex (Web RGB)":"#778794"},
               {"ID":"27", "Description":"Metallic Red", "Hex (Web RGB)":"#c00e1a"},
               {"ID":"28", "Description":"Metallic Torino Red", "Hex (Web RGB)":"#da1918"},
               {"ID":"29", "Description":"Metallic Formula Red", "Hex (Web RGB)":"#b6111b"},
               {"ID":"30", "Description":"Metallic Blaze Red", "Hex (Web RGB)":"#a51e23"},
               {"ID":"31", "Description":"Metallic Graceful Red", "Hex (Web RGB)":"#7b1a22"},
               {"ID":"32", "Description":"Metallic Garnet Red", "Hex (Web RGB)":"#8e1b1f"},
               {"ID":"33", "Description":"Metallic Desert Red", "Hex (Web RGB)":"#6f1818"},
               {"ID":"34", "Description":"Metallic Cabernet Red", "Hex (Web RGB)":"#49111d"},
               {"ID":"35", "Description":"Metallic Candy Red", "Hex (Web RGB)":"#b60f25"},
               {"ID":"36", "Description":"Metallic Sunrise Orange", "Hex (Web RGB)":"#d44a17"},
               {"ID":"37", "Description":"Metallic Classic Gold", "Hex (Web RGB)":"#c2944f"},
               {"ID":"38", "Description":"Metallic Orange", "Hex (Web RGB)":"#f78616"},
               {"ID":"39", "Description":"Matte Red", "Hex (Web RGB)":"#cf1f21"},
               {"ID":"40", "Description":"Matte Dark Red", "Hex (Web RGB)":"#732021"},
               {"ID":"41", "Description":"Matte Orange", "Hex (Web RGB)":"#f27d20"},
               {"ID":"42", "Description":"Matte Yellow", "Hex (Web RGB)":"#ffc91f"},
               {"ID":"43", "Description":"Util Red", "Hex (Web RGB)":"#9c1016"},
               {"ID":"44", "Description":"Util Bright Red", "Hex (Web RGB)":"#de0f18"},
               {"ID":"45", "Description":"Util Garnet Red", "Hex (Web RGB)":"#8f1e17"},
               {"ID":"46", "Description":"Worn Red", "Hex (Web RGB)":"#a94744"},
               {"ID":"47", "Description":"Worn Golden Red", "Hex (Web RGB)":"#b16c51"},
               {"ID":"48", "Description":"Worn Dark Red", "Hex (Web RGB)":"#371c25"},
               {"ID":"49", "Description":"Metallic Dark Green", "Hex (Web RGB)":"#132428"},
               {"ID":"50", "Description":"Metallic Racing Green", "Hex (Web RGB)":"#122e2b"},
               {"ID":"51", "Description":"Metallic Sea Green", "Hex (Web RGB)":"#12383c"},
               {"ID":"52", "Description":"Metallic Olive Green", "Hex (Web RGB)":"#31423f"},
               {"ID":"53", "Description":"Metallic Green", "Hex (Web RGB)":"#155c2d"},
               {"ID":"54", "Description":"Metallic Gasoline Blue Green", "Hex (Web RGB)":"#1b6770"},
               {"ID":"55", "Description":"Matte Lime Green", "Hex (Web RGB)":"#66b81f"},
               {"ID":"56", "Description":"Util Dark Green", "Hex (Web RGB)":"#22383e"},
               {"ID":"57", "Description":"Util Green", "Hex (Web RGB)":"#1d5a3f"},
               {"ID":"58", "Description":"Worn Dark Green", "Hex (Web RGB)":"#2d423f"},
               {"ID":"59", "Description":"Worn Green", "Hex (Web RGB)":"#45594b"},
               {"ID":"60", "Description":"Worn Sea Wash", "Hex (Web RGB)":"#65867f"},
               {"ID":"61", "Description":"Metallic Midnight Blue", "Hex (Web RGB)":"#222e46"},
               {"ID":"62", "Description":"Metallic Dark Blue", "Hex (Web RGB)":"#233155"},
               {"ID":"63", "Description":"Metallic Saxony Blue", "Hex (Web RGB)":"#304c7e"},
               {"ID":"64", "Description":"Metallic Blue", "Hex (Web RGB)":"#47578f"},
               {"ID":"65", "Description":"Metallic Mariner Blue", "Hex (Web RGB)":"#637ba7"},
               {"ID":"66", "Description":"Metallic Harbor Blue", "Hex (Web RGB)":"#394762"},
               {"ID":"67", "Description":"Metallic Diamond Blue", "Hex (Web RGB)":"#d6e7f1"},
               {"ID":"68", "Description":"Metallic Surf Blue", "Hex (Web RGB)":"#76afbe"},
               {"ID":"69", "Description":"Metallic Nautical Blue", "Hex (Web RGB)":"#345e72"},
               {"ID":"70", "Description":"Metallic Bright Blue", "Hex (Web RGB)":"#0b9cf1"},
               {"ID":"71", "Description":"Metallic Purple Blue", "Hex (Web RGB)":"#2f2d52"},
               {"ID":"72", "Description":"Metallic Spinnaker Blue", "Hex (Web RGB)":"#282c4d"},
               {"ID":"73", "Description":"Metallic Ultra Blue", "Hex (Web RGB)":"#2354a1"},
               {"ID":"74", "Description":"Metallic Bright Blue", "Hex (Web RGB)":"#6ea3c6"},
               {"ID":"75", "Description":"Util Dark Blue", "Hex (Web RGB)":"#112552"},
               {"ID":"76", "Description":"Util Midnight Blue", "Hex (Web RGB)":"#1b203e"},
               {"ID":"77", "Description":"Util Blue", "Hex (Web RGB)":"#275190"},
               {"ID":"78", "Description":"Util Sea Foam Blue", "Hex (Web RGB)":"#608592"},
               {"ID":"79", "Description":"Util Lightning blue", "Hex (Web RGB)":"#2446a8"},
               {"ID":"80", "Description":"Util Maui Blue Poly", "Hex (Web RGB)":"#4271e1"},
               {"ID":"81", "Description":"Util Bright Blue", "Hex (Web RGB)":"#3b39e0"},
               {"ID":"82", "Description":"Matte Dark Blue", "Hex (Web RGB)":"#1f2852"},
               {"ID":"83", "Description":"Matte Blue", "Hex (Web RGB)":"#253aa7"},
               {"ID":"84", "Description":"Matte Midnight Blue", "Hex (Web RGB)":"#1c3551"},
               {"ID":"85", "Description":"Worn Dark blue", "Hex (Web RGB)":"#4c5f81"},
               {"ID":"86", "Description":"Worn Blue", "Hex (Web RGB)":"#58688e"},
               {"ID":"87", "Description":"Worn Light blue", "Hex (Web RGB)":"#74b5d8"},
               {"ID":"88", "Description":"Metallic Taxi Yellow", "Hex (Web RGB)":"#ffcf20"},
               {"ID":"89", "Description":"Metallic Race Yellow", "Hex (Web RGB)":"#fbe212"},
               {"ID":"90", "Description":"Metallic Bronze", "Hex (Web RGB)":"#916532"},
               {"ID":"91", "Description":"Metallic Yellow Bird", "Hex (Web RGB)":"#e0e13d"},
               {"ID":"92", "Description":"Metallic Lime", "Hex (Web RGB)":"#98d223"},
               {"ID":"93", "Description":"Metallic Champagne", "Hex (Web RGB)":"#9b8c78"},
               {"ID":"94", "Description":"Metallic Pueblo Beige", "Hex (Web RGB)":"#503218"},
               {"ID":"95", "Description":"Metallic Dark Ivory", "Hex (Web RGB)":"#473f2b"},
               {"ID":"96", "Description":"Metallic Choco Brown", "Hex (Web RGB)":"#221b19"},
               {"ID":"97", "Description":"Metallic Golden Brown", "Hex (Web RGB)":"#653f23"},
               {"ID":"98", "Description":"Metallic Light Brown", "Hex (Web RGB)":"#775c3e"},
               {"ID":"99", "Description":"Metallic Straw Beige", "Hex (Web RGB)":"#ac9975"},
               {"ID":"100", "Description":"Metallic Moss Brown", "Hex (Web RGB)":"#6c6b4b"},
               {"ID":"101", "Description":"Metallic Biston Brown", "Hex (Web RGB)":"#402e2b"},
               {"ID":"102", "Description":"Metallic Beechwood", "Hex (Web RGB)":"#a4965f"},
               {"ID":"103", "Description":"Metallic Dark Beechwood", "Hex (Web RGB)":"#46231a"},
               {"ID":"104", "Description":"Metallic Choco Orange", "Hex (Web RGB)":"#752b19"},
               {"ID":"105", "Description":"Metallic Beach Sand", "Hex (Web RGB)":"#bfae7b"},
               {"ID":"106", "Description":"Metallic Sun Bleeched Sand", "Hex (Web RGB)":"#dfd5b2"},
               {"ID":"107", "Description":"Metallic Cream", "Hex (Web RGB)":"#f7edd5"},
               {"ID":"108", "Description":"Util Brown", "Hex (Web RGB)":"#3a2a1b"},
               {"ID":"109", "Description":"Util Medium Brown", "Hex (Web RGB)":"#785f33"},
               {"ID":"110", "Description":"Util Light Brown", "Hex (Web RGB)":"#b5a079"},
               {"ID":"111", "Description":"Metallic White", "Hex (Web RGB)":"#fffff6"},
               {"ID":"112", "Description":"Metallic Frost White", "Hex (Web RGB)":"#eaeaea"},
               {"ID":"113", "Description":"Worn Honey Beige", "Hex (Web RGB)":"#b0ab94"},
               {"ID":"114", "Description":"Worn Brown", "Hex (Web RGB)":"#453831"},
               {"ID":"115", "Description":"Worn Dark Brown", "Hex (Web RGB)":"#2a282b"},
               {"ID":"116", "Description":"Worn straw beige", "Hex (Web RGB)":"#726c57"},
               {"ID":"117", "Description":"Brushed Steel", "Hex (Web RGB)":"#6a747c"},
               {"ID":"118", "Description":"Brushed Black steel", "Hex (Web RGB)":"#354158"},
               {"ID":"119", "Description":"Brushed Aluminium", "Hex (Web RGB)":"#9ba0a8"},
               {"ID":"120", "Description":"Chrome", "Hex (Web RGB)":"#5870a1"},
               {"ID":"121", "Description":"Worn Off White", "Hex (Web RGB)":"#eae6de"},
               {"ID":"122", "Description":"Util Off White", "Hex (Web RGB)":"#dfddd0"},
               {"ID":"123", "Description":"Worn Orange", "Hex (Web RGB)":"#f2ad2e"},
               {"ID":"124", "Description":"Worn Light Orange", "Hex (Web RGB)":"#f9a458"},
               {"ID":"125", "Description":"Metallic Securicor Green", "Hex (Web RGB)":"#83c566"},
               {"ID":"126", "Description":"Worn Taxi Yellow", "Hex (Web RGB)":"#f1cc40"},
               {"ID":"127", "Description":"police car blue", "Hex (Web RGB)":"#4cc3da"},
               {"ID":"128", "Description":"Matte Green", "Hex (Web RGB)":"#4e6443"},
               {"ID":"129", "Description":"Matte Brown", "Hex (Web RGB)":"#bcac8f"},
               {"ID":"130", "Description":"Worn Orange", "Hex (Web RGB)":"#f8b658"},
               {"ID":"131", "Description":"Matte White", "Hex (Web RGB)":"#fcf9f1"},
               {"ID":"132", "Description":"Worn White", "Hex (Web RGB)":"#fffffb"},
               {"ID":"133", "Description":"Worn Olive Army Green", "Hex (Web RGB)":"#81844c"},
               {"ID":"134", "Description":"Pure White", "Hex (Web RGB)":"#ffffff"},
               {"ID":"135", "Description":"Hot Pink", "Hex (Web RGB)":"#f21f99"},
               {"ID":"136", "Description":"Salmon pink", "Hex (Web RGB)":"#fdd6cd"},
               {"ID":"137", "Description":"Metallic Vermillion Pink", "Hex (Web RGB)":"#df5891"},
               {"ID":"138", "Description":"Orange", "Hex (Web RGB)":"#f6ae20"},
               {"ID":"139", "Description":"Green", "Hex (Web RGB)":"#b0ee6e"},
               {"ID":"140", "Description":"Blue", "Hex (Web RGB)":"#08e9fa"},
               {"ID":"141", "Description":"Mettalic Black Blue", "Hex (Web RGB)":"#0a0c17"},
               {"ID":"142", "Description":"Metallic Black Purple", "Hex (Web RGB)":"#0c0d18"},
               {"ID":"143", "Description":"Metallic Black Red", "Hex (Web RGB)":"#0e0d14"},
               {"ID":"144", "Description":"hunter green", "Hex (Web RGB)":"#9f9e8a"},
               {"ID":"145", "Description":"Metallic Purple", "Hex (Web RGB)":"#621276"},
               {"ID":"146", "Description":"Metaillic V Dark Blue", "Hex (Web RGB)":"#0b1421"},
               {"ID":"147", "Description":"MODSHOP BLACK1", "Hex (Web RGB)":"#11141a"},
               {"ID":"148", "Description":"Matte Purple", "Hex (Web RGB)":"#6b1f7b"},
               {"ID":"149", "Description":"Matte Dark Purple", "Hex (Web RGB)":"#1e1d22"},
               {"ID":"150", "Description":"Metallic Lava Red", "Hex (Web RGB)":"#bc1917"},
               {"ID":"151", "Description":"Matte Forest Green", "Hex (Web RGB)":"#2d362a"},
               {"ID":"152", "Description":"Matte Olive Drab", "Hex (Web RGB)":"#696748"},
               {"ID":"153", "Description":"Matte Desert Brown", "Hex (Web RGB)":"#7a6c55"},
               {"ID":"154", "Description":"Matte Desert Tan", "Hex (Web RGB)":"#c3b492"},
               {"ID":"155", "Description":"Matte Foilage Green", "Hex (Web RGB)":"#5a6352"},
               {"ID":"156", "Description":"DEFAULT ALLOY COLOR", "Hex (Web RGB)":"#81827f"},
               {"ID":"157", "Description":"Epsilon Blue", "Hex (Web RGB)":"#afd6e4"},
               {"ID":"158", "Description":"Pure Gold", "Hex (Web RGB)":"#7a6440"},
               {"ID":"159", "Description":"Brushed Gold", "Hex (Web RGB)":"#7f6a48"}
            ]
            save_json(COLORS_FILE, default_colors)
        
        self.bot.add_view(GangPanelView())
        self.bot.add_view(GangJoinButtonView())
        self.bot.add_view(GangJoinRequestApproveView())
        

    @app_commands.command(name="cete-panel-kur", description="Çete oluşturma panelini bu kanala kurar.")
    @app_commands.default_permissions(administrator=True)
    async def cete_panel_kur(self, interaction: discord.Interaction):
        if not discord.utils.get(interaction.user.roles, id=1529546007635824680):
            return await interaction.response.send_message("❌ Bu komutu sadece **Kurucu** kullanabilir!", ephemeral=True)

        await interaction.response.send_message("Panel kuruluyor...", ephemeral=True)
        channel = interaction.channel
        
        embed = discord.Embed(
            title="ER:LC Piyadeleri Çete Sistemi",
            description=(
                "**Gerekçeler:**\n"
                "💠 Çete oluşturmak için en az 3 kişi olmanız gerekmektedir.\n"
                "💠 Çete açıldıktan sonra çete yardımları her ay başı yapılacaktır.\n"
                f"💠 Sadece Çete lideri (<@&{BOSS_ROLE_ID}>), (<@&{UNDERBOSS_ROLE_ID}>) seçebilir.\n"
                "💠 Çetenize ait bir renk seçmeniz gerekmektedir. (Sağ üstteki görsele bakarak numara seçebilirsiniz.)\n"
                "💠 Çetenizin kurulacağı parsel kodunu yazmanız gerekmektedir.\n"
                "💠 Çetenizin oluşma hikayesini kurgulamak zorundasınız.\n\n"
                "Aşağıdaki **Çete Oluştur** butonuna basarak başvuru anketini doldurabilirsiniz."
            ),
            color=discord.Color.dark_theme()
        )
        
        try:
            file1 = discord.File(os.path.join(BASE_DIR, "assets", "cete_logo_kucuk.jpg"), filename="kucuk.jpg")
            embed.set_thumbnail(url="attachment://kucuk.jpg")
            
            banner_file = os.path.join(BASE_DIR, "assets", "cete_banner.png")
            if not os.path.exists(banner_file):
                banner_file = os.path.join(BASE_DIR, "assets", "cete_banner.jpg")
            file2 = discord.File(banner_file, filename="banner.png")
            embed.set_image(url="attachment://banner.png")
            
            await channel.send(embed=embed, files=[file1, file2], view=GangPanelView())
        except Exception as e:
            await channel.send(embed=embed, view=GangPanelView())
            await interaction.followup.send(f"Görseller yüklenirken bir hata oluştu: {e}", ephemeral=True)

    @app_commands.command(name="underboss-ekle", description="Çetenize underboss eklersiniz (Sadece Boss kullanabilir).")
    @app_commands.describe(kisi="Underboss yapılacak kişi")
    async def underboss_ekle(self, interaction: discord.Interaction, kisi: discord.Member):
        cete_data = load_json(DATA_FILE)
        boss_uid = str(interaction.user.id)
        
        cete_id = None
        for cid, c in cete_data.items():
            if c["boss"] == boss_uid:
                cete_id = cid
                break
                
        if not cete_id:
            return await interaction.response.send_message("❌ Siz bir çete lideri (Boss) değilsiniz!", ephemeral=True)
            
        cete = cete_data[cete_id]
        if str(kisi.id) not in cete["members"]:
            return await interaction.response.send_message("❌ Seçtiğiniz kişi çetenizde bulunmuyor!", ephemeral=True)
            
        if len(cete.get("underbosses", [])) >= 2:
            return await interaction.response.send_message("❌ Çetenizde en fazla 2 adet Underboss bulunabilir!", ephemeral=True)
            
        if str(kisi.id) in cete.get("underbosses", []):
            return await interaction.response.send_message("❌ Bu kişi zaten Underboss!", ephemeral=True)
            
        # Role verme
        underboss_role = interaction.guild.get_role(UNDERBOSS_ROLE_ID)
        if underboss_role:
            await kisi.add_roles(underboss_role)
            
        cete_data[cete_id]["underbosses"].append(str(kisi.id))
        save_json(DATA_FILE, cete_data)

        
        await interaction.response.send_message(f"✅ Başarıyla {kisi.mention} kullanıcısı çetenizin Underboss'u yapıldı!")

    @app_commands.command(name="uye-ekle", description="Çetenize yeni üye davet edersiniz (Sadece Boss kullanabilir).")
    @app_commands.describe(kisi="Davet edilecek kişi")
    async def uye_ekle(self, interaction: discord.Interaction, kisi: discord.Member):
        cete_data = load_json(DATA_FILE)
        boss_uid = str(interaction.user.id)
        
        cete_id = None
        for cid, c in cete_data.items():
            if c["boss"] == boss_uid:
                cete_id = cid
                break
                
        if not cete_id:
            return await interaction.response.send_message("❌ Siz bir çete lideri (Boss) değilsiniz!", ephemeral=True)
            
        if is_user_in_any_gang(kisi.id):
            return await interaction.response.send_message("❌ Seçtiğiniz kişi zaten bir çetede bulunuyor!", ephemeral=True)
            
        cete = cete_data[cete_id]
        
        view = NewMemberInviteView(cete_id, cete["name"], boss_uid, str(kisi.id))
        bot_komut = interaction.client.get_channel(CETE_BILDIRIM_CHANNEL_ID)
        await bot_komut.send(content=f"🔔 Merhaba {kisi.mention}! **{cete['name']}** çetesi lideri {interaction.user.mention} sizi çetesine davet ediyor. Katılmayı kabul ediyor musunuz?", view=view)
        
        await interaction.response.send_message(f"✅ {kisi.mention} kişisine davetiye gönderildi! (Kanal: <#{CETE_BILDIRIM_CHANNEL_ID}>)", ephemeral=True)


    @app_commands.command(name="cete-panel-gonder", description="Yetkili çete yönetim panelini gönderir.")
    @app_commands.default_permissions(administrator=True)
    async def cete_panel_gonder(self, interaction: discord.Interaction):
        await interaction.response.send_message("Panel güncelleniyor...", ephemeral=True)
        await update_admin_gang_panel(interaction.client)

    @app_commands.command(name="uye-cikar", description="Çetenizden bir üyeyi atarsınız (En az 4 üye varken çalışır).")
    @app_commands.describe(kisi="Çıkarılacak kişi")
    async def uye_cikar(self, interaction: discord.Interaction, kisi: discord.Member):
        cete_data = load_json(DATA_FILE)
        boss_uid = str(interaction.user.id)
        
        cete_id = None
        for cid, c in cete_data.items():
            if c["boss"] == boss_uid:
                cete_id = cid
                break
                
        if not cete_id:
            return await interaction.response.send_message("❌ Siz bir çete lideri (Boss) değilsiniz!", ephemeral=True)
            
        cete = cete_data[cete_id]
        if str(kisi.id) not in cete["members"]:
            return await interaction.response.send_message("❌ Seçtiğiniz kişi çetenizde bulunmuyor!", ephemeral=True)
            
        if str(kisi.id) == boss_uid:
            return await interaction.response.send_message("❌ Kendinizi çeteden çıkaramazsınız!", ephemeral=True)
            
        if len(cete["members"]) <= 3:
            return await interaction.response.send_message("❌ Çeteden üye çıkarabilmek için çetenizde en az 4 kişi bulunmalıdır (3 kişi kuralı).", ephemeral=True)
            
        view = UyeCikarView(cete_id, kisi)
        await interaction.response.send_message(f"Kişiyi ({kisi.mention}) çeteden nasıl çıkarmak istersiniz?", view=view, ephemeral=True)

    @app_commands.command(name="ceteden-ayril", description="Bulunduğunuz çeteden ayrılma isteği gönderir.")
    async def ceteden_ayril(self, interaction: discord.Interaction):
        cete_data = load_json(DATA_FILE)
        user_uid = str(interaction.user.id)
        
        cete_id = None
        for cid, c in cete_data.items():
            if user_uid in c["members"]:
                cete_id = cid
                break
                
        if not cete_id:
            return await interaction.response.send_message("❌ Herhangi bir çeteye üye değilsiniz!", ephemeral=True)
            
        cete = cete_data[cete_id]
        
        if cete["boss"] == user_uid:
            return await interaction.response.send_message("❌ Boss olarak çeteden ayrılamazsınız! Çeteyi dağıtmak için yöneticilere başvurmalısınız.", ephemeral=True)
            
        if len(cete["members"]) <= 3:
            return await interaction.response.send_message("❌ Çeteniz şu an 3 kişi. Siz ayrılırsanız çete dağılacağı için doğrudan ayrılamazsınız, yetkililerle görüşün.", ephemeral=True)
            
        view = AyrilmaView(cete_id, interaction.user.id)
        bildirim_kanal = interaction.client.get_channel(CETE_BILDIRIM_CHANNEL_ID)
        
        if bildirim_kanal:
            await bildirim_kanal.send(
                content=f"🔔 <@{cete['boss']}>, {interaction.user.mention} çeteden ayrılmak istiyor. Bu kişi için nasıl bir yol izleyeceksiniz?",
                view=view
            )
            await interaction.response.send_message("✅ Ayrılma isteğiniz çete liderine bildirildi.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Bildirim kanalı bulunamadı.", ephemeral=True)
async def setup(bot):
    await bot.add_cog(CeteSistemi(bot))
