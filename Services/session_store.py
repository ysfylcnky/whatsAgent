"""Sohbet oturumlarının kalıcı (dağıtık) saklanması.

Uygulama önceden oturumları `chat_sessions` adlı global bir dict'te, yani
sürecin RAM'inde tutuyordu. Bu yapı uygulamanın birden fazla replika ile
çalışmasını imkânsız kılıyordu: müşterinin ikinci mesajı başka bir instance'a
düşerse oturum kaybolur, sepet ve sipariş durumu sıfırlanırdı.

Bu modül oturum durumunu süreç dışına (Redis) taşır ve uygulamayı stateless
hâle getirir. İki backend sunulur:

* RedisSessionStore    — production. TTL ile otomatik oturum süresi yönetimi.
* InMemorySessionStore — Redis yapılandırılmamışsa devreye giren yedek.
                         Tek instance'ta önceki davranışı birebir korur.

Çağıran kod backend'i bilmez; yalnızca `SessionRegistry` cephesi ile konuşur.

Identity Map + Unit of Work
---------------------------
`SessionRegistry` bir istek boyunca aynı oturum için HER ZAMAN aynı dict
nesnesini döndürür (Identity Map). Böylece mevcut `session["history"].append(...)`
gibi iç içe mutasyonlar çalışmaya devam eder. İstek sonunda `flush()` çağrısı
dokunulan oturumları tek seferde backend'e yazar (Unit of Work). Bu sayede
mesaj başına onlarca Redis yazması yerine bir tane yapılır.

Istek kapsamı `contextvars` ile tutulduğu için eşzamanlı webhook istekleri
birbirinin oturumunu görmez.
"""

import json
import time
from abc import ABC, abstractmethod
from collections.abc import MutableMapping
from contextvars import ContextVar

from config import REDIS_URL, SESSION_TIMEOUT


# ----------------------------------------------------------------------
# Oturum şeması
# ----------------------------------------------------------------------

def new_session():
    """Boş bir oturumun varsayılan şeması.

    Şema tek noktada tanımlanır; yeni bir alan eklenecekse yalnızca burası
    değiştirilir (DRY).
    """
    return {
        "history": [],
        "products": {},
        "active_url": None,
        "order_state": None,
        "last_order": None,
        "pending_products": None,
        "last_candidates": None,
        "message_count": 0,
        "last_activity": time.time(),
    }


# ----------------------------------------------------------------------
# Backend arayüzü
# ----------------------------------------------------------------------

class SessionStore(ABC):
    """Oturum kalıcılığı için soyut depo (repository)."""

    @abstractmethod
    def load(self, session_id):
        """Oturumu döndürür; yoksa None."""

    @abstractmethod
    def save(self, session_id, session):
        """Oturumu yazar ve süre sayacını tazeler."""

    @abstractmethod
    def delete(self, session_id):
        """Oturumu siler."""

    def cleanup(self):
        """Süresi dolmuş oturumları temizler.

        Redis'te TTL bu işi kendisi yaptığı için varsayılan uygulama boştur.
        """
        return 0


class InMemorySessionStore(SessionStore):
    """Süreç belleğinde saklayan yedek backend.

    Yalnızca tek instance'ta doğrudur; yatay ölçeklemede oturum kaybı yaşanır.
    Redis yapılandırılmadığında uygulamanın çalışmaya devam edebilmesi için
    vardır (fail-open).
    """

    def __init__(self, ttl=SESSION_TIMEOUT):
        self._ttl = ttl
        self._data = {}

    def load(self, session_id):
        return self._data.get(session_id)

    def save(self, session_id, session):
        self._data[session_id] = session

    def delete(self, session_id):
        self._data.pop(session_id, None)

    def cleanup(self):
        now = time.time()

        expired = [
            sid for sid, s in self._data.items()
            if now - s.get("last_activity", 0) > self._ttl
        ]

        for sid in expired:
            del self._data[sid]

        return len(expired)


class RedisSessionStore(SessionStore):
    """Redis üzerinde JSON olarak saklayan backend.

    Her yazmada TTL tazelenir; böylece SESSION_TIMEOUT süresince sessiz kalan
    oturum Redis tarafından otomatik silinir ve ayrı bir temizlik döngüsüne
    gerek kalmaz.

    Redis erişilemezse istisna yükseltilmez: hata loglanır ve oturum o istek
    için boş kabul edilir. Bot yanıt vermeye devam eder, yalnızca bağlamı
    kaybeder — mesajı tamamen düşürmekten iyidir.
    """

    KEY_PREFIX = "wa:session:"

    def __init__(self, client, ttl=SESSION_TIMEOUT):
        self._client = client
        self._ttl = ttl

    def _key(self, session_id):
        return f"{self.KEY_PREFIX}{session_id}"

    def load(self, session_id):
        try:
            raw = self._client.get(self._key(session_id))
        except Exception as e:
            print(f"⚠️ Redis okuma hatası ({session_id}): {e}")
            return None

        if not raw:
            return None

        try:
            return json.loads(raw)
        except (ValueError, TypeError) as e:
            # Bozuk kayıt oturumu kilitlemesin: silinip sıfırdan başlanır.
            print(f"⚠️ Bozuk oturum kaydı silindi ({session_id}): {e}")
            self.delete(session_id)
            return None

    def save(self, session_id, session):
        try:
            self._client.set(
                self._key(session_id),
                json.dumps(session, ensure_ascii=False),
                ex=self._ttl,
            )
        except (TypeError, ValueError) as e:
            # Serileştirilemeyen bir değer oturuma sızmışsa sessizce veri
            # kaybetmek yerine görünür şekilde loglanır.
            print(f"❌ Oturum serileştirilemedi ({session_id}): {e}")
        except Exception as e:
            print(f"⚠️ Redis yazma hatası ({session_id}): {e}")

    def delete(self, session_id):
        try:
            self._client.delete(self._key(session_id))
        except Exception as e:
            print(f"⚠️ Redis silme hatası ({session_id}): {e}")


