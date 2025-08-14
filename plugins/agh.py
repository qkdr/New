#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import random
import time
import json
import os
import sys
import signal
from typing import Optional

# ===================== إعدادات المستخدم =====================
# ملاحظة: معلمة الحد هنا اسمها "max" في API وهذا الحد الأقصى مسموح به هو 20
SCRIPTBLOX_API = "https://scriptblox.com/api/script/fetch"
TELEGRAM_BOT_TOKEN = "8296402846:AAHw3svTLmgRVnCImdXMZ9JAsMtyB7zteXE"       # استبدل التوكن هنا
TELEGRAM_CHAT = "@MK7CH"      # ممكن يكون "@channelname" أو رقم (مثلاً "-1001234567890")
PUBLISHED_FILE = "published_scripts.json"
REQUEST_TIMEOUT = 12      # ثواني للـ HTTP requests
POLL_INTERVAL = 60        # ثواني بين محاولات النشر
MAX_TELEGRAM_MESSAGE = 4000  # حد آمن للتأكد من عدم تجاوز حد تيليجرام
DEFAULT_FETCH_MAX = 20    # طبقاً لتوثيق API أقصى قيمة = 20
# ============================================================

session = requests.Session()
session.headers.update({"User-Agent": "ScriptBlox-Telegram-Bot/1.0"})

