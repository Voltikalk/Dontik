"""
Коллекция Telegram Premium эмодзи из пака Telegram iOS Icons (https://emoji.wivvi.net)
Содержит ID и готовые теги <tg-emoji> для разметки HTML и инлайн/обычных кнопок.
"""

def tg_emoji(emoji_id: str, fallback: str) -> str:
    """Формирует валидный тег <tg-emoji> для Telegram Bot API с HTML разметкой."""
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


# --- Идентификаторы эмодзи для кнопок (icon_custom_emoji_id) ---
ID_TELEGRAM = "6028346797368283073"   # ✈️
ID_SETTINGS = "6032742198179532882"   # ⚙
ID_LINK = "6028171274939797252"       # 🔗
ID_CHECK = "5774022692642492953"      # ✅
ID_CROSS = "5774077015388852135"      # ❌
ID_LOCK_CLOSED = "6037249452824072506"# 🔒
ID_LOCK_OPEN = "6037496202990194718"  # 🔓
ID_BOT = "6030400221232501136"        # 🤖
ID_TRASH = "6039522349517115015"      # 🗑
ID_DOWNLOAD = "6039802767931871481"   # ⬇️
ID_UPLOAD = "6039391666547201160"     # ⬆️
ID_BELL = "6039486778597970865"       # 🔔
ID_CAMERA = "6048390817033228573"     # 📷
ID_MIC = "6030722571412967168"        # 🎤
ID_VOICE_TEXT = "5933678317935791830" # 🎤
ID_CALL = "6039605143601680423"       # 📞
ID_MESSAGE = "6030784887093464891"    # 💬
ID_CHATS = "6037421444789440735"      # 💬
ID_PROFILE = "6035084557378654059"    # 👤
ID_USERS = "6032609071373226027"      # 👥
ID_PARTY = "6041731551845159060"      # 🎉
ID_LIKE = "6041720006973067267"       # 👍
ID_LOCATION = "6042011682497106307"   # 📍
ID_HOME = "6042137469204303531"       # 🏠
ID_LIGHTNING = "5884428842780594914"  # ⚡
ID_BULB = "5767288287001580715"       # 💡
ID_PIN = "6043896193887506430"        # 📌
ID_WRENCH = "5962952497197748583"     # 🔧
ID_CHART = "5936143551854285132"      # 📊
ID_GROWTH = "5938539885907415367"     # 📈
ID_GLOBE = "5776233299424843260"      # 🌐
ID_CALENDAR = "5890937706803894250"   # 📅
ID_WALLET = "5769126056262898415"     # 👛
ID_SEARCH = "6032850693348399258"     # 🔎
ID_INFO = "6028435952299413210"       # ℹ
ID_GIFT = "6032644646587338669"       # 🎁
ID_BACK = "5960671702059848143"       # ⬅️
ID_REPEAT = "6030657343744644592"     # 🔁
ID_EXIT = "6035130900075777681"       # 🚪
ID_FILE = "6037475557082403885"       # 📁
ID_DOC = "6050643982646513651"        # 📄
ID_FOLDER = "6039630677182254664"     # 📂
ID_INBOX = "5776182936638329359"      # 📥
ID_OUTBOX = "6039573425268201570"     # 📤
ID_HORN = "6021418126061605425"       # 📢
ID_MUTE = "6039505337151655702"       # 🔇
ID_CLOCK = "5983150113483134607"      # ⏰️
ID_STOPWATCH = "6037268453759389862"  # ⏲️
ID_HELLO = "6041921818896372382"      # 👋
ID_THINK = "6043960760130868895"      # 🤔
ID_ALERT = "6030563507299160824"      # ❗️
ID_QUESTION = "6030848053177486888"   # ❓
ID_BOX = "5884479287171485878"        # 📦
ID_MEDIA_PHOTO = "6030466823290360017"# 🖼
ID_NOTE = "5778299625370817409"       # 📝
ID_LIST = "5766994197705921104"       # 🗂
ID_SPEEDOMETER = "6030537810509828330"# ⏲
ID_DROP = "6050632433479455053"       # 💧
ID_AI = "5940660740758184142"         # ✨
ID_PEN = "6042134354384497423"        # ✏️


