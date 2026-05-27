# app_full_admin.py — LINE Bot ตอบอัตโนมัติ (ไม่ใช้ .env)
# (c) SITTIPONG
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, ImageMessage, TextSendMessage, ImageSendMessage,
    UnsendEvent, FlexSendMessage
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApiBlob,
)
import re, time, os, io
from datetime import datetime, timezone, timedelta

import csv, threading

import requests
from easy_slipcheck.verify_easyslip import verify_slip

import hashlib
import json


# ====== เก็บรายชื่อผู้ทัก OA ======
USERS_CSV_PATH = os.path.join(os.path.dirname(__file__), "oa_users.csv")
_USERS_LOCK = threading.Lock()

# ====== [เพิ่ม] เส้นทางไฟล์ .txt สำหรับเก็บ UID กับชื่อ ======
USERS_TXT_PATH = os.path.join(os.path.dirname(__file__), "oa_users.txt")

# ====== ใส่คีย์ตรงนี้ ======
SLIP2GO_SECRET_KEY = 'slzX867RxCyE9Vzwxzl8Xau_timGDbugdRz2wZZ8f6E='
LINE_CHANNEL_ACCESS_TOKEN = "JI9s4rEtMYgnaeuz4hCwkQxAfCXU6Wpm+J9GZcJ4HV2Y93Vdxt+odXRrhMhKxPRIt9e2UqmYskLOixXKg2qaqMNAIastgvza7RfaTgiAa+Izo7syjq3VVgDPDybLSxxjnYpFGcd9W/y13tWWSdQhaQdB04t89/1O/w1cDnyilFU="
LINE_CHANNEL_SECRET = "37b355d6c112540b7fe94d8fc2753470"
BASE_PUBLIC_URL = "https://YOUR_DOMAIN"
OA_CHAT_URL = "https://page.line.me/192byfhg"

# ====== [เพิ่ม] UID ของแอดมิน ======
ADMIN_UIDS = {
    "U255dd67c1fef32fb0eae127149c7cadc",  # ← ใส่ UID แอดมินจริง
    "Uf7e207bfdd69d8e41806436fa7a86c14",
    "U163186c5013c8f1e4820291b7b1d86bd",
    "Uc2013ea8397da6d19cbe0f931a04c949",
    "U2f156aa5effee7c1ee349b9320a35381",
}

# ====== CONFIG สำหรับเช็คสลิป ======

# รายชื่อผู้รับที่ยอมรับได้ (หลายชื่อ)
VALID_RECEIVERS = [
    "กิตติเชษฐ์ บุญอินทร์",
    "นาย กิตติเชษฐ์ บุญอินทร์",
    "Mr. kittichet boonin"
]

# ยอดขั้นต่ำ
MIN_AMOUNT = 10

# ป้องกันสลิปซ้ำ
USED_SLIP_REF = set()

# ====== ระบบเก็บรายการเปะ ======
PEH_LIST = {}   # dict[source_key] = [ "ข้อความ..." ]


# ====== ชื่อกลุ่มเป้าหมาย (ไว้โชว์ในแจ้งเตือน) ======
TARGET_GROUP_NAME = "🚀บั้งไฟน้อย 10% • เถ้าแก่น้อย •"

# ====== ค่าตั้งต้นของผลบั้งไฟ ======
SUMMARY_STATS = {"passed": 0, "failed": 0, "draw": 0}

# ====== สร้างโฟลเดอร์เก็บไฟล์รูป ======
MEDIA_DIR = os.path.join(os.path.dirname(__file__), "media")
os.makedirs(MEDIA_DIR, exist_ok=True)

app = Flask(__name__, static_url_path="/media", static_folder=MEDIA_DIR)
line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
line_msg_api_blob = MessagingApiBlob(ApiClient(Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)))
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ====== ข้อความตอบกลับ ======
ACCOUNT_TEXT = (
    "💵💰บัญชีฝากเงิน • เถ้าแก่น้อย • 💰💸\n\n"
    "©️ก๊อปข้อความแล้ววางในแอพได้เลย\n"
    "💰เลขบัญชี : 1901531176\n"
    "🎫ชื่อ : กิตติเชษฐ์ บุญอินทร์\n"
    "🔵ธนาคาร : กสิกรไทย\n\n"
    "💰ฝาก-ถอน ต้องใช้บัญชี เดียวกันเท่านั้นนะครับ ✅\n\n"
    "🙏โอนแล้วกดปุ่มสีเขียวส่งสลิปให้แอดมินหลังบ้านได้เลย🚀"
)

RULES_TEXT = (
    "📔 กติกาการเล่น (ฝากเครดิต)เพื่อเล่น 📝\n\n"
    "- ร้องหาราคาเล่นเอง ไล่- ยั้ง ต่ำ - สูง\n"
    "- มีไลฟ์สดตลอดระยะเวลาในการเล่น\n"
    "- จำราคาเล่นให้ดี หรือแคปไว้เพื่อไม่ให้เกิดปัญหา\n"
    "- โอนฝากเป็นเครดิตไว้ก่อนค่อยมาเล่น\n"
    "- โอนเงินฝากเครดิต แจ้งยอดในไลน์หลังบ้านได้เลย\n"
    "- กรณีบั้งไฟไม่จุดถือว่ายกเลิกไม่ได้เสีย\n"
    "- สามารถถอนได้ตลอดเวลา ถ้าไม่มียอดเล่นค้างอยู่\n"
    "- หักเปอร์เซ็น ร้อยละ 10 ของผู้ที่ได้ ผู้ที่เสียไม่มีการหักเปอร์เซ็น\n"
    "- สงสัยอะไรติดต่อแอดมิน\n"
    "- เมื่อติดกันแล้ว ทั้งสองฝ่ายเป็นอันว่าได้เล่น ถ้ายกเลิกต้องรับรู้กันทั้งสองฝั่ง\n"
    "  ถ้ามีเหตุสุดวิสัยแอดจะตัดสินใจเอง ห้ามยกเลิกข้อความ\n"
    "  ( หากยกแล้วแอดมินตรวจพบ ได้เสียถ้าแผลสมบูรณ์ )\n"
    "- รอลุ้นผลการแข่งขันเสร็จแอดมินจะบวกลบให้เอง ไม่เกิน 5 นาที แต่ล่ะบั้ง"
)

TRIGGERS_ACCOUNT = [r"บช", r"บัญชี"]
TRIGGERS_RULES = [r"กติก", r"วิธีเล่น"]
TRIGGERS_SUMMARY = [r"ผลบั้งไฟวันนี้", r"^summary$", r"^report$"]
TRIGGERS_FLEX = [r"^จบการรายงาน$"]

