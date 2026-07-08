/* =====================================================
   WhatsAgent · AI Usage sayfası
   usage_logs üzerinden model bazlı detaylı analiz
===================================================== */

const C = {
    green:"#25D366", violet:"#8B7CFF", cyan:"#22D3EE",
    amber:"#FBBF24", pink:"#F472B6", red:"#FB7185",
    text:"#EAECF5", muted:"#8B92AB", grid:"rgba(255,255,255,.06)"
};
const SERIES = [C.violet, C.cyan, C.green, C.amber, C.pink, C.red];

if (window.Chart){
    Chart.defaults.color = C.muted;
    Chart.defaults.font.family = "Inter, sans-serif";
    Chart.defaults.font.size = 11;
}

const AIUsage = {

    charts: {},

    async init(){
        try{
            const res = await fetch("/admin/ai-usage");
            if (!res.ok) throw new Error("HTTP " + res.status);
            this.render(await res.json());
        }catch(e){
            console.error("ai-usage", e);
            document.getElementById("modelTableBody").innerHTML =
                `<tr><td colspan="8" class="aiu-empty">Veri yüklenemedi 🙏</td></tr>`;
        }
    },

    esc(s){
        return String(s == null ? "" : s)
            .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    },

    fmtInt(n){ return (n || 0).toLocaleString("tr-TR"); },
    fmtCost(n){ return "$" + (n || 0).toFixed(4); },

    render(d){
        const s = d.summary || {};

        // Tile'lar
        document.getElementById("tRequests").textContent = this.fmtInt(s.total_requests);
        document.getElementById("tTokens").textContent   = this.fmtInt(s.total_tokens);
        document.getElementById("tTokensSub").textContent =
            `${this.fmtInt(s.prompt_tokens)} prompt · ${this.fmtInt(s.completion_tokens)} completion`;
        document.getElementById("tCost").textContent = this.fmtCost(s.total_cost_usd);
        document.getElementById("tCostTry").textContent =
            s.total_cost_try != null ? `≈ ${s.total_cost_try.toLocaleString("tr-TR")} TL` : "";
        document.getElementById("tArt").textContent = (s.avg_response_time || 0).toFixed(2);
        document.getElementById("tAvgCost").textContent = "$" + (s.avg_cost_per_request || 0).toFixed(5);

        this.renderModelTable(d.by_model || []);
        this.renderTopCustomers(d.top_customers_by_cost || []);
        this.renderCharts(d);
    },

    renderModelTable(rows){
        const tb = document.getElementById("modelTableBody");
        if (!rows.length){
            tb.innerHTML = `<tr><td colspan="8" class="aiu-empty">Henüz kullanım kaydı yok.</td></tr>`;
            return;
        }
        tb.innerHTML = rows.map(m=>`
            <tr>
                <td>${this.esc(m.model)}</td>
                <td>${this.fmtInt(m.requests)}</td>
                <td>${this.fmtInt(m.prompt_tokens)}</td>
                <td>${this.fmtInt(m.completion_tokens)}</td>
                <td>${this.fmtInt(m.total_tokens)}</td>
                <td><b>${this.fmtCost(m.cost_usd)}</b></td>
                <td>${(m.avg_response_time || 0).toFixed(2)}</td>
                <td>$${(m.avg_cost || 0).toFixed(5)}</td>
            </tr>`).join("");
    },

    renderTopCustomers(rows){
        const el = document.getElementById("topCustomers");
        if (!rows.length){
            el.innerHTML = `<div class="aiu-empty">Henüz veri yok.</div>`;
            return;
        }
        el.innerHTML = rows.map((c,i)=>`
            <div class="rank-row">
                <span class="r-i">${i+1}</span>
                <span class="r-name">${this.esc(c.sender)}</span>
                <span class="r-req">${this.fmtInt(c.requests)} istek</span>
                <span class="r-val">${this.fmtCost(c.cost_usd)}</span>
            </div>`).join("");
    },

    line(canvasId, labels, data, color, label){
        const ctx = document.getElementById(canvasId);
        if (!ctx || !window.Chart) return;
        if (this.charts[canvasId]) this.charts[canvasId].destroy();
        this.charts[canvasId] = new Chart(ctx, {
            type:"line",
            data:{ labels, datasets:[{
                label, data, borderColor:color, backgroundColor:color+"22",
                fill:true, tension:.35, pointRadius:0, borderWidth:2
            }]},
            options:{
                responsive:true, maintainAspectRatio:false,
                plugins:{ legend:{ display:false } },
                scales:{
                    x:{ grid:{ color:C.grid }, ticks:{ maxTicksLimit:8 } },
                    y:{ grid:{ color:C.grid }, beginAtZero:true }
                }
            }
        });
    },

    renderCharts(d){
        const daily = d.daily || { labels:[], cost:[], avg_response_time:[] };

        this.line("costChart", daily.labels, daily.cost, C.violet, "Maliyet (USD)");
        this.line("artChart", daily.labels, daily.avg_response_time, C.cyan, "Ort. süre (sn)");

        // Model maliyet dağılımı (doughnut)
        const ctx = document.getElementById("modelCostChart");
        if (ctx && window.Chart){
            if (this.charts.modelCostChart) this.charts.modelCostChart.destroy();
            const models = d.by_model || [];
            this.charts.modelCostChart = new Chart(ctx, {
                type:"doughnut",
                data:{
                    labels: models.map(m=>m.model),
                    datasets:[{ data: models.map(m=>m.cost_usd),
                        backgroundColor: models.map((_,i)=>SERIES[i % SERIES.length]),
                        borderColor:"rgba(0,0,0,.2)", borderWidth:1 }]
                },
                options:{
                    responsive:true, maintainAspectRatio:false, cutout:"62%",
                    plugins:{ legend:{ position:"bottom", labels:{ boxWidth:12, padding:12 } } }
                }
            });
        }
    }
};

document.addEventListener("DOMContentLoaded", ()=> AIUsage.init());