# ----------------------------------------------------------------------
# Backend seçimi
# ----------------------------------------------------------------------

def build_session_store(redis_url=REDIS_URL, ttl=SESSION_TIMEOUT):
    """REDIS_URL tanımlıysa Redis, değilse bellek içi backend döndürür.

    Bağlantı `ping` ile açılışta doğrulanır; böylece hatalı yapılandırma ilk
    müşteri mesajında değil, uygulama ayağa kalkarken fark edilir.
    """
    if not redis_url:
        print(
            "⚠️ REDIS_URL tanımlı değil — oturumlar bellekte tutulacak. "
            "Bu yapı birden fazla instance ile ÖLÇEKLENMEZ."
        )
        return InMemorySessionStore(ttl)

    try:
        import redis

        client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
            health_check_interval=30,
        )
        client.ping()

        print("✅ Oturum deposu: Redis")
        return RedisSessionStore(client, ttl)

    except Exception as e:
        print(
            f"⚠️ Redis'e bağlanılamadı ({e}) — oturumlar bellekte tutulacak. "
            "Bu yapı birden fazla instance ile ÖLÇEKLENMEZ."
        )
        return InMemorySessionStore(ttl)


# ----------------------------------------------------------------------
# İstek kapsamlı cephe (facade)
# ----------------------------------------------------------------------

# İstek boyunca yüklenmiş oturumlar. Eşzamanlı isteklerin birbirini
# etkilememesi için contextvar kullanılır.
_request_scope = ContextVar("session_request_scope", default=None)


class SessionRegistry(MutableMapping):
    """Eski `chat_sessions` dict'inin yerine geçen depo cephesi.

    Dict arayüzünü koruduğu için çağıran koddaki `registry[sender][...]`
    kullanımları değişmeden çalışır; ancak veriler artık süreç belleğinde
    değil, arkadaki `SessionStore` üzerinde yaşar.
    """

    def __init__(self, store):
        self._store = store

    # -- istek yaşam döngüsü ------------------------------------------

    def begin_request(self):
        """İstek başında temiz bir kimlik haritası (identity map) açar."""
        _request_scope.set({})

    def flush(self):
        """İstek boyunca dokunulan oturumları backend'e yazar."""
        scope = _request_scope.get()

        if not scope:
            return

        for session_id, session in scope.items():
            self._store.save(session_id, session)

        _request_scope.set({})

    def _scope(self):
        scope = _request_scope.get()

        if scope is None:
            # begin_request çağrılmadıysa (ör. arka plan görevi) tek seferlik
            # bir kapsam açılır; davranış yine doğru kalır.
            scope = {}
            _request_scope.set(scope)

        return scope

    # -- MutableMapping arayüzü ---------------------------------------

    def __getitem__(self, session_id):
        scope = self._scope()

        if session_id in scope:
            return scope[session_id]

        session = self._store.load(session_id)

        if session is None:
            raise KeyError(session_id)

        scope[session_id] = session
        return session

    def __setitem__(self, session_id, session):
        self._scope()[session_id] = session

    def __delitem__(self, session_id):
        self._scope().pop(session_id, None)
        self._store.delete(session_id)

    def __contains__(self, session_id):
        scope = self._scope()

        if session_id in scope:
            return True

        session = self._store.load(session_id)

        if session is None:
            # Var olmayan oturum için kayıt OLUŞTURULMAZ.
            return False

        # Bulunan oturum kapsama alınır: `x in reg` ardından gelen `reg[x]`
        # ikinci bir depo okuması yapmaz.
        scope[session_id] = session
        return True

    def __iter__(self):
        # Oturumların tamamını dolaşmak dağıtık depoda maliyetli ve gereksizdir
        # (temizlik işini TTL yapar). Bilinçli olarak desteklenmez.
        raise NotImplementedError(
            "Oturum deposu üzerinde tam iterasyon desteklenmez."
        )

    def __len__(self):
        raise NotImplementedError(
            "Oturum deposu üzerinde sayım desteklenmez."
        )

    def get(self, session_id, default=None):
        try:
            return self[session_id]
        except KeyError:
            return default

    # -- bakım ---------------------------------------------------------

    def cleanup(self):
        return self._store.cleanup()
