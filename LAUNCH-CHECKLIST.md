# 奇門大師 — 上架前準備報告

**日期**：2026-10-13
**專案**：qimen-app（FastAPI + Capacitor Android/iOS）
**線位址**：https://qimen-app-xwie.onrender.com

---

## 一、目前狀態總覽

| 區塊 | 狀態 | 備註 |
|---|---|---|
| GitHub 程式碼 | ✅ 已推送 | `39fe4e9`（+ 未提交 IAP 修復） |
| Render 部署 | ✅ 已上線 | `/health` 200 |
| 外洩 token | ✅ 已撤銷 | 舊 token 401 |
| 新 token | ✅ 生效 | 200 |
| 冪等性 | ✅ 已生效 | 重複事件只加一次 |
| 後端安全修復 | ✅ 全部通過 | 見第二節 |
| 前端 IAP 修復 | ⚠️ 已改未推 | 見第三節 |
| RevenueCat 金流 | 🔴 未接通 | 見第四節 |
| 機密輪換 | ⚠️ 部分完成 | 見第五節 |

---

## 二、已完成的後端修復（已線上驗證）

| 項目 | 修補前 | 修補後 | 驗證 |
|---|---|---|---|
| 外洩 token | 可用 → 免費灌點數 | 401 | ✅ |
| 程式碼預設 fallback token | `my_super_secret_token_123` 可繞過 | 401 | ✅ |
| 重複投遞同一事件 | 送 3 次 +45 點 | 只加一次 | ✅ |
| `/debug/env` | 免認證枚舉設定 | 401 需認證 | ✅ |
| `/health` | 不存在 | 200 含 DB probe | ✅ |
| CORS | `["*"]` 全開 | 白名單 | ✅ |
| Stripe webhook | HTTP 200 掩蓋失敗 | 正確回 5xx 讓 Stripe 重試 | ✅ |
| 點數競態 | 讀-改-寫 | 原子 UPDATE + RETURNING | ✅ |
| RevenueCat 驗證 | 無 | `hmac.compare_digest` + fail-closed 503 | ✅ |
| `/history/detail` | 回傳格式與前端不符 | 回傳 `{status, data}` | ✅ |
| 忘記密碼 | 缺 RESEND_API_KEY，100% 失敗 | 完整流程 | ✅ |
| `clean_stream_content` | 破壞 `air flow` 等正常文字 | 單詞邊界修正 | ✅ |
| `User.is_vip` 靜默失敗 | 寫入被 SQLAlchemy 忽略 | 已移除並文檔化 | ✅ |
| 前端 JS 語法錯誤 | 整頁白畫面 | 已修正 | ✅ |

---

## 三、前端 IAP 修復（已改，未提交）

**檔案**：`www/index.html`

### Bug 1：`initNativeIAP` 沒有 await
```diff
- if (d.id) initNativeIAP(d.id);
+ if (d.id) await initNativeIAP(d.id);
```
**影響**：`Purchases.configure()` 未完成，用戶按購買 → 失敗。

### Bug 2：`purchaseStoreProduct` 參數錯誤
```diff
- await Purchases.purchaseStoreProduct({ productIdentifier: planType });
+ const { products } = await Purchases.getProducts({ productIdentifiers: [planType] });
+ await Purchases.purchaseStoreProduct({ product: products[0] });
```
**影響**：`productIdentifier` 不是有效參數，購買必然失敗。

**驗證**：JS 語法檢查通過。

---

## 四、RevenueCat 金流上架前必做

### 🔴 必做（阻塞上架）

| # | 動作 | 位置 | 說明 |
|---|---|---|---|
| 1 | **填入 RevenueCat Public SDK key** | `www/index.html` 第 638、640 行 | 目前是佔位符 `appl_...ERE` / `goog_...ERE` |
| 2 | **設定 RevenueCat Products** | RevenueCat 後台 | Product ID 必須與程式碼一致（`topup_15` 等） |
| 3 | **設定 RevenueCat Offerings** | RevenueCat 後台 | 必須有 active Offering 含 package |
| 4 | **設定 Webhook URL** | RevenueCat → Integrations → Webhooks | `https://qimen-app-xwie.onrender.com/api/v1/payment/webhook/revenuecat` |
| 5 | **App Store Connect 設定** | Apple 後台 | Sandbox tester、IAP 商品、Tax/Banking |
| 6 | **Google Play Console 設定** | Google 後台 | IAP 商品、Merchant 帳號 |