def _add_peh_item(event, text):
    key = _source_key(event)
    if key not in PEH_LIST:
        PEH_LIST[key] = []

    PEH_LIST[key].append(text)

    # ===== สร้างหัวรายการ =====
    header = (
        f"{TARGET_GROUP_NAME}\n"
        f"สกอบั้งไฟวันนี้\n"
        f"{'-'*25}"
    )

    # ===== สร้างรายการแบบมีเลข =====
    lines = []
    for i, item in enumerate(PEH_LIST[key], start=1):
        lines.append(f"{i}. {item}")

    # รวมทั้งหมดกลับ
    return header + "\n" + "\n".join(lines)



# ====== Utility functions ======
def match_any(text, patterns):
    if not text:
        return False
    t = text.strip()
    return any(re.search(f".*{p}.*", t, re.IGNORECASE) for p in patterns)


MSG_CACHE = {}
CACHE_TTL_SEC = 3600
TZ_BKK = timezone(timedelta(hours=7))
COOLDOWN_SEC = 10
_LAST_CMD_AT = {}

def _fmt_ts_ms_to_bkk(ts_ms: int) -> str:
    dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).astimezone(TZ_BKK)
    return dt.strftime("%d/%m/%Y %H:%M:%S")

def _cache_put(message_id, info):
    now = time.time()
    MSG_CACHE[message_id] = {"ts": now, **info}
    _cache_gc(now)

def _cache_get(message_id):
    data = MSG_CACHE.get(message_id)
    if not data:
        return None
    if time.time() - data.get("ts", 0) > CACHE_TTL_SEC:
        MSG_CACHE.pop(message_id, None)
        return None
    return data

def _cache_gc(now=None):
    now = now or time.time()
    expired = [mid for mid, v in MSG_CACHE.items() if now - v.get("ts", 0) > CACHE_TTL_SEC]
    for mid in expired:
        MSG_CACHE.pop(mid, None)

def _push_to_source(event_source, message):
    st = getattr(event_source, "type", None)
    try:
        if st == "group" and getattr(event_source, "group_id", None):
            line_bot_api.push_message(event_source.group_id, message)
        elif st == "room" and getattr(event_source, "room_id", None):
            line_bot_api.push_message(event_source.room_id, message)
        elif getattr(event_source, "user_id", None):
            line_bot_api.push_message(event_source.user_id, message)
    except Exception:
        pass

def _display_name(event):
    src = event.source
    uid = getattr(src, "user_id", None)
    gid = getattr(src, "group_id", None)
    rid = getattr(src, "room_id", None)
    name = None
    try:
        if gid and uid:
            prof = line_bot_api.get_group_member_profile(gid, uid)
            name = prof.display_name
        elif rid and uid:
            prof = line_bot_api.get_room_member_profile(rid, uid)
            name = prof.display_name
        elif uid:
            prof = line_bot_api.get_profile(uid)
            name = prof.display_name
    except Exception:
        name = None
    if name:
        return name
    if uid:
        return f"user:{uid[:6]}…"
    return "ลูกค้า"

def _image_url(filename: str) -> str:
    return f"{BASE_PUBLIC_URL}/media/{filename}"

def _source_key(event) -> str:
    src = event.source
    return getattr(src, "group_id", None) or getattr(src, "room_id", None) or getattr(src, "user_id", None) or "global"


# ====== ส่วนจัดการไฟล์ oa_users.txt (UID \t DisplayName) ======
def _load_users_txt() -> dict:
    """อ่านข้อมูลปัจจุบันจาก oa_users.txt คืนค่าเป็น dict[uid]=display_name"""
    data = {}
    if os.path.exists(USERS_TXT_PATH):
        try:
            with open(USERS_TXT_PATH, "r", encoding="utf-8", newline="") as f:
                reader = csv.reader(f, delimiter="\t")
                for row in reader:
                    if not row:
                        continue
                    uid = row[0].strip()
                    name = row[1].strip() if len(row) > 1 else ""
                    if uid:
                        data[uid] = name
        except Exception:
            data = {}
    return data

