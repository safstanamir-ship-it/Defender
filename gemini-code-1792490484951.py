import discord
from discord import app_commands, ui
from discord.app_commands import Choice
from discord.ext import commands, tasks
import asyncio
import time
import re
import os
import json
import random
import sqlite3
from datetime import timedelta, datetime
from aiohttp import web
from collections import defaultdict


# ==========================================================
# 🖼️ 1. VISUAL CONSTANTS & URLS
# ==========================================================

BAN_HAMMER_URL = "https://i.imgur.com/r6R5mN1.png"
WHITELIST_ICON_URL = "https://i.imgur.com/vH9Z1Zb.png"

WELCOME_COLORS = [0x2ecc71, 0x3498db, 0x9b59b6, 0xe67e22, 0xe74c3c]
WELCOME_COLOR_NAMES = ["Green", "Blue", "Purple", "Orange", "Red"]

WHITELIST_CATEGORY_LABELS = {
    "CREATE_ROLES":    "Create Roles",
    "DELETE_ROLES":    "Delete Roles",
    "CREATE_CHANNELS": "Create Channels",
    "DELETE_CHANNELS": "Delete Channels",
    "BAN":             "Ban Members",
    "KICK":            "Kick Members",
    "MUTE":            "Mute Members",
    "ROLE_GRANT":      "Grant Roles",
}

LOGS_BUCKET_NAMES = {
    "WELCOME_LEAVE": "welcome-goodbye",
    "BANS_KICKS":    "bans-kicks",
    "MUTES":         "mutes",
    "AUTOMOD":       "automod",
    "ALERTS":        "alerts",
}

LOGS_CATEGORY_TO_BUCKET = {
    "MESSAGE_DELETE":    "AUTOMOD",
    "MESSAGE_EDIT":       "AUTOMOD",
    "MEMBER_JOIN_LEAVE": "WELCOME_LEAVE",
    "BANS":              "BANS_KICKS",
    "KICKS":             "BANS_KICKS",
    "MUTES":             "MUTES",
    "ROLE_CHANGES":      "AUTOMOD",
    "CHANNEL_CHANGES":   "AUTOMOD",
    "PERM_CHANGES":      "AUTOMOD",
    "ALERTS":            "ALERTS",
}


# ==========================================================
# 📂 2. SQLITE STORAGE PER GUILD
# ==========================================================

DB_PATH = "database.db"

DEFAULT_GUILD_CONFIG = {
    "CURRENT_LANG": "en",
    "EMBED_COLOR": 0x2b2d31,
    "LOG_CHANNEL_ID": None,
    "PANIC_MODE_ACTIVE": False,

    "LOGS_CONFIG": {
        "MODE": "manual",
        "CHANNEL_ID": None,
        "CHANNELS": {
            "WELCOME_LEAVE": None,
            "BANS_KICKS": None,
            "MUTES": None,
            "AUTOMOD": None,
            "ALERTS": None,
        },
        "MESSAGE_DELETE": True,
        "MESSAGE_EDIT": True,
        "MEMBER_JOIN_LEAVE": True,
        "BANS": True,
        "KICKS": True,
        "MUTES": True,
        "ROLE_CHANGES": True,
        "CHANNEL_CHANGES": True,
        "PERM_CHANGES": True,
        "ALERTS": True,
    },

    "VERIFY_CONFIG": {
        "ENABLED": False,
        "MODE": "button",
        "ROLE_ID": None,
        "CHANNEL_ID": None,
        "EMBED_COLOR": 0x5865F2,
        "TITLE": "🛡️ Verification",
        "DESCRIPTION": "Select a verification method to gain access to the server.",
        "EMOJI": "✅",
        "TIME_LIMIT_MINUTES": 10,
        "FAILURE_ACTION": "timeout"
    },
    "ANTITOKEN_CONFIG": {
        "ENABLED": True,
        "MAX_MESSAGES": 6,
        "WINDOW_SECONDS": 5,
        "TIMEOUT_MINUTES": 10,
        "CHALLENGE_SECONDS": 45
    },
    "TAG_ROLE_CONFIG": {
        "ENABLED": False,
        "TAG": "",
        "ROLE_ID": None
    },
    "AUTOROLE_CONFIG": {
        "ENABLED": False,
        "ROLE_ID": None
    },
    "WELCOME_CONFIG": {
        "ENABLED": True,
        "CHANNEL_ID": None,
        "USE_EMBED": True,
        "TEXT": "Welcome to the server, {member}! 🎉",
        "COLOR_INDEX": 0
    },
    "GOODBYE_CONFIG": {
        "ENABLED": False,
        "CHANNEL_ID": None,
        "USE_EMBED": True,
        "TEXT": "{member} has left the server.",
        "COLOR_INDEX": 4
    },

    "ANTIMASSMUTE_CONFIG": {
        "ENABLED": True,
        "TIME_WINDOW": 30,
        "MAX_MUTES": 3,
        "ANTIABUSE_EVERYONE": True
    },

    "AI_ACCOUNT_SCANNER": {
        "ENABLED": True,
        "MUTE_HOURS": 2,
        "BAN_ON_SUSPICIOUS_LINK": True
    },

    "AI_MEDIA_SCANNER": {
        "ENABLED": True,
        "AUTO_BAN": True
    },

    "ANTIRAID_CONFIG": {
        "ENABLED": True,
        "TIME_WINDOW": 30,
        "MAX_JOINS": 10,
        "PUNISHMENT": "timeout",
        "MUTE_HOURS": 2
    },

    "CONFIG": {
        "ENABLED": True,
        "PUNISHMENT": "kick",
        "TIME_WINDOW": 30,
        "MAX_BANS": 2,
        "MAX_KICKS": 3,
        "MAX_CHANNEL_DELETE": 3,
        "MAX_ROLE_DELETE": 3,
        "MAX_ROLE_CREATE": 3,
        "MAX_ROLE_UPDATE": 2,
        "MAX_ROLE_GRANT": 3,
        "MAX_WEBHOOK_CREATE": 3,
        "BLOCK_UNVERIFIED_BOTS": True
    },

    "SPAM_CONFIG": {
        "ENABLED": True,
        "MAX_MESSAGES": 5,
        "SPAM_WINDOW": 4,
        "PUNISHMENT": "timeout",
        "MUTE_MINUTES": 10,
        "ANTIPING": True
    },

    "ANTILINK_CONFIG": {
        "ENABLED": True,
        "MODE": "all",
        "CUSTOM_DOMAINS": ["discord.gg", "t.me"],
        "PUNISHMENT": "delete",
        "MUTE_MINUTES": 10
    },

    "ANTISPOTIFY_CONFIG": {
        "ENABLED": True,
        "PUNISHMENT": "delete",
        "MUTE_MINUTES": 10
    },

    "WHITELIST_USERS": [],
    "WHITELIST_CATEGORIES": {
        "CREATE_ROLES": [],
        "DELETE_ROLES": [],
        "CREATE_CHANNELS": [],
        "DELETE_CHANNELS": [],
        "BAN": [],
        "KICK": [],
        "MUTE": [],
        "ROLE_GRANT": []
    },
    "BLACKLISTED_BOTS": [],
    "WARN_ACTIONS": {
        "3": {"action": "mute",  "mute_minutes": 60},
        "5": {"action": "kick",  "mute_minutes": 0},
        "10": {"action": "ban",  "mute_minutes": 0}
    }
}

_config_cache: dict[int, dict] = {}
_warns_cache:  dict[int, dict] = {}

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guild_configs (
            guild_id INTEGER PRIMARY KEY,
            config TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS guild_warns (
            guild_id INTEGER PRIMARY KEY,
            warns TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def _deep_merge(base, extra):
    result = dict(base)
    for key, value in extra.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result

def get_cfg(guild_id: int) -> dict:
    if guild_id not in _config_cache:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT config FROM guild_configs WHERE guild_id = ?", (guild_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            try:
                loaded = json.loads(row[0])
                if not isinstance(loaded, dict):
                    loaded = {}
            except json.JSONDecodeError:
                loaded = {}
            _config_cache[guild_id] = _deep_merge(DEFAULT_GUILD_CONFIG, loaded)
        else:
            _config_cache[guild_id] = dict(DEFAULT_GUILD_CONFIG)
    return _config_cache[guild_id]

def get_warns(guild_id: int) -> dict:
    if guild_id not in _warns_cache:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT warns FROM guild_warns WHERE guild_id = ?", (guild_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            try:
                loaded = json.loads(row[0])
                if not isinstance(loaded, dict):
                    loaded = {}
            except json.JSONDecodeError:
                loaded = {}
            _warns_cache[guild_id] = loaded
        else:
            _warns_cache[guild_id] = {}
    return _warns_cache[guild_id]

async def save_cfg(guild_id: int):
    data = json.dumps(_config_cache.get(guild_id, DEFAULT_GUILD_CONFIG), ensure_ascii=False)
    def _save():
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO guild_configs (guild_id, config) VALUES (?, ?)", (guild_id, data))
        conn.commit()
        conn.close()
    await asyncio.to_thread(_save)

async def save_warns(guild_id: int):
    data = json.dumps(_warns_cache.get(guild_id, {}), ensure_ascii=False)
    def _save():
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO guild_warns (guild_id, warns) VALUES (?, ?)", (guild_id, data))
        conn.commit()
        conn.close()
    await asyncio.to_thread(_save)


# ==========================================================
# 🚀 3. BOT & INTENTS
# ==========================================================

TOKEN    = os.getenv("DISCORD_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
PORT     = int(os.getenv("PORT", 8080))

intents = discord.Intents.default()
intents.guilds          = True
intents.members         = True
intents.messages        = True
intents.message_content = True
intents.bans            = True
intents.presences       = True
intents.webhooks        = True

bot = commands.Bot(command_prefix="!", intents=intents)

joined_members_tracker: dict[int, list] = defaultdict(list)
message_rate_tracker: dict[tuple[int, int], list[float]] = defaultdict(list)
pending_challenges: dict[tuple[int, int], float] = {}

spam_tracker:    dict[int, list] = defaultdict(list)
actions_tracker: dict = defaultdict(lambda: defaultdict(list))


# ==========================================================
# 🛠️ 4. HELPER FUNCTIONS
# ==========================================================

def is_whitelisted(user_id: int, guild: discord.Guild, category: str | None = None) -> bool:
    if user_id == guild.owner_id or user_id == bot.user.id:
        return True
    if OWNER_ID and user_id == OWNER_ID:
        return True
    cfg = get_cfg(guild.id)
    if user_id in set(cfg.get("WHITELIST_USERS", [])):
        return True
    if category:
        cat_list = cfg.get("WHITELIST_CATEGORIES", {}).get(category, [])
        if user_id in set(cat_list):
            return True
    return False

def get_embed_color(guild_id: int) -> discord.Color:
    return discord.Color(get_cfg(guild_id).get("EMBED_COLOR", 0x2b2d31))

async def send_log(guild: discord.Guild, category: str, embed: discord.Embed, ping_admins: bool = False):
    cfg = get_cfg(guild.id)
    lc  = cfg.get("LOGS_CONFIG", {})
    if not lc.get(category, True):
        return
    if lc.get("MODE") == "auto":
        bucket = LOGS_CATEGORY_TO_BUCKET.get(category, "AUTOMOD")
        ch_id = lc.get("CHANNELS", {}).get(bucket)
    else:
        ch_id = lc.get("CHANNEL_ID")
    if not ch_id:
        return
    ch = guild.get_channel(ch_id)
    if not ch or not isinstance(ch, discord.TextChannel):
        return
    content = None
    if ping_admins:
        admins = [m for m in guild.members if m.guild_permissions.administrator and not m.bot]
        if admins:
            content = " ".join(m.mention for m in admins[:20])
    try:
        await ch.send(content=content, embed=embed)
    except discord.Forbidden:
        pass

async def send_dm(member, action: str, guild_name: str, reason: str):
    try:
        e = discord.Embed(
            title="⚡ Action Notice",
            color=discord.Color.gold(), timestamp=datetime.utcnow()
        )
        e.add_field(name="Server",   value=f"`{guild_name}`",  inline=True)
        e.add_field(name="Action",   value=f"`{action}`",      inline=True)
        e.add_field(name="Reason",   value=f"```\n{reason}\n```", inline=False)
        await member.send(embed=e)
    except discord.Forbidden:
        pass

async def notify_owner_protection(guild: discord.Guild, action: str, reason: str):
    owner = guild.owner
    if not owner:
        return
    e = discord.Embed(
        title="👑 Server Protection Activated",
        description="Suspicious activity was detected and automatic protection was applied.",
        color=discord.Color.gold(), timestamp=datetime.utcnow()
    )
    e.add_field(name="Server",        value=f"`{guild.name}`", inline=True)
    e.add_field(name="Action Taken",  value=f"`{action}`",     inline=True)
    e.add_field(name="Reason",        value=reason[:1024],     inline=False)
    try:
        await owner.send(embed=e)
    except discord.Forbidden:
        pass

def calculate_account_risk_score(member: discord.Member) -> int:
    score = 0
    age   = (datetime.utcnow() - member.created_at.replace(tzinfo=None)).days
    if age < 1:  score += 60
    elif age < 7: score += 35
    if member.avatar is None: score += 25
    un = member.name.lower()
    if re.search(r"^[a-z]+[0-9]{4,8}$", un) or len(set(un)) < 4: score += 20
    return score

def calculate_server_risk(guild: discord.Guild) -> tuple[int, int, int]:
    cfg    = get_cfg(guild.id)
    admins = sum(1 for m in guild.members if m.guild_permissions.administrator and not m.bot)
    danger = sum(1 for r in guild.roles if r.permissions.administrator or r.permissions.manage_guild
                 or r.permissions.ban_members or r.permissions.manage_channels)
    risk = 20
    if admins > 5: risk += 25
    if danger > 5: risk += 25
    if not cfg.get("CONFIG", {}).get("ENABLED"): risk += 15
    if not cfg.get("ANTIRAID_CONFIG", {}).get("ENABLED"): risk += 15
    return min(risk, 100), admins, danger

async def fake_ai_check(att: discord.Attachment) -> str:
    return "UNKNOWN"

async def antinuke_punish(guild: discord.Guild, user: discord.User, reason: str, force_kick: bool = False):
    cfg    = get_cfg(guild.id)
    p      = "kick" if force_kick else cfg.get("CONFIG", {}).get("PUNISHMENT", "kick").lower()
    member = guild.get_member(user.id)

    await send_dm(user, f"[Anti-Nuke] {p.upper()}", guild.name, reason)
    try:
        if p == "ban":
            await guild.ban(user, reason=f"[Anti-Nuke] {reason}")
        elif member:
            if p == "kick" or force_kick:
                await member.kick(reason=f"[Anti-Nuke: Crash Protection] {reason}")
            elif p in ("timeout", "mute"):
                await member.timeout(timedelta(hours=1), reason=f"[Anti-Nuke] {reason}")
    except (discord.Forbidden, discord.NotFound, discord.HTTPException) as exc:
        print(f"⚠️ Anti-nuke action failed: {exc}")

    await notify_owner_protection(guild, p.upper(), reason)

    log_e = discord.Embed(
        title="🚨 Anti-Nuke: Protection Triggered",
        description=f"**Violator:** {user.mention} (`{user.id}`)\n**Punishment:** `{p.upper()}`",
        color=discord.Color.red(), timestamp=datetime.utcnow()
    )
    log_e.add_field(name="Reason", value=f"```{reason}```", inline=False)
    await send_log(guild, "ALERTS", log_e, ping_admins=True)


def render_join_leave_message(guild: discord.Guild, member, kind: str):
    cfg = get_cfg(guild.id)
    wc  = cfg.get(f"{kind}_CONFIG", {})
    text = wc.get("TEXT", "")
    text = text.replace("{member}", member.mention).replace("{count}", str(guild.member_count))
    color = WELCOME_COLORS[wc.get("COLOR_INDEX", 0) % len(WELCOME_COLORS)]

    if wc.get("USE_EMBED", True):
        e = discord.Embed(description=text, color=color, timestamp=datetime.utcnow())
        e.set_footer(text=f"Members count: {guild.member_count}")
        try:
            e.set_thumbnail(url=member.display_avatar.url)
        except Exception:
            pass
        return None, e
    else:
        return f"{text}\n-# Members count: {guild.member_count}", None


# ==========================================================
# 🌐 5. WEB SERVER FOR RENDER / RAILWAY
# ==========================================================

async def handle_ping(request):
    return web.Response(text="OK - Bot Web Service Active", status=200)

async def handle_status(request):
    data = {
        "bot_name": str(bot.user),
        "guilds_count": len(bot.guilds),
        "latency_ms": round(bot.latency * 1000, 2),
        "status": "online",
        "timestamp": datetime.utcnow().isoformat()
    }
    return web.json_response(data)

async def start_web():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    app.router.add_get("/status", handle_status)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Web server started on port {PORT}")


# ==========================================================
# 🧹 6. CLEANUP TRACKERS
# ==========================================================

@tasks.loop(minutes=30)
async def cleanup_trackers():
    now = time.time()
    for guild_id in list(joined_members_tracker.keys()):
        joined_members_tracker[guild_id] = [
            item for item in joined_members_tracker[guild_id] if now - item[0] < 3600
        ]
    for key in list(spam_tracker.keys()):
        spam_tracker[key] = [t for t in spam_tracker[key] if now - t < 60]
    for uid in list(actions_tracker.keys()):
        for action in list(actions_tracker[uid].keys()):
            actions_tracker[uid][action] = [t for t in actions_tracker[uid][action] if now - t < 3600]


# ==========================================================
# 🌍 7. SETUP ON GUILD JOIN
# ==========================================================

class GuildJoinLangSelect(ui.Select):
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        options = [
            discord.SelectOption(label="English", value="en", emoji="🇬🇧", description="English language"),
            discord.SelectOption(label="Русский", value="ru", emoji="🇷🇺", description="Русский язык"),
            discord.SelectOption(label="العربية", value="ar", emoji="🇸🇦", description="Arabic language"),
            discord.SelectOption(label="Deutsch", value="de", emoji="🇩🇪", description="German language"),
            discord.SelectOption(label="Español", value="es", emoji="🇪🇸", description="Spanish language"),
            discord.SelectOption(label="Français", value="fr", emoji="🇫🇷", description="French language")
        ]
        super().__init__(placeholder="English", options=options, custom_id="join_lang_select")

    async def callback(self, interaction: discord.Interaction):
        cfg = get_cfg(interaction.guild.id)
        cfg["CURRENT_LANG"] = self.values[0]
        await save_cfg(interaction.guild.id)
        
        msgs = {
            "en": "Language set to English!",
            "ru": "Язык успешно изменён на Русский!",
            "ar": "تم تغيير اللغة بنجاح!",
            "de": "Sprache auf Deutsch geändert!",
            "es": "¡Idioma cambiado a Español!",
            "fr": "Langue changée en Français!"
        }
        await interaction.response.send_message(msgs.get(self.values[0], "Language updated!"), ephemeral=True)

class GuildJoinView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.add_item(GuildJoinLangSelect(guild_id))
        
        self.add_item(ui.Button(label="Support Server", url="https://discord.gg", emoji="🌐"))
        self.add_item(ui.Button(label="Vote", url="https://top.gg", emoji="💎"))
        self.add_item(ui.Button(label="Tutorial", url="https://youtube.com", emoji="⚙️"))

@bot.event
async def on_guild_join(guild: discord.Guild):
    cfg = get_cfg(guild.id)
    
    e = discord.Embed(
        title="🤝 Defender Setup",
        description=f"Thanks for adding Defender to **{guild.name}**!\n\n🌐 **Prefix:** `tp!`",
        color=get_embed_color(guild.id)
    )
    
    e.add_field(
        name="⚙️ Enabled by default",
        value=(
            "🟢 Webhook anti-spam protection (`/spam_config`)\n"
            "🟢 Warnings about unverified bots (`/antibot`)\n"
            "🟢 Anti-nuke protection (`/antinuke`)\n"
            "🟢 Anti-token protection (`/antitoken_config`)\n"
            "🟢 Anti-link protection (`/antilink_config`)\n"
            "🟢 Anti-spotify protection (`/antispotify_config`)"
        ),
        inline=False
    )
    
    e.add_field(
        name="🌐 Language",
        value=(
            "`/language` - open the language menu\n"
            "Supported languages: `العربية, Deutsch, English, Español, Français, Polski, Português, Русский, Українська`"
        ),
        inline=False
    )
    
    e.add_field(
        name="💡 Basic Commands",
        value=(
            "`/antinuke` · `/antiraid` · `/verify_setup` · `/logs_setup` · `/whitelist` · `/info`"
        ),
        inline=False
    )
    
    e.set_footer(text="Tip: run these commands to customize protection for your server.")

    candidates = [guild.system_channel] if guild.system_channel else []
    candidates += [c for c in guild.text_channels if c not in candidates]
    for channel in candidates:
        if channel and channel.permissions_for(guild.me).send_messages and channel.permissions_for(guild.me).embed_links:
            try:
                await channel.send(embed=e, view=GuildJoinView(guild.id))
                break
            except (discord.Forbidden, discord.HTTPException):
                continue

    owner = guild.owner
    if owner:
        dm_e = discord.Embed(
            title="👑 Thank you for using Defender Guard!",
            description=(
                f"Hello **{owner.name}**!\n\n"
                f"Thank you for inviting **Defender** to **{guild.name}**.\n\n"
                "⚠️ **CRITICAL STEP FOR MAXIMUM SECURITY:**\n"
                "Please go to your **Server Settings -> Roles** and **drag the Defender role higher than all other roles**!\n"
                "This ensures the bot has the authority to ban, kick, or timeout malicious administrators and raiding bots."
            ),
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )
        dm_e.set_thumbnail(url=bot.user.display_avatar.url if bot.user else None)
        try:
            await owner.send(embed=dm_e)
        except discord.Forbidden:
            pass


# ==========================================================
# 🛡️ 8. EVENTS & PROTECTIONS
# ==========================================================

@bot.event
async def on_webhooks_update(channel: discord.abc.GuildChannel):
    guild = channel.guild
    now = time.time()
    cfg = get_cfg(guild.id)
    if not cfg.get("CONFIG", {}).get("ENABLED", True):
        return
    try:
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_create):
            if entry.target and isinstance(entry.target, discord.Webhook):
                user = entry.user
                if not is_whitelisted(user.id, guild):
                    w  = cfg["CONFIG"].get("TIME_WINDOW", 30)
                    mx = cfg["CONFIG"].get("MAX_WEBHOOK_CREATE", 3)
                    actions_tracker[user.id]["webhooks"] = [t for t in actions_tracker[user.id]["webhooks"] if now - t < w]
                    actions_tracker[user.id]["webhooks"].append(now)
                    if len(actions_tracker[user.id]["webhooks"]) >= mx:
                        await antinuke_punish(guild, user, f"Mass webhook creation ({len(actions_tracker[user.id]['webhooks'])} in {w}s)")
            break
    except discord.Forbidden:
        pass

@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    guild = after.guild
    now   = time.time()
    cfg   = get_cfg(guild.id)

    am_cfg = cfg.get("ANTIMASSMUTE_CONFIG", {})
    if am_cfg.get("ENABLED", True):
        if before.timed_out_until != after.timed_out_until and after.timed_out_until is not None:
            try:
                async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.member_update):
                    if entry.target and entry.target.id == after.id:
                        admin = entry.user
                        if not is_whitelisted(admin.id, guild, "MUTE"):
                            w  = am_cfg.get("TIME_WINDOW", 30)
                            mx = am_cfg.get("MAX_MUTES", 3)
                            actions_tracker[admin.id]["mutes"] = [t for t in actions_tracker[admin.id]["mutes"] if now - t < w]
                            actions_tracker[admin.id]["mutes"].append(now)
                            if len(actions_tracker[admin.id]["mutes"]) >= mx:
                                member_obj = guild.get_member(admin.id)
                                if member_obj:
                                    try:
                                        await member_obj.timeout(timedelta(hours=1), reason="Anti-mass mute protection triggered")
                                        le = discord.Embed(title="🔇 Anti-Mass Mute Triggered",
                                                            description=f"{admin.mention} was restricted for mass muting users.",
                                                            color=discord.Color.dark_red(), timestamp=datetime.utcnow())
                                        await send_log(guild, "ALERTS", le, ping_admins=True)
                                    except discord.Forbidden:
                                        pass
                    break
            except discord.Forbidden:
                pass

    if cfg.get("CONFIG", {}).get("ENABLED", True) and len(after.roles) > len(before.roles):
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.member_role_update):
                if entry.target and entry.target.id == after.id:
                    admin = entry.user
                    if not is_whitelisted(admin.id, guild, "ROLE_GRANT"):
                        w  = cfg["CONFIG"].get("TIME_WINDOW", 30)
                        mx = cfg["CONFIG"].get("MAX_ROLE_GRANT", 3)
                        actions_tracker[admin.id]["role_grants"] = [t for t in actions_tracker[admin.id]["role_grants"] if now - t < w]
                        actions_tracker[admin.id]["role_grants"].append(now)
                        if len(actions_tracker[admin.id]["role_grants"]) >= mx:
                            await antinuke_punish(guild, admin, f"Mass role granting ({len(actions_tracker[admin.id]['role_grants'])} in {w}s)")
                break
        except discord.Forbidden:
            pass

