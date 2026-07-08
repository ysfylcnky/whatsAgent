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
from urllib.parse import urlparse
from Services.session_service import (
    store_product,
    build_products_block
)
from config import (
    MAX_HISTORY,
    LONG_SESSION_MESSAGE_LIMIT,
    SESSION_TIMEOUT,
    VERIFY_TOKEN,
    STORE_NOTIFY_PHONE,
    STORE_IBAN,
    STORE_IBAN_NAME,
)
from Services.ikas_service import (
    get_cached_ikas_context,
    get_cached_ikas_context_by_id,
    resolve_product_search,
    match_candidate_by_text,
    _normalize_tr
)
from Services.media_service import (
    download_whatsapp_media,
    transcribe_audio
)
from Services.whatsapp_service import (
    send_whatsapp_message
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

# Havale/EFT IBAN bilgisi prompt'a .env üzerinden enjekte edilir (gerçek IBAN dosyada tutulmaz)
system_prompt = system_prompt.replace(
    "{IBAN_BILGISI}",
    f"{STORE_IBAN} - {STORE_IBAN_NAME}"
)
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


def extract_group_id(value, message):

    # WhatsApp Groups API'den gelen bir mesajsa (gruba özgü bir id alanı taşır),
    # bu id'yi döndürür; normal 1:1 müşteri mesajıysa None döner.
    # NOT: Meta'nın kesin alan adı canlı bir grup mesajıyla doğrulanmalı; olası
    # birkaç konum kontrol edilir. Ham webhook gövdesi zaten yukarıda tam
    # loglanıyor, gerekirse gerçek alan adını oradan teyit edip güncelleyin.
    for source in (message, value):

        if not isinstance(source, dict):
            continue

        for key in ("group_id", "groupId", "group"):

            candidate = source.get(key)

            if not candidate:
                continue

            return candidate if isinstance(candidate, str) else candidate.get("id")

    return None


def slug_to_query(url):

    # Linkin son yol parçasından (slug) İKAS'ta aranabilir bir ürün adı çıkarır
    # Örn: https://.../yeni-sezon-liya-puantiye-etek -> "yeni sezon liya puantiye etek"
    path = url.split("?", 1)[0].rstrip("/")

    slug = path.rsplit("/", 1)[-1]

    return slug.replace("-", " ").replace("_", " ").strip()


# Bu alan adlarındaki linklerin slug'ı ürün adı içermez (Instagram post linki vb.);
# bu linkler İKAS'ta ARANMAZ. Mağazanın kendi ürün linkleri slug→İKAS ile çalışmaya devam eder.
SOCIAL_MEDIA_DOMAINS = (
    "instagram.com",
    "facebook.com",
    "fb.me",
    "fb.watch",
    "m.me"
)


def is_social_media_url(url):

    host = urlparse(url).netloc.lower().split(":")[0]

    return any(
        host == domain or host.endswith("." + domain)
        for domain in SOCIAL_MEDIA_DOMAINS
    )


def build_referral_search_text(message_text, referral):

    # Meta Click-to-WhatsApp reklamında ürün adı reklamın headline/body metnindedir;
    # mesajdaki linkler (Instagram post linki) ürün adı içermediği için çıkarılır.
    text_without_urls = re.sub(
        r"https?://[^\s]+",
        " ",
        message_text or ""
    )

    parts = [
        text_without_urls,
        referral.get("headline") or "",
        referral.get("body") or ""
    ]

    return " ".join(p.strip() for p in parts if p and p.strip()).strip()


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
    # Mağaza bildirim numarasına kısa bilgi geçer ve müşteriye kapanış mesajı gönderir.
    if STORE_NOTIFY_PHONE:

        try:

            send_whatsapp_message(
                STORE_NOTIFY_PHONE,
                "✅ Ödeme dekontu geldi."
            )

        except Exception as e:

            # Bildirim gönderimi başarısız olsa bile akış kesilmez
            print("NOTIFY SEND ERROR:", str(e))

    else:

        print("⚠️ STORE_NOTIFY_PHONE tanımlı değil")

    chat_sessions[sender]["order_state"] = "tamamlandi"

    send_whatsapp_message(
        sender,
        "Dekontunuz elimize ulaştı, siparişiniz hazırlanıp kargoya "
        "verilecek. Teşekkür ederiz 💕"
    )


def _keep_or_reset_order_state(session):

    # Ödeme bekleyen bir sipariş varsa (odeme_bekliyor) yeni ürüne geçiş bu durumu
    # İPTAL ETMEZ — sipariş takibi bozulmasın, sadece ürün gezinmesi engellenmesin.
    # Sipariş yoksa ya da zaten tamamlandıysa yeni ürün için sıfırlanır (aynı
    # oturumda farklı bir ürün için yeni sipariş alınabilir).
    if session.get("order_state") != "odeme_bekliyor":
        session["order_state"] = None


def activate_ikas_product(sender, product_id, intro=""):

    # Seçilen ürünü (net eşleşme ya da müşterinin numaralı listeden seçimi) aktif ürün yapar.
    # intro: yanıtın giriş cümlesi. Net eşleşmede boştur (yanıt doğrudan ürün adıyla başlar);
    # düzeltme akışında "... geçiyorum 😊" gibi anlamlı bir giriş cümlesiyle çağrılır.
    context = get_cached_ikas_context_by_id(product_id)

    if not context:

        return (
            "Ürün bilgisine şu anda ulaşamadım 🙏 Ürün ismini tekrar "
            "yazabilir misiniz?"
        )

    # İKAS'tan bulunan ürün, link akışıyla aynı session yapısına (products/active_url) kaydedilir
    product_key = f"ikas:{product_id}"

    store_product(
        chat_sessions[sender],
        product_key,
        context
    )

    chat_sessions[sender]["active_url"] = product_key
    _keep_or_reset_order_state(chat_sessions[sender])
    chat_sessions[sender]["pending_products"] = None

    detail = ""

    if context.get("available_colors"):
        detail += " Renkler: " + ", ".join(context["available_colors"]) + "."

    if context.get("available_sizes"):
        detail += " Bedenler: " + ", ".join(context["available_sizes"]) + "."

    if context.get("discount_price"):
        detail += f" Fiyatı {context['discount_price']} TL (indirimli)."
    elif context.get("price"):
        detail += f" Fiyatı {context['price']} TL."

    # intro boşsa yanıt doğrudan ürün adıyla başlar (baştaki gereksiz boşluk kalmaz);
    # dolu ise giriş cümlesiyle ürün adı arasına tek boşluk konur.
    prefix = f"{intro} " if intro else ""

    return (
        f"{prefix}{context.get('name', '')}.{detail} "
        "Bu ürünle ilgili sorularınızı sorabilirsiniz."
    )


def handle_urun_ara(sender, urun_ismi):

    # Müşteri ürünü isimle sorduğunda İKAS'tan aranır (aktif ürün olsa da olmasa da).
    try:

        result = resolve_product_search(urun_ismi)

    except Exception as e:

        print("IKAS SEARCH ERROR:", str(e))

        return (
            "Ürünü ararken kısa süreli bir teknik aksaklık oluştu 🙏 "
            "Ürün ismini tekrar yazabilir ya da ürün linkini gönderebilir misiniz?"
        )

    if result["status"] == "not_found":

        chat_sessions[sender]["pending_products"] = None

        return (
            f"\"{urun_ismi}\" ismiyle bir ürün bulamadım 🙏 Ürün ismini "
            "biraz daha açık yazabilir ya da ürün linkini gönderebilir misiniz?"
        )

    if result["status"] == "multiple":

        # Aktif ürün henüz değiştirilmez; müşterinin seçimi bir sonraki mesajda işlenir.
        # last_candidates seçimden SONRA da saklanır ki müşteri "yanlış söyledim,
        # iki numaraymış" gibi düzeltmelerle listeye geri dönebilsin.
        chat_sessions[sender]["pending_products"] = result["candidates"]
        chat_sessions[sender]["last_candidates"] = result["candidates"]

        lines = [
            f"{i + 1}) {candidate['name']}"
            for i, candidate in enumerate(result["candidates"])
        ]

        return (
            "Birkaç ürün buldum, hangisini kastediyorsunuz? 😊\n"
            + "\n".join(lines)
        )

    return activate_ikas_product(sender, result["product_id"])


REFERRAL_ASK_PRODUCT_MESSAGE = (
    "Hoş geldiniz 😊 Hangi ürünle ilgilenmiştiniz? "
    "Ürünün ismini yazabilir misiniz?"
)


def handle_referral_search(sender, search_text):

    # Meta reklamından (Click-to-WhatsApp) gelen ilk mesajda reklam metninden
    # (headline/body) ürün aranır. Net eşleşmede isimle bulma akışının aynısı
    # uygulanır; bulunamazsa nazikçe ürün adı istenir.
    if not search_text:

        chat_sessions[sender]["pending_products"] = None
        return REFERRAL_ASK_PRODUCT_MESSAGE

    try:

        result = resolve_product_search(search_text)

    except Exception as e:

        print("IKAS REFERRAL SEARCH ERROR:", str(e))

        chat_sessions[sender]["pending_products"] = None
        return REFERRAL_ASK_PRODUCT_MESSAGE

    if result["status"] == "single":
        return activate_ikas_product(sender, result["product_id"])

    if result["status"] == "multiple":

        # Aktif ürün henüz değiştirilmez; müşterinin seçimi bir sonraki mesajda işlenir.
        chat_sessions[sender]["pending_products"] = result["candidates"]
        chat_sessions[sender]["last_candidates"] = result["candidates"]

        lines = [
            f"{i + 1}) {candidate['name']}"
            for i, candidate in enumerate(result["candidates"])
        ]

        return (
            "Hoş geldiniz 😊 Birkaç ürün buldum, hangisini kastediyorsunuz?\n"
            + "\n".join(lines)
        )

    chat_sessions[sender]["pending_products"] = None
    return REFERRAL_ASK_PRODUCT_MESSAGE


def try_resolve_pending_selection(sender, message_text):

    # pending_products doluysa müşterinin mesajını seçim olarak yorumlar.
    # Eşleşirse ürünü aktif yapıp yanıt metnini döndürür (mesaj tüketilmiştir).
    # Eşleşmezse bekleyen listeyi iptal edip None döner (normal akışa devam edilir).
    pending = chat_sessions[sender].get("pending_products")

    if not pending:
        return None

    stripped = message_text.strip()

    number_match = re.match(r"^\s*(\d+)", stripped)

    if number_match:

        index = int(number_match.group(1)) - 1

        if 0 <= index < len(pending):
            return activate_ikas_product(sender, pending[index]["id"])

        chat_sessions[sender]["pending_products"] = None
        return None

    matched = match_candidate_by_text(stripped, pending)

    if matched:
        return activate_ikas_product(sender, matched["id"])

    chat_sessions[sender]["pending_products"] = None
    return None


# Sıra sözcükleri önek olarak eşlenir ki ek varyasyonları da yakalansın
# ("ikincisi", "ikinciydi", "ikinciymiş" → "ikinci").
ORDINAL_PREFIXES = (
    ("birinci", 1),
    ("ikinci", 2),
    ("ucuncu", 3),
    ("dorduncu", 4),
    ("besinci", 5)
)

NUMBER_WORDS = {
    "bir": 1,
    "iki": 2,
    "uc": 3,
    "dort": 4,
    "bes": 5
}

# Düzeltme niyetine işaret eden sözcükler (normalize edilmiş halleriyle);
# uzun cümlelerde liste referansı ancak bu ipuçlarından biriyle kabul edilir.
CORRECTION_CUES = (
    "yanlis",
    "pardon",
    "aslinda",
    "hayir",
    "degil",
    "ozur",
    "kusura",
    "affedersin",
    "sehven"
)


def _extract_list_reference(norm_text, candidate_count):

    # Normalize edilmiş mesajdan numaralı liste referansı (1 tabanlı indeks) çıkarır.
    # BİLİNÇLİ olarak çıplak sayılar ("2") ve birimli sayılar ("2 adet", "44 beden")
    # referans SAYILMAZ — sipariş/beden akışındaki sayılarla karışmasın.
    words = re.findall(r"[a-z0-9]+", norm_text)

    # "ikincisi", "aslında birincisi", "üçüncü olsun" gibi sıra sözcükleri
    for word in words:

        if word == "ilki" and candidate_count >= 1:
            return 1

        for prefix, index in ORDINAL_PREFIXES:

            if word.startswith(prefix) and index <= candidate_count:
                return index

    # "2 numara", "2 numaraymış", "2 nolu", "2 no"
    match = re.search(r"\b(\d{1,2})\s*(?:numara\w*|nolu|no)\b", norm_text)

    if match:

        index = int(match.group(1))

        return index if 1 <= index <= candidate_count else None

    # "iki numara", "iki numaraymış"
    match = re.search(
        r"\b(bir|iki|uc|dort|bes)\s*(?:numara\w*|nolu|no)\b",
        norm_text
    )

    if match:

        index = NUMBER_WORDS[match.group(1)]

        return index if index <= candidate_count else None

    # "numara 2", "no 2"
    match = re.search(r"\b(?:numara|no)\s*[:.]?\s*(\d{1,2})\b", norm_text)

    if match:

        index = int(match.group(1))

        return index if 1 <= index <= candidate_count else None

    return None


def try_resolve_candidate_correction(sender, message_text):

    # Son gösterilen numaralı listeye yapılan seçim/düzeltme atıflarını yakalar
    # ("2 numara", "ikincisi", "yanlış söyledim iki numaraymış", "diğeri").
    # pending_products akışından farkı: seçim yapıldıktan SONRA da çalışır
    # (last_candidates yeni bir liste sunulana kadar saklanır).
    session = chat_sessions[sender]

    candidates = session.get("last_candidates")

    if not candidates:
        return None

    norm = _normalize_tr(message_text)
    words = re.findall(r"[a-z0-9]+", norm)

    has_cue = any(
        word.startswith(cue)
        for word in words
        for cue in CORRECTION_CUES
    )

    # Uzun/serbest cümlelerde ("ikinci sorum şu..." gibi) yanlış tetiklemeyi
    # önlemek için açık bir düzeltme ipucu aranır.
    if len(words) > 8 and not has_cue:
        return None

    index = _extract_list_reference(norm, len(candidates))

    # "diğeri / öbürü": iki adaylı listede aktif olmayan ürünü işaret eder
    if index is None and len(candidates) == 2 and re.search(r"\b(digeri|oburu)\b", norm):

        active_url = session.get("active_url") or ""

        if active_url.startswith("ikas:"):

            current_id = active_url.split("ikas:", 1)[1]

            candidate_ids = [c.get("id") for c in candidates]

            if current_id in candidate_ids:
                index = 2 if candidate_ids[0] == current_id else 1

    if index is None:
        return None

    return activate_ikas_product(
        sender,
        candidates[index - 1]["id"],
        intro=f"Tabii, {index} numaralı ürüne geçiyorum 😊"
    )


def refresh_transient_state(session, reset_history=False):

    # Uzayan sohbetlerdeki eski gürültüyü atar: aktif ürün dışındaki ürünler ve
    # bekleyen aday listeleri temizlenir, tamamlanmış sipariş durumu sıfırlanır.
    # Ödeme bekleyen sipariş (odeme_bekliyor) ve aktif ürün KORUNUR — aktif akış bozulmaz.
    active_url = session.get("active_url")

    session["products"] = {
        key: context
        for key, context in session["products"].items()
        if key == active_url
    }

    session["pending_products"] = None
    session["last_candidates"] = None

    if session.get("order_state") != "odeme_bekliyor":
        session["order_state"] = None

    if reset_history:
        session["history"] = []


# Yalnızca selamlamadan ibaret mesajları yakalamak için (normalize edilmiş halleriyle)
GREETING_WORDS = {
    "merhaba", "merhabalar", "selam", "selamlar", "slm", "mrb",
    "gunaydin", "iyi", "gunler", "aksamlar", "geceler",
    "selamunaleykum", "aleykumselam", "hello", "hi", "hey",
    "hayirli", "isler", "kolay", "gelsin"
}


def is_fresh_greeting(text):

    # Mesaj kısa ve yalnızca selamlama sözcüklerinden oluşuyorsa True
    # (ör. "Merhaba", "selam iyi günler"). "merhaba bu ürün var mı" gibi
    # içerikli mesajlar selamlama SAYILMAZ.
    words = re.findall(r"[a-z]+", _normalize_tr(text))

    return 0 < len(words) <= 4 and all(w in GREETING_WORDS for w in words)


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

    # Test/inceleme amaçlı: linkin slug'ından ürün adı çıkarılıp İKAS'ta aranır
    query = slug_to_query(url)

    ai_context, _ = get_cached_ikas_context(query)

    return ai_context or {"error": "not_found", "query": query}

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

        # Grup mesajı ise (WhatsApp Groups API) müşteri mesajı gibi İŞLENMEZ:
        # AI'ya gönderilmez, yanıt verilmez; yalnızca group_id net loglanır
        # (gerçek GROUP_ID'yi buradan da teyit edebilirsiniz).
        group_id = extract_group_id(value, message)

        if group_id:

            print(f"👥 GRUP MESAJI ALGILANDI — group_id: {group_id} "
                  "(müşteri akışına girmedi, yanıt verilmedi)")

            return {"status": "ok"}

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
                "pending_products": None,
                "last_candidates": None,
                "message_count": 0,
                "last_activity": time.time()
            }
        chat_sessions[sender]["last_activity"] = time.time()

        session = chat_sessions[sender]

        session["message_count"] = session.get("message_count", 0) + 1

        # Oturum çok uzadıysa geçici durum tazelenir; bekleyen bir seçim listesi
        # varsa (aktif akış) tazeleme bir sonraki mesaja ertelenir.
        if (
            session["message_count"] >= LONG_SESSION_MESSAGE_LIMIT
            and not session.get("pending_products")
        ):

            print("🧽 Uzun oturum: geçici durum tazelendi")

            refresh_transient_state(session)

            session["message_count"] = 0

        # Müşteri baştan selamlıyorsa eski gürültü (geçmiş dahil) atılır;
        # aktif ürün ve ödeme bekleyen sipariş korunur.
        if is_fresh_greeting(message_text):

            refresh_transient_state(session, reset_history=True)

        url = extract_url(message_text)

        # Meta Click-to-WhatsApp reklamından gelen İLK mesaj referral taşır
        # (value.messages[0].referral); ürün adı reklamın headline/body
        # metnindedir, linkte değil. Sonraki mesajlarda referral gelmez.
        referral = message.get("referral")

        if referral:

            print(
                "📣 META REKLAM REFERRAL — "
                f"source_type: {referral.get('source_type')}, "
                f"source_id: {referral.get('source_id')}, "
                f"ctwa_clid: {referral.get('ctwa_clid')}"
            )

        social_url = url is not None and is_social_media_url(url)

        # Bekleyen ürün adayı listesi varsa (link/referral gelmediği sürece) mesaj önce seçim olarak yorumlanır
        if not url and not referral:

            pending_answer = try_resolve_pending_selection(sender, message_text)

            if pending_answer is not None:

                send_whatsapp_message(
                    sender,
                    pending_answer
                )

                return {"status": "ok"}

            # Seçim yapıldıktan sonra da düzeltme mümkündür:
            # "pardon yanlış söyledim iki numaraymış", "ikincisi", "diğeri"
            correction_answer = try_resolve_candidate_correction(sender, message_text)

            if correction_answer is not None:

                send_whatsapp_message(
                    sender,
                    correction_answer
                )

                return {"status": "ok"}

        # Sosyal medya linkinin slug'ı İKAS'ta aranmaz: referral varsa reklam
        # metninden ürün bulunur, yoksa nazikçe ürün adı istenir. Mağazanın
        # kendi ürün linki gelirse aşağıdaki slug akışı önceliklidir.
        if social_url or (referral and not url):

            chat_sessions[sender]["pending_products"] = None

            if referral:

                assistant_answer = handle_referral_search(
                    sender,
                    build_referral_search_text(message_text, referral)
                )

            else:

                assistant_answer = (
                    "Bu linkteki ürünü göremiyorum 🙏 Hangi ürünle "
                    "ilgilenmiştiniz? Ürünün ismini yazabilir misiniz?"
                )

            send_whatsapp_message(
                sender,
                assistant_answer
            )

            return {"status": "ok"}

        if url:

            # Link ile yeni ürün açılınca bekleyen aday listesi geçersizleşir
            chat_sessions[sender]["pending_products"] = None

            # Link akışı da tek kaynağa (İKAS) akar: slug'dan çıkarılan isimle aranır
            search_query = slug_to_query(url)

            ai_context, product_id = get_cached_ikas_context(search_query)

            if not ai_context:

                send_whatsapp_message(
                    sender,
                    "Bu linkteki ürünü bulamadım 🙏 Ürünün ismini yazabilir misiniz?"
                )

                return {"status": "ok"}

            product_key = f"ikas:{product_id}"

            store_product(
                chat_sessions[sender],
                product_key,
                ai_context
            )

            chat_sessions[sender]["active_url"] = product_key

            # Ödeme bekleyen sipariş varsa yeni ürün linki bu durumu iptal etmez (bkz. _keep_or_reset_order_state)
            _keep_or_reset_order_state(chat_sessions[sender])

            print(
                "KAYDEDİLEN ÜRÜN:",
                chat_sessions[sender]["active_url"]
            )

            cleaned_message = message_text.replace(
                url,
                ""
            ).strip()

            if not cleaned_message:

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

            # Aktif ürün her zaman İKAS kaynaklı ("ikas:<id>"); güncel veri id ile
            # tazelenir. Yenileme başarısız olursa session'daki mevcut context kullanılır.
            if active_url and active_url.startswith("ikas:"):

                product_id = active_url.split("ikas:", 1)[1]

                fresh_context = get_cached_ikas_context_by_id(product_id)

                if fresh_context:

                    store_product(
                        chat_sessions[sender],
                        active_url,
                        fresh_context
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

                order_notify_message = format_order_message(order)

                # Sipariş mağaza WhatsApp numarasına (1:1 mesaj) iletilir
                if STORE_NOTIFY_PHONE:

                    try:

                        send_whatsapp_message(
                            STORE_NOTIFY_PHONE,
                            order_notify_message
                        )

                    except Exception as e:

                        # Bildirim gönderimi başarısız olsa bile akış kesilmez
                        print("NOTIFY SEND ERROR:", str(e))

                else:

                    print("⚠️ STORE_NOTIFY_PHONE tanımlı değil")

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

            # Geçmiş bellekte de sınırsız büyümesin: saklarken de trim edilir
            chat_sessions[sender]["history"] = (
                chat_sessions[sender]["history"][-MAX_HISTORY:]
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
