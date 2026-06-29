/* =====================================================
   WhatsAgent · Command Center  (Aurora Dark)
===================================================== */

const C = {
    green:"#25D366", violet:"#8B7CFF", cyan:"#22D3EE",
    amber:"#FBBF24", pink:"#F472B6", red:"#FB7185",
    text:"#EAECF5", muted:"#8B92AB", faint:"#5A6178",
    grid:"rgba(255,255,255,.06)",
};

const SERIES_COLORS = [C.violet, C.cyan, C.green, C.amber, C.pink, C.red];

const AVATARS = [
    ["#8B7CFF","#F472B6"], ["#25D366","#22D3EE"], ["#FBBF24","#FB7185"],
    ["#22D3EE","#8B7CFF"], ["#F472B6","#FBBF24"], ["#25D366","#8B7CFF"],
];

/* ---- global Chart.js dark defaults ---- */
if (window.Chart) {
    Chart.defaults.color = C.muted;
    Chart.defaults.font.family = "Inter, sans-serif";
    Chart.defaults.font.size = 11;
}

const TOOLTIP = {
    backgroundColor:"rgba(10,12,22,.95)",
    borderColor:"rgba(255,255,255,.12)",
    borderWidth:1,
    padding:12, cornerRadius:12,
    titleFont:{family:"Sora",weight:"700",size:13},
    bodyColor:C.text, titleColor:"#fff",
    displayColors:false,
};

