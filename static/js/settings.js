/* =====================================================
   WhatsAgent · Settings sayfası
   settings tablosu (DB-öncelikli, .env fallback) düzenleme
===================================================== */

const Settings = {

    // Hangi alan hangi grupta gösterilecek
    GROUPS: {
        setGroupBank:    ["STORE_IBAN", "STORE_IBAN_NAME"],
        setGroupMetrics: ["EMPLOYEE_HOURLY_COST", "AVERAGE_CHAT_TIME_MINUTES"]
    },

    fields: [],

    esc(s){
        return String(s == null ? "" : s)
            .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
    },

    async load(){
        try{
            const res = await fetch("/admin/settings");
            if (!res.ok) throw new Error("HTTP " + res.status);
            const data = await res.json();
            this.fields = data.fields || [];
            this.render();
        }catch(e){
            console.error("settings", e);
            this.msg("Ayarlar yüklenemedi 🙏", true);
        }
    },

    fieldHtml(f){
        const badge = f.overridden
            ? `<span class="badge">panelden</span>`
            : "";
        const val = f.value == null ? "" : f.value;
        const step = f.type === "number" ? ` step="any" min="0"` : "";
        const def = (f.default == null || f.default === "") ? "—" : f.default;
        return `
            <div class="set-field">
                <label for="fld_${f.key}">${this.esc(f.label)}${badge}</label>
                <input id="fld_${f.key}" data-key="${this.esc(f.key)}"
                       type="${f.type === "number" ? "number" : "text"}"${step}
                       value="${this.esc(val)}">
                <div class="sub">Varsayılan (.env): ${this.esc(def)}</div>
            </div>`;
    },

    render(){
        const byKey = {};
        this.fields.forEach(f => byKey[f.key] = f);

        Object.entries(this.GROUPS).forEach(([containerId, keys]) => {
            const el = document.getElementById(containerId);
            if (!el) return;
            el.innerHTML = keys
                .filter(k => byKey[k])
                .map(k => this.fieldHtml(byKey[k]))
                .join("");
        });
    },

    collect(){
        const out = {};
        document.querySelectorAll("input[data-key]").forEach(inp => {
            out[inp.getAttribute("data-key")] = inp.value;
        });
        return out;
    },

    msg(text, isErr){
        const el = document.getElementById("setMsg");
        el.textContent = text;
        el.className = "set-msg " + (isErr ? "err" : "ok");
    },

    async save(){
        const btn = document.getElementById("setSave");
        btn.disabled = true;
        this.msg("Kaydediliyor…", false);
        try{
            const res = await fetch("/admin/settings", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(this.collect())
            });
            const data = await res.json().catch(() => ({}));
            if (!res.ok || !data.ok){
                this.msg(data.error || ("Hata: HTTP " + res.status), true);
            }else{
                this.fields = (data.settings && data.settings.fields) || this.fields;
                this.render();
                this.msg("Kaydedildi ve uygulandı ✓", false);
            }
        }catch(e){
            console.error("settings save", e);
            this.msg("Kaydedilemedi 🙏", true);
        }finally{
            btn.disabled = false;
        }
    },

    init(){
        document.getElementById("setSave").addEventListener("click", () => this.save());
        this.load();
    }
};

document.addEventListener("DOMContentLoaded", () => Settings.init());