def _save_user_to_txt(uid: str, display_name: str):
    """บันทึก/อัปเดต UID และชื่อ ลง oa_users.txt แบบ atomic (lock + เขียนทั้งไฟล์)"""
    if not uid:
        return
    display_name = display_name or ""
    with _USERS_LOCK:
        data = _load_users_txt()
        if data.get(uid) == display_name:
            return
        data[uid] = display_name
        tmp_path = USERS_TXT_PATH + ".tmp"
        with open(tmp_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            for k in sorted(data.keys()):
                writer.writerow([k, data[k]])
        os.replace(tmp_path, USERS_TXT_PATH)

def _search_uid_by_name(name_query: str, limit: int = 5):
    """ค้นหา UID จากชื่อ (partial match, case-insensitive)"""
    name_query = (name_query or "").strip().casefold()
    if not name_query:
        return []
    data = _load_users_txt()  # dict[uid]=display_name
    results = []
    for uid, name in data.items():
        if (name or "").casefold().find(name_query) != -1:
            results.append((uid, name))
        if len(results) >= limit:
            break
    return results

# ====== Flex Template ======
def _progress_bar(value: int, total: int, color: str, track="#E5E7EB", height="12px"):
    value = max(0, value)
    total = max(1, total)
    filled = value
    remain = max(0, total - value)
    return {
        "type": "box",
        "layout": "vertical",
        "contents": [
            {
                "type": "box",
                "layout": "horizontal",
                "height": height,
                "cornerRadius": "999px",
                "backgroundColor": track,
                "contents": [
                    {"type": "box","layout": "vertical","cornerRadius": "999px","backgroundColor": color,"contents": [],"flex": filled},
                    {"type": "box","layout": "vertical","cornerRadius": "999px","backgroundColor": "#00000000","contents": [],"flex": remain}
                ]
            }
        ]
    }

def flex_ungang_bubble():
    return {
        "type": "bubble",
        "size": "giga",
        "body": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#F1FDF1",
            "paddingAll": "20px",
            "spacing": "md",
            "contents": [
                {
                    "type": "text",
                    "text": "🐸🐸 อึ่งอ่างมาแล้วจร้า 🐸🐸",
                    "weight": "bold",
                    "size": "xl",
                    "color": "#16A34A",
                    "align": "center"
                },
                {
                    "type": "text",
                    "text": "รายการจุดบั้งไฟ วันอาทิตย์ที่ 26 ตุลาคม 2568",
                    "size": "sm",
                    "color": "#475569",
                    "align": "center",
                    "wrap": True
                },
                {"type": "separator", "margin": "md", "color": "#D1FAE5"},

                # ========= รายการ อึ่งไข่ =========
                {
                    "type": "text",
                    "text": "🎇 รายการบั้งไฟ สาย 300 บาท (อึ่งไข่)",
                    "weight": "bold",
                    "size": "md",
                    "color": "#065F46",
                    "margin": "sm"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "xs",
                    "contents": [
                        {"type": "text", "text": "• สี่ตระกูล", "size": "sm"},
                        {"type": "text", "text": "• เจ้าทัน", "size": "sm"},
                        {"type": "text", "text": "• นครหลวง", "size": "sm"},
                        {"type": "text", "text": "• ไพศาลเบิกฟ้า", "size": "sm"},
                        {"type": "text", "text": "• ทักกี้รูปหล่อ", "size": "sm"},
                        {"type": "text", "text": "• ส.บุญโฮม", "size": "sm"},
                        {"type": "text", "text": "• หนุ่มเจริญ", "size": "sm"},
                        {"type": "text", "text": "• มหาโหด | @-โป๊ยเซียนคือยาดม- ", "size": "sm"},
                        {"type": "text", "text": "• ส.ไพศาล | @Nuiy Weerapon ", "size": "sm"},
                        {"type": "text", "text": "• จอมยุทธ์", "size": "sm"}
                    ]
                },

                # ========= เส้นคั่น =========
                {"type": "separator", "margin": "lg", "color": "#D1FAE5"},

                # ========= รายการ อึ่งโคม =========
                {
                    "type": "text",
                    "text": "🏮 รายการบั้งไฟ สาย 200 บาท (อึ่งโคม)",
                    "weight": "bold",
                    "size": "md",
                    "color": "#78350F",
                    "margin": "sm"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "xs",
                    "contents": [
                        {"type": "text", "text": "• สี่ตระกูล", "size": "sm"},
                        {"type": "text", "text": "• เจ้าทัน", "size": "sm"},
                        {"type": "text", "text": "• นครหลวง", "size": "sm"},
                        {"type": "text", "text": "• ไพศาลเบิกฟ้า", "size": "sm"},
                        {"type": "text", "text": "• ทักกี้รูปหล่อ| @-โป๊ยเซียนคือยาดม-", "size": "sm"},
                        {"type": "text", "text": "• ส.บุญโฮม", "size": "sm"},
                        {"type": "text", "text": "• หนุ่มเจริญ", "size": "sm"},
                        {"type": "text", "text": "• มหาโหด", "size": "sm"},
                        {"type": "text", "text": "• ส.ไพศาล", "size": "sm"},
                        {"type": "text", "text": "• จอมยุทธ์", "size": "sm"}
                    ]
                },

                # ========= หมายเหตุ =========
                {"type": "separator", "margin": "md", "color": "#D1FAE5"},
                {
                    "type": "text",
                    "text": "💬 โอนก่อนบั้งไฟจุดเท่านั้น ไม่โอนถือว่าไม่ติด\nลงก่อนได้ก่อน!",
                    "size": "sm",
                    "color": "#166534",
                    "wrap": True,
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": "📍หมายเหตุ : ไม่จุด แตกคาฐาน หาย จาวคืนเงิน\nอึ่งไข่ = ได้เวลาเยอะสุด 🐸 | อึ่งโคม = ได้เวลาน้อยสุด 🐸",
                    "size": "xs",
                    "color": "#64748B",
                    "wrap": True,
                    "margin": "sm"
                }
            ]
        }
    }


def flex_summary_bungfai(passed, failed, draw, title_date="วันนี้"):
    total = max(1, passed + failed + draw)
    GREEN, RED, YELLOW = "#16A34A", "#DC2626", "#F59E0B"
    CHIP_BG = {"green": "#DCFCE7", "red": "#FEE2E2", "yellow": "#FEF9C3"}
    TEXT_PRIMARY, TEXT_SECONDARY = "#111827", "#64748B"
    ACCENT, SURFACE, CANVAS = "#0EA5E9", "#FFFFFF", "#F8FAFC"

    def chip(text, bg, fg):
        return {
            "type": "box", "layout": "baseline", "cornerRadius": "999px",
            "backgroundColor": bg, "paddingAll": "8px",
            "contents": [
                {"type": "text", "text": text, "size": "sm",
                 "color": fg, "weight": "bold", "align": "center"}
            ]
        }

    def row(label_left: str, value: int, color: str, chip_bg: str, emoji: str, track="#E5E7EB"):
        return {
            "type": "box", "layout": "vertical", "spacing": "sm", "margin": "md",
            "contents": [
                {"type": "box", "layout": "horizontal", "contents": [
                    {"type": "text", "text": f"{emoji} {label_left}", "size": "md",
                     "weight": "bold", "color": TEXT_PRIMARY, "align": "center", "flex": 1},
                    {"type": "text", "text": f"{value} บั้ง", "size": "md",
                     "align": "center", "color": TEXT_PRIMARY, "weight": "bold", "flex": 1}
                ]},
                _progress_bar(value, total, color=color, track=track, height="12px"),
                {"type": "box", "layout": "horizontal", "justifyContent": "center", "contents": [
                    {"type": "box", "layout": "baseline", "cornerRadius": "999px",
                     "backgroundColor": chip_bg, "paddingAll": "6px",
                     "contents": [
                         {"type": "text", "text": f"{(value * 100 / total):.0f}%",
                          "size": "xs", "color": TEXT_PRIMARY, "weight": "bold", "align": "center"}
                     ]}
                ]}
            ]
        }

    subtitle = f"รวม {total} บั้ง • {title_date}"

    return {
        "type": "bubble", "size": "giga",
        "body": {
            "type": "box", "layout": "vertical", "backgroundColor": CANVAS,
            "contents": [
                {
                    "type": "box", "layout": "vertical", "cornerRadius": "16px",
                    "backgroundColor": SURFACE, "paddingAll": "20px", "spacing": "lg",
                    "contents": [
                        {"type": "text", "text": "สรุปผลบั้งไฟวันนี้",
                         "weight": "bold", "size": "xl", "align": "center", "color": ACCENT},
                        {"type": "text", "text": subtitle,
                         "size": "sm", "align": "center", "color": TEXT_SECONDARY, "margin": "sm"},
                        {"type": "separator", "margin": "md", "color": "#E2E8F0"},
                        row("ผ่าน", passed, GREEN, CHIP_BG["green"], "✅", track="#E6F4EA"),
                        row("ไม่ผ่าน", failed, RED, CHIP_BG["red"], "❌", track="#F8E7E7"),
                        row("จาว", draw, YELLOW, CHIP_BG["yellow"], "⛔", track="#FFF5CC"),
                        {
                            "type": "box", "layout": "horizontal", "spacing": "md",
                            "margin": "lg", "justifyContent": "center",
                            "contents": [
                                chip("✅ ผ่าน", CHIP_BG["green"], TEXT_PRIMARY),
                                chip("❌ ไม่ผ่าน", CHIP_BG["red"], TEXT_PRIMARY),
                                chip("⛔ จาว", CHIP_BG["yellow"], TEXT_PRIMARY)
                            ]
                        },
                        # ✅ เพิ่มเครดิตด้านล่างสุด
                        {
                            "type": "text",
                            "text": f"• กลุ่ม: {TARGET_GROUP_NAME}",
                            "size": "xs",
                            "color": "#94A3B8",
                            "align": "center",
                            "margin": "md",
                            "wrap": True
                        }
                    ]
                }
            ]
        },
        "styles": {"body": {"backgroundColor": CANVAS}}
    }