@bot.event
async def on_message_delete(message: discord.Message):
    if not message.guild or message.author.bot:
        return
    e = discord.Embed(
        title="🗑️ Message Deleted",
        description=f"**Author:** {message.author.mention}\n**Channel:** {message.channel.mention}",
        color=discord.Color.orange(), timestamp=datetime.utcnow()
    )
    if message.content:
        e.add_field(name="Content", value=f"```\n{message.content[:1000]}\n```", inline=False)
    await send_log(message.guild, "MESSAGE_DELETE", e)

@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    if not before.guild or before.author.bot or before.content == after.content:
        return
    e = discord.Embed(
        title="✏️ Message Edited",
        description=f"**Author:** {before.author.mention}\n**Channel:** {before.channel.mention}\n[Jump to message]({after.jump_url})",
        color=discord.Color.blue(), timestamp=datetime.utcnow()
    )
    e.add_field(name="Before",  value=f"```\n{before.content[:500]}\n```", inline=False)
    e.add_field(name="After", value=f"```\n{after.content[:500]}\n```",  inline=False)
    await send_log(before.guild, "MESSAGE_EDIT", e)

@bot.event
async def on_member_remove(member: discord.Member):
    guild, now = member.guild, time.time()
    cfg = get_cfg(guild.id)
    if cfg.get("CONFIG", {}).get("ENABLED", True):
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
                et = entry.created_at.timestamp()
                if entry.target and entry.target.id == member.id and now - et < 5:
                    admin = entry.user
                    if not is_whitelisted(admin.id, guild, "KICK"):
                        w  = cfg["CONFIG"].get("TIME_WINDOW", 30)
                        mx = cfg["CONFIG"].get("MAX_KICKS", 3)
                        actions_tracker[admin.id]["kicks"] = [t for t in actions_tracker[admin.id]["kicks"] if now - t < w]
                        actions_tracker[admin.id]["kicks"].append(now)
                        if len(actions_tracker[admin.id]["kicks"]) >= mx:
                            await antinuke_punish(guild, admin, f"Mass kicks ({len(actions_tracker[admin.id]['kicks'])} in {w}s)")
                break
        except discord.Forbidden:
            pass

    e = discord.Embed(title="🚪 Member Left",
                      description=f"**User:** {member.mention} (`{member.id}`)",
                      color=discord.Color.red(), timestamp=datetime.utcnow())
    await send_log(guild, "MEMBER_JOIN_LEAVE", e)

    gc = cfg.get("GOODBYE_CONFIG", {})
    if gc.get("ENABLED") and gc.get("CHANNEL_ID"):
        ch = guild.get_channel(gc["CHANNEL_ID"])
        if ch:
            content, embed = render_join_leave_message(guild, member, "GOODBYE")
            try:
                await ch.send(content=content, embed=embed)
            except discord.Forbidden:
                pass

@bot.event
async def on_member_ban(guild: discord.Guild, user: discord.User):
    now = time.time()
    cfg = get_cfg(guild.id)
    if cfg.get("CONFIG", {}).get("ENABLED", True):
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
                et = entry.created_at.timestamp()
                if entry.target and entry.target.id == user.id and now - et < 5:
                    admin = entry.user
                    if not is_whitelisted(admin.id, guild, "BAN"):
                        w  = cfg["CONFIG"].get("TIME_WINDOW", 30)
                        mx = cfg["CONFIG"].get("MAX_BANS", 2)
                        actions_tracker[admin.id]["bans"] = [t for t in actions_tracker[admin.id]["bans"] if now - t < w]
                        actions_tracker[admin.id]["bans"].append(now)
                        if len(actions_tracker[admin.id]["bans"]) >= mx:
                            await antinuke_punish(guild, admin, f"Mass bans ({len(actions_tracker[admin.id]['bans'])} in {w}s)")
                break
        except discord.Forbidden:
            pass
    e = discord.Embed(title="🔨 Member Banned",
                      description=f"**User:** {user.mention} (`{user.id}`)",
                      color=discord.Color.dark_red(), timestamp=datetime.utcnow())
    await send_log(guild, "BANS", e)

@bot.event
async def on_guild_role_create(role: discord.Role):
    guild, now = role.guild, time.time()
    cfg = get_cfg(guild.id)
    if cfg.get("CONFIG", {}).get("ENABLED", True):
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.role_create):
                user = entry.user
                if not is_whitelisted(user.id, guild, "CREATE_ROLES"):
                    w  = cfg["CONFIG"].get("TIME_WINDOW", 30)
                    mx = cfg["CONFIG"].get("MAX_ROLE_CREATE", 3)
                    actions_tracker[user.id]["create_roles"] = [t for t in actions_tracker[user.id]["create_roles"] if now - t < w]
                    actions_tracker[user.id]["create_roles"].append(now)
                    if len(actions_tracker[user.id]["create_roles"]) >= mx:
                        await antinuke_punish(guild, user, f"Mass role creation ({len(actions_tracker[user.id]['create_roles'])} in {w}s)")
                break
        except discord.Forbidden:
            pass

@bot.event
async def on_guild_role_delete(role: discord.Role):
    guild, now = role.guild, time.time()
    cfg = get_cfg(guild.id)
    if cfg.get("CONFIG", {}).get("ENABLED", True):
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
                user = entry.user
                if not is_whitelisted(user.id, guild, "DELETE_ROLES"):
                    w  = cfg["CONFIG"].get("TIME_WINDOW", 30)
                    mx = cfg["CONFIG"].get("MAX_ROLE_DELETE", 3)
                    actions_tracker[user.id]["del_roles"] = [t for t in actions_tracker[user.id]["del_roles"] if now - t < w]
                    actions_tracker[user.id]["del_roles"].append(now)
                    if len(actions_tracker[user.id]["del_roles"]) >= mx:
                        await antinuke_punish(guild, user, f"Mass role deletion ({len(actions_tracker[user.id]['del_roles'])} in {w}s)")
                break
        except discord.Forbidden:
            pass

@bot.event
async def on_guild_role_update(before: discord.Role, after: discord.Role):
    guild, now = before.guild, time.time()
    cfg = get_cfg(guild.id)
    if cfg.get("CONFIG", {}).get("ENABLED", True):
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update):
                user = entry.user
                if not is_whitelisted(user.id, guild):
                    w  = cfg["CONFIG"].get("TIME_WINDOW", 30)
                    mx = cfg["CONFIG"].get("MAX_ROLE_UPDATE", 2)
                    actions_tracker[user.id]["update_roles"] = [t for t in actions_tracker[user.id]["update_roles"] if now - t < w]
                    actions_tracker[user.id]["update_roles"].append(now)
                    if len(actions_tracker[user.id]["update_roles"]) >= mx:
                        await antinuke_punish(guild, user, f"Frequent role updates ({len(actions_tracker[user.id]['update_roles'])} in {w}s)")
                break
        except discord.Forbidden:
            pass
    if before.permissions != after.permissions:
        e = discord.Embed(title="🔑 Role Permissions Changed",
                          description=f"**Role:** {after.mention}",
                          color=discord.Color.gold(), timestamp=datetime.utcnow())
        await send_log(guild, "PERM_CHANGES", e)
    else:
        e = discord.Embed(title="🎭 Role Updated",
                          description=f"**Role:** {after.mention}",
                          color=discord.Color.blue(), timestamp=datetime.utcnow())
        await send_log(guild, "ROLE_CHANGES", e)

