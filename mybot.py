import telebot
from telebot import types
import time
import json
import os
import random
import string
import requests
from datetime import datetime, timedelta
import threading

# ============ НАСТРОЙКИ ============
TOKEN = '8794961428:AAHatXUGU00TgirKwebRgtxbpG12lVvfeTw'
ADMIN_ID =  5195664540 # Замени на свой Telegram ID
WALLET_NUMBER = 'https://tbank.ru/cf/5XblKroB2vj'

# 3x-ui панель
XUI_URL = "http://206.251.49.161:54321/A8buQ8JOxE60kUhSTr"
XUI_USERNAME = "3sxBsFv4AT"
XUI_PASSWORD = "vfeFe6ahmG"
INBOUND_ID = 1  # ID твоего входящего подключения (обычно 1)

bot = telebot.TeleBot(TOKEN)
user_payments = {}
promocodes = {}

DATA_FILE = 'payments.json'
PROMO_FILE = 'promocodes.json'

# ============ ФУНКЦИИ ДЛЯ РАБОТЫ С 3X-UI ============
session = requests.Session()

def login_to_xui():
    try:
        login_data = {
            "username": XUI_USERNAME,
            "password": XUI_PASSWORD
        }
        response = session.post(f"{XUI_URL}/login", data=login_data, timeout=10)
        return response.status_code == 200
    except:
        return False

def create_client_in_panel(email, total_gb=100, limit_ip=1, expire_timestamp=0):
    """Создаёт клиента в 3x-ui, возвращает VLESS-ссылку или None"""
    if not login_to_xui():
        return None

    client_data = {
        "email": email,
        "totalGB": total_gb,
        "limitIp": limit_ip,
        "expiryTime": expire_timestamp,  # 0 = без ограничения
        "enable": True
    }
    try:
        response = session.post(f"{XUI_URL}/addClient", json=client_data, timeout=10)
        if response.status_code == 200:
            # Получаем ссылку
            link_resp = session.get(f"{XUI_URL}/getClientConfig/{INBOUND_ID}/{email}", timeout=10)
            if link_resp.status_code == 200:
                data = link_resp.json()
                if data.get('success'):
                    return data.get('obj', {}).get('vless', None)
    except:
        return None
    return None

def remove_client_from_panel(email):
    """Удаляет клиента из панели по email"""
    if not login_to_xui():
        return False
    try:
        response = session.post(f"{XUI_URL}/delClient", json={"email": email}, timeout=10)
        return response.status_code == 200
    except:
        return False

# ============ ЗАГРУЗКА/СОХРАНЕНИЕ ДАННЫХ ============
def load_data():
    global user_payments
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            user_payments = json.load(f)
    else:
        user_payments = {}

def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(user_payments, f, ensure_ascii=False, indent=2)

def load_promos():
    global promocodes
    if os.path.exists(PROMO_FILE):
        with open(PROMO_FILE, 'r', encoding='utf-8') as f:
            promocodes = json.load(f)
    else:
        promocodes = {}

def save_promos():
    with open(PROMO_FILE, 'w', encoding='utf-8') as f:
        json.dump(promocodes, f, ensure_ascii=False, indent=2)

load_data()
load_promos()

# ============ ДОСТУП ============
def has_access(user_id):
    user_data = user_payments.get(str(user_id), {})
    if not user_data.get('has_access', False):
        return False
    if user_data.get('expires_at', 0) > 0 and user_data['expires_at'] < time.time():
        return False
    return True

def grant_access(user_id, expires_at=0, vless_link=None):
    user_id_str = str(user_id)
    user_payments[user_id_str] = {
        'has_access': True,
        'expires_at': expires_at,
        'vless_link': vless_link,
        'paid': True
    }
    save_data()

def block_user(user_id):
    user_id_str = str(user_id)
    if user_id_str in user_payments:
        user_payments[user_id_str]['has_access'] = False
        save_data()
        return True
    return False

# ============ АВТОМАТИЧЕСКАЯ ПРОВЕРКА ИСТЕКАЮЩИХ ПОДПИСОК ============
def subscription_checker():
    while True:
        now = time.time()
        to_block = []
        for uid, data in user_payments.items():
            if data.get('has_access') and data.get('expires_at', 0) > 0 and data['expires_at'] < now:
                to_block.append(uid)
        for uid in to_block:
            block_user(uid)
            try:
                bot.send_message(int(uid), "❌ Ваша подписка истекла. Для продления нажмите /start")
            except:
                pass
        time.sleep(3600)  # проверка раз в час

