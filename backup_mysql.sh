#!/usr/bin/env bash
#
# WhatsAgent — günlük MySQL yedeği (Docker konteynerinden)
#
# Kurulum:
#   chmod +x /opt/whatsagent-ai/backup_mysql.sh
#   crontab -e   →   30 4 * * * /opt/whatsagent-ai/backup_mysql.sh >> /var/log/whatsagent-backup.log 2>&1
#
# Elle çalıştırmak için:  /opt/whatsagent-ai/backup_mysql.sh
#
# Tasarım notları:
# * `source .env` KULLANILMAZ — boşluk içeren değerler (STORE_IBAN_NAME gibi)
#   shell tarafından komut olarak yorumlanır ve script kırılır.
# * Parola MYSQL_PWD ile verilir, komut satırında görünmez (ps ile okunamaz).
# * Boş/bozuk dump sessizce kabul edilmez; doğrulanamayan yedek SİLİNİR ve
#   script hata koduyla çıkar. Sessizce başarısız olan yedek, hiç yedek
#   olmamasından daha tehlikelidir.

set -euo pipefail

APP_DIR="/opt/whatsagent-ai"
BACKUP_DIR="/root/whatsagent-backups"
RETENTION_DAYS=14

cd "$APP_DIR"

envget() { grep -E "^$1=" .env | head -1 | cut -d= -f2-; }

DB_NAME="$(envget MYSQL_DATABASE)"
DB_PASS="$(envget MYSQL_PASSWORD)"

if [ -z "$DB_NAME" ] || [ -z "$DB_PASS" ]; then
  echo "[$(date '+%F %T')] HATA: .env okunamadı (MYSQL_DATABASE/MYSQL_PASSWORD boş)"
  exit 1
fi

mkdir -p "$BACKUP_DIR"
OUT="$BACKUP_DIR/whatsagent-$(date +%F-%H%M).sql.gz"

echo "[$(date '+%F %T')] Yedek başlıyor → $OUT"

docker compose exec -T -e MYSQL_PWD="$DB_PASS" mysql \
  mysqldump -u root \
    --single-transaction --routines --triggers --events \
    --no-tablespaces --default-character-set=utf8mb4 \
    "$DB_NAME" | gzip > "$OUT"

# --- Doğrulama: dump gerçekten kullanılabilir mi ---
if [ ! -s "$OUT" ]; then
  echo "[$(date '+%F %T')] HATA: dump boş, siliniyor"
  rm -f "$OUT"
  exit 1
fi

if ! gzip -t "$OUT" 2>/dev/null; then
  echo "[$(date '+%F %T')] HATA: gzip bozuk, siliniyor"
  rm -f "$OUT"
  exit 1
fi

if ! zcat "$OUT" | tail -5 | grep -q "Dump completed"; then
  echo "[$(date '+%F %T')] HATA: dump yarım kalmış ('Dump completed' yok), siliniyor"
  rm -f "$OUT"
  exit 1
fi

TABLES=$(zcat "$OUT" | grep -c "^CREATE TABLE" || true)
if [ "$TABLES" -lt 4 ]; then
  echo "[$(date '+%F %T')] HATA: yalnız $TABLES tablo bulundu (en az 4 bekleniyor), siliniyor"
  rm -f "$OUT"
  exit 1
fi

echo "[$(date '+%F %T')] ✅ Yedek tamam: $(du -h "$OUT" | cut -f1), $TABLES tablo"

# --- Eski yedekleri temizle ---
DELETED=$(find "$BACKUP_DIR" -name "whatsagent-*.sql.gz" -mtime +$RETENTION_DAYS -print -delete | wc -l)
[ "$DELETED" -gt 0 ] && echo "[$(date '+%F %T')] $DELETED eski yedek silindi (>$RETENTION_DAYS gün)"

echo "[$(date '+%F %T')] Mevcut yedek sayısı: $(find "$BACKUP_DIR" -name 'whatsagent-*.sql.gz' | wc -l)"
