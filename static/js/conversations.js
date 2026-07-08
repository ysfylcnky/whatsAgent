/* =====================================================
   WhatsAgent · Conversations sayfası
   Sol: müşteri listesi (sayfalı) — Sağ: mesaj detayı (sayfalı)
===================================================== */

const Conversations = {

    listPage: 1,
    listTotalPages: 1,
    detailSender: null,
    detailName: null,
    detailPage: 1,
    detailTotalPages: 1,

    init(){
        this.cacheEls();
        this.bind();
        this.loadList(1);
    },

    cacheEls(){
        this.$list      = document.getElementById("convList");
        this.$listMeta  = document.getElementById("convListMeta");
        this.$listPager = document.getElementById("listPager");
        this.$listPrev  = document.getElementById("listPrev");
        this.$listNext  = document.getElementById("listNext");
        this.$listInfo  = document.getElementById("listPageInfo");

        this.$chat        = document.getElementById("chatScroll");
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
        // Sayfa 1 = en yeni mesajlar; "daha eski" sayfa numarasını artırır
        this.$detailNext.addEventListener("click", ()=> this.loadDetail(this.detailSender, this.detailName, this.detailPage + 1));
        this.$detailPrev.addEventListener("click", ()=> this.loadDetail(this.detailSender, this.detailName, this.detailPage - 1));
    },

    esc(s){
        return String(s == null ? "" : s)
            .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
            .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
    },

    async loadList(page){
        if (page < 1) return;
        try{
            const res = await fetch(`/admin/conversations?page=${page}`);
            if (!res.ok) throw new Error("HTTP " + res.status);
            const data = await res.json();
            this.renderList(data);
        }catch(e){
            this.$list.innerHTML = `<div class="conv-empty">Liste yüklenemedi 🙏</div>`;
            console.error("loadList", e);
        }
    },

    renderList(data){
        this.listPage = data.page || 1;
        this.listTotalPages = data.total_pages || 1;

        this.$listMeta.textContent = `${data.total || 0} müşteri`;

        if (!data.items || data.items.length === 0){
            this.$list.innerHTML = `<div class="conv-empty">Henüz konuşma kaydı yok.</div>`;
            this.$listPager.style.display = "none";
            return;
        }

        this.$list.innerHTML = data.items.map(it=>{
            const name = it.ad_soyad ? this.esc(it.ad_soyad) : this.esc(it.sender);
            const sub  = it.ad_soyad ? this.esc(it.sender) : "";
            return `
                <div class="conv-row" data-sender="${this.esc(it.sender)}" data-name="${this.esc(it.ad_soyad || it.sender)}">
                    <div class="r-top">
                        <span class="r-name">${name}<span class="r-badge">${it.msg_count}</span></span>
                        <span class="r-time">${this.esc(it.last_time || "")}</span>
                    </div>
                    <div class="r-last">${sub ? sub + " · " : ""}${this.esc(it.last_content)}</div>
                </div>`;
        }).join("");

        this.$list.querySelectorAll(".conv-row").forEach(row=>{
            row.addEventListener("click", ()=>{
                this.$list.querySelectorAll(".conv-row").forEach(r=> r.classList.remove("active"));
                row.classList.add("active");
                this.loadDetail(row.dataset.sender, row.dataset.name, 1);
            });
        });

        // Sayfalama
        this.$listPager.style.display = this.listTotalPages > 1 ? "flex" : "none";
        this.$listInfo.textContent = `${this.listPage} / ${this.listTotalPages}`;
        this.$listPrev.disabled = this.listPage <= 1;
        this.$listNext.disabled = this.listPage >= this.listTotalPages;
    },

    async loadDetail(sender, name, page){
        if (!sender) return;
        if (page < 1) return;
        this.detailSender = sender;
        this.detailName = name;
        try{
            const res = await fetch(`/admin/conversations/detail?sender=${encodeURIComponent(sender)}&page=${page}`);
            if (!res.ok) throw new Error("HTTP " + res.status);
            const data = await res.json();
            this.renderDetail(data);
        }catch(e){
            this.$chat.innerHTML = `<div class="conv-empty">Mesajlar yüklenemedi 🙏</div>`;
            console.error("loadDetail", e);
        }
    },

    renderDetail(data){
        this.detailPage = data.page || 1;
        this.detailTotalPages = data.total_pages || 1;

        this.$detailTitle.textContent = this.detailName || this.detailSender;
        this.$detailMeta.textContent  = `${data.total || 0} mesaj`;

        if (!data.messages || data.messages.length === 0){
            this.$chat.innerHTML = `<div class="conv-empty">Bu müşteride mesaj yok.</div>`;
            this.$detailPager.style.display = "none";
            return;
        }

        this.$chat.innerHTML = data.messages.map(m=>{
            const cls = m.direction === "giden" ? "giden" : "gelen";
            return `<div class="bubble ${cls}">${this.esc(m.content)}<span class="b-time">${this.esc(m.timestamp || "")}</span></div>`;
        }).join("");

        // En alta (en yeni mesaja) kaydır
        this.$chat.scrollTop = this.$chat.scrollHeight;

        this.$detailPager.style.display = this.detailTotalPages > 1 ? "flex" : "none";
        this.$detailInfo.textContent = `${this.detailPage} / ${this.detailTotalPages}`;
        // "Daha eski" -> sayfa artırır (üst sınır total_pages); "Daha yeni" -> azaltır (alt sınır 1)
        this.$detailNext.disabled = this.detailPage >= this.detailTotalPages;
        this.$detailPrev.disabled = this.detailPage <= 1;
    }
};

document.addEventListener("DOMContentLoaded", ()=> Conversations.init());
