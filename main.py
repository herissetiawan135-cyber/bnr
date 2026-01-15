import json, os, uuid, requests
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputFile, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, CallbackContext
)

# ================== CONFIG ==================
BOT_TOKEN = "ISI_TOKEN_BOT_KAMU"
OWNER_ID = 6739598575

PAKASIR_API_KEY = "7qFeQIWS0inCo0DNt0X8VpGI075aRtIW"
PAKASIR_BASE_URL = "https://api.pakasir.com"  # SESUAIKAN

produk_file = "produk.json"
saldo_file = "saldo.json"
riwayat_file = "riwayat.json"
statistik_file = "statistik.json"
qris_file = "qris_pending.json"
# ============================================


# ================== UTIL ==================
def load_json(file):
    if not os.path.exists(file):
        return {}
    with open(file, "r") as f:
        return json.load(f) if f.read().strip() else {}

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

def add_riwayat(uid, tipe, ket, jumlah):
    data = load_json(riwayat_file)
    uid = str(uid)
    data.setdefault(uid, []).append({
        "tipe": tipe,
        "keterangan": ket,
        "jumlah": jumlah,
        "waktu": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    })
    save_json(riwayat_file, data)

def update_statistik(uid, nominal):
    data = load_json(statistik_file)
    uid = str(uid)
    data.setdefault(uid, {"jumlah": 0, "nominal": 0})
    data[uid]["jumlah"] += 1
    data[uid]["nominal"] += nominal
    save_json(statistik_file, data)
# ==========================================


# ================== PAKASIR ==================
def create_qris(amount, invoice_id):
    headers = {
        "Authorization": f"Bearer {PAKASIR_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "invoice_id": invoice_id,
        "amount": amount,
        "payment_method": "QRIS",
        "description": f"Deposit DOTZ STORE {invoice_id}"
    }
    r = requests.post(
        f"{PAKASIR_BASE_URL}/payment/create",
        json=payload,
        headers=headers,
        timeout=15
    )
    return r.json()

def cek_qris(invoice_id):
    headers = {
        "Authorization": f"Bearer {PAKASIR_API_KEY}"
    }
    r = requests.get(
        f"{PAKASIR_BASE_URL}/payment/status/{invoice_id}",
        headers=headers,
        timeout=15
    )
    return r.json()
# ============================================


# ================== MENU ==================
async def send_main_menu(context, chat_id, user):
    saldo = load_json(saldo_file).get(str(user.id), 0)
    stat = load_json(statistik_file).get(str(user.id), {})
    jumlah = stat.get("jumlah", 0)
    total = stat.get("nominal", 0)

    text = (
        f"👋 *DOTZ STORE*\n\n"
        f"🧑 {user.full_name}\n"
        f"🆔 `{user.id}`\n"
        f"💰 Saldo: Rp{saldo:,}\n"
        f"📦 Transaksi: {jumlah}\n"
        f"💸 Total: Rp{total:,}"
    )

    keyboard = [
        [InlineKeyboardButton("📋 List Produk", callback_data="list_produk")],
        [InlineKeyboardButton("💰 Deposit QRIS", callback_data="deposit")],
        [InlineKeyboardButton("📖 Info Bot", callback_data="info")]
    ]

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
# ==========================================


# ================== DEPOSIT ==================
async def handle_deposit(update, context):
    query = update.callback_query
    nominals = [10000, 20000, 30000, 50000]
    keyboard = [
        [InlineKeyboardButton(f"Rp{n:,}", callback_data=f"deposit_{n}")]
        for n in nominals
    ]
    keyboard.append([InlineKeyboardButton("🔙 Kembali", callback_data="back")])
    await query.edit_message_text(
        "💰 *Pilih nominal deposit:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_deposit_nominal(update, context):
    query = update.callback_query
    nominal = int(query.data.split("_")[1])

    invoice_id = f"DOTZ-{uuid.uuid4().hex[:10]}"
    qris = create_qris(nominal, invoice_id)

    if not qris.get("success"):
        await query.answer("❌ QRIS gagal dibuat", show_alert=True)
        return

    qris_data = load_json(qris_file)
    qris_data[invoice_id] = {
        "user_id": query.from_user.id,
        "nominal": nominal
    }
    save_json(qris_file, qris_data)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Cek Status", callback_data=f"cek_qris:{invoice_id}")],
        [InlineKeyboardButton("🔙 Kembali", callback_data="back")]
    ])

    await query.edit_message_text(
        f"💳 *QRIS Deposit*\n\n"
        f"Nominal: Rp{nominal:,}\n"
        f"Invoice: `{invoice_id}`\n\n"
        f"Scan QR di bawah lalu klik *Cek Status*",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

    await context.bot.send_photo(
        chat_id=query.from_user.id,
        photo=qris["data"]["qris_url"]
    )

async def handle_cek_qris(update, context):
    query = update.callback_query
    invoice_id = query.data.split(":")[1]

    qris_data = load_json(qris_file)
    data = qris_data.get(invoice_id)

    if not data:
        await query.answer("Invoice tidak ditemukan", show_alert=True)
        return

    status = cek_qris(invoice_id)

    if status["data"]["status"] == "PAID":
        saldo = load_json(saldo_file)
        uid = str(data["user_id"])
        saldo[uid] = saldo.get(uid, 0) + data["nominal"]
        save_json(saldo_file, saldo)

        add_riwayat(uid, "DEPOSIT", "QRIS Pakasir", data["nominal"])
        qris_data.pop(invoice_id)
        save_json(qris_file, qris_data)

        await query.edit_message_text(
            f"✅ *Deposit berhasil!*\nSaldo +Rp{data['nominal']:,}",
            parse_mode="Markdown"
        )
        await send_main_menu(context, data["user_id"], await context.bot.get_chat(data["user_id"]))
    else:
        await query.answer("⏳ Belum dibayar", show_alert=True)
# ============================================


# ================== CALLBACK ==================
async def button_callback(update: Update, context: CallbackContext):
    data = update.callback_query.data
    await update.callback_query.answer()

    if data == "deposit":
        await handle_deposit(update, context)
    elif data.startswith("deposit_"):
        await handle_deposit_nominal(update, context)
    elif data.startswith("cek_qris:"):
        await handle_cek_qris(update, context)
    elif data == "back":
        await send_main_menu(context, update.effective_chat.id, update.effective_user)
# ============================================


async def start(update: Update, context: CallbackContext):
    await send_main_menu(context, update.effective_chat.id, update.effective_user)


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.run_polling()


if __name__ == "__main__":
    main()