def flex_calc_admin_bubble():
    """FLEX แสดงวิธีการคิดยอดของแอดมิน"""
    return {
        "type": "bubble",
        "size": "giga",
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "20px",
            "spacing": "md",
            "backgroundColor": "#FFF9EB",
            "contents": [
                {
                    "type": "text",
                    "text": "📊 วิธีการคิดยอดของแอดมิน",
                    "weight": "bold",
                    "size": "xl",
                    "color": "#E04126",
                    "align": "center"
                },
                {
                    "type": "separator",
                    "margin": "sm",
                    "color": "#FCD34D"
                },
                {
                    "type": "text",
                    "text": (
                        "⏱ แอดมินจะใช้เวลาในการคิดยอด\n"
                        "ไม่เกิน 3–5 นาที ต่อบั้ง\n\n"
                        "📋 หากสมาชิกเล่นหลายแผล\n"
                        "แอดมินจะคิดให้ตั้งแต่แผลแรกลงมาเรื่อย ๆ\n"
                        "จนถึงแผลสุดท้ายครับ\n\n"
                        "📩 หากมียอดตกหล่น หรือผิดพลาด\n"
                        "สามารถแจ้งแอดมินได้เลยนะครับ 🙏"
                    ),
                    "wrap": True,
                    "color": "#1F2937",
                    "size": "md",
                    "margin": "md"
                },
                {
                    "type": "separator",
                    "margin": "md",
                    "color": "#FCD34D"
                },
                {
                    "type": "text",
                    "text": "#กลุ่มบั้งไฟน้อย   #เถ้าแก่น้อย",
                    "size": "xs",
                    "color": "#A16207",
                    "align": "center",
                    "margin": "md",
                    "weight": "bold"
                }
            ]
        }
    }


def flex_thanks_bubble():
    return {
        "type": "bubble",
        "size": "giga",
        "hero": {
            "type": "image",
            "url": "https://i.postimg.cc/XJjQ3GPy/4757889.jpg",
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover"
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "paddingAll": "16px",
            "contents": [
                {
                    "type": "text",
                    "text": "วันนี้จบการรายงาน ขอกราบขอบคุณครับ 💖",
                    "weight": "bold",
                    "size": "xl",
                    "align": "center",
                    "color": "#E04126",
                    "wrap": True
                },
                {
                    "type": "text",
                    "text": "ยินดีกับสมาชิกที่ได้ เป็นกำลังใจให้กับสมาชิกที่เสียนะครับ พรุ่งนี้สู้ใหม่ 🎉",
                    "size": "md",
                    "align": "center",
                    "color": "#623112",
                    "wrap": True
                },
                {
                    "type": "separator",
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": "• กลุ่ม: 🚀 บั้งไฟน้อย 10% • เถ้าแก่น้อย •",
                    "size": "xs",
                    "align": "center",
                    "color": "#888888",
                    "wrap": True
                }
            ]
        }
    }


def flex_passed(amount, receiver_name, ref, sender_name):
    return {
        "type": "bubble",
        "size": "giga",
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "20px",
            "spacing": "md",
            "backgroundColor": "#F6FAFF",
            "contents": [

                # Header
                {
                    "type": "box",
                    "layout": "vertical",
                    "paddingAll": "14px",
                    "cornerRadius": "16px",
                    "backgroundColor": "#E0F2FE",
                    "contents": [
                        {
                            "type": "text",
                            "text": "✅ สลิปผ่านการตรวจสอบ",
                            "weight": "bold",
                            "size": "xl",
                            "align": "center",
                            "color": "#0284C7"
                        },
                        {
                            "type": "text",
                            "text": "ระบบตรวจสอบเรียบร้อยแล้ว",
                            "size": "sm",
                            "align": "center",
                            "color": "#38BDF8"
                        }
                    ]
                },

                # Info
                {
                    "type": "box",
                    "layout": "vertical",
                    "paddingAll": "18px",
                    "cornerRadius": "16px",
                    "backgroundColor": "#FFFFFF",
                    "borderWidth": "1px",
                    "borderColor": "#BFDBFE",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"💸 จำนวนเงิน: {amount:,} บาท",
                            "size": "md",
                            "color": "#1E293B",
                            "weight": "bold"
                        },
                        {
                            "type": "text",
                            "text": f"👤 ผู้โอน: {sender_name}",
                            "size": "sm",
                            "color": "#475569"
                        },
                        {
                            "type": "text",
                            "text": f"🏦 ผู้รับเงิน: {receiver_name}",
                            "size": "sm",
                            "color": "#475569"
                        },
                        {
                            "type": "separator",
                            "margin": "md",
                            "color": "#E2E8F0"
                        },
                        {
                            "type": "text",
                            "text": f"🔖 Ref: {ref}",
                            "size": "xs",
                            "color": "#94A3B8"
                        },
                    ]
                },

                # Footer
                {
                    "type": "text",
                    "text": "• ระบบบั้งไฟน้อย • เถ้าแก่น้อย •",
                    "size": "xs",
                    "align": "center",
                    "color": "#94A3B8",
                    "margin": "md"
                }
            ]
        }
    }