def safe_html_escape(text: str) -> str:
    if text is None:
        return ""
    return (text.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&#39;"))

def atomic_write(path: str, data):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def load_published() -> list:
    if os.path.exists(PUBLISHED_FILE):
        try:
            with open(PUBLISHED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            print(f"⚠️ خطأ بقراءة ملف المنشورات ({PUBLISHED_FILE}): {e}")
    return []

def save_published(published: list):
    try:
        atomic_write(PUBLISHED_FILE, published)
    except Exception as e:
        print(f"⚠️ خطأ بحفظ ملف المنشورات: {e}")

def fetch_scripts(max_items: int = DEFAULT_FETCH_MAX, page: int = 1) -> Optional[list]:
    """
    Use 'max' parameter (<=20) and 'page'.
    Returns list of scripts or None on error.
    """
    try:
        # ضمان أن max_items ضمن الحدود المسموح بها
        if not isinstance(max_items, int) or max_items <= 0:
            max_items = DEFAULT_FETCH_MAX
        if max_items > DEFAULT_FETCH_MAX:
            max_items = DEFAULT_FETCH_MAX

        params = {"max": max_items, "page": page}
        resp = session.get(SCRIPTBLOX_API, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError:
            print("⚠️ استجابة غير JSON من ScriptBlox:", resp.text[:300])
            return None

        # التوقع وفق التوثيق: data.result.scripts
        if isinstance(data, dict):
            result = data.get("result") or data.get("data") or {}
            scripts = result.get("scripts") if isinstance(result, dict) else None
            if isinstance(scripts, list):
                return scripts
            # fallback: قد تكون الاستجابة مباشرة مصفوفة أو تحت مفتاح آخر
            if isinstance(data.get("scripts"), list):
                return data.get("scripts")
            if isinstance(data, list):
                return data
        print("⚠️ تنسيق الاستجابة من ScriptBlox غير متوقع:", type(data))
        return None
    except requests.HTTPError as e:
        # طباعة نص الرد من السيرفر لو متوفر
        server_text = ""
        try:
            server_text = e.response.text[:500]
        except Exception:
            server_text = ""
        print(f"❌ خطأ في جلب السكربتات من ScriptBlox: {e} | رد السيرفر: {server_text}")
        return None
    except Exception as e:
        print(f"❌ خطأ في جلب السكربتات من ScriptBlox: {e}")
        return None

def choose_script(scripts: list, published: list):
    available = []
    for s in scripts:
        sid = s.get("_id") or s.get("id") or None
        if sid and sid not in published:
            available.append(s)
    if not available:
        return None
    return random.choice(available)

def build_message_payload(script: dict) -> dict:
    name = script.get("title") or script.get("name") or "بدون عنوان"
    game = (script.get("game") or {}).get("name") if isinstance(script.get("game"), dict) else script.get("game") or "غير معروف"
    sid = script.get("_id") or script.get("id") or ""
    url = f"https://scriptblox.com/script/{sid}" if sid else script.get("url") or ""
    code = script.get("script") or script.get("code") or ""

    name_h = safe_html_escape(str(name))
    game_h = safe_html_escape(str(game))
    url_h = safe_html_escape(str(url))
    code_h = safe_html_escape(str(code))

    if len(code_h) > 3500:
        code_h = code_h[:3500] + "\n\n... [مقتطع]"

    text = (
        f"<b>{name_h}</b>\n"
        f"🎮 الماب: <i>{game_h}</i>\n"
    )
    if url_h:
        text += f"🔗 <a href=\"{url_h}\">رابط السكربت</a>\n\n"
    else:
        text += "\n"

    text += f"<pre>{code_h}</pre>"

    if len(text) > MAX_TELEGRAM_MESSAGE:
        overflow = len(text) - MAX_TELEGRAM_MESSAGE
        if len(code_h) > overflow + 20:
            code_h = code_h[: max(0, len(code_h) - overflow - 20 )] + "\n\n... [مقتطع]"
            text = (
                f"<b>{name_h}</b>\n"
                f"🎮 الماب: <i>{game_h}</i>\n"
                + (f"🔗 <a href=\"{url_h}\">رابط السكربت</a>\n\n" if url_h else "\n")
                + f"<pre>{code_h}</pre>"
            )
        else:
            text = (
                f"<b>{name_h}</b>\n🎮 الماب: <i>{game_h}</i>\n"
                + (f"🔗 <a href=\"{url_h}\">رابط السكربت</a>\n\n" if url_h else "\n")
                + "الكود طويل جداً لذا يمكنك فتح الرابط للاطلاع على السكربت كامل."
            )

    payload = {
        "chat_id": TELEGRAM_CHAT,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    return payload

def send_telegram(payload: dict, max_retries: int = 3) -> bool:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    backoff = 1.5
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.post(url, data=payload, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                print("✅ تم الإرسال إلى تيليجرام.")
                return True
            else:
                print(f"⚠️ محاولة {attempt} فشلت، رمز الحالة: {resp.status_code}, رد السيرفر: {resp.text}")
        except Exception as e:
            print(f"⚠️ محاولة {attempt} فشلت بخطأ: {e}")
        time.sleep(backoff ** attempt)
    print("❌ فشل الإرسال إلى تيليجرام بعد عدة محاولات.")
    return False

def validate_config():
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN.startswith("ضع_"):
        print("❌ لم توفّر TELEGRAM_BOT_TOKEN صالح. عدّل المتغير في بداية الملف.")
        return False
    if not TELEGRAM_CHAT or (isinstance(TELEGRAM_CHAT, str) and TELEGRAM_CHAT.strip() == ""):
        print("❌ لم توفّر TELEGRAM_CHAT. ضع معرف القناة مثل @channelname أو رقم القناة.")
        return False
    return True

# Graceful shutdown
running = True
def handle_sigint(sig, frame):
    global running
    print("\n🔴 إشارة إيقاف استلمت — يغلق البرنامج بعد الانتهاء من الدورة الحالية.")
    running = False

signal.signal(signal.SIGINT, handle_sigint)
signal.signal(signal.SIGTERM, handle_sigint)

def main_loop():
    if not validate_config():
        sys.exit(1)
    published = load_published()
    print(f"ℹ️ تم تحميل {len(published)} معرف/معرفات منشورة سابقاً.")
    page = 1
    while running:
        scripts = fetch_scripts(max_items=20, page=page)  # <-- استخدم max_items <=20
        if not scripts:
            print("ℹ️ لا توجد سكربتات مُسترجعة الآن — الانتظار قبل المحاولة التالية.")
            time.sleep(max(POLL_INTERVAL, 30))
            continue

        script = choose_script(scripts, published)
        if not script:
            print("✅ كل السكربتات المسترجعة مُنشورة مسبقاً. سنحاول الصفحة التالية لاحقاً.")
            page += 1
            if page > 10:
                page = 1
                time.sleep(max(POLL_INTERVAL, 60))
            continue

        sid = script.get("_id") or script.get("id") or None
        if not sid:
            print("⚠️ السكربت المَختار لا يحتوي على معرف صالح، تجاوزته.")
            time.sleep(5)
            continue

        payload = build_message_payload(script)
        success = send_telegram(payload, max_retries=4)
        if success:
            published.append(str(sid))
            published = list(dict.fromkeys(published))
            if len(published) > 2000:
                published = published[-2000:]
            save_published(published)
            print(f"✅ سجلنا المعرف {sid} في ملف المنشورات.")
        else:
            print("⚠️ لم نتمكن من إرسال السكربت، لن نقوم بتمييزه كمنشور حتى يتم الإرسال بنجاح.")

        time.sleep(POLL_INTERVAL)

    print("🔵 تم إيقاف البرنامج بأمان.")

if __name__ == "__main__":
    main_loop()