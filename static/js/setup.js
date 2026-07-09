/* =====================================================
   WhatsAgent · Kurulum (Setup) sihirbazı
   /admin/settings/setup uçlarını tüketir. Alan şeması backend'den,
   etiket/yardım metinleri burada (backend yalın kalsın).
===================================================== */

const SECTION_META = {
    company:  { title: "Firma Bilgileri", icon: "fa-store",   desc: "Mağaza kimliği ve ödeme bilgileri." },
    whatsapp: { title: "WhatsApp",        icon: "fa-whatsapp",desc: "WhatsApp Cloud API bağlantısı.", brand: true },
    ai:       { title: "Yapay Zeka",      icon: "fa-robot",   desc: "LLM sağlayıcı erişimi (OpenAI)." },
    ikas:     { title: "ikas",            icon: "fa-plug",    desc: "ikas hesap kimlik doğrulaması." },
    product:  { title: "Ürün API",        icon: "fa-box",     desc: "Ürün arama davranışı ve canlı test." },
    notify:   { title: "Bildirimler",     icon: "fa-bell",    desc: "Sipariş bildiriminin gideceği numara." },
    advanced: { title: "Gelişmiş Ayarlar",icon: "fa-sliders", desc: "Altyapı ve teknik değerler." }
};

const FIELD_META = {
    STORE_NAME:               { label: "Firma / Mağaza Adı", help: "Panelde ve müşteriye görünen ticari adınız.", ph: "Örn. Moda Butik" },
    STORE_IBAN:               { label: "IBAN", help: "Havale/EFT talimatında müşteriye iletilir. Boşsa IBAN mesajı gönderilmez.", ph: "TR.. (24 hane)" },
    STORE_IBAN_NAME:          { label: "IBAN Ad Soyad", help: "Hesap sahibinin adı soyadı." },
    WHATSAPP_PHONE_NUMBER_ID: { label: "Phone Number ID", help: "Meta → WhatsApp → API Setup ekranındaki Phone number ID.", ph: "123456789012345" },
    WHATSAPP_ACCESS_TOKEN:    { label: "Access Token", help: "Kalıcı (System User) token önerilir; geçici token 24 saatte dolar." },
    VERIFY_TOKEN:             { label: "Verify Token", help: "Webhook doğrulaması için serbest belirlediğiniz gizli dize. Meta webhook ayarına birebir aynısı girilir." },
    OPENAI_API_KEY:           { label: "OpenAI API Key", help: "OpenAI panelinden alınır. Sadece kaydedilir, tekrar gösterilmez." },
    MODEL_NAME:               { label: "Model", help: "Boş bırakılırsa gpt-4.1-mini kullanılır. Değişikliği ileri düzey.", ph: "gpt-4.1-mini" },
    IKAS_STORE_NAME:          { label: "Store Name", help: "{ad}.myikas.com adresindeki {ad} kısmı (küçük harf).", ph: "magazam" },
    IKAS_CLIENT_ID:           { label: "Client ID", help: "ikas → Ayarlar → API bilgilerinden." },
    IKAS_CLIENT_SECRET:       { label: "Client Secret", help: "ikas API gizli anahtarı." },
    MAX_PRODUCTS:             { label: "Maksimum Ürün", help: "Bir yanıtta gösterilecek en fazla ürün adayı (1–10)." },
    CACHE_TTL:                { label: "Önbellek Süresi (sn)", help: "ikas ürün verisinin önbellekte kalma süresi (60–3600)." },
    STORE_NOTIFY_PHONE:       { label: "Bildirim Numarası", help: "Yeni sipariş/güncelleme bildirimleri bu numaraya gider.", ph: "905321112233" },
    DASHBOARD_USER:           { label: "Panel Kullanıcısı", help: "Panel giriş kullanıcı adı." },
    DASHBOARD_PASSWORD:       { label: "Panel Parolası", help: "En az 8 karakter." },
    MYSQL_HOST:               { label: "MySQL Host", help: "Uygulama zaten bu DB ile çalışıyor; buradan düzenlenemez." },
    MYSQL_PORT:               { label: "Port", help: "" },
    MYSQL_USER:               { label: "Kullanıcı", help: "" },
    MYSQL_PASSWORD:           { label: "Parola", help: "" },
    MYSQL_DATABASE:           { label: "Veritabanı", help: "" }
};