def flex_failed(reason, amount=None, receiver_name=None, sender_name=None):
    return {
        "type": "bubble",
        "size": "giga",
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "20px",
            "spacing": "md",
            "backgroundColor": "#FFF5F5",
            "contents": [
                {
                    "type": "text",
                    "text": "❌ สลิปไม่ผ่านตรวจสอบ",
                    "weight": "bold",
                    "size": "xl",
                    "align": "center",
                    "color": "#DC2626"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "paddingAll": "16px",
                    "cornerRadius": "16px",
                    "backgroundColor": "#FFFFFF",
                    "borderColor": "#FECACA",
                    "borderWidth": "1px",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"สาเหตุ: {reason}",
                            "wrap": True,
                            "color": "#B91C1C",
                            "size": "md",
                            "weight": "bold"
                        },
                        {
                            "type": "text",
                            "text": f"ยอด: {amount:,} บาท" if amount else "",
                            "size": "sm",
                            "color": "#475569"
                        },
                        {
                            "type": "text",
                            "text": f"ผู้โอน: {sender_name}" if sender_name else "",
                            "size": "sm",
                            "color": "#475569"
                        },
                        {
                            "type": "text",
                            "text": f"ผู้รับเงิน: {receiver_name}" if receiver_name else "",
                            "size": "sm",
                            "color": "#94A3B8"
                        }
                    ]
                },
                {
                    "type": "text",
                    "text": "⚠️ โปรดตรวจสอบข้อมูลแล้วลองอีกครั้ง",
                    "size": "xs",
                    "align": "center",
                    "color": "#9CA3AF",
                    "margin": "md"
                }
            ]
        }
    }


def flex_duplicate(ref=None):
    return {
        "type": "bubble",
        "size": "giga",
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "20px",
            "spacing": "md",
            "backgroundColor": "#FFFBEB",
            "contents": [
                {
                    "type": "text",
                    "text": "⚠️ สลิปนี้ถูกใช้แล้ว",
                    "weight": "bold",
                    "size": "xl",
                    "align": "center",
                    "color": "#D97706"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "paddingAll": "16px",
                    "cornerRadius": "16px",
                    "backgroundColor": "#FFFFFF",
                    "borderColor": "#FDE68A",
                    "borderWidth": "1px",
                    "contents": [
                        {
                            "type": "text",
                            "text": "ระบบตรวจพบว่าสลิปนี้เคยใช้ไปแล้ว",
                            "wrap": True,
                            "size": "md",
                            "color": "#92400E"
                        },
                        {
                            "type": "text",
                            "text": f"Ref: {ref}" if ref else "",
                            "size": "sm",
                            "color": "#6B7280",
                            "margin": "md"
                        }
                    ]
                },
                {
                    "type": "text",
                    "text": "กรุณาส่งสลิปใหม่อีกครั้ง 🧾",
                    "size": "xs",
                    "align": "center",
                    "color": "#A16207"
                }
            ]
        }
    }







@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_data(as_text=True)
    signature = request.headers.get("X-Line-Signature", "")
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"