@bot.event
async def on_guild_channel_delete(channel: discord.abc.GuildChannel):
    guild, now = channel.guild, time.time()
    cfg = get_cfg(guild.id)
    if cfg.get("CONFIG", {}).get("ENABLED", True):
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
                user = entry.user
                w = cfg["CONFIG"].get("TIME_WINDOW", 30)

                actions_tracker[user.id]["del_channels"] = [t for t in actions_tracker[user.id]["del_channels"] if now - t < w]
                actions_tracker[user.id]["del_channels"].append(now)
                del_count = len(actions_tracker[user.id]["del_channels"])

                if del_count > 3:
                    await antinuke_punish(
                        guild, user,
                        f"[Crash Protection] Critical channel deletion limit exceeded ({del_count} channels). Whitelist bypassed!",
                        force_kick=True
                    )
                elif not is_whitelisted(user.id, guild, "DELETE_CHANNELS"):
                    mx = cfg["CONFIG"].get("MAX_CHANNEL_DELETE", 3)
                    if del_count >= mx:
                        await antinuke_punish(guild, user, f"Mass channel deletion ({del_count} in {w}s)")
                break
        except discord.Forbidden:
            pass
    e = discord.Embed(title="📁 Channel Deleted",
                      description=f"**Name:** `{channel.name}` (`{channel.id}`)",
                      color=discord.Color.red(), timestamp=datetime.utcnow())
    await send_log(guild, "CHANNEL_CHANGES", e)

@bot.event
async def on_guild_channel_create(channel: discord.abc.GuildChannel):
    guild, now = channel.guild, time.time()
    cfg = get_cfg(guild.id)
    if cfg.get("CONFIG", {}).get("ENABLED", True):
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_create):
                user = entry.user
                if not is_whitelisted(user.id, guild, "CREATE_CHANNELS"):
                    w = cfg["CONFIG"].get("TIME_WINDOW", 30)
                    actions_tracker[user.id]["create_channels"] = [t for t in actions_tracker[user.id]["create_channels"] if now - t < w]
                    actions_tracker[user.id]["create_channels"].append(now)
                    if len(actions_tracker[user.id]["create_channels"]) >= 10:
                        await antinuke_punish(guild, user, f"Mass channel creation ({len(actions_tracker[user.id]['create_channels'])} in {w}s)")
                break
        except discord.Forbidden:
            pass

@bot.event
async def on_guild_update(before: discord.Guild, after: discord.Guild):
    cfg = get_cfg(after.id)
    if not cfg.get("CONFIG", {}).get("ENABLED", True):
        return
    if before.name == after.name and before.icon == after.icon:
        return
    try:
        async for entry in after.audit_logs(limit=1, action=discord.AuditLogAction.guild_update):
            if entry.user.id == bot.user.id:
                return
            if not is_whitelisted(entry.user.id, after):
                await antinuke_punish(after, entry.user, "Server settings or icon modified")
            break
    except discord.Forbidden:
        pass

@bot.event
async def on_member_join(member: discord.Member):
    guild, now = member.guild, time.time()
    cfg = get_cfg(guild.id)

    e = discord.Embed(title="📥 Member Joined",
                      description=f"**User:** {member.mention} (`{member.id}`)",
                      color=discord.Color.green(), timestamp=datetime.utcnow())
    await send_log(guild, "MEMBER_JOIN_LEAVE", e)

    blacklist = set(cfg.get("BLACKLISTED_BOTS", []))
    if member.bot:
        try:
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.bot_add):
                inviter = entry.user
                if member.id in blacklist:
                    try:
                        await member.ban(reason="[Blacklist] Malicious bot")
                    except discord.Forbidden:
                        pass
                    return
                if cfg["CONFIG"].get("BLOCK_UNVERIFIED_BOTS", True) and not is_whitelisted(inviter.id, guild):
                    try:
                        await member.ban(reason="[Anti-Bot] Unauthorized bot addition")
                    except discord.Forbidden:
                        pass
                    return
        except discord.Forbidden:
            pass

    ai = cfg.get("AI_ACCOUNT_SCANNER", {})
    if ai.get("ENABLED", True):
        rs = calculate_account_risk_score(member)
        if rs >= 50:
            mh = ai.get("MUTE_HOURS", 2)
            try:
                await member.timeout(timedelta(hours=mh), reason=f"[AI Guard] Account risk: {rs}")
                le = discord.Embed(
                    title="🤖 AI Guard: Suspicious Account",
                    description=f"**User:** {member.mention}\n**Risk:** `{rs}/100`\n**Timeout:** `{mh}`h.",
                    color=discord.Color.gold(), timestamp=datetime.utcnow()
                )
                await send_log(guild, "AUTOMOD", le)
            except discord.Forbidden:
                pass

    ar = cfg.get("AUTOROLE_CONFIG", {})
    if ar.get("ENABLED") and ar.get("ROLE_ID") and not member.bot:
        role = guild.get_role(ar["ROLE_ID"])
        if role:
            try:
                await member.add_roles(role, reason="Auto role on join")
            except discord.Forbidden:
                pass

    raid = cfg.get("ANTIRAID_CONFIG", {})
    if raid.get("ENABLED", True):
        rw = raid.get("TIME_WINDOW", 30)
        mx = raid.get("MAX_JOINS", 10)
        p  = raid.get("PUNISHMENT", "timeout").lower()
        mh = raid.get("MUTE_HOURS", 2)

        joined_members_tracker[guild.id] = [
            item for item in joined_members_tracker[guild.id] if now - item[0] < rw
        ]
        joined_members_tracker[guild.id].append((now, member))

        if len(joined_members_tracker[guild.id]) >= mx:
            for _, rm in list(joined_members_tracker[guild.id]):
                try:
                    if p == "ban":    await guild.ban(rm, reason="[Anti-Raid]")
                    elif p == "kick": await rm.kick(reason="[Anti-Raid]")
                    else:             await rm.timeout(timedelta(hours=mh), reason="[Anti-Raid]")
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
            le = discord.Embed(
                title="⚡ Anti-Raid: Protection Triggered",
                description=f"`{len(joined_members_tracker[guild.id])}` members joined in `{rw}`s. Applied: `{p.upper()}`",
                color=discord.Color.red(), timestamp=datetime.utcnow()
            )
            await send_log(guild, "ALERTS", le, ping_admins=True)
            await notify_owner_protection(guild, p.upper(), f"Raid detected: {len(joined_members_tracker[guild.id])} joins in {rw}s")

    wc = cfg.get("WELCOME_CONFIG", {})
    if wc.get("ENABLED") and wc.get("CHANNEL_ID"):
        ch = guild.get_channel(wc["CHANNEL_ID"])
        if ch:
            content, embed = render_join_leave_message(guild, member, "WELCOME")
            try:
                await ch.send(content=content, embed=embed)
            except discord.Forbidden:
                pass

@bot.event
async def on_presence_update(before: discord.Member, after: discord.Member):
    cfg = get_cfg(after.guild.id)
    sp  = cfg.get("ANTISPOTIFY_CONFIG", {})
    if not sp.get("ENABLED", False):
        return
    if is_whitelisted(after.id, after.guild):
        return
    try:
        for act in after.activities:
            if isinstance(act, discord.Spotify):
                p  = sp.get("PUNISHMENT", "delete")
                mm = sp.get("MUTE_MINUTES", 10)
                try:
                    if p == "kick":   await after.kick(reason="[Anti-Spotify] Spotify status")
                    elif p == "ban":  await after.ban(reason="[Anti-Spotify] Spotify status")
                    elif p == "mute": await after.timeout(timedelta(minutes=mm), reason="[Anti-Spotify] Spotify status")
                except discord.Forbidden:
                    pass
    except AttributeError:
        pass


