# Stripe 信用卡支付 — 配置与上线指南

> 适用分支：NewLeo `claude/stripe-checkout` + ELW `claude/stripe-checkout`
> 方案：**Stripe Checkout（Stripe 托管的支付页）**，作为 PayPal 之外的第二种付款方式。PayPal 流程完全不变。
> 默认**关闭**：不设置开关时，部署这套代码不会有任何变化。

---

## 0. 工作原理（一分钟版）

1. 顾客在结账第 3 步（Payment Method）看到 PayPal 按钮，下方多一个 **“Pay with card (Stripe)”** 按钮（仅在开关打开时显示）。
2. 点击后，后端用**数据库里的订单总额**（商品小计 + 运费 − 优惠 + 美国关税，已四舍五入到分，币种 **USD**）创建一个 Stripe Checkout Session，浏览器跳转到 Stripe 的安全支付页。浏览器传来的任何金额都不会被使用。
3. 付款成功 → Stripe 跳回 `https://eyelovewear.com/checkout/stripe/success?session_id=...`，该页向后端确认；后端向 Stripe 查询，确认已付款后把订单标记为 **PAID**（与 PayPal 完全相同的状态变化：写 Payment 记录、冻结收货地址、清空购物车中的已付商品、发确认邮件），然后跳到原有的 `/order-confirmation` 页面。
4. 同时 Stripe 会调用 **Webhook**（服务器对服务器）。即使顾客付款后直接关掉浏览器，订单也会被标记为已付。两条路径都是幂等的：同一笔付款只记录一次、只发一封邮件。
5. 顾客在 Stripe 页面点“返回” → `/checkout/stripe/cancel`，未扣款，未付订单被释放，商品仍在购物车。

卡号等敏感信息只在 Stripe 页面输入，**不经过我们的服务器**（PCI 合规范围最小：SAQ A）。

---

## 1. Stripe 账户（需要 Edward 决定 / 操作）

公司主体在中国大陆，Stripe **不支持中国大陆主体直接开户**。常见做法是用 **香港公司** 或 **海外公司（如美国 LLC、新加坡等）** 开户。代码与主体无关，所有配置都来自环境变量，换主体只需换 key。

开户时需要准备：公司注册文件、董事/实际控制人身份证明、公司银行账户（与主体同名，用于结算）、网站 URL（https://eyelovewear.com，需有退货政策、联系方式、隐私政策、商品价格）、业务描述（“Prescription eyeglasses and sunglasses, online retail, shipping to the US and Canada”）。

> 注意：所有订单以 **USD** 收款。若结算账户不是美元，Stripe 会换汇（有换汇费）。可以在 Dashboard 里加一个美元结算账户来避免。

---

## 2. Dashboard 里要做的事（先在 **Test mode / 测试模式** 下做一遍）

右上角打开 **Test mode**（测试模式）开关，以下步骤在测试模式完成并测试通过后，再在 **Live mode** 重复一次。

### 2.1 API 密钥
- 路径：**Developers → API keys**
- 复制 **Secret key**（`sk_test_...`，上线时是 `sk_live_...`）→ 填入服务器 `.env` 的 `STRIPE_SECRET_KEY`。
- **Publishable key**（`pk_test_...`）→ `STRIPE_PUBLISHABLE_KEY`（托管 Checkout 其实用不到，可留存备用）。
- 建议改用 **Restricted key（受限密钥）**，权限只开：*Checkout Sessions: Write*、*PaymentIntents: Read*、*Charges: Read*（其它都 None）。
- 密钥只放服务器 `.env`，**不要**发微信/邮件、不要提交到 git。

### 2.2 Webhook
- 路径：**Developers → Webhooks → Add endpoint**（新版界面叫 *Workbench → Webhooks → Create an event destination*）
- **Endpoint URL**：
  ```
  https://admin.eyelovewear.com/api/order/stripe/webhook
  ```
  （后端 API 在 `admin.eyelovewear.com/api/...`，与前端 `VITE_API_BASE_URL` 默认值一致；路径定义在 `Order/urls.py`。注意不要漏掉结尾、不要加 `/`。）
- **API version**：用默认（账户当前版本）即可。
- **要订阅的事件（Events）**：
  - `checkout.session.completed` （必选，付款成功的主事件）
  - `checkout.session.async_payment_succeeded`
  - `checkout.session.async_payment_failed`
  - `payment_intent.succeeded`
  - `payment_intent.payment_failed`
  - `charge.refunded`
- 创建后点开该 endpoint → **Signing secret → Reveal**，复制 `whsec_...` → 填入 `.env` 的 `STRIPE_WEBHOOK_SECRET`。
- **测试模式和正式模式的 webhook 是两个不同的 endpoint，signing secret 也不同**，上线时要换。