const Dashboard = {

    apiUrl:"/admin/dashboard",
    data:null,
    charts:{},
    trendMetric:"requests",

    async init(){
        this.startClock();
        this.setControls();
        this.showLoading();
        await this.load();
    },

    startClock(){
        const tick = ()=>{
            const d = new Date();
            const el = document.getElementById("liveClock");
            if (el) el.textContent = d.toLocaleTimeString("tr-TR",{hour:"2-digit",minute:"2-digit"});
            const line = document.getElementById("todayLine");
            if (line) line.textContent = d.toLocaleDateString("tr-TR",
                {weekday:"long",day:"numeric",month:"long"}) + " · canlı görünüm";
        };
        tick();
        setInterval(tick, 30000);
    },

    setControls(){
        const r = document.getElementById("refreshBtn");
        if (r) r.addEventListener("click",()=>this.refresh(r));

        const t = document.getElementById("trendToggle");
        if (t) t.querySelectorAll(".seg-btn").forEach(b=>{
            b.addEventListener("click",()=>{
                t.querySelectorAll(".seg-btn").forEach(x=>x.classList.remove("active"));
                b.classList.add("active");
                this.trendMetric = b.dataset.metric;
                this.renderTrend();
            });
        });
    },

    async refresh(btn){
        btn.classList.add("spinning");
        await this.load();
        setTimeout(()=>btn.classList.remove("spinning"), 700);
    },

    async load(){
        try{
            const res = await fetch(this.apiUrl);
            if(!res.ok) throw new Error("API");
            this.data = await res.json();
            this.render();
        }catch(e){
            console.error(e);
            this.showError();
        }
    },

    render(){
        const b=this.data.business, u=this.data.usage, p=this.data.performance;
        const dt=this.data.charts.daily_trend;

        this.animate("uniqueCustomers", b.unique_customers);
        this.animate("totalRequests", b.total_requests);
        this.currency("aiCost", b.ai_cost_try);
        this.currency("estimatedSavings", b.estimated_savings);

        this.text("savedHours", b.estimated_saved_hours+" sa");
        this.currency("employeeCost", b.estimated_employee_cost);
        this.text("usdRate", "₺"+ (u.usd_try_rate? u.usd_try_rate.toFixed(2):"-"));
        this.text("responseTime", p.average_response_time+" sn");

        this.hideLoading();

        // trend rozetleri
        this.trendBadge("trendCustomers", dt.customers);
        this.trendBadge("trendRequests", dt.requests);
        this.trendBadge("trendCost", dt.cost);
        this.trendBadge("trendSavings", dt.requests);

        // sparkline'lar
        this.spark("sparkCustomers", dt.customers, C.green);
        this.spark("sparkRequests", dt.requests, C.violet);
        this.spark("sparkCost", dt.cost, C.amber);
        this.spark("sparkSavings", dt.requests, C.cyan);

        // ana grafikler
        this.renderTrend();
        this.renderDonut();
        this.renderHourly();
        this.renderModel();
        this.renderGauge();
        this.renderTimeline();
        this.renderTopCustomers();
    },

    /* ---------- sparklines ---------- */
    spark(id, data, color){
        const cv=document.getElementById(id); if(!cv) return;
        this.kill(id);
        const ctx=cv.getContext("2d");
        const g=ctx.createLinearGradient(0,0,0,46);
        g.addColorStop(0,color+"66"); g.addColorStop(1,color+"00");
        this.charts[id]=new Chart(ctx,{
            type:"line",
            data:{labels:data.map((_,i)=>i),datasets:[{
                data:data, borderColor:color, backgroundColor:g,
                borderWidth:2.5, fill:true, tension:.45,
                pointRadius:0, pointHoverRadius:0,
            }]},
            options:{responsive:true,maintainAspectRatio:false,
                plugins:{legend:{display:false},tooltip:{enabled:false}},
                scales:{x:{display:false},y:{display:false}},
                animation:{duration:900},
            },
        });
    },

    /* ---------- trend badge ---------- */
    trendBadge(id, arr){
        const el=document.getElementById(id); if(!el) return;
        if(!arr || arr.length<2){ el.style.display="none"; return; }
        const h=Math.ceil(arr.length/2);
        const recent=arr.slice(-h).reduce((a,b)=>a+b,0);
        const prev=arr.slice(0,arr.length-h).reduce((a,b)=>a+b,0) || 0;
        let pct = prev===0 ? (recent>0?100:0) : ((recent-prev)/prev*100);
        const up = pct>=0;
        el.className = "trend " + (up?"up":"down");
        el.innerHTML = `<i class="fa-solid fa-arrow-${up?"up":"down"}"></i> ${Math.abs(pct).toFixed(0)}%`;
        el.style.display="inline-flex";
    },

    /* ---------- 1. hero trend ---------- */
    renderTrend(){
        const cv=document.getElementById("trendChart"); if(!cv||!this.data) return;
        const dt=this.data.charts.daily_trend, m=this.trendMetric;
        const color={requests:C.violet,tokens:C.cyan,cost:C.amber}[m];
        const ctx=cv.getContext("2d");
        this.kill("trend");
        const g=ctx.createLinearGradient(0,0,0,300);
        g.addColorStop(0,color+"55"); g.addColorStop(.6,color+"18"); g.addColorStop(1,color+"00");

        this.charts.trend=new Chart(ctx,{
            type:"line",
            data:{labels:dt.labels.map(this.shortDate),datasets:[{
                data:dt[m], borderColor:color, backgroundColor:g,
                borderWidth:3, fill:true, tension:.42,
                pointRadius:0, pointHoverRadius:6,
                pointHoverBackgroundColor:color, pointHoverBorderColor:"#fff", pointHoverBorderWidth:2,
            }]},
            options:{responsive:true,maintainAspectRatio:false,
                interaction:{mode:"index",intersect:false},
                plugins:{legend:{display:false},tooltip:{...TOOLTIP,callbacks:{
                    label:c=> m==="cost" ? " $"+c.parsed.y.toFixed(4)
                        : " "+c.parsed.y.toLocaleString("tr-TR")+" "+m,
                }}},
                scales:{
                    x:{grid:{display:false},border:{display:false},ticks:{maxTicksLimit:8}},
                    y:{grid:{color:C.grid},border:{display:false},ticks:{maxTicksLimit:5,padding:8}},
                },
            },
        });
    },

    /* ---------- 2. donut ---------- */
    renderDonut(){
        const cv=document.getElementById("tokenSplitChart"); if(!cv) return;
        const u=this.data.usage, pr=u.prompt_tokens||0, co=u.completion_tokens||0;
        this.text("donutTotal", this.compact(pr+co));
        this.kill("donut");
        this.charts.donut=new Chart(cv.getContext("2d"),{
            type:"doughnut",
            data:{labels:["Prompt","Completion"],datasets:[{
                data:[pr,co], backgroundColor:[C.violet,C.cyan],
                borderWidth:0, hoverOffset:10, spacing:2,
            }]},
            options:{responsive:true,maintainAspectRatio:false,cutout:"74%",
                plugins:{legend:{display:false},tooltip:{...TOOLTIP,displayColors:true,callbacks:{
                    label:c=>{const t=pr+co;const p=t?(c.parsed/t*100).toFixed(1):0;
                        return ` ${c.label}: ${c.parsed.toLocaleString("tr-TR")} (${p}%)`;}
                }}},
            },
        });
        this.legend("tokenLegend",["Prompt","Completion"],[C.violet,C.cyan]);
    },

    /* ---------- 3. hourly bars ---------- */
    renderHourly(){
        const cv=document.getElementById("hourlyChart"); if(!cv) return;
        const h=this.data.charts.hourly_activity;
        const ctx=cv.getContext("2d");
        this.kill("hourly");
        const g=ctx.createLinearGradient(0,0,0,230);
        g.addColorStop(0,C.violet); g.addColorStop(1,"rgba(34,211,238,.5)");
        this.charts.hourly=new Chart(ctx,{
            type:"bar",
            data:{labels:h.labels,datasets:[{
                data:h.requests, backgroundColor:g, hoverBackgroundColor:C.green,
                borderRadius:5, borderSkipped:false, barPercentage:.72, categoryPercentage:.9,
            }]},
            options:{responsive:true,maintainAspectRatio:false,
                plugins:{legend:{display:false},tooltip:{...TOOLTIP,callbacks:{
                    title:i=>i[0].label, label:c=>" "+c.parsed.y+" istek"}}},
                scales:{
                    x:{grid:{display:false},border:{display:false},ticks:{maxTicksLimit:12,autoSkip:true,font:{size:10}}},
                    y:{grid:{color:C.grid},border:{display:false},ticks:{maxTicksLimit:4,padding:6}},
                },
            },
        });
    },

    /* ---------- 4. model polar ---------- */
    renderModel(){
        const cv=document.getElementById("modelChart"); if(!cv) return;
        const m=this.data.charts.model_distribution;
        this.kill("model");
        if(!m.labels.length){ this.emptyCanvas(cv); return; }
        this.charts.model=new Chart(cv.getContext("2d"),{
            type:"polarArea",
            data:{labels:m.labels,datasets:[{
                data:m.requests,
                backgroundColor:m.labels.map((_,i)=>SERIES_COLORS[i%SERIES_COLORS.length]+"bb"),
                borderColor:"rgba(10,12,22,.6)", borderWidth:2,
            }]},
            options:{responsive:true,maintainAspectRatio:false,
                plugins:{legend:{position:"bottom",labels:{usePointStyle:true,pointStyle:"circle",padding:14,boxWidth:8,font:{size:11}}},
                    tooltip:{...TOOLTIP,displayColors:true,callbacks:{label:c=>" "+c.parsed.r+" istek"}}},
                scales:{r:{grid:{color:C.grid},angleLines:{color:C.grid},ticks:{display:false,backdropColor:"transparent"}}},
            },
        });
    },

    /* ---------- 5. gauge (half doughnut) ---------- */
    renderGauge(){
        const cv=document.getElementById("gaugeChart"); if(!cv) return;
        const rt=this.data.performance.average_response_time||0;
        const max=5, frac=Math.min(rt/max,1);
        const color = rt<=1.8 ? C.green : rt<=3.2 ? C.amber : C.red;
        this.text("gaugeValue", rt.toFixed(1));
        const gv=document.getElementById("gaugeValue"); if(gv) gv.style.color=color;
        this.kill("gauge");
        this.charts.gauge=new Chart(cv.getContext("2d"),{
            type:"doughnut",
            data:{datasets:[{
                data:[frac,1-frac],
                backgroundColor:[color,"rgba(255,255,255,.07)"],
                borderWidth:0, circumference:180, rotation:270, cutout:"76%",
            }]},
            options:{responsive:true,maintainAspectRatio:false,
                plugins:{legend:{display:false},tooltip:{enabled:false}},
            },
        });
    },

    /* ---------- 6. timeline ---------- */
    renderTimeline(){
        const box=document.getElementById("activityTimeline"); if(!box) return;
        const items=this.data.recent_activity||[];
        if(!items.length){ box.innerHTML=this.emptyHTML("clock","Henüz aktivite yok."); return; }
        box.innerHTML=items.map((it,i)=>{
            const audio = it.model && it.model.includes("transcribe");
            return `<div class="tl-item" style="animation-delay:${i*.05}s">
                <div class="tl-icon ${audio?"audio":""}"><i class="fa-solid fa-${audio?"microphone":"comment-dots"}"></i></div>
                <div class="tl-body">
                    <div class="tl-top">
                        <span class="tl-sender">${this.mask(it.sender)}</span>
                        <span class="tl-time">${this.ago(it.timestamp)}</span>
                    </div>
                    <div class="tl-meta">
                        <span class="chip">${it.model||"?"}</span>
                        <span class="chip"><b>${(it.total_tokens||0).toLocaleString("tr-TR")}</b> token</span>
                        <span class="chip"><b>${it.response_time||0}</b> sn</span>
                    </div>
                </div>
            </div>`;
        }).join("");
    },

    /* ---------- 7. top customers rank list ---------- */
    renderTopCustomers(){
        const box=document.getElementById("topCustomers"); if(!box) return;
        const t=this.data.charts.top_customers;
        if(!t.labels.length){ box.innerHTML=this.emptyHTML("user","Henüz müşteri yok."); return; }
        const max=Math.max(...t.requests,1);
        box.innerHTML=t.labels.map((s,i)=>{
            const [a,b]=AVATARS[i%AVATARS.length];
            const medal = i<3 ? ["🥇","🥈","🥉"][i] : (i+1);
            return `<div class="rank-item" style="animation-delay:${i*.05}s">
                <span class="rank-medal">${medal}</span>
                <div class="rank-ava" style="background:linear-gradient(135deg,${a},${b})">${this.initials(s)}</div>
                <div class="rank-body">
                    <div class="rank-top">
                        <span class="rank-name">${this.mask(s)}</span>
                        <span class="rank-val">${t.requests[i]} istek</span>
                    </div>
                    <div class="rank-bar"><div class="rank-fill" data-w="${(t.requests[i]/max*100).toFixed(1)}"
                        style="background:linear-gradient(90deg,${a},${b})"></div></div>
                </div>
            </div>`;
        }).join("");
        requestAnimationFrame(()=>{
            box.querySelectorAll(".rank-fill").forEach(f=>{ f.style.width=f.dataset.w+"%"; });
        });
    },

    /* ---------- utils ---------- */
    legend(id,labels,colors){
        const el=document.getElementById(id); if(!el) return;
        el.innerHTML=labels.map((l,i)=>
            `<div class="legend-item"><span class="legend-dot" style="background:${colors[i]}"></span>${l}</div>`).join("");
    },
    kill(k){ if(this.charts[k]){ this.charts[k].destroy(); delete this.charts[k]; } },
    emptyCanvas(cv){ const x=cv.getContext("2d"); x.clearRect(0,0,cv.width,cv.height);
        x.font="13px Inter"; x.fillStyle=C.faint; x.textAlign="center"; x.fillText("Veri yok",cv.width/2,cv.height/2); },
    emptyHTML(icon,txt){ return `<div class="empty"><i class="fa-solid fa-${icon}"></i><span>${txt}</span></div>`; },
    mask(s){ if(!s) return "—"; s=String(s); return s.length<=6?s:s.slice(0,4)+"•••"+s.slice(-3); },
    initials(s){ if(!s) return "?"; s=String(s); return s.slice(-2); },
    shortDate(d){ const p=String(d).split("-"); return p.length===3?`${p[2]}.${p[1]}`:d; },
    ago(ts){ const t=new Date(String(ts).replace(" ","T")); const s=(Date.now()-t.getTime())/1000;
        if(isNaN(s)) return ts; if(s<60) return "az önce"; if(s<3600) return Math.floor(s/60)+" dk";
        if(s<86400) return Math.floor(s/3600)+" sa"; return Math.floor(s/86400)+" gün"; },
    compact(n){ if(n>=1e6) return (n/1e6).toFixed(1)+"M"; if(n>=1e3) return (n/1e3).toFixed(1)+"K"; return ""+n; },

    text(id,v){ const e=document.getElementById(id); if(e) e.textContent=v; },
    currency(id,v){ const e=document.getElementById(id); if(!e) return;
        if(v==null){ e.textContent="-"; return; }
        e.textContent=new Intl.NumberFormat("tr-TR",{style:"currency",currency:"TRY",maximumFractionDigits:0}).format(v); },
    animate(id,v){ const e=document.getElementById(id); if(!e) return;
        const end=Number(v)||0, dur=1000, t0=performance.now();
        const step=t=>{ const p=Math.min((t-t0)/dur,1); const ease=1-Math.pow(1-p,3);
            e.textContent=Math.floor(ease*end).toLocaleString("tr-TR");
            if(p<1) requestAnimationFrame(step); };
        requestAnimationFrame(step); },

    showLoading(){ document.querySelectorAll(".kpi-card h2,.biz-item strong").forEach(e=>e.classList.add("loading")); },
    hideLoading(){ document.querySelectorAll(".loading").forEach(e=>e.classList.remove("loading")); },
    showError(){ this.hideLoading();
        const box=document.getElementById("activityTimeline");
        if(box) box.innerHTML=this.emptyHTML("triangle-exclamation","Veriler alınamadı."); },
};

document.addEventListener("DOMContentLoaded",()=>Dashboard.init());