class AntiTokenChallengeView(ui.View):
    def __init__(self, guild_id: int, user_id: int):
        super().__init__(timeout=60)
        self.guild_id = guild_id
        self.user_id = user_id

    @ui.button(label="I am human · Continue", emoji="🛡️", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("This verification is intended for another user.", ephemeral=True)
        pending_challenges.pop((self.guild_id, self.user_id), None)
        await interaction.response.send_message("✅ Verification passed. Thank you!", ephemeral=True)
        self.stop()


async def start_antitoken_challenge(member: discord.Member, cfg: dict) -> bool:
    key = (member.guild.id, member.id)
    acfg = cfg.get("ANTITOKEN_CONFIG", {})
    pending_challenges[key] = time.time() + int(acfg.get("CHALLENGE_SECONDS", 45))
    embed = discord.Embed(
        title="🛡️ Anti-Token Spam Verification",
        description=(f"You are sending messages too fast on **{discord.utils.escape_markdown(member.guild.name)}**.\n"
                     f"Click the button within {int(acfg.get('CHALLENGE_SECONDS', 45))} seconds "
                     "to confirm that you are not a bot. If you continue chatting without verifying, a timeout will be applied."),
        color=discord.Color.orange()
    )
    try:
        await member.send(embed=embed, view=AntiTokenChallengeView(member.guild.id, member.id))
        return True
    except (discord.Forbidden, discord.HTTPException):
        pending_challenges.pop(key, None)
        return False


@bot.event
async def on_message(message: discord.Message):
    if not message.guild or message.author.bot:
        return

    guild = message.guild
    cfg = get_cfg(guild.id)

    if message.webhook_id:
        am_cfg = cfg.get("ANTIMASSMUTE_CONFIG", {})
        if am_cfg.get("ANTIABUSE_EVERYONE", True) and ("@everyone" in message.content or "@here" in message.content):
            try:
                await message.delete()
                webhooks = await message.channel.webhooks()
                for wh in webhooks:
                    if wh.id == message.webhook_id:
                        await wh.delete(reason="Webhook abuse protection")
                        break
                le = discord.Embed(title="🪝 Webhook Abuse Prevented",
                                    description=f"Message containing `@everyone/@here` deleted in {message.channel.mention}, webhook deleted.",
                                    color=discord.Color.dark_red(), timestamp=datetime.utcnow())
                await send_log(guild, "ALERTS", le, ping_admins=True)
            except (discord.Forbidden, discord.HTTPException):
                pass
            return

    if is_whitelisted(message.author.id, guild):
        return await bot.process_commands(message)

    anti_cfg = cfg.get("ANTITOKEN_CONFIG", {})
    challenge_key = (guild.id, message.author.id)

    if anti_cfg.get("ENABLED", True) and challenge_key in pending_challenges:
        try:
            await message.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass
        try:
            await message.author.timeout(timedelta(minutes=int(anti_cfg.get("TIMEOUT_MINUTES", 10))), reason="[Anti-Token] Verification ignored")
            await message.channel.send(f"🔇 {message.author.mention}, timed out: verification failed.", delete_after=7)
        except (discord.Forbidden, discord.HTTPException):
            pass
        pending_challenges.pop(challenge_key, None)
        return

    if anti_cfg.get("ENABLED", True):
        now = time.time()
        rate_key = (guild.id, message.author.id)
        window = max(1, int(anti_cfg.get("WINDOW_SECONDS", 5)))
        max_messages = max(2, int(anti_cfg.get("MAX_MESSAGES", 6)))
        message_rate_tracker[rate_key] = [t for t in message_rate_tracker[rate_key] if now - t <= window]
        message_rate_tracker[rate_key].append(now)
        if len(message_rate_tracker[rate_key]) >= max_messages:
            sent = await start_antitoken_challenge(message.author, cfg)
            if sent:
                try:
                    await message.channel.send(f"🛡️ {message.author.mention}, verification sent to your direct messages.", delete_after=8)
                except discord.HTTPException:
                    pass
                return

    tag_cfg = cfg.get("TAG_ROLE_CONFIG", {})
    tag = str(tag_cfg.get("TAG", "")).strip()
    role_id = tag_cfg.get("ROLE_ID")
    if tag_cfg.get("ENABLED") and tag and role_id and tag.casefold() in message.author.display_name.casefold():
        role = message.guild.get_role(int(role_id))
        if role and role not in message.author.roles and message.guild.me and message.guild.me.top_role > role:
            try:
                await message.author.add_roles(role, reason=f"Tag auto-role: {tag}")
            except (discord.Forbidden, discord.HTTPException):
                pass

    al = cfg.get("ANTILINK_CONFIG", {})
    if al.get("ENABLED", False):
        mode     = al.get("MODE", "all")
        has_link = False
        if mode == "all" and re.search(r"https?://|discord\.gg|t\.me", message.content, re.I):
            has_link = True
        elif mode == "custom":
            for dom in al.get("CUSTOM_DOMAINS", []):
                if dom.lower() in message.content.lower():
                    has_link = True
                    break
        if has_link:
            try:
                await message.delete()
                p  = al.get("PUNISHMENT", "delete")
                mm = al.get("MUTE_MINUTES", 10)
                if p == "mute":   await message.author.timeout(timedelta(minutes=mm), reason="[Anti-Link]")
                elif p == "kick": await message.author.kick(reason="[Anti-Link]")
                elif p == "ban":  await message.author.ban(reason="[Anti-Link]")
                await message.channel.send(f"⚠️ {message.author.mention}, links are restricted!", delete_after=5)
            except discord.Forbidden:
                pass
            return

    sp = cfg.get("ANTISPOTIFY_CONFIG", {})
    if sp.get("ENABLED", False):
        if "open.spotify.com" in message.content.lower() or "spotify:track:" in message.content.lower():
            try:
                await message.delete()
                p  = sp.get("PUNISHMENT", "delete")
                mm = sp.get("MUTE_MINUTES", 10)
                if p == "mute":   await message.author.timeout(timedelta(minutes=mm), reason="[Anti-Spotify]")
                elif p == "kick": await message.author.kick(reason="[Anti-Spotify]")
                elif p == "ban":  await message.author.ban(reason="[Anti-Spotify]")
            except discord.Forbidden:
                pass
            return

    panic = cfg.get("PANIC_MODE_ACTIVE", False)
    if panic and message.attachments:
        try:
            await message.delete()
            await message.channel.send(f"⚠️ {message.author.mention}, panic mode active!", delete_after=5)
        except discord.Forbidden:
            pass
        return

    ai_m = cfg.get("AI_MEDIA_SCANNER", {})
    if ai_m.get("ENABLED", True) and message.attachments:
        for att in message.attachments:
            if await fake_ai_check(att) == "ILLEGAL":
                try:
                    await message.delete()
                    await message.guild.ban(message.author, reason="[AI Scanner] Prohibited content")
                    le = discord.Embed(
                        title="⛔ AI Media Scanner: Ban",
                        description=f"**User:** {message.author.mention}\n**Action:** Ban.",
                        color=discord.Color.dark_red(), timestamp=datetime.utcnow()
                    )
                    await send_log(message.guild, "ALERTS", le, ping_admins=True)
                except discord.Forbidden:
                    pass
                return

    sp_cfg = cfg.get("SPAM_CONFIG", {})
    if sp_cfg.get("ENABLED", True):
        if sp_cfg.get("ANTIPING", True) and ("@everyone" in message.content or "@here" in message.content):
            if not message.author.guild_permissions.mention_everyone:
                try:
                    await message.delete()
                    await message.channel.send(f"{message.author.mention}, everyone/here pings are restricted.", delete_after=5)
                except (discord.Forbidden, discord.HTTPException):
                    pass
                return

        now  = time.time()
        key  = (guild.id, message.author.id)
        w    = sp_cfg.get("SPAM_WINDOW", 4)
        mx   = sp_cfg.get("MAX_MESSAGES", 5)
        spam_tracker[key] = [t for t in spam_tracker[key] if now - t < w]
        spam_tracker[key].append(now)
        if len(spam_tracker[key]) >= mx:
            try:
                await message.channel.purge(limit=mx, check=lambda m: m.author.id == message.author.id)
                p  = sp_cfg.get("PUNISHMENT", "timeout").lower()
                mm = sp_cfg.get("MUTE_MINUTES", 10)
                if p == "ban":    await guild.ban(message.author, reason="[Anti-Spam]")
                elif p == "kick": await guild.kick(message.author, reason="[Anti-Spam]")
                else:
                    await message.author.timeout(timedelta(minutes=mm), reason="[Anti-Spam]")
                    await message.channel.send(f"🔇 {message.author.mention} timed out for `{mm}`m due to spam.", delete_after=5)
                le = discord.Embed(
                    title="💬 Anti-Spam: Punishment Applied",
                    description=f"**User:** {message.author.mention}\n**Action:** `{p.upper()}`",
                    color=discord.Color.orange(), timestamp=datetime.utcnow()
                )
                await send_log(guild, "AUTOMOD", le)
            except discord.Forbidden:
                pass
            return

    await bot.process_commands(message)


# ==========================================================
# 🎛️ 9. PANELS AND BUTTONS
# ==========================================================

class WhitelistUserSelect(ui.UserSelect):
    def __init__(self, action: str):
        self.action = action
        super().__init__(
            placeholder=f"Select user to {'add to' if action == 'add' else 'remove from'} Whitelist...",
            min_values=1, max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        u   = self.values[0]
        uid = u.id
        cfg = get_cfg(interaction.guild.id)
        wl  = set(cfg.get("WHITELIST_USERS", []))

        if self.action == "add":
            wl.add(uid)
            cfg["WHITELIST_USERS"] = list(wl)
            await save_cfg(interaction.guild.id)
            await interaction.response.send_message(f"✅ {u.mention} added to Whitelist!", ephemeral=True)
        else:
            if uid == interaction.guild.owner_id:
                return await interaction.response.send_message("❌ Cannot remove the server owner!", ephemeral=True)
            wl.discard(uid)
            cfg["WHITELIST_USERS"] = list(wl)
            await save_cfg(interaction.guild.id)
            await interaction.response.send_message(f"🗑️ {u.mention} removed from Whitelist!", ephemeral=True)

class WhitelistControlView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Add", style=discord.ButtonStyle.success, emoji="👑")
    async def add_btn(self, interaction: discord.Interaction, button: ui.Button):
        v = ui.View(); v.add_item(WhitelistUserSelect("add"))
        await interaction.response.send_message("Select user:", view=v, ephemeral=True)

    @ui.button(label="Remove", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def remove_btn(self, interaction: discord.Interaction, button: ui.Button):
        v = ui.View(); v.add_item(WhitelistUserSelect("remove"))
        await interaction.response.send_message("Select user:", view=v, ephemeral=True)

    @ui.button(label="List", style=discord.ButtonStyle.secondary, emoji="📄")
    async def list_btn(self, interaction: discord.Interaction, button: ui.Button):
        cfg = get_cfg(interaction.guild.id)
        wl  = set(cfg.get("WHITELIST_USERS", []))
        lines = []
        for uid in wl:
            u = interaction.guild.get_member(uid) or await bot.fetch_user(uid)
            lines.append(f"▫️ {u.mention if u else uid} (`{uid}`)")
        e = discord.Embed(
            title="📜 WHITELIST",
            description="\n".join(lines) if lines else "List is empty.",
            color=get_embed_color(interaction.guild.id)
        )
        await interaction.response.send_message(embed=e, ephemeral=True)

def build_whitelist_embed(guild: discord.Guild) -> discord.Embed:
    cfg = get_cfg(guild.id)
    wl  = cfg.get("WHITELIST_USERS", [])
    cats = cfg.get("WHITELIST_CATEGORIES", {})
    cat_summary = "\n".join(f"▫️ **{WHITELIST_CATEGORY_LABELS[k]}:** `{len(v)}`" for k, v in cats.items())
    e = discord.Embed(
        title="👑 WHITELIST MANAGEMENT",
        description=(
            "Whitelisted users are exempt from all security protections.\n"
            "⚠️ Deleting more than 3 channels at once triggers an auto-kick regardless of whitelist status.\n\n"
            f"▫️ **Owner:** <@{guild.owner_id}>\n"
            f"▫️ **Whitelisted Users:** `{len(wl)}`\n\n"
            "**Category Immunities:**\n" + (cat_summary or "—") + "\n\n"
            "Use `/whitelist add`, `/whitelist category_add` and other subcommands to configure precise permissions."
        ),
        color=get_embed_color(guild.id)
    )
    e.set_thumbnail(url=WHITELIST_ICON_URL)
    return e


class AntiLinkDomainsModal(ui.Modal, title="🌐 Anti-Link Domains"):
    domains = ui.TextInput(label="Domains separated by comma", placeholder="discord.gg, t.me, youtube.com")

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_cfg(interaction.guild.id)
        parsed = [d.strip() for d in self.domains.value.split(",") if d.strip()]
        cfg["ANTILINK_CONFIG"]["CUSTOM_DOMAINS"] = parsed
        await save_cfg(interaction.guild.id)
        await interaction.response.send_message(f"✅ Domains saved: `{', '.join(parsed)}`", ephemeral=True)
        await interaction.message.edit(embed=build_antilink_embed(interaction.guild.id), view=AntiLinkControlView(interaction.guild.id))

def build_antilink_embed(guild_id: int) -> discord.Embed:
    cfg  = get_cfg(guild_id)
    al   = cfg.get("ANTILINK_CONFIG", {})
    on   = al.get("ENABLED", False)
    mode = "All Links" if al.get("MODE") == "all" else "Custom Domains"
    doms = ", ".join(al.get("CUSTOM_DOMAINS", [])) or "None"
    return discord.Embed(
        title="🔗 ANTI-LINK PROTECTION",
        description=(
            f"▫️ **Status:** {'🟢 Enabled' if on else '🔴 Disabled'}\n"
            f"▫️ **Mode:** `{mode}`\n"
            f"▫️ **Domains:** `{doms}`\n"
            f"▫️ **Punishment:** `{al.get('PUNISHMENT','delete').upper()}`\n"
            f"▫️ **Timeout:** `{al.get('MUTE_MINUTES',10)}m`"
        ),
        color=get_embed_color(guild_id)
    )

class AntiLinkControlView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @ui.button(label="Toggle ON/OFF", style=discord.ButtonStyle.primary)
    async def toggle(self, i: discord.Interaction, b):
        cfg = get_cfg(i.guild.id)
        cfg["ANTILINK_CONFIG"]["ENABLED"] = not cfg["ANTILINK_CONFIG"].get("ENABLED", False)
        await save_cfg(i.guild.id)
        await i.response.edit_message(embed=build_antilink_embed(i.guild.id), view=AntiLinkControlView(i.guild.id))

    @ui.button(label="All Links", style=discord.ButtonStyle.secondary)
    async def mode_all(self, i: discord.Interaction, b):
        cfg = get_cfg(i.guild.id); cfg["ANTILINK_CONFIG"]["MODE"] = "all"
        await save_cfg(i.guild.id)
        await i.response.edit_message(embed=build_antilink_embed(i.guild.id), view=AntiLinkControlView(i.guild.id))

    @ui.button(label="Custom Domains", style=discord.ButtonStyle.secondary)
    async def mode_custom(self, i: discord.Interaction, b):
        cfg = get_cfg(i.guild.id); cfg["ANTILINK_CONFIG"]["MODE"] = "custom"
        await save_cfg(i.guild.id)
        await i.response.edit_message(embed=build_antilink_embed(i.guild.id), view=AntiLinkControlView(i.guild.id))

    @ui.button(label="Delete", style=discord.ButtonStyle.secondary, row=1)
    async def pun_del(self, i: discord.Interaction, b):
        cfg = get_cfg(i.guild.id); cfg["ANTILINK_CONFIG"]["PUNISHMENT"] = "delete"
        await save_cfg(i.guild.id)
        await i.response.edit_message(embed=build_antilink_embed(i.guild.id), view=AntiLinkControlView(i.guild.id))

    @ui.button(label="Mute", style=discord.ButtonStyle.secondary, row=1)
    async def pun_mute(self, i: discord.Interaction, b):
        cfg = get_cfg(i.guild.id); cfg["ANTILINK_CONFIG"]["PUNISHMENT"] = "mute"
        await save_cfg(i.guild.id)
        await i.response.edit_message(embed=build_antilink_embed(i.guild.id), view=AntiLinkControlView(i.guild.id))

    @ui.button(label="Kick", style=discord.ButtonStyle.danger, row=1)
    async def pun_kick(self, i: discord.Interaction, b):
        cfg = get_cfg(i.guild.id); cfg["ANTILINK_CONFIG"]["PUNISHMENT"] = "kick"
        await save_cfg(i.guild.id)
        await i.response.edit_message(embed=build_antilink_embed(i.guild.id), view=AntiLinkControlView(i.guild.id))

    @ui.button(label="Ban", style=discord.ButtonStyle.danger, row=1)
    async def pun_ban(self, i: discord.Interaction, b):
        cfg = get_cfg(i.guild.id); cfg["ANTILINK_CONFIG"]["PUNISHMENT"] = "ban"
        await save_cfg(i.guild.id)
        await i.response.edit_message(embed=build_antilink_embed(i.guild.id), view=AntiLinkControlView(i.guild.id))

    @ui.button(label="Edit Domains", style=discord.ButtonStyle.success, row=1)
    async def domains_btn(self, i: discord.Interaction, b):
        await i.response.send_modal(AntiLinkDomainsModal())


class AntiSpotifyMuteModal(ui.Modal, title="⏱️ Anti-Spotify Timeout"):
    minutes = ui.TextInput(label="Minutes", placeholder="10", max_length=4)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            cfg = get_cfg(interaction.guild.id)
            cfg["ANTISPOTIFY_CONFIG"]["MUTE_MINUTES"] = int(self.minutes.value)
            await save_cfg(interaction.guild.id)
            await interaction.response.send_message(f"✅ Anti-Spotify timeout set to: `{self.minutes.value}`m", ephemeral=True)
            await interaction.message.edit(embed=build_spotify_embed(interaction.guild.id), view=AntiSpotifyView(interaction.guild.id))
        except ValueError:
            await interaction.response.send_message("❌ Enter numbers only!", ephemeral=True)

def build_spotify_embed(guild_id: int) -> discord.Embed:
    cfg = get_cfg(guild_id)
    sp  = cfg.get("ANTISPOTIFY_CONFIG", {})
    on  = sp.get("ENABLED", False)
    return discord.Embed(
        title="🎵 ANTI-SPOTIFY PROTECTION",
        description=(
            f"▫️ **Status:** {'🟢 Enabled' if on else '🔴 Disabled'}\n"
            f"▫️ **Punishment:** `{sp.get('PUNISHMENT','delete').upper()}`\n"
            f"▫️ **Timeout:** `{sp.get('MUTE_MINUTES',10)}m`\n"
            "*Blocks Spotify links and statuses*"
        ),
        color=discord.Color.from_rgb(30, 215, 96)
    )

class AntiSpotifyView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @ui.button(label="Toggle ON/OFF", style=discord.ButtonStyle.success)
    async def toggle(self, i: discord.Interaction, b):
        cfg = get_cfg(i.guild.id)
        cfg["ANTISPOTIFY_CONFIG"]["ENABLED"] = not cfg["ANTISPOTIFY_CONFIG"].get("ENABLED", False)
        await save_cfg(i.guild.id)
        await i.response.edit_message(embed=build_spotify_embed(i.guild.id), view=AntiSpotifyView(i.guild.id))

    @ui.button(label="Delete", style=discord.ButtonStyle.secondary)
    async def p_del(self, i: discord.Interaction, b):
        cfg = get_cfg(i.guild.id); cfg["ANTISPOTIFY_CONFIG"]["PUNISHMENT"] = "delete"
        await save_cfg(i.guild.id)
        await i.response.edit_message(embed=build_spotify_embed(i.guild.id), view=AntiSpotifyView(i.guild.id))

    @ui.button(label="Mute", style=discord.ButtonStyle.secondary)
    async def p_mute(self, i: discord.Interaction, b):
        cfg = get_cfg(i.guild.id); cfg["ANTISPOTIFY_CONFIG"]["PUNISHMENT"] = "mute"
        await save_cfg(i.guild.id)
        await i.response.edit_message(embed=build_spotify_embed(i.guild.id), view=AntiSpotifyView(i.guild.id))

    @ui.button(label="Kick", style=discord.ButtonStyle.danger)
    async def p_kick(self, i: discord.Interaction, b):
        cfg = get_cfg(i.guild.id); cfg["ANTISPOTIFY_CONFIG"]["PUNISHMENT"] = "kick"
        await save_cfg(i.guild.id)
        await i.response.edit_message(embed=build_spotify_embed(i.guild.id), view=AntiSpotifyView(i.guild.id))

    @ui.button(label="Ban", style=discord.ButtonStyle.danger)
    async def p_ban(self, i: discord.Interaction, b):
        cfg = get_cfg(i.guild.id); cfg["ANTISPOTIFY_CONFIG"]["PUNISHMENT"] = "ban"
        await save_cfg(i.guild.id)
        await i.response.edit_message(embed=build_spotify_embed(i.guild.id), view=AntiSpotifyView(i.guild.id))

    @ui.button(label="Timeout Duration", style=discord.ButtonStyle.primary, row=1)
    async def mute_time(self, i: discord.Interaction, b):
        await i.response.send_modal(AntiSpotifyMuteModal())


class AntiNukeModal(ui.Modal, title="🛡️ Anti-Nuke Settings"):
    window    = ui.TextInput(label="Time Window (sec)",          placeholder="30", max_length=4)
    max_bans  = ui.TextInput(label="Bans Threshold",             placeholder="2",  max_length=3)
    max_kicks = ui.TextInput(label="Kicks Threshold",            placeholder="3",  max_length=3)
    max_ch    = ui.TextInput(label="Delete Channels (max 3)",    placeholder="3",  max_length=3)
    punish    = ui.TextInput(label="Punishment (ban/kick/timeout)", placeholder="kick", max_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            p = self.punish.value.strip().lower()
            if p not in ["ban", "kick", "timeout", "mute"]:
                return await interaction.response.send_message("❌ Choose ban / kick / timeout", ephemeral=True)
            cfg = get_cfg(interaction.guild.id)
            cfg["CONFIG"].update({
                "TIME_WINDOW": int(self.window.value),
                "MAX_BANS":    int(self.max_bans.value),
                "MAX_KICKS":   int(self.max_kicks.value),
                "MAX_CHANNEL_DELETE": int(self.max_ch.value),
                "PUNISHMENT":  p
            })
            await save_cfg(interaction.guild.id)
            await interaction.response.send_message("✅ Anti-Nuke settings updated!", ephemeral=True)
            await interaction.message.edit(embed=build_antinuke_embed(interaction.guild.id), view=AntiNukeControlView(interaction.guild.id))
        except ValueError:
            await interaction.response.send_message("❌ Enter numbers only!", ephemeral=True)

def build_antinuke_embed(guild_id: int) -> discord.Embed:
    cfg   = get_cfg(guild_id)
    c     = cfg.get("CONFIG", {})
    panic = cfg.get("PANIC_MODE_ACTIVE", False)
    return discord.Embed(
        title="🛡️ ANTI-NUKE PROTECTION",
        description=(
            f"▫️ **Status:** {'🟢 Enabled' if c.get('ENABLED',True) else '🔴 Disabled'}\n"
            f"▫️ **Panic Mode:** {'🚨 ACTIVE' if panic else '⚪ Inactive'}\n"
            f"▫️ **Punishment:** `{c.get('PUNISHMENT','kick').upper()}`\n"
            f"▫️ **Bans:** `{c.get('MAX_BANS',2)}/{c.get('TIME_WINDOW',30)}s`\n"
            f"▫️ **Kicks:** `{c.get('MAX_KICKS',3)}/{c.get('TIME_WINDOW',30)}s`\n"
            f"▫️ **Channels:** `{c.get('MAX_CHANNEL_DELETE',3)}/{c.get('TIME_WINDOW',30)}s` (whitelist bypass limit: 3)\n"
            f"▫️ **Roles:** create `{c.get('MAX_ROLE_CREATE',3)}` / delete `{c.get('MAX_ROLE_DELETE',3)}` / grant `{c.get('MAX_ROLE_GRANT',3)}`"
        ),
        color=discord.Color.dark_red() if panic else get_embed_color(guild_id)
    )

class AntiNukeControlView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @ui.button(label="Toggle ON/OFF", style=discord.ButtonStyle.primary)
    async def toggle(self, i: discord.Interaction, b):
        cfg = get_cfg(i.guild.id); cfg["CONFIG"]["ENABLED"] = not cfg["CONFIG"].get("ENABLED", True)
        await save_cfg(i.guild.id)
        await i.response.edit_message(embed=build_antinuke_embed(i.guild.id), view=AntiNukeControlView(i.guild.id))

    @ui.button(label="Limits", style=discord.ButtonStyle.secondary)
    async def config(self, i: discord.Interaction, b):
        await i.response.send_modal(AntiNukeModal())

    @ui.button(label="Panic Mode", style=discord.ButtonStyle.danger)
    async def panic(self, i: discord.Interaction, b):
        cfg = get_cfg(i.guild.id); cfg["PANIC_MODE_ACTIVE"] = not cfg.get("PANIC_MODE_ACTIVE", False)
        await save_cfg(i.guild.id)
        await i.response.edit_message(embed=build_antinuke_embed(i.guild.id), view=AntiNukeControlView(i.guild.id))

    @ui.button(label="Anti-Bot Toggle", style=discord.ButtonStyle.secondary, row=1)
    async def toggle_bot(self, i: discord.Interaction, b):
        cfg = get_cfg(i.guild.id)
        cfg["CONFIG"]["BLOCK_UNVERIFIED_BOTS"] = not cfg["CONFIG"].get("BLOCK_UNVERIFIED_BOTS", True)
        await save_cfg(i.guild.id)
        await i.response.edit_message(embed=build_antinuke_embed(i.guild.id), view=AntiNukeControlView(i.guild.id))

    @ui.button(label="Reset Defaults", style=discord.ButtonStyle.danger, row=1)
    async def reset(self, i: discord.Interaction, b):
        cfg = get_cfg(i.guild.id)
        cfg["CONFIG"].update({"ENABLED": True, "PUNISHMENT": "kick", "TIME_WINDOW": 30,
                               "MAX_BANS": 2, "MAX_KICKS": 3, "MAX_CHANNEL_DELETE": 3,
                               "MAX_ROLE_DELETE": 3, "MAX_ROLE_CREATE": 3, "MAX_ROLE_GRANT": 3,
                               "BLOCK_UNVERIFIED_BOTS": True})
        cfg["PANIC_MODE_ACTIVE"] = False
        await save_cfg(i.guild.id)
        await i.response.edit_message(embed=build_antinuke_embed(i.guild.id), view=AntiNukeControlView(i.guild.id))


class AntiRaidModal(ui.Modal, title="⚡ Anti-Raid Settings"):
    window    = ui.TextInput(label="Time Window (sec)",   placeholder="30",      max_length=4)
    max_joins = ui.TextInput(label="Max Joins",           placeholder="10",     max_length=3)
    punish    = ui.TextInput(label="Punishment",         placeholder="timeout", max_length=10)
    mh        = ui.TextInput(label="Timeout (Hours)",     placeholder="2",      max_length=3)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            p = self.punish.value.strip().lower()
            if p not in ["ban", "kick", "timeout", "mute"]:
                return await interaction.response.send_message("❌ Choose ban/kick/timeout", ephemeral=True)
            cfg = get_cfg(interaction.guild.id)
            cfg["ANTIRAID_CONFIG"].update({
                "TIME_WINDOW": int(self.window.value),
                "MAX_JOINS":   int(self.max_joins.value),
                "PUNISHMENT":  p,
                "MUTE_HOURS":  int(self.mh.value)
            })
            await save_cfg(interaction.guild.id)
            await interaction.response.send_message("✅ Anti-Raid settings updated!", ephemeral=True)
            await interaction.message.edit(embed=build_antiraid_embed(interaction.guild.id), view=AntiRaidControlView(interaction.guild.id))
        except ValueError:
            await interaction.response.send_message("❌ Enter numbers only!", ephemeral=True)

def build_antiraid_embed(guild_id: int) -> discord.Embed:
    cfg = get_cfg(guild_id)
    r   = cfg.get("ANTIRAID_CONFIG", {})
    return discord.Embed(
        title="⚡ ANTI-RAID PROTECTION",
        description=(
            f"▫️ **Status:** {'🟢 Enabled' if r.get('ENABLED',True) else '🔴 Disabled'}\n"
            f"▫️ **Limit:** `{r.get('MAX_JOINS',10)} users / {r.get('TIME_WINDOW',30)}s`\n"
            f"▫️ **Punishment:** `{r.get('PUNISHMENT','timeout').upper()}`\n"
            f"▫️ **Timeout:** `{r.get('MUTE_HOURS',2)}h`"
        ),
        color=get_embed_color(guild_id)
    )

class AntiRaidControlView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @ui.button(label="Toggle ON/OFF", style=discord.ButtonStyle.primary)
    async def toggle(self, i: discord.Interaction, b):
        cfg = get_cfg(i.guild.id)
        cfg["ANTIRAID_CONFIG"]["ENABLED"] = not cfg["ANTIRAID_CONFIG"].get("ENABLED", True)
        await save_cfg(i.guild.id)
        await i.response.edit_message(embed=build_antiraid_embed(i.guild.id), view=AntiRaidControlView(i.guild.id))

    @ui.button(label="Settings", style=discord.ButtonStyle.secondary)
    async def settings(self, i: discord.Interaction, b):
        await i.response.send_modal(AntiRaidModal())


def build_logs_embed(guild_id: int) -> discord.Embed:
    cfg = get_cfg(guild_id)
    lc  = cfg.get("LOGS_CONFIG", {})
    mode = lc.get("MODE", "manual")
    lines = [
        f"▫️ **Mode:** `{'Auto' if mode == 'auto' else 'Manual'}`",
    ]
    if mode == "auto":
        chs = lc.get("CHANNELS", {})
        for key, name in LOGS_BUCKET_NAMES.items():
            cid = chs.get(key)
            lines.append(f"▫️ **{name}:** {f'<#{cid}>' if cid else 'not created'}")
    else:
        cid = lc.get("CHANNEL_ID")
        lines.append(f"▫️ **Channel:** {f'<#{cid}>' if cid else 'not selected'}")
    lines += [
        "",
        f"▫️ **Message Deletes:** {'🟢' if lc.get('MESSAGE_DELETE') else '🔴'}",
        f"▫️ **Message Edits:** {'🟢' if lc.get('MESSAGE_EDIT') else '🔴'}",
        f"▫️ **Member Join/Leave:** {'🟢' if lc.get('MEMBER_JOIN_LEAVE') else '🔴'}",
        f"▫️ **Bans / Kicks:** {'🟢' if lc.get('BANS') else '🔴'}",
        f"▫️ **Mutes:** {'🟢' if lc.get('MUTES') else '🔴'}",
        f"▫️ **Roles / Channels / Perms:** {'🟢' if lc.get('ROLE_CHANGES') else '🔴'}",
        f"▫️ **Security Alerts:** {'🟢' if lc.get('ALERTS') else '🔴'}",
    ]
    return discord.Embed(title="🪵 LOGS SETUP", description="\n".join(lines), color=get_embed_color(guild_id))

class LogsSetupView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    async def _toggle(self, interaction: discord.Interaction, *keys):
        cfg = get_cfg(interaction.guild.id)
        lc  = cfg.get("LOGS_CONFIG", {})
        for k in keys:
            lc[k] = not lc.get(k, True)
        await save_cfg(interaction.guild.id)
        await interaction.response.edit_message(embed=build_logs_embed(interaction.guild.id), view=LogsSetupView(interaction.guild.id))

    @ui.button(label="Messages", style=discord.ButtonStyle.secondary)
    async def t1(self, i, b): await self._toggle(i, "MESSAGE_DELETE", "MESSAGE_EDIT")

    @ui.button(label="Join/Leave", style=discord.ButtonStyle.secondary)
    async def t2(self, i, b): await self._toggle(i, "MEMBER_JOIN_LEAVE")

    @ui.button(label="Bans/Kicks", style=discord.ButtonStyle.secondary)
    async def t3(self, i, b): await self._toggle(i, "BANS", "KICKS")

    @ui.button(label="Mutes", style=discord.ButtonStyle.secondary)
    async def t4(self, i, b): await self._toggle(i, "MUTES")

    @ui.button(label="Roles/Channels/Perms", style=discord.ButtonStyle.secondary, row=1)
    async def t5(self, i, b): await self._toggle(i, "ROLE_CHANGES", "CHANNEL_CHANGES", "PERM_CHANGES")

    @ui.button(label="Alerts", style=discord.ButtonStyle.secondary, row=1)
    async def t6(self, i, b): await self._toggle(i, "ALERTS")


def build_welcome_embed(guild_id: int) -> discord.Embed:
    cfg = get_cfg(guild_id)
    wc = cfg.get("WELCOME_CONFIG", {})
    gc = cfg.get("GOODBYE_CONFIG", {})

    def block(cfgpart, title):
        ch = f"<#{cfgpart.get('CHANNEL_ID')}>" if cfgpart.get("CHANNEL_ID") else "not selected"
        color_name = WELCOME_COLOR_NAMES[cfgpart.get("COLOR_INDEX", 0) % len(WELCOME_COLOR_NAMES)]
        return (
            f"**{title}**\n"
            f"▫️ Status: {'🟢 Enabled' if cfgpart.get('ENABLED') else '🔴 Disabled'}\n"
            f"▫️ Channel: {ch}\n"
            f"▫️ Embed: {'Yes' if cfgpart.get('USE_EMBED', True) else 'No'}\n"
            f"▫️ Color: {color_name}\n"
            f"▫️ Text: {cfgpart.get('TEXT', '')[:150]}"
        )

    e = discord.Embed(
        title="👋 WELCOME & GOODBYE",
        description=block(wc, "Welcome") + "\n\n" + block(gc, "Goodbye") +
                     "\n\nAvailable variables: `{member}` and `{count}`.",
        color=get_embed_color(guild_id)
    )
    return e

class WelcomeTextModal(ui.Modal, title="✏️ Edit Message Text"):
    def __init__(self, guild_id: int, kind: str):
        super().__init__()
        self.guild_id = guild_id
        self.kind = kind
        current = get_cfg(guild_id).get(f"{kind}_CONFIG", {}).get("TEXT", "")
        self.text = ui.TextInput(
            label="Text", style=discord.TextStyle.paragraph, max_length=1000,
            default=current, placeholder="Use {member} and {count}"
        )
        self.add_item(self.text)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_cfg(self.guild_id)
        cfg.setdefault(f"{self.kind}_CONFIG", {})["TEXT"] = self.text.value
        await save_cfg(self.guild_id)
        await interaction.response.send_message("✅ Text saved successfully.", ephemeral=True)

class WelcomeColorSelect(ui.Select):
    def __init__(self, guild_id: int, kind: str):
        self.guild_id = guild_id
        self.kind = kind
        options = [discord.SelectOption(label=name, value=str(idx)) for idx, name in enumerate(WELCOME_COLOR_NAMES)]
        super().__init__(placeholder="Select embed color...", options=options)

    async def callback(self, interaction: discord.Interaction):
        cfg = get_cfg(self.guild_id)
        cfg.setdefault(f"{self.kind}_CONFIG", {})["COLOR_INDEX"] = int(self.values[0])
        await save_cfg(self.guild_id)
        await interaction.response.send_message(f"🎨 Color set to: {WELCOME_COLOR_NAMES[int(self.values[0])]}", ephemeral=True)

class WelcomeChannelSelect(ui.ChannelSelect):
    def __init__(self, guild_id: int, kind: str):
        self.guild_id = guild_id
        self.kind = kind
        super().__init__(placeholder="Select channel...", channel_types=[discord.ChannelType.text])

    async def callback(self, interaction: discord.Interaction):
        cfg = get_cfg(self.guild_id)
        cfg.setdefault(f"{self.kind}_CONFIG", {})["CHANNEL_ID"] = self.values[0].id
        await save_cfg(self.guild_id)
        await interaction.response.send_message(f"📌 Channel set to: {self.values[0].mention}", ephemeral=True)

class WelcomeEditView(ui.View):
    def __init__(self, guild_id: int, kind: str):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.kind = kind
        self.add_item(WelcomeChannelSelect(guild_id, kind))
        self.add_item(WelcomeColorSelect(guild_id, kind))

    @ui.button(label="Embed ON/OFF", style=discord.ButtonStyle.secondary, row=2)
    async def toggle_embed(self, i: discord.Interaction, b):
        cfg = get_cfg(self.guild_id)
        part = cfg.setdefault(f"{self.kind}_CONFIG", {})
        part["USE_EMBED"] = not part.get("USE_EMBED", True)
        await save_cfg(self.guild_id)
        await i.response.send_message(f"🖼️ Embed: {'enabled' if part['USE_EMBED'] else 'disabled'}", ephemeral=True)

    @ui.button(label="Edit Text", style=discord.ButtonStyle.primary, row=2)
    async def edit_text(self, i: discord.Interaction, b):
        await i.response.send_modal(WelcomeTextModal(self.guild_id, self.kind))

class WelcomeMainView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @ui.button(label="Welcome ON/OFF", style=discord.ButtonStyle.success)
    async def toggle_welcome(self, i: discord.Interaction, b):
        cfg = get_cfg(self.guild_id)
        cfg.setdefault("WELCOME_CONFIG", {})["ENABLED"] = not cfg["WELCOME_CONFIG"].get("ENABLED", True)
        await save_cfg(self.guild_id)
        await i.response.edit_message(embed=build_welcome_embed(self.guild_id), view=WelcomeMainView(self.guild_id))

    @ui.button(label="Goodbye ON/OFF", style=discord.ButtonStyle.secondary)
    async def toggle_goodbye(self, i: discord.Interaction, b):
        cfg = get_cfg(self.guild_id)
        cfg.setdefault("GOODBYE_CONFIG", {})["ENABLED"] = not cfg["GOODBYE_CONFIG"].get("ENABLED", False)
        await save_cfg(self.guild_id)
        await i.response.edit_message(embed=build_welcome_embed(self.guild_id), view=WelcomeMainView(self.guild_id))

    @ui.button(label="Configure Welcome", style=discord.ButtonStyle.primary, row=1)
    async def edit_welcome(self, i: discord.Interaction, b):
        await i.response.send_message("Welcome settings:", view=WelcomeEditView(self.guild_id, "WELCOME"), ephemeral=True)

    @ui.button(label="Configure Goodbye", style=discord.ButtonStyle.primary, row=1)
    async def edit_goodbye(self, i: discord.Interaction, b):
        await i.response.send_message("Goodbye settings:", view=WelcomeEditView(self.guild_id, "GOODBYE"), ephemeral=True)


class CaptchaModal(ui.Modal):
    def __init__(self, code: str, guild_id: int, expires_at: float):
        super().__init__(title="🔢 Verification Code")
        self.code = code
        self.guild_id = guild_id
        self.expires_at = expires_at
        self.inp = ui.TextInput(label="5-digit Code", placeholder="Enter digits from panel", min_length=5, max_length=5)
        self.add_item(self.inp)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_cfg(self.guild_id)
        vc = cfg.get("VERIFY_CONFIG", {})
        if time.time() > self.expires_at:
            return await interaction.response.send_message("⌛ Time expired. Click 'Verify' again.", ephemeral=True)
        if self.inp.value.strip() == self.code:
            role_id = vc.get("ROLE_ID")
            role = interaction.guild.get_role(role_id) if role_id else None
            if role:
                try:
                    await interaction.user.add_roles(role, reason="Verification passed")
                except discord.Forbidden:
                    return await interaction.response.send_message("❌ Cannot grant role. Check bot permissions and hierarchy.", ephemeral=True)
            return await interaction.response.send_message("✅ Verification completed!", ephemeral=True)
        await interaction.response.send_message("❌ Incorrect code. Please try again via the panel.", ephemeral=True)

class VerifyEmojiView(ui.View):
    def __init__(self, guild_id: int):
        cfg = get_cfg(guild_id).get("VERIFY_CONFIG", {})
        super().__init__(timeout=max(60, int(cfg.get("TIME_LIMIT_MINUTES", 10)) * 60))
        self.guild_id = guild_id
        correct = cfg.get("EMOJI", "✅")
        choices = [correct, "🔒" if correct != "🔒" else "🌙", "🌟" if correct != "🌟" else "🍀"]
        random.shuffle(choices)
        for emoji in choices:
            button = ui.Button(label=emoji, style=discord.ButtonStyle.secondary, custom_id=f"verify_emoji:{guild_id}:{emoji}")
            button.callback = self._make_callback(emoji, correct)
            self.add_item(button)

    def _make_callback(self, chosen, correct):
        async def callback(interaction: discord.Interaction):
            cfg = get_cfg(self.guild_id).get("VERIFY_CONFIG", {})
            role_id = cfg.get("ROLE_ID")
            if chosen != correct:
                return await interaction.response.send_message("❌ Incorrect emoji. Try again.", ephemeral=True)
            role = interaction.guild.get_role(role_id) if role_id else None
            if role:
                try:
                    await interaction.user.add_roles(role, reason="Emoji verification passed")
                except discord.Forbidden:
                    return await interaction.response.send_message("❌ Bot cannot grant role. Check permissions.", ephemeral=True)
            await interaction.response.send_message("✅ Verification completed!", ephemeral=True)
        return callback

class VerifyPublicView(ui.View):
    def __init__(self, guild_id: int | None = None):
        super().__init__(timeout=None)
        self.guild_id = guild_id

    @ui.button(label="✅ Verify", style=discord.ButtonStyle.success, custom_id="verify_btn_action")
    async def verify(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.guild is None:
            return await interaction.response.send_message("This button only works on servers.", ephemeral=True)
        cfg = get_cfg(interaction.guild.id)
        vc = cfg.get("VERIFY_CONFIG", {})
        if not vc.get("ENABLED", False):
            return await interaction.response.send_message("⚠️ Verification is currently disabled.", ephemeral=True)
        mode = vc.get("MODE", "button")
        if mode == "button":
            role_id = vc.get("ROLE_ID")
            role = interaction.guild.get_role(role_id) if role_id else None
            if role:
                try:
                    await interaction.user.add_roles(role, reason="Verification passed")
                except discord.Forbidden:
                    return await interaction.response.send_message("❌ Bot cannot grant role. Check permissions.", ephemeral=True)
            await interaction.response.send_message("✅ Verification completed!", ephemeral=True)
        elif mode == "captcha":
            code = str(random.randint(10000, 99999))
            limit = int(vc.get("TIME_LIMIT_MINUTES", 10))
            await interaction.response.send_modal(CaptchaModal(code, interaction.guild.id, time.time() + limit * 60))
        elif mode == "emoji":
            await interaction.response.send_message(f"Click the correct emoji **{vc.get('EMOJI', '✅')}**. Time limit: {vc.get('TIME_LIMIT_MINUTES', 10)}m.", view=VerifyEmojiView(interaction.guild.id), ephemeral=True)

class VerifyTextModal(ui.Modal, title="✏️ Verification Panel Text"):
    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id
        vc = get_cfg(guild_id).get("VERIFY_CONFIG", {})
        self.title_input = ui.TextInput(label="Title", default=str(vc.get("TITLE", "🛡️ Verification"))[:100], max_length=100)
        self.desc_input = ui.TextInput(label="Description", default=str(vc.get("DESCRIPTION", "Verify that you are human."))[:1000], style=discord.TextStyle.paragraph, max_length=1000)
        self.add_item(self.title_input)
        self.add_item(self.desc_input)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = get_cfg(self.guild_id)
        cfg.setdefault("VERIFY_CONFIG", {})["TITLE"] = self.title_input.value
        cfg["VERIFY_CONFIG"]["DESCRIPTION"] = self.desc_input.value
        await save_cfg(self.guild_id)
        await interaction.response.send_message("✅ Text saved successfully.", ephemeral=True)

class VerifyLimitModal(ui.Modal, title="⏱️ Verification Time Limit"):
    def __init__(self, guild_id: int):
        super().__init__()
        self.guild_id = guild_id
        current = get_cfg(guild_id).get("VERIFY_CONFIG", {}).get("TIME_LIMIT_MINUTES", 10)
        self.minutes = ui.TextInput(label="Minutes (1–1440)", default=str(current), min_length=1, max_length=4)
        self.add_item(self.minutes)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            minutes = int(self.minutes.value)
            if not 1 <= minutes <= 1440:
                raise ValueError
            cfg = get_cfg(self.guild_id)
            cfg.setdefault("VERIFY_CONFIG", {})["TIME_LIMIT_MINUTES"] = minutes
            await save_cfg(self.guild_id)
            await interaction.response.send_message(f"✅ Verification time limit set to: **{minutes}m**.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Enter an integer between 1 and 1440.", ephemeral=True)

class VerifyModeSelect(ui.Select):
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        super().__init__(placeholder="Select verification mode...", options=[
            discord.SelectOption(label="Button", value="button", emoji="🔘"),
            discord.SelectOption(label="Emoji Select", value="emoji", emoji="😀"),
            discord.SelectOption(label="Captcha Code", value="captcha", emoji="🔢")])

    async def callback(self, interaction: discord.Interaction):
        cfg = get_cfg(self.guild_id)
        cfg.setdefault("VERIFY_CONFIG", {})["MODE"] = self.values[0]
        await save_cfg(self.guild_id)
        await interaction.response.edit_message(embed=build_verify_config_embed(self.guild_id), view=VerifyConfigView(self.guild_id))

class VerifyConfigView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.add_item(VerifyModeSelect(guild_id))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("⛔ Requires 'Manage Server' permission.", ephemeral=True)
            return False
        return True

    @ui.button(label="✏️ Panel Text", style=discord.ButtonStyle.secondary, row=1)
    async def edit_text(self, i: discord.Interaction, b: ui.Button):
        await i.response.send_modal(VerifyTextModal(self.guild_id))

    @ui.button(label="⏱️ Time Limit", style=discord.ButtonStyle.secondary, row=1)
    async def set_limit(self, i: discord.Interaction, b: ui.Button):
        await i.response.send_modal(VerifyLimitModal(self.guild_id))

    @ui.button(label="🟢 Toggle ON/OFF", style=discord.ButtonStyle.primary, row=2)
    async def toggle(self, i: discord.Interaction, b: ui.Button):
        cfg = get_cfg(self.guild_id)
        vc = cfg.setdefault("VERIFY_CONFIG", {})
        vc["ENABLED"] = not vc.get("ENABLED", False)
        await save_cfg(self.guild_id)
        await i.response.edit_message(embed=build_verify_config_embed(self.guild_id), view=VerifyConfigView(self.guild_id))

    @ui.button(label="🚀 Send Panel", style=discord.ButtonStyle.success, row=2)
    async def send_panel(self, i: discord.Interaction, b: ui.Button):
        cfg = get_cfg(self.guild_id)
        vc = cfg.get("VERIFY_CONFIG", {})
        if not vc.get("ENABLED", False):
            return await i.response.send_message("⚠️ Enable verification first.", ephemeral=True)
        e = discord.Embed(title=vc.get("TITLE", "🛡️ Verification"), description=vc.get("DESCRIPTION", "Verify that you are human."), color=int(vc.get("EMBED_COLOR", get_embed_color(self.guild_id))))
        e.add_field(name="Mode", value={"button": "🔘 Button", "emoji": "😀 Emoji", "captcha": "🔢 Captcha"}.get(vc.get("MODE", "button"), "Button"), inline=True)
        e.add_field(name="Time Limit", value=f"{vc.get('TIME_LIMIT_MINUTES', 10)}m", inline=True)
        if vc.get("MODE") == "emoji":
            e.add_field(name="Instruction", value=f"Click the emoji {vc.get('EMOJI', '✅')} in the prompt.", inline=False)
        channel = i.guild.get_channel(vc.get("CHANNEL_ID")) if vc.get("CHANNEL_ID") else i.channel
        if not isinstance(channel, discord.TextChannel):
            return await i.response.send_message("❌ Specify text channel via /verify_setup.", ephemeral=True)
        await channel.send(embed=e, view=VerifyPublicView(self.guild_id))
        await i.response.send_message(f"✅ Verification panel sent to {channel.mention}.", ephemeral=True)

def build_verify_config_embed(guild_id: int) -> discord.Embed:
    vc = get_cfg(guild_id).get("VERIFY_CONFIG", {})
    mode = {"button": "Button", "emoji": "Emoji Select", "captcha": "Captcha Code"}.get(vc.get("MODE", "button"), "Button")
    return discord.Embed(title="✅ Verification Setup", description=(
        f"**Status:** {'🟢 Enabled' if vc.get('ENABLED') else '🔴 Disabled'}\n"
        f"**Role:** <@&{vc.get('ROLE_ID')}>\n**Channel:** <#{vc.get('CHANNEL_ID')}>\n"
        f"**Mode:** {mode}\n**Time Limit:** {vc.get('TIME_LIMIT_MINUTES', 10)}m\n"
        f"**Title:** {vc.get('TITLE', '🛡️ Verification')}\n**Emoji:** {vc.get('EMOJI', '✅')}"), color=int(vc.get("EMBED_COLOR", get_embed_color(guild_id))))


class WarnConfigSelect(ui.Select):
    def __init__(self, warn_count: str):
        self.warn_count = warn_count
        options = [
            discord.SelectOption(label="Mute 🔇", value="mute", emoji="🔇"),
            discord.SelectOption(label="Kick 👢",  value="kick", emoji="👢"),
            discord.SelectOption(label="Ban 🔨",  value="ban",  emoji="🔨"),
        ]
        super().__init__(placeholder=f"Punishment for {warn_count} warns...", options=options)

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        cfg = get_cfg(interaction.guild.id)
        if selected == "mute":
            await interaction.response.send_modal(WarnMuteModal(self.warn_count))
        else:
            cfg["WARN_ACTIONS"][self.warn_count] = {"action": selected, "mute_minutes": 0}
            await save_cfg(interaction.guild.id)
            await interaction.response.send_message(f"✅ For **{self.warn_count}** warns: `{selected.upper()}`", ephemeral=True)

class WarnMuteModal(ui.Modal, title="⏱️ Warn Mute Duration"):
    def __init__(self, warn_count: str):
        super().__init__()
        self.warn_count = warn_count
        self.minutes = ui.TextInput(label="Timeout (minutes)", placeholder="60", default="60")
        self.add_item(self.minutes)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            mins = int(self.minutes.value)
            cfg  = get_cfg(interaction.guild.id)
            cfg["WARN_ACTIONS"][self.warn_count] = {"action": "mute", "mute_minutes": mins}
            await save_cfg(interaction.guild.id)
            await interaction.response.send_message(f"✅ For **{self.warn_count}** warns: MUTE `{mins}`m", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Enter a number!", ephemeral=True)

class WarnConfigView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        cfg = get_cfg(guild_id)
        for count in sorted(cfg.get("WARN_ACTIONS", {}).keys(), key=lambda x: int(x))[:4]:
            self.add_item(WarnConfigSelect(str(count)))


# ==========================================================
# 🔨 10. SLASH COMMANDS
# ==========================================================

async def cooldown_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"⏳ Please wait `{error.retry_after:.1f}`s before reusing this command!", ephemeral=True)
    else:
        print(f"⚠️ Command error: {error}")
        if not interaction.response.is_done():
            await interaction.response.send_message("⚠️ An error occurred while executing the command.", ephemeral=True)

bot.tree.on_error = cooldown_error


# ---------- Whitelist Commands Group ----------

whitelist_group = app_commands.Group(name="whitelist", description="👑 Whitelist Management")

@whitelist_group.command(name="add", description="Grant full whitelist immunity to a user")
@app_commands.default_permissions(administrator=True)
async def whitelist_add_cmd(interaction: discord.Interaction, user: discord.User):
    if not is_whitelisted(interaction.user.id, interaction.guild):
        return await interaction.response.send_message("❌ Only whitelisted users can manage the whitelist!", ephemeral=True)
    cfg = get_cfg(interaction.guild.id)
    wl = set(cfg.get("WHITELIST_USERS", []))
    wl.add(user.id)
    cfg["WHITELIST_USERS"] = list(wl)
    await save_cfg(interaction.guild.id)
    await interaction.response.send_message(f"👑 {user.mention} added to full Whitelist.", ephemeral=True)

@whitelist_group.command(name="remove", description="Remove a user from full Whitelist")
@app_commands.default_permissions(administrator=True)
async def whitelist_remove_cmd(interaction: discord.Interaction, user: discord.User):
    if not is_whitelisted(interaction.user.id, interaction.guild):
        return await interaction.response.send_message("❌ Only whitelisted users can manage the whitelist!", ephemeral=True)
    if user.id == interaction.guild.owner_id:
        return await interaction.response.send_message("❌ Cannot remove the server owner!", ephemeral=True)
    cfg = get_cfg(interaction.guild.id)
    wl = set(cfg.get("WHITELIST_USERS", []))
    wl.discard(user.id)
    cfg["WHITELIST_USERS"] = list(wl)
    await save_cfg(interaction.guild.id)
    await interaction.response.send_message(f"🗑️ {user.mention} removed from full Whitelist.", ephemeral=True)

@whitelist_group.command(name="category_add", description="Grant immunity for a specific category")
@app_commands.describe(category="Protection category to grant immunity for")
@app_commands.choices(category=[Choice(name=label, value=key) for key, label in WHITELIST_CATEGORY_LABELS.items()])
@app_commands.default_permissions(administrator=True)
async def whitelist_category_add_cmd(interaction: discord.Interaction, user: discord.User, category: Choice[str]):
    if not is_whitelisted(interaction.user.id, interaction.guild):
        return await interaction.response.send_message("❌ Only whitelisted users can manage the whitelist!", ephemeral=True)
    cfg = get_cfg(interaction.guild.id)
    cats = cfg.setdefault("WHITELIST_CATEGORIES", {})
    lst = set(cats.get(category.value, []))
    lst.add(user.id)
    cats[category.value] = list(lst)
    await save_cfg(interaction.guild.id)
    await interaction.response.send_message(f"✅ {user.mention}: granted immunity for «{category.name}».", ephemeral=True)

@whitelist_group.command(name="category_remove", description="Remove immunity for a specific category")
@app_commands.describe(category="Protection category to remove immunity for")
@app_commands.choices(category=[Choice(name=label, value=key) for key, label in WHITELIST_CATEGORY_LABELS.items()])
@app_commands.default_permissions(administrator=True)
async def whitelist_category_remove_cmd(interaction: discord.Interaction, user: discord.User, category: Choice[str]):
    if not is_whitelisted(interaction.user.id, interaction.guild):
        return await interaction.response.send_message("❌ Only whitelisted users can manage the whitelist!", ephemeral=True)
    cfg = get_cfg(interaction.guild.id)
    cats = cfg.setdefault("WHITELIST_CATEGORIES", {})
    lst = set(cats.get(category.value, []))
    lst.discard(user.id)
    cats[category.value] = list(lst)
    await save_cfg(interaction.guild.id)
    await interaction.response.send_message(f"🗑️ {user.mention}: immunity for «{category.name}» removed.", ephemeral=True)

@whitelist_group.command(name="list", description="Display full whitelist and categories list")
@app_commands.default_permissions(administrator=True)
async def whitelist_list_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=build_whitelist_embed(interaction.guild), ephemeral=True)

@whitelist_group.command(name="panel", description="Open full whitelist control panel")
@app_commands.default_permissions(administrator=True)
async def whitelist_panel_cmd(interaction: discord.Interaction):
    if not is_whitelisted(interaction.user.id, interaction.guild):
        return await interaction.response.send_message("❌ Access restricted to whitelisted users!", ephemeral=True)
    await interaction.response.send_message(embed=build_whitelist_embed(interaction.guild), view=WhitelistControlView())

bot.tree.add_command(whitelist_group)


# ---------- Other Commands ----------

@bot.tree.command(name="antibot", description="🤖 Settings to block unauthorized bot additions")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.cooldown(1, 3.0)
async def antibot_cmd(interaction: discord.Interaction, status: bool = None):
    cfg = get_cfg(interaction.guild.id)
    if status is not None:
        cfg["CONFIG"]["BLOCK_UNVERIFIED_BOTS"] = status
        await save_cfg(interaction.guild.id)
        state_str = "🟢 Enabled (all unauthorized bots will be blocked)" if status else "🔴 Disabled (adding bots allowed)"
        return await interaction.response.send_message(f"✅ Anti-Bot updated: **{state_str}**", ephemeral=True)

    current = cfg["CONFIG"].get("BLOCK_UNVERIFIED_BOTS", True)
    e = discord.Embed(
        title="🤖 ANTI-BOT PROTECTION",
        description=f"▫️ **Block Status:** `{'🟢 ON' if current else '🔴 OFF'}`\n\n*If enabled, any bot added by non-whitelisted users is banned immediately.*",
        color=get_embed_color(interaction.guild.id)
    )
    await interaction.response.send_message(embed=e, view=AntiNukeControlView(interaction.guild.id))

@bot.tree.command(name="antilink_config", description="🔗 Anti-Link Panel")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.cooldown(1, 3.0)
async def antilink_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=build_antilink_embed(interaction.guild.id), view=AntiLinkControlView(interaction.guild.id))

@bot.tree.command(name="antispotify_config", description="🎵 Anti-Spotify Panel")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.cooldown(1, 3.0)
async def antispotify_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=build_spotify_embed(interaction.guild.id), view=AntiSpotifyView(interaction.guild.id))

@bot.tree.command(name="antinuke", description="🛡️ Anti-Nuke Panel")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.cooldown(1, 3.0)
async def antinuke_cmd(interaction: discord.Interaction):
    if not is_whitelisted(interaction.user.id, interaction.guild):
        return await interaction.response.send_message("❌ Access restricted to whitelisted users!", ephemeral=True)
    await interaction.response.send_message(embed=build_antinuke_embed(interaction.guild.id), view=AntiNukeControlView(interaction.guild.id))

@bot.tree.command(name="antiraid", description="⚡ Anti-Raid Panel")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.cooldown(1, 3.0)
async def antiraid_cmd(interaction: discord.Interaction):
    if not is_whitelisted(interaction.user.id, interaction.guild):
        return await interaction.response.send_message("❌ Access restricted to whitelisted users!", ephemeral=True)
    await interaction.response.send_message(embed=build_antiraid_embed(interaction.guild.id), view=AntiRaidControlView(interaction.guild.id))

@bot.tree.command(name="panic", description="🚨 Panic Mode Control")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.cooldown(1, 3.0)
async def panic_cmd(interaction: discord.Interaction):
    if not is_whitelisted(interaction.user.id, interaction.guild):
        return await interaction.response.send_message("❌ Access restricted to whitelisted users!", ephemeral=True)
    await interaction.response.send_message(embed=build_antinuke_embed(interaction.guild.id), view=AntiNukeControlView(interaction.guild.id))

@bot.tree.command(name="ai_panel", description="🧠 AI Scanners Panel")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.cooldown(1, 3.0)
async def ai_panel_cmd(interaction: discord.Interaction):
    if not is_whitelisted(interaction.user.id, interaction.guild):
        return await interaction.response.send_message("❌ Access restricted to whitelisted users!", ephemeral=True)
    cfg = get_cfg(interaction.guild.id)
    e = discord.Embed(
        title="🧠 AI PROTECTION",
        description=(
            f"▫️ **Account Scanner:** `{'🟢' if cfg.get('AI_ACCOUNT_SCANNER',{}).get('ENABLED') else '🔴'}`\n"
            f"▫️ **Media Filter:** `{'🟢' if cfg.get('AI_MEDIA_SCANNER',{}).get('ENABLED') else '🔴'}`"
        ),
        color=get_embed_color(interaction.guild.id)
    )
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="security_settings", description="📊 Comprehensive Security Audit")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.cooldown(1, 5.0)
async def security_cmd(interaction: discord.Interaction):
    guild = interaction.guild
    risk, admins, danger = calculate_server_risk(guild)
    cfg = get_cfg(guild.id)
    e = discord.Embed(title="🛡️ Security Audit Overview",
                      color=get_embed_color(guild.id), timestamp=datetime.utcnow())
    e.add_field(name="🛡️ Anti-Nuke",
                value=f"Bans: `{cfg['CONFIG'].get('MAX_BANS',2)}` | Kicks: `{cfg['CONFIG'].get('MAX_KICKS',3)}` | Channels: `{cfg['CONFIG'].get('MAX_CHANNEL_DELETE',3)}`\nPunishment: `{cfg['CONFIG'].get('PUNISHMENT','kick').upper()}`", inline=False)
    e.add_field(name="⚡ Anti-Raid",
                value=f"Limit: `{cfg['ANTIRAID_CONFIG'].get('MAX_JOINS',10)}/{cfg['ANTIRAID_CONFIG'].get('TIME_WINDOW',30)}s` | Punishment: `{cfg['ANTIRAID_CONFIG'].get('PUNISHMENT','timeout').upper()}`", inline=False)
    e.add_field(name="🔍 Server Analysis",
                value=f"Admins: `{admins}` | Dangerous Roles: `{danger}`", inline=False)
    e.add_field(name="⚠️ Risk Score", value=f"```yaml\nRisk: {risk}/100\n```", inline=False)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="risk", description="⚠️ Quick Risk Assessment")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.cooldown(1, 3.0)