threading.Thread(target=subscription_checker, daemon=True).start()

# ============ ОТПРАВКА УВЕДОМЛЕНИЙ АДМИНУ ============
def send_access_request_to_admin(user_id, username):
    text = f"🔔 НОВЫЙ ЗАПРОС НА ДОСТУП!\n👤 @{username or 'no username'}\n🆔 {user_id}\n✅ /grant {user_id}"
    bot.send_message(ADMIN_ID, text)

# ============ АДМИН-КОМАНДЫ ============
@bot.message_handler(commands=['grant'])
def grant_access_command(message):
    if message.chat.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ /grant USER_ID")
        return
    user_id = parts[1]
    grant_access(user_id, expires_at=time.time() + 30*86400)
    bot.reply_to(message, f"✅ Доступ выдан {user_id} на 30 дней")
    try:
        bot.send_message(int(user_id), "🎉 Администратор выдал вам доступ! Нажмите /start")
    except:
        pass

@bot.message_handler(commands=['block'])
def block_command(message):
    if message.chat.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ /block USER_ID")
        return
    user_id = parts[1]
    if block_user(user_id):
        bot.reply_to(message, f"✅ {user_id} заблокирован")

@bot.message_handler(commands=['unblock'])
def unblock_command(message):
    if message.chat.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ /unblock USER_ID")
        return
    user_id = parts[1]
    grant_access(user_id, expires_at=time.time() + 30*86400)
    bot.reply_to(message, f"✅ {user_id} разблокирован")

@bot.message_handler(commands=['users'])
def list_users(message):
    if message.chat.id != ADMIN_ID:
        return
    text = "👥 ПОЛЬЗОВАТЕЛИ:\n"
    for uid, data in user_payments.items():
        status = "✅" if data.get('has_access') else "❌"
        expires = datetime.fromtimestamp(data['expires_at']).strftime('%d.%m') if data.get('expires_at') else "∞"
        text += f"{status} {uid} до {expires}\n"
    bot.reply_to(message, text)

# ============ ПРОМОКОДЫ ============
@bot.message_handler(commands=['createpromo'])
def create_promo(message):
    if message.chat.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 5:
        bot.reply_to(message, "❌ /createpromo forever/month days_until_expire discount_value max_uses\nПример: /createpromo month 30 50 10")
        return
    tariff = parts[1]
    days = int(parts[2])
    discount = int(parts[3])
    max_uses = int(parts[4])
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    promocodes[code] = {
        'tariff': tariff,
        'days': days,
        'discount': discount,
        'max_uses': max_uses,
        'used_count': 0
    }
    save_promos()
    bot.reply_to(message, f"✅ Промокод {code} создан (скидка {discount}₽, {max_uses} активаций)")

@bot.message_handler(commands=['promo'])
def promo(message):
    if not has_access(message.chat.id):
        send_main_menu(message.chat.id)
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ /promo КОД")
        return
    code = parts[1]
    if code not in promocodes:
        bot.reply_to(message, "❌ Неверный промокод")
        return
    promo = promocodes[code]
    if promo['used_count'] >= promo['max_uses']:
        bot.reply_to(message, "❌ Промокод уже использован")
        return
    discount = promo['discount']
    promo['used_count'] += 1
    save_promos()
    bot.reply_to(message, f"✅ Промокод активирован! Ваша скидка {discount}₽ будет применена при покупке")

# ============ МЕНЮ И ПОКУПКА ============
def send_main_menu(chat_id):
    if has_access(chat_id):
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton('💰 Купить', callback_data='buy'),
            types.InlineKeyboardButton('🎁 Пробный период', callback_data='trial'),
            types.InlineKeyboardButton('🆘 Поддержка', callback_data='support')
        )
        bot.send_message(chat_id, "🏆 Главное меню", reply_markup=markup)
    else:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton('🔓 Получить доступ', callback_data='request_access'))
        bot.send_message(chat_id, "🔒 У вас нет доступа. Нажмите кнопку, чтобы запросить его.", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'request_access')