# --- Готовые HTML теги <tg-emoji> для текстов сообщений ---
E_TELEGRAM = tg_emoji(ID_TELEGRAM, "✈️")
E_SETTINGS = tg_emoji(ID_SETTINGS, "⚙")
E_LINK = tg_emoji(ID_LINK, "🔗")
E_CHECK = tg_emoji(ID_CHECK, "✅")
E_CROSS = tg_emoji(ID_CROSS, "❌")
E_LOCK = tg_emoji(ID_LOCK_CLOSED, "🔒")
E_LOCK_OPEN = tg_emoji(ID_LOCK_OPEN, "🔓")
E_BOT = tg_emoji(ID_BOT, "🤖")
E_TRASH = tg_emoji(ID_TRASH, "🗑")
E_DOWNLOAD = tg_emoji(ID_DOWNLOAD, "⬇️")
E_UPLOAD = tg_emoji(ID_UPLOAD, "⬆️")
E_BELL = tg_emoji(ID_BELL, "🔔")
E_CAMERA = tg_emoji(ID_CAMERA, "📷")
E_MIC = tg_emoji(ID_MIC, "🎤")
E_VOICE_TEXT = tg_emoji(ID_VOICE_TEXT, "🎤")
E_CALL = tg_emoji(ID_CALL, "📞")
E_MESSAGE = tg_emoji(ID_MESSAGE, "💬")
E_CHATS = tg_emoji(ID_CHATS, "💬")
E_PROFILE = tg_emoji(ID_PROFILE, "👤")
E_USERS = tg_emoji(ID_USERS, "👥")
E_PARTY = tg_emoji(ID_PARTY, "🎉")
E_LIKE = tg_emoji(ID_LIKE, "👍")
E_LOCATION = tg_emoji(ID_LOCATION, "📍")
E_HOME = tg_emoji(ID_HOME, "🏠")
E_LIGHTNING = tg_emoji(ID_LIGHTNING, "⚡")
E_BULB = tg_emoji(ID_BULB, "💡")
E_PIN = tg_emoji(ID_PIN, "📌")
E_WRENCH = tg_emoji(ID_WRENCH, "🔧")
E_CHART = tg_emoji(ID_CHART, "📊")
E_GROWTH = tg_emoji(ID_GROWTH, "📈")
E_GLOBE = tg_emoji(ID_GLOBE, "🌐")
E_CALENDAR = tg_emoji(ID_CALENDAR, "📅")
E_WALLET = tg_emoji(ID_WALLET, "👛")
E_SEARCH = tg_emoji(ID_SEARCH, "🔎")
E_INFO = tg_emoji(ID_INFO, "ℹ")
E_GIFT = tg_emoji(ID_GIFT, "🎁")
E_BACK = tg_emoji(ID_BACK, "⬅️")
E_REPEAT = tg_emoji(ID_REPEAT, "🔁")
E_EXIT = tg_emoji(ID_EXIT, "🚪")
E_FILE = tg_emoji(ID_FILE, "📁")
E_DOC = tg_emoji(ID_DOC, "📄")
E_FOLDER = tg_emoji(ID_FOLDER, "📂")
E_INBOX = tg_emoji(ID_INBOX, "📥")
E_OUTBOX = tg_emoji(ID_OUTBOX, "📤")
E_HORN = tg_emoji(ID_HORN, "📢")
E_MUTE = tg_emoji(ID_MUTE, "🔇")
E_CLOCK = tg_emoji(ID_CLOCK, "⏰️")
E_STOPWATCH = tg_emoji(ID_STOPWATCH, "⏲️")
E_HELLO = tg_emoji(ID_HELLO, "👋")
E_THINK = tg_emoji(ID_THINK, "🤔")
E_ALERT = tg_emoji(ID_ALERT, "❗️")
E_QUESTION = tg_emoji(ID_QUESTION, "❓")
E_BOX = tg_emoji(ID_BOX, "📦")
E_PHOTO = tg_emoji(ID_MEDIA_PHOTO, "🖼")
E_NOTE = tg_emoji(ID_NOTE, "📝")
E_LIST = tg_emoji(ID_LIST, "🗂")
E_SPEEDOMETER = tg_emoji(ID_SPEEDOMETER, "⏲")
E_DROP = tg_emoji(ID_DROP, "💧")
E_AI = tg_emoji(ID_AI, "✨")
