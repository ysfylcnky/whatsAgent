"""Oturum deposu (Services/session_store.py) için izole doğrulama scripti.

Ana akışa dokunmadan çalışır; canlı Redis gerektirmez. Gerçek bir Redis'e
karşı koşmak için REDIS_URL tanımlıyken `--live` bayrağı ile çalıştırın:

    python debug_session_store.py
    python debug_session_store.py --live
"""

import json
import sys
import time

from Services.session_store import (
    InMemorySessionStore,
    RedisSessionStore,
    SessionRegistry,
    build_session_store,
    new_session,
)


class FakeRedis:
    """Sunucu gerektirmeden RedisSessionStore'u sınamak için asgari çift."""

    def __init__(self):
        self.data = {}
        self.ttls = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ex=None):
        self.data[key] = value
        self.ttls[key] = ex

    def delete(self, key):
        self.data.pop(key, None)
        self.ttls.pop(key, None)

    def ping(self):
        return True


class BrokenRedis(FakeRedis):
    """Redis kesintisini taklit eder — uygulama çökmemeli."""

    def get(self, key):
        raise ConnectionError("redis down")

    def set(self, key, value, ex=None):
        raise ConnectionError("redis down")


results = []


def check(name, condition):
    results.append((name, bool(condition)))
    print(f"{'✅' if condition else '❌'} {name}")


def test_round_trip(store, label):
    """Oturum yazılıp okunduğunda içerik aynen dönmeli."""
    registry = SessionRegistry(store)

    registry.begin_request()
    registry["905551112233"] = new_session()
    registry["905551112233"]["order_state"] = "odeme_bekliyor"
    registry["905551112233"]["history"].append({"role": "user", "content": "M beden var mı?"})
    registry["905551112233"]["products"]["https://x/y"] = {"name": "Elbise"}
    registry.flush()

    # Yeni istek: veriler yalnızca depodan gelebilir.
    registry.begin_request()
    session = registry.get("905551112233")

    check(f"[{label}] oturum yeni istekte bulunuyor", session is not None)
    check(f"[{label}] order_state korundu", session["order_state"] == "odeme_bekliyor")
    check(f"[{label}] history korundu", len(session["history"]) == 1)
    check(f"[{label}] iç içe products korundu", session["products"]["https://x/y"]["name"] == "Elbise")
    check(f"[{label}] Türkçe karakter bozulmadı", session["history"][0]["content"].endswith("var mı?"))


def test_identity_map():
    """Aynı istek içinde aynı dict nesnesi dönmeli (iç içe mutasyon çalışsın)."""
    registry = SessionRegistry(InMemorySessionStore())
    registry.begin_request()
    registry["a"] = new_session()

    check("identity map: aynı nesne", registry["a"] is registry["a"])

    registry["a"]["history"].append({"role": "user", "content": "x"})
    check("iç içe mutasyon görünür", len(registry["a"]["history"]) == 1)


def test_contains_does_not_create():
    """`in` kontrolü var olmayan oturumu OLUŞTURMAMALI."""
    store = InMemorySessionStore()
    registry = SessionRegistry(store)
    registry.begin_request()

    check("bilinmeyen oturum 'in' ile False", "yok" not in registry)
    registry.flush()
    check("bilinmeyen oturum depoya yazılmadı", store.load("yok") is None)
    check("bilinmeyen oturumda get() None döner", registry.get("yok") is None)


def test_no_flush_no_write():
    """flush() çağrılmadan depoya yazılmamalı (unit of work sınırı)."""
    store = InMemorySessionStore()
    registry = SessionRegistry(store)
    registry.begin_request()
    registry["b"] = new_session()

    check("flush öncesi depo boş", store.load("b") is None)
    registry.flush()
    check("flush sonrası depo dolu", store.load("b") is not None)


def test_ttl_applied():
    """Her yazmada TTL tazelenmeli (kayan süre)."""
    fake = FakeRedis()
    store = RedisSessionStore(fake, ttl=1800)
    store.save("c", new_session())

    check("Redis kaydına TTL uygulandı", fake.ttls["wa:session:c"] == 1800)
    check("Redis anahtarı ön ekli", "wa:session:c" in fake.data)


def test_expiry():
    """Bellek içi backend'de süresi dolan oturum temizlenmeli."""
    store = InMemorySessionStore(ttl=1)
    session = new_session()
    session["last_activity"] = time.time() - 10
    store.save("d", session)

    check("temizlik süresi dolanı buldu", store.cleanup() == 1)
    check("süresi dolan oturum silindi", store.load("d") is None)


def test_redis_outage_is_survivable():
    """Redis düşerse istisna sızmamalı; bot bağlamsız da olsa yanıt vermeli."""
    store = RedisSessionStore(BrokenRedis())

    try:
        loaded = store.load("e")
        store.save("e", new_session())
        check("Redis kesintisinde istisna sızmadı", loaded is None)
    except Exception as exc:
        check(f"Redis kesintisinde istisna sızmadı ({exc})", False)


def test_corrupt_record_recovers():
    """Bozuk JSON oturumu kilitlememeli; silinip sıfırdan başlanmalı."""
    fake = FakeRedis()
    fake.data["wa:session:f"] = "{bozuk"
    store = RedisSessionStore(fake)

    check("bozuk kayıt None döndü", store.load("f") is None)
    check("bozuk kayıt silindi", "wa:session:f" not in fake.data)


def test_session_is_json_serializable():
    """Şemadaki her alan JSON'a yazılabilmeli."""
    try:
        json.dumps(new_session())
        check("varsayılan oturum şeması JSON uyumlu", True)
    except (TypeError, ValueError) as exc:
        check(f"varsayılan oturum şeması JSON uyumlu ({exc})", False)


def main():
    print("--- Oturum deposu doğrulaması ---\n")

    test_session_is_json_serializable()
    test_identity_map()
    test_contains_does_not_create()
    test_no_flush_no_write()
    test_ttl_applied()
    test_expiry()
    test_redis_outage_is_survivable()
    test_corrupt_record_recovers()

    test_round_trip(InMemorySessionStore(), "bellek")
    test_round_trip(RedisSessionStore(FakeRedis()), "redis-sahte")

    if "--live" in sys.argv:
        store = build_session_store()
        test_round_trip(store, f"canlı:{type(store).__name__}")

    failed = [name for name, ok in results if not ok]

    print(f"\n{len(results) - len(failed)}/{len(results)} kontrol geçti.")

    if failed:
        print("BAŞARISIZ:")
        for name in failed:
            print(f"  - {name}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