async def risk_cmd(interaction: discord.Interaction):
    guild = interaction.guild
    risk, admins, danger = calculate_server_risk(guild)
    cfg = get_cfg(guild.id)

    if risk < 30:
        status, color = "🟢 Low Risk", discord.Color.green()
    elif risk < 60:
        status, color = "🟡 Medium Risk", discord.Color.gold()
    elif risk < 85:
        status, color = "🟠 High Risk", discord.Color.orange()
    else:
        status, color = "🔴 Critical Risk", discord.Color.red()

    e = discord.Embed(
        title="📊 Server Risk Rating",
        description=f"**Status:** {status}\n**Index:** `{risk}/100`",
        color=color, timestamp=datetime.utcnow()
    )
    e.add_field(name="👥 Administrators", value=f"`{admins}`", inline=True)
    e.add_field(name="⚠️ Dangerous Roles", value=f"`{danger}`", inline=True)

    an_status = "🟢 Enabled" if cfg.get("CONFIG", {}).get("ENABLED") else "🔴 Disabled"
    ar_status = "🟢 Enabled" if cfg.get("ANTIRAID_CONFIG", {}).get("ENABLED") else "🔴 Disabled"

    e.add_field(name="🛡️ Anti-Nuke", value=an_status, inline=True)
    e.add_field(name="⚡ Anti-Raid", value=ar_status, inline=True)

    await interaction.response.send_message(embed=e)

