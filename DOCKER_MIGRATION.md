# WhatsAgent — Docker'a Geçiş Runbook'u

Sunucu: Ubuntu 24.04 · Proje: `/opt/whatsagent-ai` · MySQL 8.0.46 (193M) · nginx ön yüzde

## Tespit edilen durum

| Bileşen | Durum |
|---|---|
| Uygulama | `whatsagent.service` (systemd), venv + uvicorn, `0.0.0.0:8000` |
| Veritabanı | Native MySQL 8.0.46, `127.0.0.1:3306`, 193M |
| Ön yüz | nginx: `api.mumifashion.com`, 443 TLS (Certbot) → `proxy_pass http://127.0.0.1:8000` |
| Docker | **KURULU DEĞİL** — adım 0 gerekli |
| Disk | 22G boş (fazlasıyla yeterli) |

## Neden bu plan güvenli

`docker-compose.yml`'da MySQL servisinin `ports:` tanımı yok — konteyner MySQL'i yalnız
compose ağında görünür, host'ta 3306'yı işgal etmez. Bu yüzden **native MySQL çalışmaya
devam edebilir** ve dokunulmamış bir geri dönüş ağı olarak durur.

Çakışan tek şey 8000 portu. Yani kesinti yalnız uygulama tarafında.

MySQL sürümü (8.0.46) compose'daki imajla (`mysql:8.0`) aynı major sürüm — charset ve
authentication plugin uyumsuzluğu riski yok.

---

## Adım 0 — Docker kurulumu (kesinti YOK)

Uygulama çalışmaya devam ederken yapılır.

```bash
# Eski/çakışan paketleri temizle
for p in docker.io docker-doc docker-compose podman-docker containerd runc; do
  apt-get remove -y $p 2>/dev/null
done

# Resmi Docker deposu
apt-get update
apt-get install -y ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Doğrula
docker --version
docker compose version
docker run --rm hello-world
```

---

## Adım 1 — Yedek (kesinti YOK)

```bash
cd /opt/whatsagent-ai
STAMP=$(date +%F-%H%M)
mkdir -p /root/whatsagent-backup-$STAMP

# .env'den DB bilgilerini oku.
# NOT: `source .env` KULLANMA — STORE_IBAN_NAME gibi boşluklu değerler
# shell tarafından komut olarak yorumlanır ve script kırılır.
envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2-; }
MYSQL_USER=$(envget MYSQL_USER)
MYSQL_PASSWORD=$(envget MYSQL_PASSWORD)
MYSQL_DATABASE=$(envget MYSQL_DATABASE)

# Veritabanı dump'ı (routines + triggers + events dahil)
mysqldump -h 127.0.0.1 -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" \
  --single-transaction --routines --triggers --events \
  --no-tablespaces \
  --default-character-set=utf8mb4 \
  "$MYSQL_DATABASE" > /root/whatsagent-backup-$STAMP/db.sql

# --no-tablespaces: uygulama kullanıcısında PROCESS yetkisi olmadığı için
# mysqldump tablespace metadata'sını yazamaz ve hata basar. Veriye etkisi
# yoktur, bayrak yalnızca gürültüyü keser.

# Yapılandırma ve kod
cp .env /root/whatsagent-backup-$STAMP/env.backup
cp /etc/systemd/system/whatsagent.service /root/whatsagent-backup-$STAMP/
tar czf /root/whatsagent-backup-$STAMP/app.tar.gz --exclude=venv --exclude=.git .

# Dump'ın gerçekten dolu olduğunu DOĞRULA (boş dump en sinsi hatadır)
ls -lh /root/whatsagent-backup-$STAMP/db.sql
tail -1 /root/whatsagent-backup-$STAMP/db.sql   # "Dump completed" yazmalı

# Referans satır sayıları — restore sonrası karşılaştıracağız
mysql -h 127.0.0.1 -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "
SELECT 'conversations', COUNT(*) FROM conversations
UNION ALL SELECT 'customers', COUNT(*) FROM customers
UNION ALL SELECT 'orders', COUNT(*) FROM orders
UNION ALL SELECT 'usage_logs', COUNT(*) FROM usage_logs;" \
  | tee /root/whatsagent-backup-$STAMP/rowcounts-before.txt
```

`db.sql` birkaç yüz KB'den küçükse veya `tail` "Dump completed" göstermiyorsa **DURDUR.**

