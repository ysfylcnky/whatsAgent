E-ticarette reklana harcadığınız her lira, WhatsApp'ta cevapsız kalan bir mesajda eriyor olabilir. 📉

Son dönemde üzerinde çalıştığım projeyi paylaşmak istiyorum: reklam veren e-ticaret satıcıları için geliştirdiğim, WhatsApp üzerinden çalışan yapay zeka destekli bir satış asistanı.

Problem net: Reklamlar müşteriyi WhatsApp'a getiriyor, ama gelen mesajların çoğu geç cevaplanıyor ya da hiç cevaplanmıyor. Gece düşen "bu üründe M beden var mı?" sorusu sabaha kadar beklerse, o satış çoktan kaçmış oluyor. Yani reklam bütçesi trafiği getiriyor, dönüşüm ise cevapsız mesajlarda kayboluyor.

Çözüm: 7/24 çalışan, insan gibi konuşan ve gerçek stok verisine bağlı bir asistan.

Müşteri ürünü ister isimle ("puantiyeli etek var mı?") ister linkle sorsun, asistan mağazanın canlı envanterinden renk / beden / stok / fiyat bilgisini anında veriyor. Siparişi baştan sona alıyor, özetleyip müşteriye onaylatıyor ve mağaza ekibine iletiyor. Ödeme, kargo ve iade–değişim sorularını da yanıtlıyor — hatta gelen sesli mesajları bile anlayıp cevaplıyor.

Kısacası: reklam trafiğini ve kaçan mesajları satışa çeviren bir katman.

🛠 Kullandığım teknolojiler:
→ Python + FastAPI — webhook ve servis katmanı
→ OpenAI GPT-4.1-mini — function/tool calling ile ürün arama ve sipariş oluşturma
→ OpenAI ses transkripsiyonu — sesli mesaj desteği
→ İKAS Admin GraphQL API — gerçek zamanlı ürün ve stok verisi
→ MySQL — kullanım ve maliyet loglama
→ Chart.js ile canlı yönetim paneli — istek, token, maliyet ve tasarruf (ROI) takibi
→ WhatsApp Cloud API, Ubuntu sunucu üzerinde

En keyif aldığım kısım: Yapay zekayı basit bir "chatbot" olmaktan çıkarıp gerçek envanter ve sipariş akışına bağlamak. Doğru ürünü, doğru stokla, doğru fiyatla söylediğin an iş bambaşka bir yere gidiyor. Bu süreçte JSON tabanlı veri çekmekten platformun kendi API'sine geçmek, tool calling'i sipariş akışına oturtmak ve WhatsApp'ın altyapısını uçtan uca kurmak çok şey öğretti.

Şu an ürünü canlıya alma aşamasındayız. Geri bildirime ve sohbete açığım — e-ticaret, yapay zeka ve otomasyon konuşmayı seven varsa çekinmeden yazsın. 🙌

#yapayzeka #eticaret #whatsapp #otomasyon #python #openai #fastapi #girişimcilik #yazılım #chatbot
