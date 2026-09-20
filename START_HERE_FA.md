# شروع نسخه 2.0.0 RC1

این ZIP سورس کامل RedNexus با قابلیت‌های جدید است؛ repoهای پنج پروژه مستقل
می‌مانند. این بسته هنوز انتشار پایدار تأییدشده نیست؛ گزارش تست داخل docs است.

## ارتقای پروژه فعلی

1. مأموریت در حال اجرا را تمام کن؛ موارد منتظر تأیید را تمام یا لغو کن.
2. server و workerهای قدیمی را با Ctrl+C ببند. دیتابیس را حذف نکن.
3. ZIP را در پوشه جدا استخراج کن، نه مستقیم روی پروژه.
4. PowerShell را در پوشه استخراج‌شده حاوی README باز کن:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\UPGRADE.ps1 -Target "C:\Users\saeed\Desktop\rednexus-ai"
cd C:\Users\saeed\Desktop\rednexus-ai
.\SETUP.ps1
.\ECOSYSTEM.ps1 -Action doctor
```

اسکریپت از سورس قبلی و دیتابیس SQLite پیش‌فرض backup می‌گیرد. config، data،
.git، .env و محیط Python حفظ می‌شوند. از دیتابیس سفارشی/PostgreSQL جدا backup بگیر.
حساب saeid و reviewer باقی می‌مانند؛ **bootstrap را دوباره اجرا نکن**.
workflowهای pending قبلی ممکن است به‌علت fingerprint جدید block شوند؛ بعد از
بررسی، مأموریت جدید بساز. عملیات نامطمئن را خودکار تکرار نکن.

## روشن‌کردن روزمره

سرویس‌های پروژه‌ها را طبق روال خودشان روشن کن، سپس:

```powershell
.\START_ECOSYSTEM.cmd
```

API و یک worker با ظرفیت دو مأموریت هم‌زمان شروع می‌شوند و وضعیت چاپ می‌کنند.
پنجره را باز نگه دار. Ctrl+C هر دو را متوقف می‌کند؛ قطع عملیات اثرگذارِ در حال
اجرا ممکن است نیاز به reconciliation داشته باشد. نسخه قدیمی را هم‌زمان روشن نگذار.

- Nexus: `http://127.0.0.1:8000`
- RedPA backend: `http://127.0.0.1:8111`
- RedPA frontend: `http://127.0.0.1:3001`

## توکن بدون قرارگرفتن رمز در repo

در PowerShell جدا داخل پروژه:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\ECOSYSTEM.ps1 -Action redpa-login -Username saeed@example.com
```

رمز در prompt مخفی وارد می‌شود. توکن خارج repo در پوشه کاربر و با DPAPI ویندوز
ذخیره می‌شود. worker در فراخوانی بعدی آن را می‌خواند. اگر متغیر محیطی قدیمی داری،
آن را در پنجره شروع worker پاک کن؛ اولویت با متغیر محیطی است:

```powershell
Remove-Item Env:NEXUS_REDPA_TOKEN -ErrorAction SilentlyContinue
```

پس از انقضای توکن، login را تکرار کن؛ password دیتابیس را تغییر نده. اگر توکن آماده
داری از `ECOSYSTEM.ps1 -Action credential-set` استفاده کن.

## تست روی سیستم تو

1. `redpa.documents` با `{}`؛ آرایه خالی هم نتیجه معتبر است.
2. `redpa.chat` با conversation_id واقعی و content؛ سپس تأیید reviewer مستقل.
3. Workflow builder: دو مرحله با binding. نمونه `examples/v2-bindings.json`
   فقط برای manifest دمو است.
4. Templates: ذخیره/اجرای نسخه؛ Agent teams: دو assignment با بودجه مشخص.
5. Operations: worker و خطاها؛ Semantic memory: پس از تنظیم embedding provider.

README و `docs/V2_IMPLEMENTATION.md` جزئیات و محدودیت‌ها را دارند. اجرای ویندوز،
مرورگر، مدل زنده و PostgreSQL/Redis باید در محیط مقصد تأیید شوند.
# آپدیت اجرای واقعی

برای نصب این بسته و اجرای workflow شرطی RedPulse → RedWorld، ابتدا
`docs/LIVE_UPDATE_FA.md` را بخوانید. این بسته همچنان integration preview است.