const STATUS_TEXT = { ok: "Tamamlandı", missing: "Eksik", untested: "Test edilmedi" };

const Setup = {

    state: null,
    openId: null,
    tested: {},   // bölüm bazlı canlı test sonucu (ok/fail) — DB'den bağımsız yeşil/kırmızı

    esc(s){
        return String(s == null ? "" : s)
            .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
    },

    async load(){
        try{
            const res = await fetch("/admin/settings/setup");
            if (!res.ok) throw new Error("HTTP " + res.status);
            this.state = await res.json();
            if (this.openId === null){
                // İlk açılışta ilk eksik/test edilmemiş zorunlu bölümü aç
                const first = (this.state.sections || []).find(s => s.required && s.status !== "ok");
                this.openId = first ? first.id : (this.state.sections[0] && this.state.sections[0].id);
            }
            this.render();
        }catch(e){
            console.error("setup load", e);
            document.getElementById("accordion").innerHTML =
                '<div class="acc"><div class="acc-body" style="display:block">Durum yüklenemedi 🙏</div></div>';
        }
    },

    fieldHtml(f){
        const meta = FIELD_META[f.key] || { label: f.key, help: "" };
        const readonly = f.target === "readonly";
        const saved = f.secret && f.set ? '<span class="saved">✓ kayıtlı</span>' : "";
        const type = f.secret ? "password" : (f.type === "number" ? "number" : "text");
        const val = (f.secret || f.value == null) ? "" : f.value;
        const ph = f.secret && f.set ? "•••••••• (kayıtlı — değiştirmek için yaz)" : (meta.ph || "");
        const numAttr = f.type === "number"
            ? ` step="1"${f.min != null ? ' min="' + f.min + '"' : ''}${f.max != null ? ' max="' + f.max + '"' : ''}`
            : "";
        let hint = meta.help || "";
        if (f.target === "env" && !readonly) hint += (hint ? " · " : "") + "Kayıt sonrası yeniden başlatma gerekir.";
        return `
            <div class="field">
                <label>${this.esc(meta.label)}${f.required ? ' <span style="color:var(--amber)">*</span>' : ''}${saved}</label>
                <input data-key="${this.esc(f.key)}" data-section-field type="${type}"${numAttr}
                       ${readonly ? "disabled" : ""} value="${this.esc(val)}" placeholder="${this.esc(ph)}">
                ${hint ? `<div class="hint">${this.esc(hint)}</div>` : ""}
            </div>`;
    },

    sectionHtml(sec){
        const meta = SECTION_META[sec.id] || { title: sec.id, icon: "fa-gear", desc: "" };
        const iconCls = (meta.brand ? "fa-brands " : "fa-solid ") + meta.icon;
        const pill = `<span class="pill ${sec.status}" id="pill_${sec.id}">${STATUS_TEXT[sec.status] || sec.status}</span>`;
        const fields = sec.fields.map(f => this.fieldHtml(f)).join("");

        // Ürün API bölümünde canlı arama testi için sorgu kutusu (kaydedilmez)
        const testQuery = sec.id === "product"
            ? `<div class="field"><label>Test araması</label>
                 <input id="productQuery" type="text" placeholder="örn. etek">
                 <div class="hint">Sadece bağlantıyı denemek için — kaydedilmez.</div></div>`
            : "";

        const testBtn = sec.test
            ? `<button class="btn btn-ghost" data-test="${sec.id}"><i class="fa-solid fa-plug-circle-check"></i> Test Et</button>`
            : "";
        const hasEditable = sec.fields.some(f => f.target !== "readonly");
        const saveBtn = hasEditable
            ? `<button class="btn btn-primary" data-save="${sec.id}"><i class="fa-solid fa-floppy-disk"></i> Kaydet</button>`
            : "";

        return `
            <div class="acc ${this.openId === sec.id ? "open" : ""}" data-acc="${sec.id}">
                <div class="acc-head" data-head="${sec.id}">
                    <div class="ico"><i class="${iconCls}"></i></div>
                    <div class="htxt">
                        <h3>${this.esc(meta.title)}${sec.required ? ' <span class="req">ZORUNLU</span>' : ''}</h3>
                        <div class="desc">${this.esc(meta.desc)}</div>
                    </div>
                    ${pill}
                    <i class="fa-solid fa-chevron-down chev"></i>
                </div>
                <div class="acc-body">
                    ${fields}${testQuery}
                    <div class="acc-actions">
                        ${saveBtn}${testBtn}
                        <span class="acc-msg" id="msg_${sec.id}"></span>
                    </div>
                </div>
            </div>`;
    },

    // İlk giriş karşılama bandı — yalnız kurulum tamamlanmadıysa gösterilir
    renderBanner(){
        const el = document.getElementById("firstRunBanner");
        if (!el) return;
        el.innerHTML = this.state.completed ? "" : `
            <div class="first-run">
                <div class="ico"><i class="fa-solid fa-hand-sparkles"></i></div>
                <div>
                    <h2>WhatsAgent'a hoş geldin 👋</h2>
                    <p>Panoyu kullanmaya başlamadan önce entegrasyonlarını bağlaman gerekiyor.
                       Aşağıdaki <strong>zorunlu</strong> bölümleri doldurup test et, ardından
                       <strong>Kurulumu Tamamla</strong>'ya bas — sonra panel otomatik açılır.</p>
                </div>
            </div>`;
    },

    render(){
        const secs = this.state.sections || [];
        document.getElementById("accordion").innerHTML = secs.map(s => this.sectionHtml(s)).join("");
        this.renderBanner();

        // Olay bağlama (event delegation yerine sade doğrudan bağlama)
        document.querySelectorAll("[data-head]").forEach(h =>
            h.addEventListener("click", () => this.toggle(h.getAttribute("data-head"))));
        document.querySelectorAll("[data-save]").forEach(b =>
            b.addEventListener("click", () => this.save(b.getAttribute("data-save"))));
        document.querySelectorAll("[data-test]").forEach(b =>
            b.addEventListener("click", () => this.test(b.getAttribute("data-test"))));

        this.applyTestFlags();
        this.updateProgress();
    },

    toggle(id){
        this.openId = (this.openId === id) ? null : id;
        document.querySelectorAll("[data-acc]").forEach(a =>
            a.classList.toggle("open", a.getAttribute("data-acc") === this.openId));
    },

    collect(id){
        const out = {};
        document.querySelectorAll(`[data-acc="${id}"] input[data-section-field]`).forEach(inp => {
            if (inp.disabled) return;               // readonly (MySQL) gönderilmez
            out[inp.getAttribute("data-key")] = inp.value;
        });
        return out;
    },

    msg(id, text, kind){
        const el = document.getElementById("msg_" + id);
        if (!el) return;
        el.textContent = text;
        el.className = "acc-msg " + (kind || "info");
    },

    updateProgress(){
        const secs = this.state.sections || [];
        const req = secs.filter(s => s.required);
        const ready = req.filter(s => s.status !== "missing").length;
        const pct = req.length ? Math.round(ready / req.length * 100) : 0;

        document.getElementById("progressBar").style.width = pct + "%";
        document.getElementById("progressCount").textContent = `${ready}/${req.length} zorunlu bölüm hazır`;

        const db = document.getElementById("dbStatus");
        db.textContent = this.state.db_ok ? "Veritabanı bağlı" : "Veritabanı erişilemiyor";
        db.className = "db " + (this.state.db_ok ? "ok" : "err");

        const allReady = ready === req.length && this.state.db_ok;
        const untested = req.some(s => s.test && s.status === "untested");
        const btn = document.getElementById("btnComplete");
        btn.disabled = !allReady;
        document.getElementById("finishHint").textContent = !allReady
            ? "Eksik zorunlu bölümler var — tamamlayıp kaydet."
            : (untested ? "Hazır. Bağlantıları test etmen önerilir, sonra tamamla."
                        : "Her şey hazır — kurulumu tamamlayabilirsin.");
    },

    setPill(id, cls, text){
        const p = document.getElementById("pill_" + id);
        if (p){ p.className = "pill " + cls; p.textContent = text; }
    },

    // Canlı test sonuçlarını rozetlere yansıt (başarı=yeşil, başarısız=kırmızı)
    applyTestFlags(){
        Object.keys(this.tested).forEach(id => {
            const ok = this.tested[id] === "ok";
            this.setPill(id, ok ? "ok" : "missing", ok ? "Bağlantı OK" : "Başarısız");
        });
    },

    // Test/kaydet sonrası input'ları bozmadan yalnız statü rozetlerini tazele
    async refreshStatuses(){
        try{
            const res = await fetch("/admin/settings/setup");
            if (!res.ok) return;
            this.state = await res.json();
            (this.state.sections || []).forEach(s =>
                this.setPill(s.id, s.status, STATUS_TEXT[s.status] || s.status));
            this.applyTestFlags();
            this.updateProgress();
        }catch(e){ /* sessiz */ }
    },

    async save(id){
        this.msg(id, "Kaydediliyor…", "info");
        try{
            const res = await fetch("/admin/settings/setup/save", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ section: id, fields: this.collect(id) })
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.ok){
                this.msg(id, data.error || ("Hata: HTTP " + res.status), "err");
                return;
            }
            const note = data.restart_required
                ? "Kaydedildi ✓ — geçerli olması için sunucuyu yeniden başlatın."
                : "Kaydedildi ve uygulandı ✓";
            // Değerler kalıcı olduğundan tam yenileme güvenli
            if (data.state){ this.state = data.state; this.render(); }
            else await this.load();
            this.msg(id, note, "ok");
        }catch(e){
            console.error("setup save", e);
            this.msg(id, "Kaydedilemedi 🙏", "err");
        }
    },

    async test(id){
        const btn = document.querySelector('[data-test="' + id + '"]');
        if (btn) btn.disabled = true;
        this.msg(id, "Test ediliyor…", "info");
        const values = this.collect(id);
        if (id === "product"){
            const q = document.getElementById("productQuery");
            if (q) values.query = q.value;
        }
        try{
            const res = await fetch("/admin/settings/setup/test", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ section: id, values })
            });
            const data = await res.json().catch(() => ({}));
            const ok = !!data.ok;
            // Sonucu hem rozete (yeşil/kırmızı) hem mesaja anında yansıt
            this.tested[id] = ok ? "ok" : "fail";
            this.setPill(id, ok ? "ok" : "missing", ok ? "Bağlantı OK" : "Başarısız");
            this.msg(id, (ok ? "✓ " : "✗ ") + (data.message || data.error || (ok ? "" : "Bağlantı doğrulanamadı.")), ok ? "ok" : "err");
            // Girilen (kaydedilmemiş) değerler kaybolmasın diye sadece rozetleri tazele
            await this.refreshStatuses();
        }catch(e){
            console.error("setup test", e);
            this.msg(id, "Test edilemedi 🙏", "err");
        }finally{
            if (btn) btn.disabled = false;
        }
    },

    async complete(){
        const btn = document.getElementById("btnComplete");
        btn.disabled = true;
        try{
            const res = await fetch("/admin/settings/setup/complete", { method: "POST" });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.ok){
                document.getElementById("finishHint").textContent = data.error || ("Hata: HTTP " + res.status);
                btn.disabled = false;
                return;
            }
            window.location.href = "/dashboard";
        }catch(e){
            console.error("setup complete", e);
            document.getElementById("finishHint").textContent = "Tamamlanamadı 🙏";
            btn.disabled = false;
        }
    },

    init(){
        document.getElementById("btnComplete").addEventListener("click", () => this.complete());
        this.load();
    }
};

document.addEventListener("DOMContentLoaded", () => Setup.init());
