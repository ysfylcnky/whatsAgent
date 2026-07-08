/* =====================================================
   WhatsAgent · Customers sayfası
   Sol: müşteri listesi (sayfalı) — Sağ: sipariş geçmişi (sayfalı)
===================================================== */

const Customers = {

    listPage: 1,
    listTotalPages: 1,
    detailPhone: null,
    detailName: null,
    detailPage: 1,
    detailTotalPages: 1,

    init(){
        this.cacheEls();
        this.bind();
        this.loadList(1);
    },

    cacheEls(){
        this.$list      = document.getElementById("custList");
        this.$listMeta  = document.getElementById("custListMeta");
        this.$listPager = document.getElementById("listPager");
        this.$listPrev  = document.getElementById("listPrev");
        this.$listNext  = document.getElementById("listNext");
        this.$listInfo  = document.getElementById("listPageInfo");

        this.$detail      = document.getElementById("custDetail");
        this.$detailTitle = document.getElementById("detailTitle");
        this.$detailMeta  = document.getElementById("detailMeta");
        this.$detailPager = document.getElementById("detailPager");
        this.$detailPrev  = document.getElementById("detailPrev");   // daha yeni
        this.$detailNext  = document.getElementById("detailNext");   // daha eski
        this.$detailInfo  = document.getElementById("detailPageInfo");
    },

    bind(){
        this.$listPrev.addEventListener("click", ()=> this.loadList(this.listPage - 1));
        this.$listNext.addEventListener("click", ()=> this.loadList(this.listPage + 1));
        // Sayfa 1 = en yeni siparişler; "daha eski" sayfa numarasını artırır
        this.$detailNext.addEventListener("click", ()=> this.loadDetail(this.detailPhone, this.detailName, this.detailPage + 1));
        this.$detailPrev.addEventListener("click", ()=> this.loadDetail(this.detailPhone, this.detailName, this.detailPage - 1));
    },

    esc(s){
        return String(s == null ? "" : s)
            .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
            .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
    },

    async loadList(page){
        if (page < 1) return;
        try{
            const res = await fetch(`/admin/customers?page=${page}`);
            if (!res.ok) throw new Error("HTTP " + res.status);
            this.renderList(await res.json());
        }catch(e){
            this.$list.innerHTML = `<div class="cust-empty">Liste yüklenemedi 🙏</div>`;
            console.error("loadList", e);
        }
    },

    renderList(data){
        this.listPage = data.page || 1;
        this.listTotalPages = data.total_pages || 1;
        this.$listMeta.textContent = `${data.total || 0} müşteri`;

        if (!data.items || data.items.length === 0){
            this.$list.innerHTML = `<div class="cust-empty">Henüz sipariş veren müşteri yok.</div>`;
            this.$listPager.style.display = "none";
            return;
        }

        this.$list.innerHTML = data.items.map(it=>{
            const name = it.ad_soyad ? this.esc(it.ad_soyad) : this.esc(it.phone);
            return `
                <div class="cust-row" data-phone="${this.esc(it.phone)}" data-name="${this.esc(it.ad_soyad || it.phone)}">
                    <div class="r-top">
                        <span class="r-name">${name}</span>
                        <span class="r-pill">${it.order_count} sipariş</span>
                    </div>
                    <div class="r-phone">${this.esc(it.phone)}</div>
                    <div class="r-meta">
                        <span><i class="fa-regular fa-clock"></i> Son sipariş: ${this.esc(it.last_order_time || "—")}</span>
                    </div>
                </div>`;
        }).join("");

        this.$list.querySelectorAll(".cust-row").forEach(row=>{
            row.addEventListener("click", ()=>{
                this.$list.querySelectorAll(".cust-row").forEach(r=> r.classList.remove("active"));
                row.classList.add("active");
                this.loadDetail(row.dataset.phone, row.dataset.name, 1);
            });
        });

        this.$listPager.style.display = this.listTotalPages > 1 ? "flex" : "none";
        this.$listInfo.textContent = `${this.listPage} / ${this.listTotalPages}`;
        this.$listPrev.disabled = this.listPage <= 1;
        this.$listNext.disabled = this.listPage >= this.listTotalPages;
    },

    async loadDetail(phone, name, page){
        if (!phone) return;
        if (page < 1) return;
        this.detailPhone = phone;
        this.detailName = name;
        try{
            const res = await fetch(`/admin/customers/detail?phone=${encodeURIComponent(phone)}&page=${page}`);
            if (!res.ok) throw new Error("HTTP " + res.status);
            this.renderDetail(await res.json());
        }catch(e){
            this.$detail.innerHTML = `<div class="cust-empty">Sipariş geçmişi yüklenemedi 🙏</div>`;
            console.error("loadDetail", e);
        }
    },

    renderDetail(data){
        this.detailPage = data.page || 1;
        this.detailTotalPages = data.total_pages || 1;

        this.$detailTitle.textContent = this.detailName || this.detailPhone;
        this.$detailMeta.textContent  = `${data.total || 0} kayıt`;

        const summary = `
            <div class="cust-summary">
                <div><span class="s-label">Telefon</span><span class="s-val">${this.esc(data.phone)}</span></div>
                <div><span class="s-label">İlk görülme</span><span class="s-val">${this.esc(data.first_seen || "—")}</span></div>
                <div><span class="s-label">Son görülme</span><span class="s-val">${this.esc(data.last_seen || "—")}</span></div>
            </div>`;

        if (!data.orders || data.orders.length === 0){
            this.$detail.innerHTML = summary + `<div class="cust-empty">Bu müşteride sipariş kaydı yok.</div>`;
            this.$detailPager.style.display = "none";
            return;
        }

        const cards = data.orders.map(o=>{
            const badge = o.is_update ? `<span class="badge-update">güncelleme</span>` : "";
            return `
                <div class="order-card">
                    <div class="o-head">
                        <span class="o-urun">${this.esc(o.urun)}${badge}</span>
                        <span class="o-time">${this.esc(o.timestamp || "")}</span>
                    </div>
                    <div class="o-grid">
                        <span>Renk: <b>${this.esc(o.renk || "—")}</b></span>
                        <span>Beden: <b>${this.esc(o.beden || "—")}</b></span>
                        <span>Adet: <b>${this.esc(o.adet)}</b></span>
                        <span>Ödeme: <b>${this.esc(o.odeme_sekli || "—")}</b></span>
                    </div>
                    <div class="o-addr"><i class="fa-solid fa-location-dot"></i> ${this.esc(o.teslimat_adresi || "—")}</div>
                </div>`;
        }).join("");

        this.$detail.innerHTML = summary + cards;
        this.$detail.scrollTop = 0;

        this.$detailPager.style.display = this.detailTotalPages > 1 ? "flex" : "none";
        this.$detailInfo.textContent = `${this.detailPage} / ${this.detailTotalPages}`;
        this.$detailNext.disabled = this.detailPage >= this.detailTotalPages;
        this.$detailPrev.disabled = this.detailPage <= 1;
    }
};

document.addEventListener("DOMContentLoaded", ()=> Customers.init());