# ====== Message Handlers ======
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_text = event.message.text or ""
    user_id = getattr(event.source, "user_id", None)

    # ===== เก็บข้อความลงแคช พร้อมรองรับกรณี reply =====
    sender_name = _display_name(event) or ""

    # ตรวจว่าข้อความนี้ตอบกลับข้อความไหน
    reply_to_id = getattr(event.message, "quotedMessageId", None)



    _cache_put(event.message.id, {
        "type": "text",
        "text": user_text,
        "uid": user_id,
        "name": sender_name,
        "reply_token": event.reply_token,   # เพื่อให้ reply แบบฟรี
        "reply_to_id": reply_to_id          # เก็บว่า reply มาจากข้อความไหน
    })


    # บันทึก UID + ชื่อลงไฟล์
    try:
        if user_id:
            _save_user_to_txt(user_id, sender_name)
    except Exception:
        pass

    is_admin = user_id in ADMIN_UIDS

    # === คำสั่ง "@ชื่อ uid" (เฉพาะแอดมิน) ===
    m_uid_lookup = re.match(r"^@(.+?)\s+uid$", user_text.strip(), re.IGNORECASE)
    if m_uid_lookup and is_admin:
        query_name = m_uid_lookup.group(1).strip()
        matches = _search_uid_by_name(query_name, limit=10)
        if not matches:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"ไม่พบชื่อที่ตรงกับ “{query_name}” ในระบบ")
            )
            return
        if len(matches) == 1:
            uid_found, name_found = matches[0]
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"🔍 UID ของ {name_found or 'ไม่ทราบชื่อ'} คือ:\n{uid_found}")
            )
            return
        lines = ["พบหลายคนที่ชื่อคล้ายกัน (ลองระบุให้แคบลง):"]
        for uid_found, name_found in matches:
            lines.append(f"• {name_found or '(ไม่มีชื่อ)'}  →  {uid_found}")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="\n".join(lines)))
        return

    # === UID ของตัวเอง ===
    if user_text.strip().lower() == "uid":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=f"🔍 UID ของคุณคือ:\n{user_id or 'ไม่พบ UID'}")
        )
        return
    
    if is_admin and "เปะ" in user_text:

        lines = user_text.split("\n")
        added = False
        final_output = None

        for line in lines:
            m = re.match(r"^เปะ\s+(.+)$", line.strip())
            if m:
                item_text = m.group(1).strip()
                final_output = _add_peh_item(event, item_text)
                added = True

        if added:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=final_output)
            )
            return

    if user_text.strip() == "ล้างรายการ" and is_admin:
        key = _source_key(event)
        PEH_LIST[key] = []
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text="ล้างรายการเรียบร้อย"))
        return

    
    # ====== [ตั้งค่าเปิด/ปิดฟีเจอร์ชวนเล่น] ======
    ENABLE_INVITE_FLEX = True   # 🔘 True = เปิด / False = ปิด

    # ====== ชวนเล่น (เฉพาะแอดมิน / เปิดปิดได้ใน Config) ======
    if re.search(r"^ชวนเล่น$", user_text.strip(), re.IGNORECASE):
        if not is_admin:
            return

        # 🔒 ถ้า Config ปิดไว้ ให้แจ้งแอดมิน
        if not ENABLE_INVITE_FLEX:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="⚠️ ระบบชวนเล่นถูกปิดอยู่ใน Config (ENABLE_INVITE_FLEX = False)")
            )
            return

        if _hit_cooldown(event, "invite"):
            return

        # ===== Flex เนื้อหาชวนเล่น =====
        bubble = {
            "type": "bubble",
            "size": "giga",
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "20px",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "🚀 บั้งไฟน้อยเถ้าแก่น้อย!",
                        "weight": "bold",
                        "size": "xl",
                        "color": "#E04126",
                        "align": "center"
                    },
                    {
                        "type": "text",
                        "text": "🔥 มาครัยสมาชิกบั้งแรกขึ้นฐานเรียบร้อยครับ!",
                        "size": "md",
                        "color": "#623112",
                        "align": "center",
                        "wrap": True
                    },
                    {"type": "separator", "margin": "md"},
                    {
                        "type": "text",
                        "text": "🔥วันนี้เจอกันที่ สาราคาม รับประกันความมันส์เช่นเดิม!! หมานๆคร้าบ🙏🏻",
                        "wrap": True,
                        "color": "#166534",
                        "margin": "sm",
                        "size": "sm"
                    }
                ]
            }
        }

        # ส่ง Flex กลับให้แอดมินดู
        line_bot_api.reply_message(
            event.reply_token,
            FlexSendMessage(alt_text="🚀 บั้งไฟน้อยชวนมาเล่นวันนี้!", contents=bubble)
        )
        return

    
    


    # ====== วิธียก (เฉพาะแอดมิน) ======
    if re.search(r"^วิธียก$", user_text.strip(), re.IGNORECASE):
        if not is_admin:
            return
        if _hit_cooldown(event, "flex_cancel_rules"):
            return

        bubble = {
            "type": "bubble",
            "size": "giga",
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "20px",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "📜 กฏการยกเลิก / เปลี่ยนแปลงแผล",
                        "weight": "bold",
                        "size": "xl",
                        "color": "#E04126",
                        "align": "center",
                    },
                    {
                        "type": "separator",
                        "margin": "sm",
                        "color": "#E2E8F0"
                    },
                    {
                        "type": "text",
                        "text": (
                            "❌ แผลยกเลิก\n"
                            "ให้สมาชิกตกลงกันทั้งสองฝ่ายถึงจะสามารถยกเลิกได้\n"
                            "ถ้าตอบผิด หรือจะบ่ติดแล้วต้องแจ้งให้อีกฝ่ายรับรู้\n"
                            "แล้วตกลงกันก่อนว่าจะยก ถ้าอีกฝ่ายบ่รับรู้\n"
                            "ให้ ‘ยึดแผลเดิม’ เป็นแผลสมบูรณ์นะครับสมาชิก 🙏"
                        ),
                        "wrap": True,
                        "size": "md",
                        "color": "#111827",
                        "margin": "md"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "margin": "lg",
                        "contents": [
                            {
                                "type": "text",
                                "text": "💡 หมายเหตุ:",
                                "weight": "bold",
                                "color": "#E04126",
                                "size": "sm"
                            },
                            {
                                "type": "text",
                                "text": (
                                    "- อย่ายกเลิกข้อความหลังจากติดกันแล้ว\n"
                                    "- หากแอดมินตรวจพบการลบข้อความโดยไม่ได้รับอนุญาต\n"
                                    "  อาจถูกตัดสินให้ ‘ได้เสียตามแผลเดิม’"
                                ),
                                "wrap": True,
                                "size": "sm",
                                "color": "#475569"
                            }
                        ]
                    },
                    {
                        "type": "separator",
                        "margin": "md",
                        "color": "#E2E8F0"
                    },
                    {
                        "type": "text",
                        "text": f"• กลุ่ม: {TARGET_GROUP_NAME}",
                        "size": "xs",
                        "color": "#94A3B8",
                        "align": "center",
                        "margin": "md",
                        "wrap": True
                    }
                ]
            }
        }

        line_bot_api.reply_message(
            event.reply_token,
            FlexSendMessage(alt_text="กฏการยกเลิก / เปลี่ยนแปลงแผล", contents=bubble)
        )
        return
    

    # === คำสั่ง "ผล 20 30 4" (เฉพาะแอดมิน) ===
    m = re.match(r"^ผล\s*(\d+)\s+(\d+)\s+(\d+)$", user_text.strip())
    if m and is_admin:
        SUMMARY_STATS["passed"], SUMMARY_STATS["failed"], SUMMARY_STATS["draw"] = map(int, m.groups())
        bubble = flex_summary_bungfai(**SUMMARY_STATS)
        line_bot_api.reply_message(event.reply_token,
                                   FlexSendMessage(alt_text="สรุปผลบั้งไฟวันนี้ 💥", contents=bubble))
        return

    # ====== ขอบคุณลูกค้า (เฉพาะแอดมิน) ======
    if match_any(user_text, TRIGGERS_FLEX):
        if not is_admin:
            return
        if _hit_cooldown(event, "flex_thanks"):
            return
        bubble = flex_thanks_bubble()
        line_bot_api.reply_message(event.reply_token,
                                   FlexSendMessage(alt_text="ขอบคุณลูกค้าทุกท่าน 💥", contents=bubble))
        return

    # ====== ผลบั้งไฟวันนี้ (เฉพาะแอดมิน) ======
    if match_any(user_text, TRIGGERS_SUMMARY):
        if not is_admin:
            return
        if _hit_cooldown(event, "summary"):
            return
        bubble = flex_summary_bungfai(**SUMMARY_STATS)
        line_bot_api.reply_message(event.reply_token,
                                   FlexSendMessage(alt_text="สรุปผลบั้งไฟวันนี้ 💥", contents=bubble))
        return

    # ====== บัญชี (รองรับหลายคำ เช่น บช / บันชี / บัญชี / ขอบัญชี) ======
    if re.search(r"^(บช|บันชี|บัญชี|บันขี|เลขบัญชี|เลข.บัญชี|เลขบันชี|บัณชี|ขอบัญชี)$", user_text.strip(), re.IGNORECASE):
        if _hit_cooldown(event, "account"):
            return

        flex_bubble = {
            "type": "bubble",
            "size": "kilo",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "height": "sm",
                        "action": {
                            "type": "uri",
                            "label": "📤 กดปุ่มเพื่อส่งสลิป",
                            "uri": OA_CHAT_URL
                        }
                    }
                ]
            }
        }

        line_bot_api.reply_message(
            event.reply_token,
            [
                TextSendMessage(text=ACCOUNT_TEXT),
                FlexSendMessage(alt_text="💰 ส่งสลิปยืนยันที่นี่", contents=flex_bubble)
            ]
        )
        return


    # ====== ถอนทั้งหมด (เฉพาะแอดมิน) ======
    if re.search(r"^ถอนทั้งหมด$", user_text.strip(), re.IGNORECASE):
        if not is_admin:
            return
        if _hit_cooldown(event, "withdraw_all"):
            return

        bubble = {
            "type": "bubble",
            "size": "giga",
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "20px",
                "spacing": "md",
                "backgroundColor": "#F0FDF4",
                "contents": [
                    {
                        "type": "text",
                        "text": "💸 เคลียร์ยอดถอนทั้งหมดแล้วครับ 💸",
                        "weight": "bold",
                        "size": "xl",
                        "color": "#16A34A",
                        "align": "center"
                    },
                    {
                        "type": "separator",
                        "margin": "sm",
                        "color": "#BBF7D0"
                    },
                    {
                        "type": "text",
                        "text": (
                            "✅ แอดมินได้ทำการเคลียร์ยอดถอนทั้งหมดเรียบร้อยแล้ว\n"
                            "📅 หากมีรายการค้าง แจ้งหลังบ้านได้เลยครับ\n\n"
                            "🙏 ขอบคุณทุกท่านที่ร่วมสนุกวันนี้ครับ 💚"
                        ),
                        "wrap": True,
                        "color": "#14532D",
                        "size": "md",
                        "margin": "md"
                    },
                    {
                        "type": "separator",
                        "margin": "md",
                        "color": "#BBF7D0"
                    },
                    {
                        "type": "text",
                        "text": f"• กลุ่ม: {TARGET_GROUP_NAME}",
                        "size": "xs",
                        "color": "#6B7280",
                        "align": "center",
                        "margin": "md",
                        "wrap": True
                    }
                ]
            }
        }

        line_bot_api.reply_message(
            event.reply_token,
            FlexSendMessage(
                alt_text="💸 เคลียร์ยอดถอนทั้งหมดแล้วครับ 💸",
                contents=bubble
            )
        )
        return




    # ====== กติกา (Flex Version) ======
    if user_text.strip() == "กติกา":
        cmd_name = "rules_exact"
        if _hit_cooldown(event, cmd_name):
            return  # ป้องกันสแปมส่งซ้ำ

        bubble = {
            "type": "bubble",
            "size": "giga",
            "body": {
                "type": "box",
                "layout": "vertical",
                "paddingAll": "20px",
                "backgroundColor": "#FFFDF5",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "📜 กติกาการเล่น บั้งไฟน้อย",
                        "weight": "bold",
                        "size": "xl",
                        "color": "#E04126",
                        "align": "center"
                    },
                    {"type": "separator", "margin": "md", "color": "#FCD34D"},
                    {
                        "type": "text",
                        "text": (
                            "🎯 1. ร้องหาราคาเล่นเอง ไล่-ยั้ง ต่ำ-สูง\n"
                            "💥 2. มีไลฟ์สดตลอดระยะเวลาในการเล่น\n"
                            "📸 3. จำราคาเล่นให้ดี หรือแคปไว้เพื่อไม่ให้เกิดปัญหา\n"
                            "💰 4. โอนฝากเครดิตไว้ก่อนค่อยมาเล่น\n"
                            "📩 5. แจ้งยอดในไลน์หลังบ้านได้เลย\n"
                            "🚫 6. ฝากก่อนเล่น ถ้าหากเล่นไม่มีเครดิต จะไม่ได้เสียทุกกรณี\n"
                            "💸 7. หักเปอร์เซ็น 10% จากผู้ที่ได้เท่านั้น\n"
                            "🕐 8. สามารถถอนได้ทุกเวลา หากไม่มียอดค้างเล่น\n"
                            "⚖️ 9. หากยกเลิก ต้องรับรู้ทั้งสองฝ่าย\n"
                            "🛑 10. ห้ามลบข้อความหลังติดกันแล้ว หากตรวจพบ แอดจะตัดสินให้ได้เสียตามแผล"
                        ),
                        "wrap": True,
                        "color": "#1F2937",
                        "size": "md",
                        "margin": "md"
                    },
                    {"type": "separator", "margin": "md", "color": "#FCD34D"},
                    {
                        "type": "text",
                        "text": "📍หมายเหตุ:\n- รอลุ้นผลการแข่งขัน แอดมินจะบวกลบให้ไม่เกิน 5 นาที\n- สงสัยติดต่อแอดมินได้ทันทีครับ 🙏",
                        "wrap": True,
                        "size": "sm",
                        "color": "#6B7280"
                    },
                    {
                        "type": "text",
                        "text": f"• กลุ่ม: {TARGET_GROUP_NAME}",
                        "size": "xs",
                        "color": "#94A3B8",
                        "align": "center",
                        "margin": "md"
                    }
                ]
            },
            "styles": {"body": {"backgroundColor": "#FFFDF5"}}
        }

        line_bot_api.reply_message(
            event.reply_token,
            FlexSendMessage(
                alt_text="📜 กติกาการเล่น บั้งไฟน้อย",
                contents=bubble
            )
        )
        return


    # ====== วิธีคิดยอด (เฉพาะแอดมิน) ======
    if user_text.strip() == "แอดคิดยอด":
        if not is_admin:
            return
        if _hit_cooldown(event, "calc_admin"):
            return

        bubble = flex_calc_admin_bubble()
        line_bot_api.reply_message(
            event.reply_token,
            FlexSendMessage(
                alt_text="📊 วิธีคิดยอดของแอดมิน",
                contents=bubble
            )
        )
        return

