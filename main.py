import sys

# Windows konsolu (cp1254) emoji içeren print'lerde çökmesin diye UTF-8'e geç
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import PlainTextResponse
import json
import time
import re
from Services.session_service import (
    store_product,
    build_products_block
)
from config import (
    MAX_HISTORY,
    SESSION_TIMEOUT,
    VERIFY_TOKEN,
    WHATSAPP_GROUP_ID,
)
from Services.product_service import (
    get_product_context,
    build_ai_context,
    get_cached_ai_context
)
from Services.ikas_service import get_cached_ikas_context
from Services.media_service import (
    download_whatsapp_media,
    transcribe_audio
)
from Services.whatsapp_service import (
    send_whatsapp_message,
    send_whatsapp_group_message
)
from Services.openai_service import (
    general_chat,
    product_chat
)
from Services.order_service import format_order_message
from Services.usage_logger import initialize_database
from Services.message_service import is_duplicate
from Services.dashboard_service import get_dashboard_data


with open("sales_prompt.txt", "r", encoding="utf-8") as f:
    system_prompt = f.read()
general_prompt = open(
    "general_prompt.txt",
    encoding="utf-8"
).read()


def extract_url(text):

    urls = re.findall(
        r"https?://[^\s]+",
        text
    )

    if urls:
        return urls[0]

    return None


def looks_like_payment_done(text):

    # Müşteri metinle ödeme yaptığını / dekont gönderdiğini belirtiyor mu?
    lower = text.lower()

    keywords = [
        "ödedim",
        "odedim",
        "ödeme yaptım",
        "odeme yaptim",
        "havale yaptım",
        "havale yaptim",
        "eft yaptım",
        "eft yaptim",
        "dekont",
        "parayı yatırdım",
        "parayi yatirdim",
        "parayı gönderdim",
        "parayi gonderdim"
    ]

    return any(k in lower for k in keywords)


def close_order_with_receipt(sender):

    # Havale/EFT siparişinde dekont gelince siparişi kapatır.
    # Gruba kısa bilgi geçer ve müşteriye kapanış mesajı gönderir.
    if WHATSAPP_GROUP_ID:

        try:

            send_whatsapp_group_message(
                WHATSAPP_GROUP_ID,
                "✅ Ödeme dekontu geldi."
            )

        except Exception as e:

            # Grup gönderimi başarısız olsa bile akış kesilmez
            print("GROUP SEND ERROR:", str(e))

    else:

        print("⚠️ WHATSAPP_GROUP_ID tanımlı değil")

    chat_sessions[sender]["order_state"] = "tamamlandi"

    send_whatsapp_message(
        sender,
        "Dekontunuz elimize ulaştı, siparişiniz hazırlanıp kargoya "
        "verilecek. Teşekkür ederiz 💕"
    )


def handle_urun_ara(sender, urun_ismi):

    # Müşteri ürünü isimle sorduğunda İKAS'tan aranır; bulunursa aktif ürün yapılır.
    try:

        context, product_id = get_cached_ikas_context(urun_ismi)

    except Exception as e:

        print("IKAS SEARCH ERROR:", str(e))

        return (
            "Ürünü ararken kısa süreli bir teknik aksaklık oluştu 🙏 "
            "Ürün ismini tekrar yazabilir ya da ürün linkini gönderebilir misiniz?"
        )

    if not context:

        return (
            f"\"{urun_ismi}\" ismiyle bir ürün bulamadım 🙏 Ürün ismini "
            "biraz daha açık yazabilir ya da ürün linkini gönderebilir misiniz?"
        )

    # İKAS'tan bulunan ürün, link akışıyla aynı session yapısına (products/active_url) kaydedilir
    product_key = f"ikas:{product_id}"

    store_product(
        chat_sessions[sender],
        product_key,
        context
    )

    chat_sessions[sender]["active_url"] = product_key
    chat_sessions[sender]["order_state"] = None

    detail = ""

    if context.get("available_colors"):
        detail += " Renkler: " + ", ".join(context["available_colors"]) + "."

    if context.get("available_sizes"):
        detail += " Bedenler: " + ", ".join(context["available_sizes"]) + "."

    if context.get("discount_price"):
        detail += f" Fiyatı {context['discount_price']} TL (indirimli)."
    elif context.get("price"):
        detail += f" Fiyatı {context['price']} TL."

    return (
        f"Buldum 😊 {context.get('name', '')}.{detail} "
        "Bu ürünle ilgili sorularınızı sorabilirsiniz."
    )