@bot.tree.command(name="logs_setup", description="🪵 Setup Logging: Auto or Manual")
@app_commands.describe(mode="Auto creates channels automatically; Manual lets you pick an existing channel", channel="Channel for manual mode")
@app_commands.choices(mode=[
    Choice(name="Auto — bot creates logging channels automatically", value="auto"),
    Choice(name="Manual — select an existing channel", value="manual"),
])
@app_commands.default_permissions(administrator=True)
@app_commands.checks.cooldown(1, 5.0)
async def logs_setup_cmd(interaction: discord.Interaction, mode: Choice[str], channel: discord.TextChannel = None):
    guild = interaction.guild
    cfg = get_cfg(guild.id)
    lc = cfg.setdefault("LOGS_CONFIG", {})

    if mode.value == "manual":
        if not channel:
            return await interaction.response.send_message("❌ For manual mode, specify a channel using `channel` parameter.", ephemeral=True)
        lc["MODE"] = "manual"
        lc["CHANNEL_ID"] = channel.id
        await save_cfg(guild.id)
        return await interaction.response.send_message(embed=build_logs_embed(guild.id), view=LogsSetupView(guild.id))

    await interaction.response.defer(ephemeral=True)
    try:
        category = discord.utils.get(guild.categories, name="Logs") or await guild.create_category("Logs")
        channels = {}
        for key, chname in LOGS_BUCKET_NAMES.items():
            existing = discord.utils.get(category.channels, name=chname)
            ch = existing or await guild.create_text_channel(chname, category=category)
            channels[key] = ch.id
        lc["MODE"] = "auto"
        lc["CHANNELS"] = channels
        await save_cfg(guild.id)
        await interaction.followup.send(embed=build_logs_embed(guild.id), view=LogsSetupView(guild.id))
    except discord.Forbidden:
        await interaction.followup.send("❌ Missing permissions to create channels ('Manage Channels' required).")