### 🟡 建議（上架後）

| # | 動作 | 說明 |
|---|---|---|
| 7 | 設定 RevenueCat HMAC 簽章 | 更強的 webhook 驗證 |
| 8 | 沙盤測試完整購買流程 | 確認 webhook 收到事件 |
| 9 | 設定 Render alerting | 監控 5xx 錯誤 |
| 10 | 設定 Supabase 備份 | 定期备份 |

---

## 五、機密輪換狀態

| 項目 | 狀態 | 備註 |
|---|---|---|
| RevenueCat webhook token | ✅ 已輪換 | 舊 token 401，新 token 200 |
| RevenueCat 帳號密碼 | ⚠️ 已改 | `Kk92815867` → 已修改 |
| Render 帳號密碼 | ⚠️ 已改 | — |
| Stripe webhook secret | 🔴 未換 | 仍在公開 git 歷史 |
| DeepSeek API key | 🔴 未換 | 仍在公開 git 歷史 |
| Google API key | 🔴 未換 | 仍在公開 git 歷史 |
| RevenueCat 帳號密碼 | 🔴 未換 | 仍在公開 git 歷史 |

---

## 六、上架前檢查清單

### 程式碼
- [ ] 推送 IAP 修復（`www/index.html`）
- [ ] 填入 RevenueCat Public SDK key
- [ ] 確認 Product ID 與 RevenueCat 後台一致
- [ ] 沙盤測試購買流程

### 安全
- [ ] 舊 token 已撤銷 ✅
- [ ] 新 token 已生效 ✅
- [ ] 密碼已改 ✅
- [ ] 建議輪換 Stripe/DeepSeek/Google keys
- [ ] 建議清 git 歷史（`git filter-repo` + force-push）

### 部署
- [ ] Render 已部署 ✅
- [ ] RevenueCat webhook 已設定
- [ ] App Store / Play Console 已設定

### 文檔
- [ ] README 更新
- [ ] DEPLOYMENT.md 已有 ✅
- [ ] `.env.example` 已有 ✅

---

## 七、指令記錄

### 推送未提交的 IAP 修復
```powershell
cd C:\Users\User\qimen-app
git add www/index.html
git commit -m "fix: correct RevenueCat IAP calls in frontend"
git push origin main
```

### 驗證 RevenueCat webhook 端點
```powershell
curl.exe -s -o NUL -w "%{http_code}`n" -X POST "https://qimen-app-xwie.onrender.com/api/v1/payment/webhook/revenuecat" -H "Authorization: Bearer rc_VjMmlRUY9bTvmbsvSQo4uRB2Uu7cR66CSupWtp-O47_mAbYf" -H "Content-Type: application/json" -d '{"event":{"type":"TEST"}}'
```

### 驗證舊 token 已失效
```powershell
curl.exe -s -o NUL -w "%{http_code}`n" -X POST "https://qimen-app-xwie.onrender.com/api/v1/payment/webhook/revenuecat" -H "Authorization: Bearer qimen_...2026" -H "Content-Type: application/json" -d '{"event":{"type":"TEST"}}'
```
（應回 401）

---

## 八、風險提醒

1. **RevenueCat 方案**：Webhooks 需要 Pro 方案，確認你的方案包含
2. **Product ID 一致性**：程式碼裡的 `topup_15` 必須與 RevenueCat 後台完全一致
3. **git 歷史**：`4fb7f62` 仍含 `pw.txt`、`API KEY.txt`、`__temp_webhook_test.py`，建議清歷史
4. **密碼洩漏**：`pw.txt` 裡的帳號密碼仍在公開 git 歷史，建議改密碼

---

**報告結束**
