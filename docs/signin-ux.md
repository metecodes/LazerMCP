# Google giriş akışı

Google ile giriş düğmeleri ortak `/nav-auth.js` dosyasını yüklemeli. Tercih edilen işaretleme:

```html
<a data-google-signin href="/auth/google?next=%2Fdashboard">Google ile gir</a>
<script src="/nav-auth.js"></script>
```

`.btn-google`, `#nav-signin` ve `/auth/google` bağlantıları da desteklenir. Profil/hesap yönetimi bağlantılarına bu işaretleri eklemeyin. `next` verilmezse giriş sonrası hedef `/dashboard` olur. Bağlayıcı OAuth akışlarında `/oauth/authorize?...` hedefinin tamamını URL kodlayarak koruyun.

Ortak kod `/api/auth/start` üzerinden sağlayıcı URL'sini alır ve mevcut sayfadan Google'a gider; `/account` üzerinde ikinci tıklama gerektirmez. Aktif oturum varsa hedefe doğrudan döner. Çift tıklama kilidi, 15 saniyelik zaman aşımı ve yerinde tekrar deneme mesajı vardır. Geri düğmesiyle dönüşte kilit temizlenir.

`/auth/callback` artık hesap sayfasından bağımsızdır. URL tokenlarını hemen temizler, sunucuda oturum oluşturur ve `location.replace` ile hedefe geçer. Hata/iptalde tekrar deneme gösterir. Sağlayıcının hesap seçimi/izin ekranları korunur. JavaScript kapalıysa `/auth/google` mevcut yönlendirme yedeği olarak kalır.

14 Eylül çalışması sırasında altı HTML sayfası başka bir düzenleme nedeniyle boştu. Bunlar geri yüklenmedi veya değiştirilmedi. Son kontrolde sayfa içerikleri diğer düzenleme tarafından geri yazılmıştı; landing, account, connect ve dashboard sayfalarının ortak scripti yüklediği ve giriş düğmelerinin desteklenen seçicilerle eşleştiği salt okunur olarak doğrulandı. Gerçek Google hesabıyla giriş/iptal/dönüş akışı tarayıcıda denenmeli. Canlı dağıtım yapılmadı.

Kontroller: `python -m unittest discover -s tests -p test_signin_ux.py`, `python -m unittest discover -s tests -p test_auth.py`, `node --test tests/signin_ux.test.cjs`.
