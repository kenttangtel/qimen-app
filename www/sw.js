// 註冊 Service Worker，讓系統具備 PWA 安裝資格
self.addEventListener('install', (e) => {
    console.log('[Service Worker] 安裝成功');
});

self.addEventListener('fetch', (e) => {
    // 基本的網路請求放行
    e.respondWith(fetch(e.request).catch(() => new Response('網路連線失敗，請檢查網路狀態。')));
});