---

## Adım 2 — Kodu ve imajı hazırla (kesinti YOK)

Kesintiyi kısaltmak için imaj derlemesi ve indirmeler uygulama hâlâ ayaktayken yapılır.

```bash
cd /opt/whatsagent-ai

# Yeni kodu al (session_store.py, güncel compose, requirements)
git pull        # veya dosyaları elle kopyala

# .env'e Redis satırı ekle (konteyner içinde compose bunu zaten ezer,
# ama konteyner dışı çalıştırmalar için tutarlı olsun)
grep -q "^REDIS_URL=" .env || echo "REDIS_URL=redis://redis:6379/0" >> .env

# İmajları önceden derle ve indir — bu adım dakikalar sürebilir, kesinti yaratmaz
docker compose build
docker compose pull
```

> **TEYİT EDİLDİ:** `MYSQL_USER=whatsagent` (root değil) → `mysql:8.0` imajı sorunsuz
> açılır, compose'da değişiklik gerekmiyor. `MYSQL_DATABASE=whatsagent`.
> Compose `MYSQL_ROOT_PASSWORD`'ü de `${MYSQL_PASSWORD}` değerine set ettiği için
> Adım 3'teki `-u root -p"$MYSQL_PASSWORD"` restore komutu çalışır.

---

## Adım 3 — Geçiş (KESİNTİ BAŞLIYOR ~2-4 dk)

Düşük trafikli bir saat seç. Bu süredeki WhatsApp mesajları **kaybolur**, Meta yeniden denemez.

```bash
cd /opt/whatsagent-ai
STAMP=<adım-1'deki-değer>

# 1) Eski uygulamayı durdur ve OTOMATİK BAŞLAMAYI KAPAT
#    disable atlanırsa sunucu yeniden başladığında 8000 için çakışır
systemctl stop whatsagent
systemctl disable whatsagent

# 2) Native MySQL'e DOKUNMA — geri dönüş ağımız, çakışma da yaratmıyor

# 3) Konteynerleri başlat
docker compose up -d

# 4) MySQL konteynerinin hazır olmasını bekle
#
# DİKKAT — `mysqladmin ping` TEK BAŞINA YETMEZ.
# mysql imajı ilk açılışta önce geçici bir sunucu başlatır, init SQL'lerini
# onun üzerinde çalıştırır ve root parolasını EN SON uygular. `ping` bu geçici
# sunucuya da "mysqld is alive" der; healthcheck bile "Healthy" gösterir.
# Bu anda restore denenirse ERROR 1045 (Access denied) alınır.
#
# Doğru kontrol: init'in bittiğini logdan teyit et VE auth'u fiilen dene.
echo "MySQL init bekleniyor..."
for i in $(seq 1 60); do
  docker compose logs mysql 2>&1 | grep -q "init process done" \
    && docker compose exec -T -e MYSQL_PWD="$MYSQL_PASSWORD" mysql \
         mysql -u root -e "SELECT 1;" >/dev/null 2>&1 \
    && { echo "✅ MySQL hazır ve auth çalışıyor"; break; }
  echo "  bekleniyor... ($i/60)"; sleep 3
done

# 5) Dump'ı restore et
set -a; source .env; set +a
docker compose exec -T mysql mysql -u root -p"$MYSQL_PASSWORD" \
  --default-character-set=utf8mb4 "$MYSQL_DATABASE" \
  < /root/whatsagent-backup-$STAMP/db.sql

# 6) Uygulamayı yeniden başlat (boş DB'ye bağlanmış olabilir)
docker compose restart app
```

---

## Adım 4 — Doğrulama (bu adımı ATLAMA)

