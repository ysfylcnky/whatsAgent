/* =====================================================
   WhatsAgent · Reports sayfası
   Tarih aralıklı özet (AI + sipariş + mesaj) + CSV export
===================================================== */

const Reports = {

    esc(s){
        return String(s == null ? "" : s)
            .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    },

    fmtInt(n){ return (n || 0).toLocaleString("tr-TR"); },
    fmtCost(n){ return "$" + (n || 0).toFixed(4); },

    ymd(d){
        const p = x => String(x).padStart(2, "0");
        return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}`;
    },

    range(){
        return {
            start: document.getElementById("repStart").value,
            end:   document.getElementById("repEnd").value
        };
    },

    initDates(){
        const end = new Date();
        const start = new Date();
        start.setDate(start.getDate() - 29);
        document.getElementById("repStart").value = this.ymd(start);
        document.getElementById("repEnd").value   = this.ymd(end);
    },

    async load(){
        const { start, end } = this.range();
        const qs = `?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`;
        try{
            const res = await fetch("/admin/reports" + qs);
            if (!res.ok) throw new Error("HTTP " + res.status);
            this.render(await res.json());
        }catch(e){
            console.error("reports", e);
            document.getElementById("repRangeNote").textContent = "Veri yüklenemedi 🙏";
        }
    },

    row(k, v){
        return `<div class="rep-row"><span class="k">${this.esc(k)}</span><span class="v">${v}</span></div>`;
    },

    render(d){
        const ai = d.ai || {}, o = d.orders || {}, m = d.messages || {};

        document.getElementById("repRangeNote").textContent =
            `Aralık: ${this.esc(d.start)} — ${this.esc(d.end)}` +
            (d.usd_try_rate ? `  ·  1 USD ≈ ${d.usd_try_rate.toLocaleString("tr-TR")} TL` : "");

        // Tile'lar
        document.getElementById("tReq").textContent = this.fmtInt(ai.requests);
        document.getElementById("tTokens").textContent = `${this.fmtInt(ai.total_tokens)} token`;
        document.getElementById("tCost").textContent = this.fmtCost(ai.cost_usd);
        document.getElementById("tCostTry").textContent =
            ai.cost_try != null ? `≈ ${ai.cost_try.toLocaleString("tr-TR")} TL` : "";
        document.getElementById("tOrders").textContent = this.fmtInt(o.count);
        document.getElementById("tOrdersSub").textContent =
            o.update_count ? `+${this.fmtInt(o.update_count)} güncelleme` : "güncelleme yok";
        document.getElementById("tQty").textContent = this.fmtInt(o.total_quantity);
        document.getElementById("tMsg").textContent = this.fmtInt((m.incoming || 0) + (m.outgoing || 0));
        document.getElementById("tMsgSub").textContent =
            `${this.fmtInt(m.incoming)} gelen · ${this.fmtInt(m.outgoing)} giden`;

        // AI kartı
        document.getElementById("repAi").innerHTML =
            this.row("İstek", this.fmtInt(ai.requests)) +
            this.row("Prompt token", this.fmtInt(ai.prompt_tokens)) +
            this.row("Completion token", this.fmtInt(ai.completion_tokens)) +
            this.row("Toplam token", this.fmtInt(ai.total_tokens)) +
            this.row("Maliyet (USD)", this.fmtCost(ai.cost_usd)) +
            this.row("Maliyet (TL)", ai.cost_try != null ? `${ai.cost_try.toLocaleString("tr-TR")} TL` : "—") +
            this.row("Ort. yanıt süresi", `${(ai.avg_response_time || 0).toFixed(2)} sn`);

        // Sipariş kartı
        document.getElementById("repOrders").innerHTML =
            this.row("Sipariş sayısı", this.fmtInt(o.count)) +
            this.row("Güncelleme", this.fmtInt(o.update_count)) +
            this.row("Toplam adet", this.fmtInt(o.total_quantity));

        const pay = o.by_payment || [];
        document.getElementById("repPay").innerHTML = pay.length
            ? pay.map(p => this.row(p.odeme_sekli, this.fmtInt(p.count))).join("")
            : `<div class="rep-empty">Bu aralıkta sipariş yok.</div>`;

        // Mesaj kartı
        document.getElementById("repMsg").innerHTML =
            this.row("Gelen mesaj", this.fmtInt(m.incoming)) +
            this.row("Giden mesaj", this.fmtInt(m.outgoing)) +
            this.row("Tekil müşteri", this.fmtInt(m.unique_customers));
    },

    exportCsv(kind){
        const { start, end } = this.range();
        const qs = `?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`;
        window.location.href = `/admin/reports/export/${kind}${qs}`;
    },

    init(){
        this.initDates();
        document.getElementById("repApply").addEventListener("click", () => this.load());
        document.getElementById("repExportOrders").addEventListener("click", () => this.exportCsv("orders"));
        document.getElementById("repExportUsage").addEventListener("click", () => this.exportCsv("usage"));
        this.load();
    }
};

document.addEventListener("DOMContentLoaded", () => Reports.init());