@handler.add(UnsendEvent)
def handle_unsend(event):
    print("🔥 UnsendEvent detected")

    msg_id = event.unsend.message_id
    info = _cache_get(msg_id)

    if not info:
        print("⚠️ ไม่มีข้อมูลข้อความในแคช")
        return

    sender_uid = info.get("uid")             # UID คนที่ลบข้อความ
    sender = info.get("name", "ลูกค้า")      # ชื่อคนที่ลบ
    deleted_text = info.get("text", "(ไม่พบข้อความ)")
    reply_token = info.get("reply_token")
    reply_to_id = info.get("reply_to_id")

    # ❗ แอดมินลบ → ไม่แจ้ง
    if sender_uid in ADMIN_UIDS:
        print(f"⚠️ ข้อความถูกลบโดยแอดมิน ({sender}) → ไม่แจ้งเตือน")
        return

    if not reply_token:
        print("⚠️ reply_token หมดอายุ")
        return

    # นาทีนี้ **ลบปุ๊บแจ้งปั๊บ** → ตัด diff ออกไปเลย
    time_now = datetime.now(TZ_BKK).strftime("%H:%M:%S")

    # ตรวจลบข้อความที่เป็น reply หรือไม่
    origin = _cache_get(reply_to_id) if reply_to_id else None
    original_sender = origin.get("name") if origin else None
    original_text = origin.get("text") if origin else None

    if origin:
        # ลบข้อความ reply
        msg = (
            f"❌❌ มีการลบข้อความตอบกลับ ❌❌\n"
            f"🧑‍💬 ผู้ลบ: {sender}\n"
            f"🗣️ ต้นฉบับของ: {original_sender}\n"
            f"💬 ข้อความที่ถูกลบ: {deleted_text}\n"
            f"💬 ข้อความต้นฉบับ: {original_text}\n"
            f"🕒 เวลา: {time_now}"
        )
    else:
        # ลบข้อความปกติ
        msg = (
            f"❌❌ มีการลบข้อความ ❌❌\n"
            f"🧑‍💬 ผู้ลบ: {sender}\n"
            f"🕒 เวลา: {time_now}\n"
            f"💬 ข้อความที่ถูกลบ: {deleted_text}"
        )

    try:
        line_bot_api.reply_message(reply_token, TextSendMessage(text=msg))
        print("✅ แจ้งเตือนสำเร็จ")
    except Exception as e:
        print("❌ ส่งแจ้งเตือนล้มเหลว:", e)