@bot.tree.command(name="verify_setup", description="✅ Setup Server Verification")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.cooldown(1, 3.0)
async def verify_cmd(interaction: discord.Interaction, role: discord.Role, channel: discord.TextChannel = None):
    cfg = get_cfg(interaction.guild.id)
    vc = cfg.setdefault("VERIFY_CONFIG", {})
    vc.update({"ROLE_ID": role.id, "ENABLED": True})
    target = channel or interaction.channel
    vc["CHANNEL_ID"] = target.id
    await save_cfg(interaction.guild.id)
    await interaction.response.send_message(embed=build_verify_config_embed(interaction.guild.id), view=VerifyConfigView(interaction.guild.id), ephemeral=True)

@bot.tree.command(name="embed_color", description="🎨 Set Bot Embed Color")
@app_commands.checks.has_permissions(manage_guild=True)
async def embed_color_cmd(interaction: discord.Interaction, hex_color: str):
    value = hex_color.strip().removeprefix("#").removeprefix("0x")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        return await interaction.response.send_message("❌ Use HEX format like `#5865F2`.", ephemeral=True)
    cfg = get_cfg(interaction.guild.id)
    cfg["EMBED_COLOR"] = int(value, 16)
    cfg.setdefault("VERIFY_CONFIG", {})["EMBED_COLOR"] = int(value, 16)
    await save_cfg(interaction.guild.id)
    await interaction.response.send_message(embed=discord.Embed(title="🎨 Color Updated", description=f"New color: `#{value.upper()}`", color=int(value, 16)), ephemeral=True)

@bot.tree.command(name="tagrole_config", description="🏷️ Configure Auto-Role by Nickname Tag")
@app_commands.checks.has_permissions(manage_guild=True)
async def tagrole_config_cmd(interaction: discord.Interaction, tag: str, role: discord.Role, enabled: bool = True):
    if role.is_default() or (interaction.guild.me and interaction.guild.me.top_role <= role):
        return await interaction.response.send_message("❌ Role must be below bot's top role and cannot be @everyone.", ephemeral=True)
    cfg = get_cfg(interaction.guild.id)
    cfg["TAG_ROLE_CONFIG"] = {"ENABLED": enabled, "TAG": tag[:32], "ROLE_ID": role.id}
    await save_cfg(interaction.guild.id)
    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(f"🏷️ Tag auto-role {state}. Tag: `{discord.utils.escape_markdown(tag[:32])}`, Role: {role.mention}.", ephemeral=True)

@bot.tree.command(name="autorole", description="🧩 Configure Auto-Role assigned on join")
@app_commands.checks.has_permissions(manage_guild=True)
async def autorole_cmd(interaction: discord.Interaction, role: discord.Role, enabled: bool = True):
    if role.is_default() or (interaction.guild.me and interaction.guild.me.top_role <= role):
        return await interaction.response.send_message("❌ Role must be below bot's top role and cannot be @everyone.", ephemeral=True)
    cfg = get_cfg(interaction.guild.id)
    cfg["AUTOROLE_CONFIG"] = {"ENABLED": enabled, "ROLE_ID": role.id}
    await save_cfg(interaction.guild.id)
    state = "enabled" if enabled else "disabled"
    await interaction.response.send_message(f"🧩 Auto-role {state}. Role: {role.mention}.", ephemeral=True)

@bot.tree.command(name="welcome_settings", description="👋 Configure Welcome and Goodbye messages")
@app_commands.checks.has_permissions(manage_guild=True)
async def welcome_settings_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(embed=build_welcome_embed(interaction.guild.id), view=WelcomeMainView(interaction.guild.id))

@bot.tree.command(name="antitoken_config", description="🛡️ Configure Anti-Token Message Rate Limits")
@app_commands.checks.has_permissions(manage_guild=True)
async def antitoken_config_cmd(interaction: discord.Interaction, enabled: bool,
                                max_messages: app_commands.Range[int, 3, 20] = 6,
                                window_seconds: app_commands.Range[int, 2, 15] = 5,
                                timeout_minutes: app_commands.Range[int, 1, 1440] = 10):
    cfg = get_cfg(interaction.guild.id)
    cfg["ANTITOKEN_CONFIG"].update({"ENABLED": enabled, "MAX_MESSAGES": max_messages, "WINDOW_SECONDS": window_seconds, "TIMEOUT_MINUTES": timeout_minutes})
    await save_cfg(interaction.guild.id)
    await interaction.response.send_message(f"🛡️ Anti-token {'enabled' if enabled else 'disabled'}: {max_messages} msgs in {window_seconds}s; Timeout {timeout_minutes}m", ephemeral=True)

