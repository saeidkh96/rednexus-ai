> RC1 historical reference. Current RC2 setup: [ECOSYSTEM_SETUP_FA.md](ECOSYSTEM_SETUP_FA.md); current integration evidence: [INTEGRATION_STATUS.md](INTEGRATION_STATUS.md).

# نصب و ارتقای RedNexus

این بسته نسخه‌ی `1.0.0-rc.1` است: پلتفرم اجرایی آماده‌ی آزمایش، با اتصال‌های پنج پروژه در حالت demo. تا وقتی اتصال واقعی پروژه‌ها و تست‌های محیط مقصد تأیید نشده، آن را نسخه‌ی پایدار کامل نمی‌نامیم.

## ۱. انتقال روی پروژه‌ی قبلی

API و worker قبلی را ببند. ZIP جدید را در یک پوشه‌ی جدا استخراج کن. برای حفظ پروژه‌ی قبلی و تهیه‌ی backup از سورس، از داخل پوشه‌ی جدید اجرا کن:

```powershell
.\scripts\UPGRADE.ps1 -Target "C:\Users\saeed\Desktop\rednexus-ai"
```

این اسکریپت از سورس قبلی یک پوشه‌ی backup کنار پروژه می‌سازد و سورس جدید را کپی می‌کند. `.env`، `.venv`، `.git`، `data` و فایل‌های دیتابیس سطح اول را جایگزین نمی‌کند. خود اسکریپت PowerShell در محیط فعلی اجرا نشده؛ روش دستی هم این است که اول پوشه‌ی قبلی را کپی و backup کنی، بعد محتویات سورس جدید را جایگزین کنی و همین موارد را نگه داری.

وارد پروژه‌ی اصلی شو:

```powershell
cd C:\Users\saeed\Desktop\rednexus-ai
```

## ۲. نصب وابستگی‌ها و ساخت دیتابیس

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m rednexus.platform.cli migrate
```

اگر `.venv` سالم داری، دستور اول لازم نیست. اگر با Python دیگری ساخته شده و نصب مشکل دارد، محیط مجازی تازه بساز. این نسخه روی Linux و Python 3.12 آزمایش شده است؛ تأیید قبلی تو برای Windows مربوط به v0.0.1 بود.

دیتابیس جدید به‌صورت پیش‌فرض در `data/nexus-v1.db` است. داده‌های نسخه‌ی قدیمی خودکار وارد آن نمی‌شوند؛ فایل قدیمی حذف نمی‌شود.

## ۳. ساخت حساب اصلی؛ فقط یک‌بار

```powershell
.\.venv\Scripts\python.exe -m rednexus.platform.cli bootstrap --workspace red --username saeid
```

رمز حداقل ۱۲ کاراکتری انتخاب کن. موقع تایپ نمایش داده نمی‌شود. اجرای دوباره‌ی bootstrap رمز قبلی را تغییر نمی‌دهد و اگر workspace موجود باشد خطا می‌دهد؛ این رفتار عمدی است.

## ۴. اجرای Studio و API

ترمینال اول:

```powershell
.\.venv\Scripts\python.exe -m rednexus.platform.cli serve
```

ترمینال دوم، در همان پوشه:

```powershell
.\.venv\Scripts\python.exe -m rednexus.platform.cli worker
```

در مرورگر `http://127.0.0.1:8000` را باز کن. ورود:

- Workspace: `red`
- Username: `saeid`
- Password: رمزی که ساختی

اگر worker اجرا نباشد، mission در وضعیت queued می‌ماند. Refresh صفحه نیاز به ورود دوباره دارد چون token در حافظه‌ی تب نگهداری می‌شود؛ دکمه‌ی Refresh داخل Studio ورود را حفظ می‌کند.

## ۵. اولین مأموریت

New mission را بزن، هدف را بنویس و قابلیت‌ها را انتخاب کن. ترتیب اجرای نسخه‌ی فعلی همان ترتیب فهرست است؛ برای ترتیب سفارشی از API استفاده کن. ابزارهای demo برچسب مشخص دارند و نتیجه‌ی واقعی پروژه‌های قبلی را تولید نمی‌کنند.

اگر RedForge را انتخاب کنی، اجرا برای review متوقف می‌شود. در Workspace team یک کاربر جدا با نقش `reviewer` بساز و این grant را بده:

```text
review:redforge.propose
```

با آن حساب وارد شو، Approvals را باز کن، ورودی مرحله و دلیل تصمیم را بررسی کن و تأیید/رد بده. درخواست‌کننده نمی‌تواند workflow خودش را تأیید کند.

## ۶. تست

```powershell
.\.venv\Scripts\python.exe scripts/validate.py
```

این فرمان lint، تست‌ها، دموی جدید و دموی قدیمی را اجرا می‌کند. تست PostgreSQL و Redis تا وقتی آدرس محیط تست تعیین نشده با وضعیت skipped مشخص می‌شوند.

```powershell
.\.venv\Scripts\python.exe scripts/check_release.py
```

فعلاً `stable_v1_ready: false` و exit code برابر ۲ درست است: اتصال‌های واقعی و تأیید محیط مقصد هنوز تکمیل نشده‌اند.

## ۷. اتصال واقعی پروژه‌ها

فایل `config/projects.json` اتصال‌ها را تعیین می‌کند. برای هر پروژه باید API، قرارداد داده و روش احراز هویت فعلی آن را بررسی کنیم و endpoint مشخص اضافه کنیم. صرفاً عوض‌کردن `demo` به `http` بدون تطبیق قرارداد کافی نیست.

اتصال snapshot/advance به RedWorld v1.4.0 با سورس واقعی تست شده است؛ راهنمای فعال‌سازی آن در `REDWORLD_INTEGRATION.md` است. سورس یا OpenAPI فعلی RedPA، RedPulse، RedGuard و RedForge برای تکمیل اتصال‌های باقی‌مانده لازم است. راهنمای فنی در `ADAPTER_GUIDE.md` است.