@handler.add(MessageEvent, message=ImageMessage)
def handle_image(event):
    try:
        # โหลดรูปจาก LINE
        content = line_msg_api_blob.get_message_content(
            message_id=event.message.id, async_req=True
        )
        image_bytes = content.get()
        # ===== สร้าง Image Hash กันสลิปซ้ำ =====
        image_hash = hashlib.sha256(image_bytes).hexdigest()

        # เรียก Slip2Go Basic Mode
        url = "https://connect.slip2go.com/api/verify-slip/qr-image/info"
        headers = {"Authorization": f"Bearer {SLIP2GO_SECRET_KEY}"}

        r = requests.post(
            url,
            headers=headers,
            files={"file": ("slip.jpg", bytes(image_bytes), "image/jpeg")}
        )

        res = r.json()
        code = str(res.get("code", ""))
        data = res.get("data", {})

        # ดึงข้อมูลหลัก
        # ---- สร้างสลิปโค้ดพิเศษกันซ้ำ ----
        raw_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        ref_hash = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
        # ใช้ ref ของ Slip2Go ถ้ามี ถ้าไม่มีให้ใช้ ref_hash
        ref = data.get("referenced") or ref_hash
        amount = data.get("amount", 0)

        receiver_name = (
            data.get("receiver", {})
                .get("account", {})
                .get("name", "")
        )

        sender_name = (
            data.get("sender", {})
                .get("account", {})
                .get("name", "")
        )




        # ===== 1) เช็คสลิปซ้ำด้วย REF ก่อน =====
        if ref in USED_SLIP_REF:
            bubble = flex_duplicate(ref)
            line_bot_api.reply_message(
                event.reply_token,
                FlexSendMessage(alt_text="สลิปซ้ำ", contents=bubble)
            )
            return

        # ===== แล้วค่อยเช็คจากรูปภาพเช่นเดิม =====
        if image_hash in USED_SLIP_REF:
            bubble = flex_duplicate(image_hash[:12])
            line_bot_api.reply_message(
                event.reply_token,
                FlexSendMessage(alt_text="สลิปซ้ำ", contents=bubble)
            )
            return



        # ===== 2) เช็คชื่อผู้รับ (หลายชื่อ) =====
        valid_name = any(receiver_name.strip() == n.strip() for n in VALID_RECEIVERS)

        # ===== 3) เช็คยอดขั้นต่ำ =====
        valid_amount = amount >= MIN_AMOUNT

        # ===== 4) เช็คสถานะ Slip2Go =====
        if code not in ["200000", "200200"]:
            bubble = flex_failed("สลิปไม่ถูกต้องในระบบธนาคาร ❌", amount, receiver_name, sender_name)
            line_bot_api.reply_message(
                event.reply_token,
                FlexSendMessage(alt_text="สลิปไม่ผ่าน", contents=bubble)
            )
            return


        # ===== 5) รวมผลการตรวจสอบ =====
        if not valid_name:
            bubble = flex_failed("ชื่อผู้รับไม่ถูกต้อง", amount, receiver_name, sender_name)
            line_bot_api.reply_message(event.reply_token, FlexSendMessage("fail", bubble))
            return

        if not valid_amount:
            bubble = flex_failed(f"ยอดขั้นต่ำคือ {MIN_AMOUNT} บาท", amount, receiver_name, sender_name)
            line_bot_api.reply_message(event.reply_token, FlexSendMessage("fail", bubble))
            return

        # ===== 6) ถ้าผ่านทั้งหมด → SAVE ว่าใช้แล้ว =====
        USED_SLIP_REF.add(ref)
        USED_SLIP_REF.add(image_hash)

        # ส่ง Flex ผ่าน
        bubble = flex_passed(amount, receiver_name, ref, sender_name)
        line_bot_api.reply_message(
            event.reply_token,
            FlexSendMessage(alt_text="สลิปผ่าน", contents=bubble)
        )

    except Exception as e:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(f"❌ ตรวจสอบสลิปผิดพลาด\n{str(e)}")
        )



def _hit_cooldown(event, cmd_name: str) -> bool:
    now = time.time()
    key = f"{_source_key(event)}::{cmd_name}"
    last = _LAST_CMD_AT.get(key, 0)

    cooldowns = {
        "rules_exact": 240,  # 4 นาที
    }
    cd = cooldowns.get(cmd_name, COOLDOWN_SEC)

    if now - last < cd:
        return True
    _LAST_CMD_AT[key] = now
    return False


from apscheduler.schedulers.background import BackgroundScheduler

def send_daily_invite():
    """ส่ง Flex เชิญชวนผู้เล่นไปยังทุกคน"""
    users = _load_users_txt()  # โหลด UID ทั้งหมด
    if not users:
        print("⚠️ ไม่มีผู้ใช้ใน oa_users.txt")
        return

    bubble = {
        "type": "bubble",
        "size": "giga",
        "body": {
            "type": "box",
            "layout": "vertical",
            "paddingAll": "20px",
            "spacing": "md",
            "contents": [
                {"type": "text", "text": "🚀 บั้งไฟน้อย เถ้าแก่น้อย!", 
                 "weight": "bold", "size": "xl", "color": "#E04126", "align": "center"},
                {"type": "text", "text": "อย่าพลาดบั้งไฟรอบใหม่! มันส์แน่ 💥", 
                 "size": "md", "color": "#623112", "align": "center"},
                {"type": "separator", "margin": "md"},
                {"type": "text", "text": "💬 มาครับสมาชิก\nฝาก พิมพ์ บช ได้เลย!", 
                 "wrap": True, "color": "#166534", "margin": "sm", "size": "sm"},
            ]
        },
    }

    for uid in users.keys():
        try:
            line_bot_api.push_message(uid, FlexSendMessage(
                alt_text="🚀 บั้งไฟน้อย ชวนมาเล่นวันนี้!",
                contents=bubble
            ))
            print(f"✅ ส่งข้อความเชิญไปยัง {uid}")
        except Exception as e:
            print(f"❌ ส่งให้ {uid} ไม่สำเร็จ: {e}")

# ====== ตั้งเวลาให้รันทุกวันตอน 02:05 ======
scheduler = BackgroundScheduler(timezone="Asia/Bangkok")
scheduler.add_job(send_daily_invite, 'cron', hour=13, minute=00)
scheduler.start()

print("🕑 Scheduler started: ส่ง Flex เชิญอัตโนมัติทุกวันเวลา 13:52")
# ====== ตรวจสอบสลิปด้วยรูปภาพ (EasySlip Integration) ======
from easy_slipcheck.verify_easyslip import verify_slip


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)