```bash
cd /opt/whatsagent-ai

# A) Satır sayıları adım 1'deki referansla EŞLEŞMELİ
set -a; source .env; set +a
docker compose exec -T mysql mysql -u root -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "
SELECT 'conversations', COUNT(*) FROM conversations
UNION ALL SELECT 'customers', COUNT(*) FROM customers
UNION ALL SELECT 'orders', COUNT(*) FROM orders
UNION ALL SELECT 'usage_logs', COUNT(*) FROM usage_logs;"

diff <(...) /root/whatsagent-backup-$STAMP/rowcounts-before.txt   # gözle karşılaştır

# B) Redis GERÇEKTEN devrede mi — en kolay gözden kaçan kontrol
docker compose logs app | grep -E "Oturum deposu|bellekte tutulacak"
#   ✅ "Oturum deposu: Redis"        → doğru
#   ⚠️ "...bellekte tutulacak"       → Redis devrede DEĞİL, aşağıya bak

# C) Konteynerler ayakta mı
docker compose ps

# D) Uygulama yanıt veriyor mu
curl -sI http://127.0.0.1:8000/ | head -1

# E) nginx zinciri sağlam mı — dışarıdan HTTPS ile
curl -sI https://api.mumifashion.com/ | head -1

# E2) Port artık dışarı KAPALI olmalı (güvenlik iyileştirmesi doğrulaması)
curl -sI --max-time 5 http://<SUNUCU_PUBLIC_IP>:8000/ && echo "⚠️ HÂLÂ AÇIK" || echo "✅ dışarı kapalı"

# F) Türkçe karakter kontrolü — charset sorunu buradan anlaşılır
docker compose exec -T mysql mysql -u root -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" \
  -e "SELECT message FROM conversations ORDER BY id DESC LIMIT 5;"
#   'ğüşıöç' düzgün görünmeli, '?' veya 'Ã¼' görünmemeli

# G) EN ÖNEMLİSİ: kendi telefonundan gerçek bir WhatsApp mesajı at
#    Bot yanıt veriyorsa geçiş başarılı
docker compose logs -f app
```

### Redis devrede değilse

`import redis` başarısız olursa uygulama **çökmez**, sessizce bellek içi yedeğe düşer.
Bu kasıtlı (Redis kesintisinde bot susmasın diye) ama ilk kurulumda gözden kaçar.

```bash
docker compose exec app python -c "import redis; print(redis.__version__)"
# ModuleNotFoundError alırsan imaj eski demektir:
docker compose build --no-cache app && docker compose up -d
```

---

## Geri dönüş (herhangi bir adımda, ~30 sn)

Native MySQL'e dokunmadığımız için bu her zaman çalışır:

```bash
cd /opt/whatsagent-ai
docker compose down
systemctl enable whatsagent
systemctl start whatsagent
systemctl status whatsagent
```

Kod değişikliği de geri alınacaksa:

```bash
cd /opt/whatsagent-ai
git checkout <önceki-commit>
cp /root/whatsagent-backup-$STAMP/env.backup .env
systemctl restart whatsagent
```

---

## Adım 5 — Temizlik (en az 1 hafta SONRA)

Sistem sorunsuz çalıştığından emin olmadan bunları yapma.

```bash
# Native MySQL'i durdur (veriyi SİLME, sadece durdur)
systemctl stop mysql
systemctl disable mysql

# Bir hafta daha bekle, sorun çıkmazsa /var/lib/mysql kaldırılabilir
# Yedekler /root/whatsagent-backup-* altında kalsın
```

---

## Geçiş sonrası açık kalan konular

| Konu | Durum |
|---|---|
| Port bağlama | `127.0.0.1:8000:8000` olarak değiştirildi — panel artık yalnız nginx (TLS) üzerinden erişilebilir. Öncesinde `0.0.0.0:8000` ile Basic Auth parolası düz metin olarak internete açıktı. |
| Çoklu replika | Sabit host portu `--scale` ile çoklu replikayı bloklar. Ölçekleme istendiğinde nginx `upstream` bloğu + port aralığı gerekir. |
| Tek uvicorn worker | Uygulama artık stateless, `--workers 4` güvenli. Dockerfile'da gunicorn'a geçilebilir. |
| Redis `maxmemory-policy` | Tanımsız (varsayılan `noeviction`). Tüm anahtarlar TTL'li olduğu için `volatile-lru` uygun. |
| Redis parolası | Yok. Port dışarı açılmadığı, yalnız compose ağında olduğu için iç ağda kabul edilebilir. |
| Otomatik yedek | Native MySQL'de cron yedeği varsa konteyner MySQL'e uyarlanmalı. **Kontrol et:** `crontab -l` |
| nginx `proxy_pass` | `sites-enabled/` ve `conf.d/` içinde bulunamadı; config başka bir yerde. Geçişi etkilemez: compose `8000:8000` ile aynı port sözleşmesini koruduğu için giriş yolu değişmez. `nginx -T` ile yeri tespit edilmeli. |
