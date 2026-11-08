import os
import logging
import sqlite3
import random
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler
)

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import arabic_reshaper
from bidi.algorithm import get_display

# تحميل متغيرات البيئة محلياً (لو ملف .env موجود)
load_dotenv()

# قراءة التوكن والآي دي سواء من ملف محلي أو من إعدادات السيرفر السحابي
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_TELEGRAM_ID = os.getenv("OWNER_TELEGRAM_ID")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("⚠️ يا باشا، توكن البوت مش موجود! تأكد من إضافته في ملف .env محلياً أو في إعدادات السيرفر.")

if OWNER_TELEGRAM_ID:
    OWNER_TELEGRAM_ID = int(str(OWNER_TELEGRAM_ID).strip())

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# حالات محادثة الحجز وأرشيف الأعطال
DEVICE_MODEL, DEVICE_ISSUE = range(2)
ARCHIVE_MODEL, ARCHIVE_ISSUE, ARCHIVE_SOLUTION, SEARCH_ARCHIVE = range(10, 14)

# =====================================================================
# 🗄️ إعداد قاعدة البيانات (SQLite Database Setup)
# =====================================================================
def init_db():
    conn = sqlite3.connect("workshop.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id TEXT PRIMARY KEY,
            user_id INTEGER,
            user_name TEXT,
            model TEXT,
            issue TEXT,
            status TEXT,
            created_at TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            ticket_id TEXT,
            user_id INTEGER,
            rating INTEGER,
            feedback TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS solutions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model TEXT,
            issue TEXT,
            solution TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def db_add_ticket(ticket_id, user_id, user_name, model, issue):
    conn = sqlite3.connect("workshop.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ticket_id, user_id, user_name, model, issue, "🔄 الجهاز وصل الورشة وجاري فحصه", datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    conn.commit()
    conn.close()

def db_get_ticket(ticket_id):
    conn = sqlite3.connect("workshop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def db_update_status(ticket_id, new_status):
    conn = sqlite3.connect("workshop.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE tickets SET status = ? WHERE ticket_id = ?", (new_status, ticket_id))
    conn.commit()
    conn.close()

def db_get_all_tickets():
    conn = sqlite3.connect("workshop.db")
    cursor = conn.cursor()
    cursor.execute("SELECT ticket_id, user_name, model, status FROM tickets")
    rows = cursor.fetchall()
    conn.close()
    return rows

def db_add_solution(model, issue, solution):
    conn = sqlite3.connect("workshop.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO solutions (model, issue, solution, created_at) VALUES (?, ?, ?, ?)",
                   (model, issue, solution, datetime.now().strftime("%Y-%m-%d")))
    conn.commit()
    conn.close()

def db_search_solutions(keyword):
    conn = sqlite3.connect("workshop.db")
    cursor = conn.cursor()
    keyword_pattern = f"%{keyword}%"
    cursor.execute("SELECT model, issue, solution, created_at FROM solutions WHERE model LIKE ? OR issue LIKE ? OR solution LIKE ?",
                   (keyword_pattern, keyword_pattern, keyword_pattern))
    rows = cursor.fetchall()
    conn.close()
    return rows

# =====================================================================
# 🔤 دالة ضبط النصوص العربية (من اليمين لليسار)
# =====================================================================
def fix_arabic(text):
    try:
        reshaped_text = arabic_reshaper.reshape(text)
        bidi_text = get_display(reshaped_text)
        return bidi_text
    except:
        return text

# =====================================================================
# 📄 دالة توليد فاتورة PDF احترافية بالعربي (باسم أبانوب عاطف)
# =====================================================================
def generate_arabic_invoice(ticket_id, customer_name, model, issue, price, notes):
    filename = f"Invoice_{ticket_id}.pdf"
    c = canvas.Canvas(filename, pagesize=letter)
    width, height = letter

    try:
        pdfmetrics.registerFont(TTFont('ArabicFont', 'arial.ttf'))
        font_name = 'ArabicFont'
    except:
        font_name = 'Helvetica'

    c.setStrokeColorRGB(0.1, 0.1, 0.3)
    c.setLineWidth(2)
    c.rect(30, 30, width - 60, height - 60)

    c.setFont(font_name, 18)
    c.setFillColorRGB(0.1, 0.1, 0.3)
    c.drawCentredString(width / 2, height - 65, fix_arabic("ورشة لي لي / الكينج لصيانة الهواتف الذكية"))
    
    c.setFont(font_name, 10)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.drawCentredString(width / 2, height - 85, fix_arabic("الإسكندرية، باكوس - بجوار مكتبة الهلال | تليفون وواتساب: 01270587201"))
    
    c.setLineWidth(1)
    c.line(50, height - 105, width - 50, height - 105)

    c.setFont(font_name, 12)
    c.setFillColorRGB(0, 0, 0)
    c.drawRightString(width - 50, height - 140, fix_arabic(f"فاتورة صيانة رسمية - رقم التذكرة: {ticket_id}"))
    c.drawString(50, height - 140, f"التاريخ: {datetime.now().strftime('%Y-%m-%d')}")

    c.setFillColorRGB(0.95, 0.95, 0.95)
    c.rect(45, height - 280, width - 90, 115, fill=1, stroke=0)

    c.setFillColorRGB(0, 0, 0)
    c.setFont(font_name, 11)
    c.drawRightString(width - 60, height - 180, fix_arabic("بيانات العميل والجهاز:"))
    
    c.setFont(font_name, 11)
    c.drawRightString(width - 75, height - 205, fix_arabic(f"اسم العميل: {customer_name}"))
    c.drawRightString(width - 75, height - 225, fix_arabic(f"نوع الموبايل: {model}"))
    c.drawRightString(width - 75, height - 245, fix_arabic(f"العطل المبلغ عنه: {issue}"))

    c.setStrokeColorRGB(0.8, 0.8, 0.8)
    c.rect(45, height - 410, width - 90, 100, fill=0, stroke=1)

    c.setFont(font_name, 11)
    c.drawRightString(width - 60, height - 325, fix_arabic("تفاصيل الإصلاح والملاحظات:"))
    
    c.setFont(font_name, 11)
    c.drawRightString(width - 75, height - 350, fix_arabic(f"ملاحظات: {notes}"))
    
    c.setFont(font_name, 12)
    c.setFillColorRGB(0.8, 0.1, 0.1)
    c.drawRightString(width - 75, height - 385, fix_arabic(f"إجمالي التكلفة المطلوبة: {price} جنيه مصري"))

    c.setLineWidth(0.5)
    c.line(50, height - 435, width - 50, height - 435)

    c.setFont(font_name, 11)
    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.drawRightString(width - 50, height - 465, fix_arabic("شروط الضمان وسياسة الورشة:"))
    
    c.setFont(font_name, 10)
    c.drawRightString(width - 60, height - 490, fix_arabic("- البطاريات وفلاتات وسوكتات الشحن تشمل ضمان معتمد ضد عيوب الصناعة."))
    c.drawRightString(width - 60, height - 510, fix_arabic("- الشاشات لا يوجد عليها ضمان بعد الاستلام والتركيب."))
    c.drawRightString(width - 60, height - 530, fix_arabic("- الورشة غير مسؤولة عن الأجهزة التي يتم تركها لأكثر من 30 يوماً."))

    c.setFont(font_name, 11)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(50, height - 590, fix_arabic("توقيع المهندس المسؤول:"))
    c.setFont(font_name, 11)
    c.drawString(50, height - 610, fix_arabic("أبانوب عاطف"))

    c.save()
    return filename

# =====================================================================
# 📚 قاموس الأسعار التفاعلية والردود
# =====================================================================
PRICES_TABLE = {
    "iPhone": {
        "شاشة (أصلية / كوبي)": "من 600 إلى 2500 جنيه حسب الموديل",
        "بطارية أصلية بضمان": "من 400 إلى 900 جنيه",
        "سوكت شحن (Lightning / Type-C)": "من 250 إلى 500 جنيه",
        "سوفت وير أو فك حسابات": "حسب الإصدار ويفضل الكشف بالورشة"
    },
    "Samsung": {
        "شاشة (AMOLED / TFT)": "من 500 إلى 3000 جنيه حسب الموديل",
        "بطارية أصلية بضمان": "من 350 إلى 700 جنيه",
        "سوكت شحن (Type-C)": "من 200 إلى 400 جنيه",
        "إزالة حساب جوجل (FRP)": "من 150 إلى 350 جنيه"
    },
    "Xiaomi_Oppo": {
        "شاشة": "من 450 إلى 1800 جنيه",
        "بطارية": "من 300 إلى 600 جنيه",
        "سوكت شحن": "من 200 إلى 350 جنيه",
        "تفليش وسوفت وير": "من 150 إلى 300 جنيه"
    }
}

PRICE_RESPONSES = [
    "💵 **بخصوص الأسعار وتكلفة القطع يا باشا:**\nالأسعار بتتغير حسب الموديل ونوع القطعة. استعمل زر (حاسبة الأسعار) في القائمة، أو تواصل معنا مباشرة عبر الواتساب: `01270587201`"
]

FALLBACK_RESPONSES = [
    "🔧 **يا هلا بيك يا باشا:**\nالعطل ده محتاج فحص مباشر على الباور سبلاي والمجهر في الورشة بباكوس. كلم المهندس فوراً على الواتساب: `01270587201`"
]

LOCAL_FAQ = {
    ("عنوان", "مكان", "فين", "المحل فين", "عنوانكم", "المنشية", "باكوس", "مكتبة الهلال"): 
        "📍 **عنوان المحل بالتفصيل:**\nالإسكندرية، باكوس، عند مشاريع المنشية والمحطة، بجوار مكتبة الهلال. منورنا يا باشا في أي وقت!",
    ("رقم", "تليفون", "اتصال", "واتساب", "تواصل", "رقمكم", "كلمكم ازاي", "الواتس"): 
        "📞 **رقم التليفون والواتساب الرسمي:**\nتقدر تكلمنا أو تبعت لنا رسالة على الواتساب مباشرة:\n👉 `01270587201`",
    ("اسم", "المحل", "مين", "انتو مين", "الكينج", "لي لي"): 
        "🏪 **محل 'لي لي' أو 'الكينج'**\nمتخصصون في صيانة الهواتف الذكية (أندرويد وآيفون) هاردوير دقيق، شبلنة آيسيات، وفك حسابات السوفت وير.",
    ("مواعيد", "فتح", "قفل", "الساعة كام", "شغالين امتى"): 
        "⏰ **مواعيد العمل:**\nشغالين كل يوم، وتقدر تتواصل معانا وتتشرفنا في الورشة في أي وقت.",
    ("فحص", "كشف", "مقايسة", "بكام الكشف"): 
        "🔍 **فحص الجهاز:**\nالفحص والمقايسة المبدئية للأجهزة داخل المحل مجانية تماماً يا باشا!"
}

# =====================================================================
# 🚀 رسالة البدء والترحيب (مع زر مشاركة الورشة)
# =====================================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = f"أهلاً بيك يا **{user.first_name}** في محل *'لي لي / الكينج'* لصيانة الهواتف بباكوس! 🛠️\n\nاختر من الأقسام التفاعلية بالأسفل أو احجز موعدك:"
    
    bot_username = context.bot.username
    share_text_encoded = f"https://t.me/share/url?url=https://t.me/{bot_username}&text=🔗%20تعال%20احجز%20صيانة%20موبايلك%20عند%20أفضل%20ورشة%20في%20باكوس%20(لي%20لي%20/%20الكينج)!%20هنا%20البوت%20الرسمي:"

    keyboard = [
        [InlineKeyboardButton("💰 حاسبة الأسعار التفاعلية", callback_data="price_calc_menu"), InlineKeyboardButton("📅 حجز موعد صيانة", callback_data="start_booking")],
        [InlineKeyboardButton("🔍 حالة الجهاز (تذكرة)", callback_data="check_status"), InlineKeyboardButton("📍 العنوان والمواعيد", callback_data="faq_location")],
        [InlineKeyboardButton("📤 مشاركة الورشة مع أصحابك", url=share_text_encoded)],
        [InlineKeyboardButton("📞 تواصل واتساب", url="https://wa.me/201270587201")]
    ]
    
    if OWNER_TELEGRAM_ID and user.id == OWNER_TELEGRAM_ID:
        keyboard.insert(0, [InlineKeyboardButton("👑 لوحة تحكم الأدمن والأرشيف", callback_data="admin_panel")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="Markdown")

# =====================================================================
# 💰 حاسبة الأسعار التفاعلية للعملاء
# =====================================================================
async def price_calculator_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🍏 آيفون (iPhone)", callback_data="calc_brand_iPhone")],
        [InlineKeyboardButton("📱 سامسونج (Samsung)", callback_data="calc_brand_Samsung")],
        [InlineKeyboardButton("📱 شاومي و أوبو (Xiaomi / Oppo)", callback_data="calc_brand_Xiaomi_Oppo")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_home")]
    ]
    await query.message.edit_text(
        "💰 **حاسبة الأسعار التفاعلية للورشة:**\nاختر ماركة الهاتف لمعرفة تكلفة قطع الغيار والصيانة التقديرية:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def price_calculator_parts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    brand = query.data.replace("calc_brand_", "")
    context.user_data['calc_brand'] = brand
    
    brand_parts = PRICES_TABLE.get(brand, {})
    keyboard = []
    for part_name in brand_parts.keys():
        keyboard.append([InlineKeyboardButton(part_name, callback_data=f"calc_part_{part_name}")])
    
    keyboard.append([InlineKeyboardButton("🔙 اختيار ماركة أخرى", callback_data="price_calc_menu")])
    
    brand_display_name = brand.replace("_", " / ")
    await query.message.edit_text(
        f"📱 **ماركة الجهاز: {brand_display_name}**\nاختر القطعة أو العطل المطلوب:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def price_calculator_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    part_name = query.data.replace("calc_part_", "")
    brand = context.user_data.get('calc_brand', 'iPhone')
    
    estimated_price = PRICES_TABLE.get(brand, {}).get(part_name, "يحدد بالورشة")
    brand_display_name = brand.replace("_", " / ")
    
    text = (
        f"📊 **نتيجة التقدير المبدئي:**\n\n"
        f"📱 الماركة: *{brand_display_name}*\n"
        f"🛠️ الخدمة: *{part_name}*\n"
        f"💰 التكلفة التقديرية: `{estimated_price}`\n\n"
        f"📌 *ملحوظة:* الأسعار قابلة للتغير البسيط حسب الموديل والدقة، ويسعدنا زيارتك للمحل في باكوس للفحص المجاني!"
    )
    keyboard = [
        [InlineKeyboardButton("📅 حجز موعد صيانة الآن", callback_data="start_booking")],
        [InlineKeyboardButton("💬 استفسار واتساب", url="https://wa.me/201270587201")],
        [InlineKeyboardButton("🔙 حاسبة الأسعار", callback_data="price_calc_menu")]
    ]
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

# =====================================================================
# 📚 أرشيف الأعطال والحلول (Knowledge Base للأدمن أبانوب)
# =====================================================================
async def admin_archive_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("➕ إضافة حل عطل جديد بالأرشيف", callback_data="arch_add")],
        [InlineKeyboardButton("🔎 البحث في الأرشيف", callback_data="arch_search")],
        [InlineKeyboardButton("👑 لوحة التحكم الرئيسية", callback_data="admin_panel")]
    ]
    await query.message.edit_text(
        "📚 **أرشيف أعطال ورشة 'لي لي / الكينج':**\nسجل وحافظ على حلول الصيانة الخاصة بك لترجع لها في أي وقت:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def arch_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("📝 **إضافة حل جديد للأرشيف**\n\nاكتب لي **موديل الجهاز** (مثلاً: iPhone 11 أو Samsung A32):")
    return ARCHIVE_MODEL

async def arch_receive_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['arch_model'] = update.message.text
    await update.message.reply_text("تمام. اكتب باختصار **وصف العطل** (مثلاً: فاصل نور شاشة أو شحن وهمي):")
    return ARCHIVE_ISSUE

async def arch_receive_issue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['arch_issue'] = update.message.text
    await update.message.reply_text(" ممتاز. اكتب الآن **خطوات الحل أو الإصلاح التقني** بالتفصيل (مثل: تغيير ايسي الشحن / عمل كوبري كذا):")
    return ARCHIVE_SOLUTION

async def arch_receive_solution(update: Update, context: ContextTypes.DEFAULT_TYPE):
    solution_text = update.message.text
    model = context.user_data.get('arch_model')
    issue = context.user_data.get('arch_issue')
    
    db_add_solution(model, issue, solution_text)
    
    await update.message.reply_text(
        f"✅ **تم حفظ حل العطل في الأرشيف بنجاح يا أبانوب يا باشا!**\n\n"
        f"📱 الموديل: {model}\n"
        f"⚠️ العطل: {issue}\n"
        f"💡 الحل: {solution_text}",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def arch_search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("🔎 **البحث في أرشيف الأعطال:**\nاكتب اسم الموديل أو الكلمة المفتاحية للبحث عنها (مثلاً: `A51` أو `إي كلاود`):")
    return SEARCH_ARCHIVE

async def arch_execute_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyword = update.message.text.strip()
    results = db_search_solutions(keyword)
    
    if not results:
        await update.message.reply_text(f"❌ لم يتم العثور على نتائج مطابقة للبحث عن: `{keyword}`", parse_mode="Markdown")
        return ConversationHandler.END
        
    text = f"📚 **نتائج البحث في الأرشيف عن ({keyword}):**\n\n"
    for r in results:
        m, iss, sol, date = r
        text += f"📱 **الموديل:** {m}\n⚠️ **العطل:** {iss}\n💡 **الحل:** {sol}\n📅 **التاريخ:** {date}\n-------------------\n"
        
    await update.message.reply_text(text, parse_mode="Markdown")
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم إلغاء العملية.")
    return ConversationHandler.END

# =====================================================================
# 📅 نظام الحجز المسبق وإعطاء رقم تذكرة
# =====================================================================
async def booking_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("🛠️ **حجز موعد صيانة مسبق**\n\nمن فضلك، اكتب لي **نوع الموبايل وموديله** إيه؟ (مثلاً: Samsung A51 أو iPhone X)")
    return DEVICE_MODEL

async def receive_device_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['device_model'] = update.message.text
    await update.message.reply_text("تمام جداً. اكتب لي باختصار **إيه العطل أو المشكلة الدقيقة** اللي في الجهاز؟")
    return DEVICE_ISSUE

async def receive_device_issue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    issue = update.message.text
    model = context.user_data.get('device_model')
    
    ticket_num = random.randint(1000, 9999)
    ticket_id = f"LK-{ticket_num}"
    
    db_add_ticket(ticket_id, user.id, user.full_name, model, issue)

    confirmation_text = f"✅ **تم تسجيل حجزك بنجاح يا باشا!**\n\n🎫 **رقم التذكرة الخاص بك:** `{ticket_id}`\n📱 الجهاز: {model}\n⚠️ العطل: {issue}\n\nاحفظ رقم التذكرة دي عشان تقدر تسأل بيها عن حالة جهازك في أي وقت. منورنا!"
    await update.message.reply_text(confirmation_text, parse_mode="Markdown")
    
    if OWNER_TELEGRAM_ID:
        owner_notification = f"🚨 **طلب صيانة هندسي جديد (تذكرة: {ticket_id})!**\n\n👤 العميل: {user.full_name}\n📱 الموبايل: {model}\n⚠️ العطل: {issue}\n🆔 آي دي العميل: `{user.id}`"
        try:
            keyboard = [[InlineKeyboardButton("💬 مراسلة العميل", url=f"tg://user?id={user.id}")]]
            await context.bot.send_message(chat_id=OWNER_TELEGRAM_ID, text=owner_notification, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        except Exception as e:
            print(f"❌ خطأ في إرسال الإشعار للأدمن: {e}")
            
    return ConversationHandler.END

# =====================================================================
# 📸 استقبال صور الأعطال والتسليم
# =====================================================================
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo_file = await update.message.photo[-1].get_file()
    
    if OWNER_TELEGRAM_ID and user.id == OWNER_TELEGRAM_ID and context.user_data.get('admin_sending_photo_to'):
        target_user_id = context.user_data['admin_sending_photo_to']
        ticket_id = context.user_data['admin_sending_photo_ticket']
        
        try:
            await context.bot.send_photo(
                chat_id=target_user_id,
                photo=photo_file.file_id,
                caption=f"📸 **صورة تسليم الجهاز (تذكرة: `{ticket_id}`):**\nورشة 'لي لي / الكينج' تشكر ثقتكم الدائمة بنا!",
                parse_mode="Markdown"
            )
            await update.message.reply_text("✅ تم إرسال الصورة للعميل بنجاح!")
        except Exception as e:
            await update.message.reply_text(f"❌ حدث خطأ أثناء إرسال الصورة: {e}")
            
        context.user_data.pop('admin_sending_photo_to', None)
        context.user_data.pop('admin_sending_photo_ticket', None)
        return

    await update.message.reply_text(
        "📸 **وصلتني صورة الجهاز أو العطل يا باشا!**\n\n"
        "تم توجيهها للمهندس أبانوب لتقدير التكلفة، أو يمكنك التواصل عبر الواتساب:\n"
        "👉 `01270587201`",
        parse_mode="Markdown"
    )
    
    if OWNER_TELEGRAM_ID and user.id != OWNER_TELEGRAM_ID:
        try:
            caption = f"📸 **صورة عطل جديدة مرفقة من العميل:**\n👤 الاسم: {user.full_name}\n🆔 الآي دي: `{user.id}`"
            await context.bot.send_photo(chat_id=OWNER_TELEGRAM_ID, photo=photo_file.file_id, caption=caption, parse_mode="Markdown")
        except Exception as e:
            print(f"❌ خطأ في إعادة توجيه الصورة للأدمن: {e}")

# =====================================================================
# 👑 لوحة تحكم الأدمن
# =====================================================================
async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if OWNER_TELEGRAM_ID and user_id != OWNER_TELEGRAM_ID:
        await query.message.reply_text("⚠️ هذه اللوحة مخصصة لصاحب المحل فقط.")
        return

    tickets = db_get_all_tickets()
    
    text = f"👑 **لوحة تحكم ورشة 'لي لي / الكينج' (أبانوب عاطف):**\n\nاختر إدارة التذاكر أو أدخل على الأرشيف الهندسي:"
    keyboard = [
        [InlineKeyboardButton("📚 أرشيف الأعطال والحلول (Knowledge Base)", callback_data="admin_archive")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back_home")]
    ]
    
    if tickets:
        text += "\n\n🎫 **التذاكر النشطة:**"
        for t in tickets:
            ticket_id, name, model, status = t
            keyboard.append([InlineKeyboardButton(f"🎫 {ticket_id} | {model} ({name})", callback_data=f"adm_t_{ticket_id}")])

    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_ticket_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data.startswith("adm_t_"):
        ticket_id = data.replace("adm_t_", "")
        ticket = db_get_ticket(ticket_id)
        if not ticket:
            await query.message.reply_text("⚠️ التذكرة غير موجودة.")
            return
            
        t_id, u_id, name, model, issue, status, created = ticket
        text = (
            f"🎫 **تفاصيل التذكرة: `{t_id}`**\n\n"
            f"👤 العميل: {name}\n"
            f"🆔 الآي دي: `{u_id}`\n"
            f"📱 الجهاز: {model}\n"
            f"⚠️ العطل: {issue}\n"
            f"📊 الحالة الحالية: *{status}*\n"
            f"📅 تاريخ الحجز: {created}"
        )
        keyboard = [
            [InlineKeyboardButton("🔄 جاري الفحص", callback_data=f"st_{t_id}_1")],
            [InlineKeyboardButton("🛠️ جاري الإصلاح", callback_data=f"st_{t_id}_2")],
            [InlineKeyboardButton("✅ تم الإصلاح وجاهز", callback_data=f"st_{t_id}_3")],
            [InlineKeyboardButton("💬 الرد المباشر", callback_data=f"reply_u_{u_id}_{t_id}"), InlineKeyboardButton("📸 إرسال صورة", callback_data=f"send_p_{u_id}_{t_id}")],
            [InlineKeyboardButton("📄 إصدار وتوليد الفاتورة بالعربي (PDF)", callback_data=f"invoice_req_{t_id}")],
            [InlineKeyboardButton("🔙 رجوع للقائمة", callback_data="admin_panel")]
        ]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def admin_set_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data 
    
    parts = data.split("_")
    ticket_id = parts[1]
    status_code = parts[2]
    
    status_dict = {
        "1": "🔄 جاري الفحص في الورشة",
        "2": "🛠️ الجهاز خاضع للإصلاح الآن",
        "3": "✅ تم إصلاح الجهاز وجاهز للاستلام"
    }
    
    new_status = status_dict.get(status_code, "🔄 جاري العمل")
    ticket = db_get_ticket(ticket_id)
    if not ticket:
        await query.message.reply_text("⚠️ التذكرة غير موجودة.")
        return
        
    user_id = ticket[1]
    db_update_status(ticket_id, new_status)
    
    await query.message.reply_text(f"✅ تم تحديث حالة التذكرة `{ticket_id}` بنجاح!", parse_mode="Markdown")
    
    try:
        customer_msg = f"🔔 **تحديث هام بشأن جهازك (تذكرة: `{ticket_id}`):**\n\nالحالة الآن: *{new_status}*\n\nلأي استفسار، تواصل معنا على الواتساب: `01270587201`"
        reply_markup = None
        if status_code == "3":
            customer_msg += "\n\n⭐ نرجو تقييم تجربتك معنا بعد استلام جهازك:"
            reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("⭐ تقييم خدمة الصيانة", callback_data=f"rate_{ticket_id}")]])
            
        await context.bot.send_message(chat_id=user_id, text=customer_msg, reply_markup=reply_markup, parse_mode="Markdown")
    except Exception as e:
        print(f"❌ لم يتمكن البوت من إرسال الإشعار للعميل: {e}")

async def admin_start_invoice_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = query.data.replace("invoice_req_", "")
    
    context.user_data['making_invoice_ticket'] = ticket_id
    
    await query.message.reply_text(
        f"📄 **إصدار فاتورة عربية باسم أبانوب عاطف (تذكرة: `{ticket_id}`):**\n\n"
        f"من فضلك اكتب **السعر والملاحظات** بالصيغة التالية في رسالة واحدة:\n"
        f"`[السعر], [الملاحظات]`\n\n"
        f"*(مثال: `450, تغيير سوكت شحن أصلي وضمان شهر`)*\n\n"
        f"*(لإلغاء العملية، اكتب: `إلغاء`)*",
        parse_mode="Markdown"
    )

async def admin_start_send_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data 
    parts = data.split("_")
    target_user_id = int(parts[2])
    ticket_id = parts[3]
    
    context.user_data['admin_sending_photo_to'] = target_user_id
    context.user_data['admin_sending_photo_ticket'] = ticket_id
    
    await query.message.reply_text(
        f"📸 **إرسال صورة للعميل (تذكرة: `{ticket_id}`):**\n\n"
        f"قم بإرسال **الصورة** الآن في الشات هنا، وسيتم إرسالها للعميل.\n"
        f"*(لإلغاء العملية، اكتب: `إلغاء`)*",
        parse_mode="Markdown"
    )

async def admin_start_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data 
    parts = data.split("_")
    target_user_id = int(parts[2])
    ticket_id = parts[3]
    
    context.user_data['admin_replying_to'] = target_user_id
    context.user_data['admin_replying_ticket'] = ticket_id
    
    await query.message.reply_text(
        f"💬 **وضع الرد المباشر (تذكرة: `{ticket_id}`):**\n\n"
        f"اكتب الرسالة اللي عاوز تبعتها للعميل دلوقتي حالا في الشات.\n"
        f"*(لإلغاء الرد، اكتب: `إلغاء`)*",
        parse_mode="Markdown"
    )

# =====================================================================
# ⭐ نظام تقييم خدمة العملاء
# =====================================================================
async def start_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ticket_id = query.data.replace("rate_", "")
    
    keyboard = [
        [
            InlineKeyboardButton("⭐ 1", callback_data=f"r_{ticket_id}_1"),
            InlineKeyboardButton("⭐⭐ 2", callback_data=f"r_{ticket_id}_2"),
            InlineKeyboardButton("⭐⭐⭐ 3", callback_data=f"r_{ticket_id}_3")
        ],
        [
            InlineKeyboardButton("⭐⭐⭐⭐ 4", callback_data=f"r_{ticket_id}_4"),
            InlineKeyboardButton("⭐⭐⭐⭐⭐ 5", callback_data=f"r_{ticket_id}_5")
        ]
    ]
    await query.message.reply_text("تقييمك يهمنا جداً لتحسين خدماتنا في ورشة 'لي لي / الكينج'. من فضلك اختر عدد النجوم:", reply_markup=InlineKeyboardMarkup(keyboard))

async def save_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data 
    parts = data.split("_")
    ticket_id = parts[1]
    score = parts[2]
    user_id = query.from_user.id
    
    conn = sqlite3.connect("workshop.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO ratings VALUES (?, ?, ?, ?)", (ticket_id, user_id, int(score), "تم التقييم بنجاح"))
    conn.commit()
    conn.close()
    
    await query.message.reply_text(f"شكراً لك يا باشا على تقييمك ({score}/5)! رأيك يهمنا ودائماً في خدمة دقيقة ومميزة بباكوس.")
    
    if OWNER_TELEGRAM_ID:
        try:
            await context.bot.send_message(chat_id=OWNER_TELEGRAM_ID, text=f"⭐ **تقييم جديد من عميل:**\n🎫 التذكرة: `{ticket_id}`\n📊 الدرجة: {score} نجوم من 5", parse_mode="Markdown")
        except Exception:
            pass

# =====================================================================
# 📥 معالجة رسائل الأدمن والعملاء
# =====================================================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_message = update.message.text.strip()
    user_message_lower = user_message.lower()
    
    if OWNER_TELEGRAM_ID and user.id == OWNER_TELEGRAM_ID:
        if user_message_lower == "إلغاء":
            context.user_data.pop('admin_replying_to', None)
            context.user_data.pop('admin_sending_photo_to', None)
            context.user_data.pop('making_invoice_ticket', None)
            await update.message.reply_text("❌ تم إلغاء العملية الحالية.")
            return

        if context.user_data.get('making_invoice_ticket'):
            ticket_id = context.user_data['making_invoice_ticket']
            context.user_data.pop('making_invoice_ticket', None)
            
            try:
                parts = user_message.split(",", 1)
                price = parts[0].strip()
                notes = parts[1].strip() if len(parts) > 1 else "صيانة عامة"
                
                ticket = db_get_ticket(ticket_id)
                if not ticket:
                    await update.message.reply_text("⚠️ التذكرة غير موجودة.")
                    return
                    
                t_id, u_id, name, model, issue, status, created = ticket
                pdf_file = generate_arabic_invoice(t_id, name, model, issue, price, notes)
                
                with open(pdf_file, "rb") as f:
                    await context.bot.send_document(
                        chat_id=u_id,
                        document=f,
                        filename=f"Invoice_{t_id}.pdf",
                        caption=f"📄 **فاتورة صيانة جهازك الرسمية (تذكرة: `{t_id}`):**\nالمبلغ الإجمالي: {price} جنيه مصري\nمهندس الصيانة: أبانوب عاطف\nورشة 'لي لي / الكينج' بباكوس.",
                        parse_mode="Markdown"
                    )
                    
                await update.message.reply_text(f"✅ تم توليد وإرسال الفاتورة العربية للعميل بنجاح!")
                if os.path.exists(pdf_file):
                    os.remove(pdf_file)
            except Exception as e:
                await update.message.reply_text(f"❌ خطأ في إنشاء الفاتورة. تأكد من الصيغة: `السعر, الملاحظات`\nالخطأ: {e}")
            return

        if context.user_data.get('admin_replying_to'):
            target_user_id = context.user_data['admin_replying_to']
            ticket_id = context.user_data['admin_replying_ticket']
            
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=f"📩 **رد خاص من المهندس أبانوب عاطف (ورشة 'لي لي / الكينج' - تذكرة `{ticket_id}`):**\n\n{user_message}\n\n📞 الواتساب: `01270587201`",
                    parse_mode="Markdown"
                )
                await update.message.reply_text(f"✅ تم إرسال الرد للعميل بنجاح!", parse_mode="Markdown")
            except Exception as e:
                await update.message.reply_text(f"❌ حدث خطأ أثناء إرسال الرد: {e}")
                
            context.user_data.pop('admin_replying_to', None)
            context.user_data.pop('admin_replying_ticket', None)
            return

    if user_message.upper().startswith("LK-"):
        ticket_key = user_message.upper()
        ticket = db_get_ticket(ticket_key)
        if ticket:
            t_id, u_id, name, model, issue, status, created = ticket
            await update.message.reply_text(
                f"🎫 **تفاصيل التذكرة ({t_id}):**\n\n"
                f"📱 الجهاز: {model}\n"
                f"⚠️ العطل: {issue}\n"
                f"📊 الحالة الحالية: *{status}*\n"
                f"📅 وقت الحجز: {created}\n\n"
                f"لأي استفسار إضافي، كلمنا على الواتساب: `01270587201`",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("⚠️ عذراً يا باشا، رقم التذكرة ده مش موجود في النظام. اتأكد من الرقم أو تواصل معنا على الواتساب: `01270587201`")
        return

    reply_text = None
    price_keywords = ["اسعار", "سعر", "كام", "تكلفة", "بكام", "مصاريف", "حساب"]
    if any(pk in user_message_lower for pk in price_keywords):
        reply_text = random.choice(PRICE_RESPONSES)
    else:
        for keywords, answer in LOCAL_FAQ.items():
            if any(kw in user_message_lower for kw in keywords):
                reply_text = answer
                break
                
    if not reply_text:
        reply_text = random.choice(FALLBACK_RESPONSES)

    bot_username = context.bot.username
    share_text_encoded = f"https://t.me/share/url?url=https://t.me/{bot_username}&text=🔗%20تعال%20احجز%20صيانة%20موبايلك%20عند%20أفضل%20ورشة%20في%20باكوس%20(لي%20لي%20/%20الكينج)!%20هنا%20البوت%20الرسمي:"

    keyboard = [
        [InlineKeyboardButton("💰 حاسبة الأسعار التفاعلية", callback_data="price_calc_menu"), InlineKeyboardButton("📅 حجز موعد صيانة", callback_data="start_booking")],
        [InlineKeyboardButton("📤 مشاركة الورشة مع أصحابك", url=share_text_encoded)],
        [InlineKeyboardButton("📞 تواصل واتساب", url="https://wa.me/201270587201")]
    ]
    reply_markup_obj = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(reply_text, reply_markup=reply_markup_obj, parse_mode="Markdown")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "check_status":
        await query.message.reply_text("🔍 من فضلك، اكتب لي **رقم التذكرة** اللي وصلك وقت الحجز (مثل `LK-4821`):")
    elif data == "faq_location":
        await query.message.reply_text("📍 **عنوان المحل:**\nالإسكندرية، باكوس، عند مشاريع المنشية والمحطة، بجوار مكتبة الهلال. منورنا في أي وقت يا باشا!", parse_mode="Markdown")
    elif data == "back_home":
        await query.message.reply_text("🏠 تم العودة للقائمة الرئيسية. اضغط `/start` لعرض القائمة التفاعلية.")

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    booking_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(booking_start, pattern="^start_booking$")],
        states={
            DEVICE_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_device_model)],
            DEVICE_ISSUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_device_issue)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        per_message=False
    )

    archive_add_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(arch_add_start, pattern="^arch_add$")],
        states={
            ARCHIVE_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, arch_receive_model)],
            ARCHIVE_ISSUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, arch_receive_issue)],
            ARCHIVE_SOLUTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, arch_receive_solution)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        per_message=False
    )

    archive_search_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(arch_search_start, pattern="^arch_search$")],
        states={
            SEARCH_ARCHIVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, arch_execute_search)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
        per_message=False
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(booking_handler)
    app.add_handler(archive_add_handler)
    app.add_handler(archive_search_handler)
    
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.add_handler(CallbackQueryHandler(admin_panel_handler, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_archive_menu, pattern="^admin_archive$"))
    app.add_handler(CallbackQueryHandler(admin_ticket_manage, pattern="^adm_t_"))
    app.add_handler(CallbackQueryHandler(admin_set_status, pattern="^st_"))
    app.add_handler(CallbackQueryHandler(admin_start_reply, pattern="^reply_u_"))
    app.add_handler(CallbackQueryHandler(admin_start_send_photo, pattern="^send_p_"))
    app.add_handler(CallbackQueryHandler(admin_start_invoice_input, pattern="^invoice_req_"))
    
    app.add_handler(CallbackQueryHandler(price_calculator_menu, pattern="^price_calc_menu$"))
    app.add_handler(CallbackQueryHandler(price_calculator_parts, pattern="^calc_brand_"))
    app.add_handler(CallbackQueryHandler(price_calculator_result, pattern="^calc_part_"))
    
    app.add_handler(CallbackQueryHandler(start_rating, pattern="^rate_"))
    app.add_handler(CallbackQueryHandler(save_rating, pattern="^r_"))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("🚀 نظام ورشة 'لي لي / الكينج' يعمل بكامل المزايا ومجهز للسيرفر...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()