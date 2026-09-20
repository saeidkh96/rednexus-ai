# نصب RedNexus 2.0.0 RC2

این بسته امکانات مرحله‌های ۱ تا ۸ را جمع می‌کند، ولی **نسخه stable تأییدشده نیست**.
تست Windows، مرورگر، سرویس‌های زیرساخت و مدل‌های واقعی باید در محیط مقصد یا CI پاس شوند.
اثر خرابی موتور روی اقتصاد RedWorld در این بسته پیاده‌سازی نشده؛ برای آن تغییر خود مدل RedWorld لازم است.

## نصب بدون از دست دادن تنظیمات

۱. همه API و Workerهای RedNexus را با Ctrl+C ببند. سرویس‌های پروژه‌های دیگر را لازم نیست متوقف کنی.
۲. ZIP را **در پوشه جدا** باز کن، نه مستقیم روی پروژه. از پروژه و دیتابیس بکاپ بگیر.
۳. داخل پوشه rednexus-ai استخراج‌شده PowerShell باز کن:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\UPGRADE.ps1 -Target 'C:\Users\saeed\Desktop\rednexus-ai'
```

اسکریپت config، data، .env، .venv و .git مقصد را نگه می‌دارد و از کد و SQLite پیش‌فرض بکاپ می‌گیرد.
اگر NEXUS_DATABASE_URL سفارشی یا PostgreSQL داری، **قبل از ارتقا از همان پایگاه بکاپ بگیر**؛ بکاپ خودکار فقط SQLite پیش‌فرض است.
تنظیمات فعلی که اجرای fc0bd205 با آن موفق بود حفظ می‌شوند؛ نیازی به bootstrap دوباره یا ساخت کاربر تکراری نیست.

۴. داخل پروژه اصلی:

```powershell
cd C:\Users\saeed\Desktop\rednexus-ai
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe scripts\acceptance.py
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\ECOSYSTEM.ps1 -Action preflight
.\ECOSYSTEM.ps1 -Action serve
```

۵. در PowerShell جدا داخل همان پوشه:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\ECOSYSTEM.ps1 -Action worker
```

آدرس نمایش‌داده‌شده توسط API را باز کن؛ معمولاً http://127.0.0.1:8000 است.
Ctrl+F5 بزن و دوباره وارد حساب شو تا فایل‌های رابط جدید بارگذاری شوند.

## اکنون بدون کپی JSON

- **New mission** → انتخاب Recipe → **Create draft** → **Validate** → **Queue mission**.
- برای تست بدون تغییر جهان، **Low risk → conditional skip check** را انتخاب کن.
- داده‌های نمونه با API واقعی پردازش می‌شوند؛ بررسی کن ریسک واقعاً زیر آستانه باشد و مرحله دوم skipped شود.
- ریسک بالا: منتظر reviewer جدا با `review:redworld.advance` بمان.
- اپراتور باید `tool:redpulse.analyze` و `tool:redworld.advance` داشته باشد.
- در **Workspace team → Edit existing access** مجوز کاربر موجود را ویرایش کن؛ مجوزهای دیگر را ناخواسته حذف نکن.
- تغییر مجوز خودت توسط همان حساب مجاز نیست؛ از مدیر دیگری استفاده کن.
- در جزئیات اجرا **Download execution evidence** خروجی، رویدادها و پلان را دانلود می‌کند.

## انتقال معنایی به RedPA

قالب **RedPulse result → reviewed RedPA chat** خروجی کامل مرحله اول را به متن پیام مرحله دوم وصل می‌کند.
UUID یک conversation موجود در RedPA لازم است؛ UUID ساختگی یا شناسه Nexus را وارد نکن.
بهتر است conversation اختصاصی قبلاً دستور تحلیل نگهداری داشته باشد.
کلید حساب RedPA باید مثل قبل خارج از مخزن تنظیم باشد. اتصال مدل RedPA هم باید آماده باشد.
مجوزها: اپراتور `tool:redpulse.analyze` و `tool:redpa.chat`؛ reviewer جدا `review:redpa.chat`.
قبل از تأیید، متن واقعی پیام را بررسی کن؛ این مرحله پیام را در RedPA ثبت می‌کند.

## تیم ایجنت و حافظه

در Agents پروفایل‌های محدود به قابلیت بساز. در Agent teams اهداف را وارد کن و Propose assignments بزن.
پیشنهاد خودکار اجرا نمی‌شود؛ ورودی‌ها و بودجه را بررسی کن و Queue group بزن.
پروفایل ordered برای قابلیت native ورودی را حدس نمی‌زند؛ از workflow صریح یا model planner پیکربندی‌شده استفاده کن.
Check progress وضعیت تیم ثبت‌شده را نشان می‌دهد.
حافظه namespace و مجوز مستقل دارد. Semantic memory برای embedding واقعی به provider پیکربندی‌شده نیاز دارد.

## تست و بازگشت

`artifacts/acceptance/report.json` و فایل‌های log نتیجه واقعی اجرای تست محلی را نشان می‌دهند.
Skipped به معنی پاس نیست. برای مرورگر:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-browser.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe scripts\acceptance.py --browser
```

برای rollback: API و worker را ببند، کد قبلی و بکاپ دیتابیس متناظر را برگردان.
برگرداندن Nexus اثرهای قبلی در RedWorld یا پیام‌های RedPA را برنمی‌گرداند.
گزارش کامل محدوده و گیت‌ها: ROADMAP_1_TO_8.md و RC2_VALIDATION.md.