### 2.3 Checkout 外观（Branding）
- 路径：**Settings → Branding**（品牌）
  - 上传 Logo / Icon（eyelovewear 心形 logo）
  - Brand color：`#A82E68`（网站主色），Accent color 可同色
- 路径：**Settings → Checkout and Payment Links**（可选）：开启 “Display business name / logo”。
- **Settings → Public details（公开信息）**：填写 Business name `Eyelovewear`、客服邮箱、客服电话、网站 `https://eyelovewear.com`、隐私政策和服务条款链接（Checkout 页底部会显示）。

### 2.4 账单描述符（Statement descriptor，顾客信用卡账单上显示的名字）
- 路径：**Settings → Public details → Statement descriptor**
- 建议：`EYELOVEWEAR`（5–22 个字符，只能英文字母/数字/空格，不能全是数字）。
- **Shortened descriptor**（短前缀）：`ELW` 或 `EYELOVE`。
- 可选：服务器 `.env` 设置 `STRIPE_STATEMENT_DESCRIPTOR_SUFFIX=ORDER`，账单上会显示为 `ELW* ORDER`（前缀 + 后缀总长 ≤ 22）。不设也可以。

### 2.5 支付方式
- 路径：**Settings → Payment methods**
- 代码**没有写死**支付方式，由这里决定。建议开启：**Cards**（Visa/Mastercard/Amex/Discover/JCB/UnionPay 视主体支持）、**Apple Pay**、**Google Pay**、**Link**。
- 暂不建议开启需要多天到账的方式（如 ACH 银行转账），虽然代码已支持（`async_payment_succeeded`）。
- Apple Pay：托管 Checkout 无需验证域名。

### 2.6 风控 / 退款
- **Radar**（默认开启）即可。可在 *Radar → Rules* 打开 “Block if CVC verification fails” 和 “Block if postal code verification fails”。
- **退款**：在 Stripe Dashboard 的 Payments 里对该笔付款点 *Refund*。Webhook 会自动把退款写到订单的 `refound_status` / `refound_amount`，并在订单的 *Order Updates* 里留一条记录。**订单状态（order_status）不会自动改**——请在 Django 后台手动改为 REFUND（改状态会给顾客发邮件，所以交给人工决定）。

---

## 3. 服务器 `.env`（后端，NewLeo）

在服务器上 NewLeo 的 `.env` 里加入（`docker-compose.yml` 已用 `env_file: .env` 读取，无需改 compose）：

```dotenv
STRIPE_ENABLED=true
STRIPE_SECRET_KEY=sk_test_...          # 上线时换成 sk_live_... 或 rk_live_...
STRIPE_PUBLISHABLE_KEY=pk_test_...     # 可选
STRIPE_WEBHOOK_SECRET=whsec_...        # 对应模式下 webhook endpoint 的 signing secret
# 可选：
# STRIPE_RETURN_BASE_URL=https://eyelovewear.com   # 默认等于 FRONTEND_BASE_URL
# STRIPE_STATEMENT_DESCRIPTOR_SUFFIX=ORDER
```

- `STRIPE_ENABLED` 不是 `true` 或 `STRIPE_SECRET_KEY` 为空 → 所有 Stripe 接口返回 404，等于没装。
- `STRIPE_WEBHOOK_SECRET` 为空 → webhook 接口返回 404（成功页仍可确认付款，但关掉浏览器的顾客不会自动标记为已付）。**正式上线必须配置。**
- 修改 `.env` 后需要重启后端容器。

### 数据库迁移
本分支新增迁移 `Order/migrations/0028_stripe_checkout.py`（只**新增**两个可为空字符串的字段 `stripe_checkout_session_id`、`stripe_payment_intent_id`，并给 Payment 的网关选项加 `stripe`）。容器启动命令里已有 `python manage.py migrate`，部署时自动执行。
新增依赖：`requirements.txt` 中的 `stripe>=17,<18`（重建镜像时自动安装）。

## 4. 前端构建变量（ELW）

Vite 在**构建时**读取变量。在 ELW 构建目录放 `.env.production`（已在 .gitignore 中）：

```dotenv
VITE_STRIPE_ENABLED=true
```

然后重新构建/部署前端。不设置 → 结账页只有 PayPal，和现在一模一样。
不需要 `VITE_STRIPE_PUBLISHABLE_KEY`（托管 Checkout 由后端创建会话，浏览器只是跳转）。

**前后端两个开关都要打开**按钮才会出现并可用。建议顺序：先开后端（不影响顾客，因为按钮还没显示）→ 测试接口 → 再开前端。

---

## 5. 测试（测试模式，不会真实扣款）