def request_access_callback(call):
    send_access_request_to_admin(call.from_user.id, call.from_user.username)
    bot.answer_callback_query(call.id, "Запрос отправлен администратору")
    bot.send_message(call.from_user.id, "📩 Запрос отправлен")

@bot.callback_query_handler(func=lambda call: call.data == 'buy')
def buy_callback(call):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton('🔥 Навсегда (499₽)', callback_data='forever'),
        types.InlineKeyboardButton('📆 Месяц (99₽)', callback_data='month')
    )
    bot.edit_message_text("Выберите тариф:", chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ['forever', 'month'])
def payment_callback(call):
    if call.data == 'forever':
        price = 499
        days = 9999
    else:
        price = 99
        days = 30

    # Применяем скидку, если есть
    # Здесь можно проверить промокод пользователя (упрощённо)

    label = f"{call.data}_{call.from_user.id}_{int(time.time())}"
    user_payments[str(call.from_user.id)] = {
        'label': label,
        'amount': price,
        'type': call.data,
        'paid': False
    }
    save_data()

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton('✅ Я оплатил', callback_data=f'check_{label}'))
    text = f"💰 К оплате: {price}₽\n💳 {WALLET_NUMBER}\nУкажите ID {call.from_user.id}\nПосле оплаты нажмите кнопку"
    bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('check_'))
def check_payment(call):
    label = call.data.replace('check_', '')
    uid = str(call.from_user.id)
    if uid not in user_payments or user_payments[uid].get('label') != label:
        bot.answer_callback_query(call.id, "Ошибка")
        return
    if user_payments[uid].get('paid'):
        bot.answer_callback_query(call.id, "Уже оплачено")
        return

    # Отправляем админу на подтверждение
    bot.send_message(ADMIN_ID, f"🔔 Платёж от {uid}\nТариф {user_payments[uid]['type']}\nСумма {user_payments[uid]['amount']}₽\n/approve {uid}")
    bot.answer_callback_query(call.id, "Заявка отправлена")

@bot.callback_query_handler(func=lambda call: call.data == 'trial')
def trial_callback(call):
    uid = str(call.from_user.id)
    email = f"trial_{uid}_{int(time.time())}"
    expires_at = int(time.time() + 86400)  # 24 часа

    link = create_client_in_panel(email, total_gb=0, limit_ip=1, expire_timestamp=expires_at)
    if link:
        grant_access(call.from_user.id, expires_at=expires_at, vless_link=link)
        bot.send_message(call.from_user.id, f"🎁 Пробный период активирован!\nВаша ссылка:\n{link}\nДействует 24 часа")
        bot.answer_callback_query(call.id, "Пробный период активирован")
    else:
        bot.answer_callback_query(call.id, "Ошибка, попробуйте позже")

@bot.callback_query_handler(func=lambda call: call.data == 'support')
def support_callback(call):
    bot.send_message(call.from_user.id, "🆘 Поддержка: @SOM_VPN69")

@bot.message_handler(commands=['start'])
def start(message):
    send_main_menu(message.chat.id)

# ============ ПОДТВЕРЖДЕНИЕ ОПЛАТЫ АДМИНОМ ============
@bot.message_handler(commands=['approve'])
def approve_payment(message):
    if message.chat.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ /approve USER_ID")
        return
    uid = parts[1]
    if uid not in user_payments:
        bot.reply_to(message, "❌ Платёж не найден")
        return

    user_data = user_payments[uid]
    tariff = user_data['type']
    if tariff == 'forever':
        expires_at = time.time() + 10*365*86400
        total_gb = 0
    else:
        expires_at = time.time() + 30*86400
        total_gb = 100

    email = f"user_{uid}_{int(time.time())}"
    link = create_client_in_panel(email, total_gb=total_gb, limit_ip=1, expire_timestamp=int(expires_at))
    if not link:
        bot.reply_to(message, "❌ Ошибка создания клиента в панели")
        return

    grant_access(uid, expires_at=expires_at, vless_link=link)
    user_payments[uid]['paid'] = True
    save_data()

    bot.reply_to(message, f"✅ Подписка для {uid} активирована")
    try:
        bot.send_message(int(uid), f"✅ Оплата подтверждена!\n🔗 Ваша ссылка:\n{link}")
    except:
        pass

# ============ ЗАПУСК ============
def run_bot():
    while True:
        try:
            print("✅ Бот запущен")
            bot.infinity_polling(timeout=60)
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_bot()