@bot.tree.command(name="warn", description="⚠️ Issue a warning to a member")
@app_commands.default_permissions(manage_messages=True)
@app_commands.checks.cooldown(1, 2.0)
async def warn_cmd(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    if member.bot:
        return await interaction.response.send_message("❌ Cannot warn a bot!", ephemeral=True)
    cfg = get_cfg(interaction.guild.id)
    db  = get_warns(interaction.guild.id)
    uid = str(member.id)
    if uid not in db:
        db[uid] = []
    db[uid].append({"reason": reason, "moderator": interaction.user.id, "ts": str(datetime.utcnow())})
    await save_warns(interaction.guild.id)
    cnt = len(db[uid])
    await send_dm(member, f"Warning #{cnt}", interaction.guild.name, reason)
    e = discord.Embed(title="⚠️ Warning Issued", color=discord.Color.gold(), timestamp=datetime.utcnow())
    e.add_field(name="User", value=member.mention)
    e.add_field(name="Total Warns", value=f"`{cnt}`")
    e.add_field(name="Reason", value=reason, inline=False)
    await interaction.response.send_message(embed=e)
    action_info = cfg.get("WARN_ACTIONS", {}).get(str(cnt))
    if action_info:
        act  = action_info.get("action")
        mins = action_info.get("mute_minutes", 60)
        try:
            if act == "kick":
                await member.kick(reason=f"[Auto-Warn] {cnt} warnings")
            elif act == "ban":
                await member.ban(reason=f"[Auto-Warn] {cnt} warnings")
            elif act == "mute":
                await member.timeout(timedelta(minutes=mins), reason=f"[Auto-Warn] {cnt} warnings")
                await send_log(interaction.guild, "MUTES", discord.Embed(title="🔇 Auto-Mute for Warnings", description=f"{member.mention} — timed out for {mins}m.", color=discord.Color.orange()))
        except discord.Forbidden:
            pass

@bot.tree.command(name="warn_config", description="⚙️ Configure auto-punishments for warnings")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.cooldown(1, 3.0)
async def warn_config_cmd(interaction: discord.Interaction):
    cfg = get_cfg(interaction.guild.id)
    wa  = cfg.get("WARN_ACTIONS", {})
    e = discord.Embed(
        title="⚠️ Warnings Configuration",
        description="\n".join(f"▫️ **{k} warns:** `{v.get('action','?').upper()}`" for k, v in sorted(wa.items(), key=lambda x: int(x[0]))),
        color=get_embed_color(interaction.guild.id)
    )
    await interaction.response.send_message(embed=e, view=WarnConfigView(interaction.guild.id))

@bot.tree.command(name="ban", description="🔨 Ban a member")
@app_commands.default_permissions(ban_members=True)
@app_commands.checks.cooldown(1, 2.0)
async def ban_cmd(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await send_dm(member, "BAN 🔨", interaction.guild.name, reason)
    await member.ban(reason=reason)
    await send_log(interaction.guild, "BANS", discord.Embed(title="🔨 Ban", description=f"{member.mention} — banned by {interaction.user.mention}.\nReason: {reason}", color=discord.Color.dark_red()))
    await interaction.response.send_message(f"🔨 Banned {member.mention}. Reason: `{reason}`")

@bot.tree.command(name="kick", description="👢 Kick a member")
@app_commands.default_permissions(kick_members=True)
@app_commands.checks.cooldown(1, 2.0)
async def kick_cmd(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    await send_dm(member, "KICK 👢", interaction.guild.name, reason)
    await member.kick(reason=reason)
    await send_log(interaction.guild, "KICKS", discord.Embed(title="👢 Kick", description=f"{member.mention} — kicked by {interaction.user.mention}.\nReason: {reason}", color=discord.Color.orange()))
    await interaction.response.send_message(f"👢 Kicked {member.mention}. Reason: `{reason}`")

@bot.tree.command(name="mute", description="🔇 Timeout a member")
@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.cooldown(1, 2.0)
async def mute_cmd(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "No reason provided"):
    await member.timeout(timedelta(minutes=minutes), reason=reason)
    await send_dm(member, f"MUTE {minutes}m 🔇", interaction.guild.name, reason)
    await send_log(interaction.guild, "MUTES", discord.Embed(title="🔇 Mute", description=f"{member.mention} — timed out for {minutes}m by {interaction.user.mention}.\nReason: {reason}", color=discord.Color.orange()))
    await interaction.response.send_message(f"🔇 {member.mention} timed out for `{minutes}` minutes.")

@bot.tree.command(name="unmute", description="🔊 Remove timeout from a member")
@app_commands.default_permissions(moderate_members=True)
@app_commands.checks.cooldown(1, 2.0)
async def unmute_cmd(interaction: discord.Interaction, member: discord.Member):
    await member.timeout(None)
    await send_log(interaction.guild, "MUTES", discord.Embed(title="🔊 Timeout Removed", description=f"{member.mention} — timeout removed by {interaction.user.mention}.", color=discord.Color.green()))
    await interaction.response.send_message(f"🔊 Timeout removed from {member.mention}.")

@bot.tree.command(name="massban", description="🔨 Mass ban up to 5 users")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.cooldown(1, 5.0)
async def massban_cmd(interaction: discord.Interaction,
                      u1: discord.User, u2: discord.User = None, u3: discord.User = None,
                      u4: discord.User = None, u5: discord.User = None, reason: str = "Mass ban"):
    if not is_whitelisted(interaction.user.id, interaction.guild):
        return await interaction.response.send_message("❌ Access restricted to whitelisted users!", ephemeral=True)
    users  = [u for u in [u1, u2, u3, u4, u5] if u]
    banned = []
    for u in users:
        try:
            await interaction.guild.ban(u, reason=f"[Mass Ban] {reason}")
            banned.append(u.mention)
        except discord.Forbidden:
            pass
    await interaction.response.send_message(f"🔨 Banned `{len(banned)}`: {', '.join(banned)}")

@bot.tree.command(name="massunban", description="🔓 Mass unban up to 5 users")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.cooldown(1, 5.0)
async def massunban_cmd(interaction: discord.Interaction,
                        u1: discord.User, u2: discord.User = None, u3: discord.User = None,
                        u4: discord.User = None, u5: discord.User = None):
    if not is_whitelisted(interaction.user.id, interaction.guild):
        return await interaction.response.send_message("❌ Access restricted to whitelisted users!", ephemeral=True)
    users    = [u for u in [u1, u2, u3, u4, u5] if u]
    unbanned = []
    for u in users:
        try:
            await interaction.guild.unban(u)
            unbanned.append(f"`{u.name}`")
        except (discord.NotFound, discord.Forbidden):
            pass
    await interaction.response.send_message(f"🔓 Unbanned `{len(unbanned)}`: {', '.join(unbanned)}")

@bot.tree.command(name="masskick", description="👢 Mass kick up to 5 users")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.cooldown(1, 5.0)
async def masskick_cmd(interaction: discord.Interaction,
                       m1: discord.Member, m2: discord.Member = None, m3: discord.Member = None,
                       m4: discord.Member = None, m5: discord.Member = None, reason: str = "Mass kick"):
    if not is_whitelisted(interaction.user.id, interaction.guild):
        return await interaction.response.send_message("❌ Access restricted to whitelisted users!", ephemeral=True)
    members = [m for m in [m1, m2, m3, m4, m5] if m]
    kicked  = []
    for m in members:
        try:
            await m.kick(reason=f"[Mass Kick] {reason}")
            kicked.append(m.mention)
        except discord.Forbidden:
            pass
    await interaction.response.send_message(f"👢 Kicked `{len(kicked)}`: {', '.join(kicked)}")

@bot.tree.command(name="massmute", description="🔇 Mass timeout up to 5 users")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.cooldown(1, 5.0)
async def massmute_cmd(interaction: discord.Interaction, minutes: int,
                       m1: discord.Member, m2: discord.Member = None, m3: discord.Member = None,
                       m4: discord.Member = None, m5: discord.Member = None, reason: str = "Mass mute"):
    if not is_whitelisted(interaction.user.id, interaction.guild):
        return await interaction.response.send_message("❌ Access restricted to whitelisted users!", ephemeral=True)
    members = [m for m in [m1, m2, m3, m4, m5] if m]
    muted   = []
    for m in members:
        try:
            await m.timeout(timedelta(minutes=minutes), reason=f"[Mass Mute] {reason}")
            muted.append(m.mention)
        except discord.Forbidden:
            pass
    await interaction.response.send_message(f"🔇 Timed out for `{minutes}`m: `{len(muted)}` users: {', '.join(muted)}")

@bot.tree.command(name="massunmute", description="🔊 Mass remove timeout up to 5 users")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.cooldown(1, 5.0)
async def massunmute_cmd(interaction: discord.Interaction,
                         m1: discord.Member, m2: discord.Member = None, m3: discord.Member = None,
                         m4: discord.Member = None, m5: discord.Member = None):
    if not is_whitelisted(interaction.user.id, interaction.guild):
        return await interaction.response.send_message("❌ Access restricted to whitelisted users!", ephemeral=True)
    members = [m for m in [m1, m2, m3, m4, m5] if m]
    done    = []
    for m in members:
        try:
            await m.timeout(None)
            done.append(m.mention)
        except discord.Forbidden:
            pass
    await interaction.response.send_message(f"🔊 Timeout removed for `{len(done)}`: {', '.join(done)}")

@bot.tree.command(name="delete", description="🧹 Purge messages (1-1000)")
@app_commands.default_permissions(manage_messages=True)
@app_commands.checks.cooldown(1, 5.0)
async def delete_cmd(interaction: discord.Interaction, amount: int):
    if amount < 1 or amount > 1000:
        return await interaction.response.send_message("❌ Specify a number between 1 and 1000!", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    total, remaining = 0, amount
    while remaining > 0:
        batch = min(remaining, 100)
        try:
            deleted = await interaction.channel.purge(limit=batch)
            total += len(deleted)
            remaining -= batch
            if total % 200 == 0 and remaining > 0:
                await interaction.edit_original_response(content=f"⏳ Deleted `{total}/{amount}`...")
            if len(deleted) < batch:
                break
            await asyncio.sleep(1)
        except discord.Forbidden:
            return await interaction.followup.send("❌ Missing permissions!")
        except Exception:
            break
    await interaction.followup.send(f"🧹 Purged `{total}` messages!")

@bot.tree.command(name="delspam", description="💥 Delete spam messages by member or keyword")
@app_commands.default_permissions(manage_messages=True)
@app_commands.checks.cooldown(1, 3.0)
async def delspam_cmd(interaction: discord.Interaction, member: discord.Member = None, keyword: str = None, limit: int = 100):
    await interaction.response.defer(ephemeral=True)

    def check(msg):
        if member and msg.author.id != member.id:
            return False
        if keyword and keyword.lower() not in msg.content.lower():
            return False
        return True
    try:
        deleted = await interaction.channel.purge(limit=limit, check=check)
        await interaction.followup.send(f"💥 Deleted `{len(deleted)}` messages!")
    except discord.Forbidden:
        await interaction.followup.send("❌ Missing permissions!")

@bot.tree.command(name="delroles", description="🎭 Bulk delete roles")
@app_commands.describe(mode="unused — delete empty roles, target — delete specific role")
@app_commands.default_permissions(manage_roles=True)
@app_commands.checks.cooldown(1, 5.0)
async def delroles_cmd(interaction: discord.Interaction, mode: str, target_role: discord.Role = None):
    if mode == "unused":
        await interaction.response.defer()
        deleted = 0
        for role in list(interaction.guild.roles):
            if len(role.members) == 0 and not role.is_default() and not role.managed:
                try:
                    await role.delete(reason="[Delete Roles] Empty role")
                    deleted += 1
                except discord.Forbidden:
                    pass
        await interaction.followup.send(f"🧹 Deleted `{deleted}` empty roles.")
    elif mode == "target" and target_role:
        try:
            name = target_role.name
            await target_role.delete(reason="[Delete Roles]")
            await interaction.response.send_message(f"🗑️ Role `{name}` deleted!")
        except discord.Forbidden:
            await interaction.response.send_message("❌ Missing permissions!", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Specify `unused` or `target` along with a role!", ephemeral=True)

@bot.tree.command(name="massdel_channel", description="🔥 Mass delete channels by name prefix")
@app_commands.default_permissions(manage_channels=True)
@app_commands.checks.cooldown(1, 5.0)
async def massdel_channel_cmd(interaction: discord.Interaction, prefix: str):
    if not is_whitelisted(interaction.user.id, interaction.guild):
        return await interaction.response.send_message("❌ Access restricted to whitelisted users!", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    count = 0
    for ch in list(interaction.guild.channels):
        if ch.name.startswith(prefix):
            try:
                await ch.delete(reason="[Mass Channel Deletion]")
                count += 1
            except discord.Forbidden:
                pass
    await interaction.followup.send(f"🔥 Deleted `{count}` channels starting with prefix `{prefix}`.")

@bot.tree.command(name="serverinfo", description="🏰 Server information")
@app_commands.checks.cooldown(1, 3.0)
async def serverinfo_cmd(interaction: discord.Interaction):
    g = interaction.guild
    e = discord.Embed(title=f"🏰 {g.name}", color=get_embed_color(g.id), timestamp=datetime.utcnow())
    if g.icon:
        e.set_thumbnail(url=g.icon.url)
    e.add_field(name="👑 Owner", value=f"<@{g.owner_id}>")
    e.add_field(name="🆔 ID", value=f"`{g.id}`")
    e.add_field(name="📅 Created", value=f"<t:{int(g.created_at.timestamp())}:R>")
    e.add_field(name="👥 Members", value=f"`{g.member_count}`")
    e.add_field(name="🎭 Roles", value=f"`{len(g.roles)}`")
    e.add_field(name="📁 Channels", value=f"`{len(g.channels)}`")
    e.add_field(name="🚀 Boosts", value=f"`{g.premium_subscription_count}` (Level {g.premium_tier})")
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="userinfo", description="👤 User profile information")
@app_commands.checks.cooldown(1, 3.0)
async def userinfo_cmd(interaction: discord.Interaction, member: discord.Member = None):
    t    = member or interaction.user
    risk = calculate_account_risk_score(t)
    e = discord.Embed(title=f"👤 {t.name}", color=get_embed_color(interaction.guild.id), timestamp=datetime.utcnow())
    e.set_thumbnail(url=t.display_avatar.url)
    e.add_field(name="🆔 ID", value=f"`{t.id}`")
    e.add_field(name="🤖 Bot?", value="Yes" if t.bot else "No")
    e.add_field(name="👑 Whitelisted?", value="Yes" if is_whitelisted(t.id, interaction.guild) else "No")
    e.add_field(name="📅 Account Created", value=f"<t:{int(t.created_at.timestamp())}:R>", inline=False)
    if isinstance(t, discord.Member) and t.joined_at:
        e.add_field(name="📥 Joined Server", value=f"<t:{int(t.joined_at.timestamp())}:R>", inline=False)
        roles = [r.mention for r in t.roles if not r.is_default()]
        e.add_field(name=f"🎭 Roles ({len(roles)})", value=", ".join(roles[:10]) if roles else "None", inline=False)
    e.add_field(name="⚠️ Risk Score", value=f"`{risk}/100`", inline=False)
    await interaction.response.send_message(embed=e)

@bot.tree.command(name="banlist", description="📜 List server bans")
@app_commands.default_permissions(ban_members=True)
@app_commands.checks.cooldown(1, 5.0)
async def banlist_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        bans = [entry async for entry in interaction.guild.bans(limit=25)]
        if not bans:
            return await interaction.followup.send("📜 No bans found.")
        desc = [f"▫️ **{b.user.name}** (`{b.user.id}`) — {b.reason or '—'}" for b in bans]
        e = discord.Embed(title=f"🔨 Bans List ({len(bans)})", description="\n".join(desc),
                          color=get_embed_color(interaction.guild.id))
        await interaction.followup.send(embed=e)
    except discord.Forbidden:
        await interaction.followup.send("❌ Missing permissions!")

@bot.tree.command(name="language", description="🌐 Change interface language")
@app_commands.default_permissions(administrator=True)
@app_commands.checks.cooldown(1, 3.0)
async def language_cmd(interaction: discord.Interaction, lang: str):
    cfg = get_cfg(interaction.guild.id)
    if lang.lower() in ["ru", "russian", "русский"]:
        cfg["CURRENT_LANG"] = "ru"
        await save_cfg(interaction.guild.id)
        await interaction.response.send_message("🌐 Language changed to **Русский**", ephemeral=True)
    elif lang.lower() in ["en", "english"]:
        cfg["CURRENT_LANG"] = "en"
        await save_cfg(interaction.guild.id)
        await interaction.response.send_message("🌐 Language changed to **English**", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Select `ru` or `en`", ephemeral=True)

@bot.tree.command(name="ping", description="🏓 Check bot latency")
@app_commands.checks.cooldown(1, 5.0)
async def ping_cmd(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    color   = discord.Color.green() if latency < 100 else discord.Color.orange() if latency < 200 else discord.Color.red()
    e = discord.Embed(title="🏓 Pong!", description=f"**Latency:** `{latency}ms`", color=color)
    await interaction.response.send_message(embed=e)


class InfoCategorySelect(ui.Select):
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        options = [
            discord.SelectOption(label="🛡️ Security",     value="sec"),
            discord.SelectOption(label="🔨 Moderation",   value="mod"),
            discord.SelectOption(label="🎨 Settings",     value="cfg"),
        ]
        super().__init__(placeholder="Select a category...", options=options)

    async def callback(self, interaction: discord.Interaction):
        e = discord.Embed(color=get_embed_color(interaction.guild.id))
        if self.values[0] == "sec":
            e.title = "🛡️ Security"
            e.description = (
                "▫️ `/antinuke` — Anti-Nuke panel\n"
                "▫️ `/antiraid` — Anti-Raid panel\n"
                "▫️ `/antibot` — Block unauthorized bots\n"
                "▫️ `/whitelist` — Whitelist management (add/remove/category_add/category_remove/list/panel)\n"
                "▫️ `/antilink_config` — Link protection\n"
                "▫️ `/antispotify_config` — Spotify protection\n"
                "▫️ `/ai_panel` — AI scanners\n"
                "▫️ `/security_settings` — Security audit\n"
                "▫️ `/risk` — Server risk score\n"
                "▫️ `/panic` — Panic mode"
            )
        elif self.values[0] == "mod":
            e.title = "🔨 Moderation"
            e.description = (
                "▫️ `/ban` `/kick` `/mute` `/unmute` — Standard punishments\n"
                "▫️ `/massban` `/massunban` — Mass ban/unban up to 5\n"
                "▫️ `/masskick` `/massmute` `/massunmute` — Mass kick/mute/unmute up to 5\n"
                "▫️ `/warn` `/warn_config` — Warns & auto punishments\n"
                "▫️ `/delete` — Purge 1-1000 messages\n"
                "▫️ `/delspam` — Targeted spam cleanup\n"
                "▫️ `/delroles` — Role deletion\n"
                "▫️ `/massdel_channel` — Mass channel deletion by prefix\n"
                "▫️ `/banlist` — Bans list"
            )
        else:
            e.title = "🎨 Settings"
            e.description = (
                "▫️ `/serverinfo` — Server information\n"
                "▫️ `/userinfo` — Member profile & risk score\n"
                "▫️ `/logs_setup` — Configure logs (Auto/Manual)\n"
                "▫️ `/verify_setup` — Verification setup\n"
                "▫️ `/autorole` — Auto role on join\n"
                "▫️ `/welcome_settings` — Welcome & goodbye messages\n"
                "▫️ `/tagrole_config` — Tag auto-role\n"
                "▫️ `/embed_color` — Embed color\n"
                "▫️ `/language` — Interface language\n"
                "▫️ `/ping` — Bot latency"
            )
        await interaction.response.edit_message(embed=e)

class InfoView(ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.add_item(InfoCategorySelect(guild_id))

@bot.tree.command(name="info", description="ℹ️ Command Help Directory")
@app_commands.checks.cooldown(1, 3.0)
async def info_cmd(interaction: discord.Interaction):
    e = discord.Embed(
        title="🤖 Command Directory",
        description="Select a category from the dropdown menu below.",
        color=get_embed_color(interaction.guild.id)
    )
    e.set_thumbnail(url=bot.user.display_avatar.url if bot.user else None)
    await interaction.response.send_message(embed=e, view=InfoView(interaction.guild.id))


# ==========================================================
# 🚀 11. BOT LAUNCH & INITIALIZATION
# ==========================================================

@bot.event
async def on_ready():
    activity = discord.Activity(type=discord.ActivityType.watching, name="/info | /security_settings")
    await bot.change_presence(status=discord.Status.dnd, activity=activity)

    if not getattr(bot, "_persistent_views_registered", False):
        bot.add_view(VerifyPublicView())
        bot._persistent_views_registered = True
    if not cleanup_trackers.is_running():
        cleanup_trackers.start()
    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} commands!")
    except Exception as e:
        print(f"❌ Sync error: {e}")
    print(f"🛡️ Bot [{bot.user}] is online across {len(bot.guilds)} servers!")

async def main():
    if not TOKEN:
        print("❌ DISCORD_TOKEN is not set!")
        return
    async with bot:
        asyncio.create_task(start_web())
        await bot.start(TOKEN, reconnect=True)

if __name__ == "__main__":
    asyncio.run(main())