测试模式的 key 下，用 Stripe 官方测试卡（任意未来日期、任意 3 位 CVC、任意邮编）：

| 卡号 | 结果 |
|---|---|
| `4242 4242 4242 4242` | 付款成功 |
| `4000 0000 0000 0002` | 被拒（card declined） |
| `4000 0000 0000 9995` | 余额不足 |
| `4000 0025 0000 3155` | 需要 3D Secure 验证（弹窗里点 Complete） |
| `4000 0000 0000 0341` | 绑定成功但扣款失败 |

测试清单：
1. 加一副眼镜到购物车 → 结账 → 第 3 步出现 “Pay with card (Stripe)” → 点击跳到 Stripe 页面，**金额与页面上的 Total 完全一致（USD）**。
2. 用 `4242...` 付款 → 回到网站显示 “Order Placed!”，收到确认邮件；Django 后台该订单 `payment_status=PAID`、`payment_type=stripe`，Payments 里有一条 gateway=Stripe 的记录。
3. Stripe Dashboard → Webhooks → 该 endpoint → 看到事件返回 **200**。
4. 在 Stripe 页面点左上角返回 → 显示 “Payment cancelled”，购物车商品还在，可以再用 PayPal 付。
5. 用 `4000 0000 0000 0002` → Stripe 页面提示被拒，订单仍为 UNPAID，可换卡重试。
6. 访客（Guest）结账再走一遍；用优惠码 + 运费 + 美国关税的订单再走一遍，核对金额。
7. 在 Stripe Dashboard 对一笔测试付款做部分退款 / 全额退款 → 订单的 Order Updates 里出现 “Stripe: refund”。
8. 确认 PayPal 付款照常可用。

也可以用 Stripe CLI 本地测试 webhook：`stripe listen --forward-to localhost:8000/api/order/stripe/webhook`（CLI 会打印一个临时 `whsec_...`，填入本地 `.env`）。

### 异常情况（后台如何识别）
以下情况订单会被标记 **issue_order = True**，并在 *Order Updates* 里写明原因，请人工处理：
- Stripe 实收金额/币种与订单总额不一致（不会标记为已付）；
- 订单已经用 PayPal 付过，又用 Stripe 付了一次（需退款其中一笔）；
- 顾客在旧的待付订单被取消后仍完成了付款（钱已收、订单标记为已付，但需核对商品）。

---

## 6. 上线检查清单（Go-live）

- [ ] Stripe 账户主体确定、**激活完成**（Activate payments），结算银行账户已绑定（建议 USD 账户）。
- [ ] 在 **Live mode** 重做第 2 节：API key（建议受限密钥）、Webhook endpoint（同一 URL，新的 `whsec_...`）、Branding、Public details、Statement descriptor、Payment methods。
- [ ] 服务器 `.env` 换成 **live** 的 `STRIPE_SECRET_KEY` 和 **live** 的 `STRIPE_WEBHOOK_SECRET`，`STRIPE_ENABLED=true`，重启后端。
- [ ] 后端迁移 `0028_stripe_checkout` 已执行（`python manage.py showmigrations Order`）。
- [ ] 前端 `.env.production` 有 `VITE_STRIPE_ENABLED=true`，已重新构建部署。
- [ ] 用一张真实卡下一笔小额订单（例如最便宜的商品），确认：订单 PAID、邮件收到、Webhook 200；然后在 Dashboard 退款，确认退款记录写入订单。
- [ ] 网站有清晰的退货/退款政策、联系方式（Stripe 审核和拒付争议时需要）。
- [ ] 关注第一周的 Dashboard → Payments / Disputes（拒付）。
- [ ] 紧急关闭：服务器 `.env` 设 `STRIPE_ENABLED=false` 并重启后端即可（前端按钮若仍显示，点击会提示 “Card payment is not available”，PayPal 不受影响）；之后再把前端变量关掉重新构建。

---

## 7. 技术参考

| 项目 | 位置 |
|---|---|
| 后端逻辑 | `Order/stripe_checkout.py` |
| 接口 | `POST /api/order/stripe/create_session`、`GET /api/order/stripe/session_status`、`POST /api/order/stripe/webhook` |
| 配置 | `Leoptique/settings.py`（`STRIPE_*`），示例见 `.env.example` |
| 迁移 | `Order/migrations/0028_stripe_checkout.py` |
| 测试 | `Order/test_stripe_checkout.py`（Stripe API 全部 mock） |
| 前端 | ELW：`src/lib/stripeCheckout.ts`、`src/components/Checkout/StripeCheckoutButton.tsx`、`src/pages/StripeReturn.tsx`、`e2e/stripe-checkout.e2e.mjs` |