def cleanup_sessions():
    now = time.time()

    expired_sessions = []

    for session_id, session in chat_sessions.items():

        if now - session["last_activity"] > SESSION_TIMEOUT:
            expired_sessions.append(session_id)

    for session_id in expired_sessions:
        del chat_sessions[session_id]

    if expired_sessions:
        print(f"🧹 {len(expired_sessions)} oturum temizlendi.")


app = FastAPI()
app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)

templates = Jinja2Templates(
    directory="templates"
)
initialize_database()
chat_sessions = {}


@app.get("/")
def home():
    return {"status": "ok"}


@app.get("/product-context")
def product_context(url: str):

    product = get_product_context(url)

    ai_context = build_ai_context(product)

    return ai_context

@app.get("/admin/dashboard")
def admin_dashboard():

    return get_dashboard_data()

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={}
    )

@app.get("/webhook")
async def verify_webhook(request: Request):

    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(content=challenge)

    return PlainTextResponse(
        content="Verification failed",
        status_code=403
    )


@app.post("/webhook")
async def whatsapp_webhook(request: Request):
    cleanup_sessions()
    body = await request.json()

    value = body["entry"][0]["changes"][0]["value"]

    if "messages" not in value:
        return {"status": "ok"}

    print("WHATSAPP WEBHOOK:")
    print(json.dumps(body, indent=2, ensure_ascii=False))

    try:

        print("TRY BLOĞUNA GİRDİ")

        message = (
            body["entry"][0]
            ["changes"][0]
            ["value"]["messages"][0]
        )

        message_id = message["id"]

        if is_duplicate(message_id):
            print(f"⚠️ Duplicate Message: {message_id}")
            return {"status": "duplicate"}

        sender = message["from"]

        message_type = message.get("type")

        if message_type == "text":

            message_text = message["text"]["body"]

        elif message_type == "audio":

            media_id = message["audio"]["id"]

            audio_bytes = download_whatsapp_media(media_id)

            message_text = transcribe_audio(audio_bytes)

        elif message_type == "image":

            # Ödeme bekleniyorsa gelen görsel dekont olarak işlenir, sipariş kapanır.
            session = chat_sessions.get(sender)

            if session and session.get("order_state") == "odeme_bekliyor":

                close_order_with_receipt(sender)

                return {"status": "ok"}

            send_whatsapp_message(
                sender,
                "Şu an yazılı ve sesli mesajları yanıtlayabiliyorum 😊"
            )

            return {"status": "ok"}

        else:

            send_whatsapp_message(
                sender,
                "Şu an yazılı ve sesli mesajları yanıtlayabiliyorum 😊"
            )

            return {"status": "ok"}

        print("SENDER:", sender)
        print("MESSAGE:", message_text)

        if sender not in chat_sessions:
            chat_sessions[sender] = {
                "history": [],
                "products": {},
                "active_url": None,
                "order_state": None,
                "last_activity": time.time()
            }
        chat_sessions[sender]["last_activity"] = time.time()

        url = extract_url(message_text)

        if url:

            chat_sessions[sender]["active_url"] = url

            # Yeni ürün linki gelince sipariş durumu sıfırlanır (aynı oturumda yeni sipariş alınabilir)
            chat_sessions[sender]["order_state"] = None

            print(
                "KAYDEDİLEN URL:",
                chat_sessions[sender]["active_url"]
            )

            cleaned_message = message_text.replace(
                url,
                ""
            ).strip()

            if not cleaned_message:

                try:

                    ai_context = get_cached_ai_context(url)

                    store_product(
                        chat_sessions[sender],
                        url,
                        ai_context
                    )

                except Exception as e:

                    print("PRODUCT ERROR:", str(e))

                    send_whatsapp_message(
                        sender,
                        "Ürün bilgisine şu anda ulaşamadım 🙏 Linki tekrar gönderebilir misiniz?"
                    )

                    return {"status": "ok"}

                send_whatsapp_message(
                    sender,
                    "Ürünü görüntüledim 😊 Bu ürünle ilgili sorularınızı sorabilirsiniz."
                )

                return {"status": "ok"}

            message_text = cleaned_message

        active_url = chat_sessions[sender]["active_url"]

        order_state = chat_sessions[sender].get("order_state")

        # Havale/EFT'de ödeme bekleniyorsa: müşteri metinle ödeme yaptığını
        # belirtirse dekont kabul edilir ve sipariş kapatılır.
        if order_state == "odeme_bekliyor" and looks_like_payment_done(message_text):

            close_order_with_receipt(sender)

            return {"status": "ok"}

        lower_message = message_text.lower()

        if any(
                phrase in lower_message
                for phrase in [
                    "başka ürün",
                    "farklı ürün",
                    "ürün linki göndereyim",
                    "link göndereyim",
                    "başka bir ürün",
                    "başka ürün hakkında"
                ]
        ):
            send_whatsapp_message(
                sender,
                "Tabii 😊 İncelememi istediğiniz ürünün linkini gönderebilirsiniz."
            )

            return {"status": "ok"}

        if not active_url:
            response = general_chat(
                general_prompt,
                message_text,
                sender
            )

            tool_call = response.get("tool_call")

            if tool_call and tool_call["name"] == "urun_ara":

                assistant_answer = handle_urun_ara(
                    sender,
                    tool_call["arguments"].get("urun_ismi", message_text)
                )

            else:

                assistant_answer = response["answer"]

                if not assistant_answer:

                    assistant_answer = (
                        "Bu konuda size nasıl yardımcı olabilirim? 😊"
                    )

            send_whatsapp_message(
                sender,
                assistant_answer
            )

            return {"status": "ok"}

        try:

            ai_context = get_cached_ai_context(active_url)

            store_product(
                chat_sessions[sender],
                active_url,
                ai_context
            )

            products_block = build_products_block(
                chat_sessions[sender]
            )

            history = chat_sessions[sender]["history"][-MAX_HISTORY:]

            # siparis_olustur tool'u yalnızca yeni sipariş alınabilir durumda (order_state None) verilir
            response = product_chat(
                system_prompt,
                products_block,
                history,
                message_text,
                sender,
                include_order_tool=(order_state is None)
            )
            print(response) # geçici

            tool_call = response.get("tool_call")

            # Müşteri siparişi onayladıysa model siparis_olustur tool'unu çağırır
            if tool_call and tool_call["name"] == "siparis_olustur":

                order = tool_call["arguments"]

                group_message = format_order_message(order)

                # Sipariş mağaza WhatsApp grubuna iletilir
                if WHATSAPP_GROUP_ID:

                    try:

                        send_whatsapp_group_message(
                            WHATSAPP_GROUP_ID,
                            group_message
                        )

                    except Exception as e:

                        # Grup gönderimi başarısız olsa bile akış kesilmez
                        print("GROUP SEND ERROR:", str(e))

                else:

                    print("⚠️ WHATSAPP_GROUP_ID tanımlı değil")

                # Müşteriye dönen bilgilendirme ve sipariş durumu ödeme türüne göre değişir
                if order.get("odeme_sekli") == "Havale/EFT":

                    # Havale/EFT'de önce ödeme/dekont beklenir
                    chat_sessions[sender]["order_state"] = "odeme_bekliyor"

                    assistant_answer = (
                        "Siparişiniz alındı 😊 Ödemenizi yaptıktan sonra "
                        "siparişiniz hazırlanıp kargoya verilecektir. "
                        "Dekontunuzu buraya iletebilirsiniz 💕"
                    )

                else:

                    # Kapıda Ödeme'de sipariş doğrudan tamamlanır
                    chat_sessions[sender]["order_state"] = "tamamlandi"

                    assistant_answer = (
                        "Siparişiniz alındı 😊 En kısa sürede hazırlanıp "
                        "kargoya verilecek. Kargo takip numaranız mesaj olarak "
                        "tarafınıza iletilecek 💕"
                    )

            elif tool_call and tool_call["name"] == "urun_ara":

                assistant_answer = handle_urun_ara(
                    sender,
                    tool_call["arguments"].get("urun_ismi", message_text)
                )

            else:

                assistant_answer = response["answer"]

                # Tool çağrısı yokken içerik None gelirse nazik bir fallback
                if not assistant_answer:

                    assistant_answer = (
                        "Bu konuda size nasıl yardımcı olabilirim? 😊"
                    )

            chat_sessions[sender]["history"].append(
                {
                    "role": "user",
                    "content": message_text
                }
            )

            chat_sessions[sender]["history"].append(
                {
                    "role": "assistant",
                    "content": assistant_answer
                }
            )

            send_whatsapp_message(
                sender,
                assistant_answer
            )

        except Exception as e:

            print("PRODUCT ERROR:", str(e))

            send_whatsapp_message(
                sender,
                "Ürün bilgisi alınırken hata oluştu."
            )


    except Exception as e:

        print("WEBHOOK ERROR:")

        print(str(e))

        try:

            if "sender" in locals():
                send_whatsapp_message(

                    sender,

                    "Şu anda kısa süreli teknik bir aksaklık oluştu 🙏 Lütfen birkaç dakika sonra tekrar dener misiniz?"

                )


        except Exception:

            pass

        return {"status": "error"}

    return {"status": "ok"}
