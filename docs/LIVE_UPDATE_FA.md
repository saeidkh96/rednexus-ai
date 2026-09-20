# آپدیت اتصال واقعی — ۲۰ سپتامبر ۲۰۲۶

این بسته تکمیل تمام roadmap یا release نهایی نیست. اتصال‌های HTTP موجود را یکسان می‌کند،
preflight و workflow شرطی اضافه می‌کند. تست با سرویس‌های واقعی لپ‌تاپ هنوز لازم است.

## نصب
server و worker را در پنجره‌های خودشان با Ctrl+C متوقف کن. از پروژه نسخه‌ی پشتیبان بگیر.
محتویات پوشه‌ی rednexus-ai داخل ZIP را روی پوشه‌ی پروژه کپی و فایل‌های هم‌نام را جایگزین کن.
بسته حاوی data، .env، .venv و credentials نیست؛ فایل‌های محلی را حذف نکن.
اصلاحات قبلی worker lock و CLI timeout حفظ شده‌اند. نسخه همچنان RC1 است.

## سرویس‌ها
RedPulse باید روی 8002، RedWorld v2 روی 8100، RedPA روی 8111، RedGuard روی 8112 و RedForge روی 8114 باشند.
برای RedPulse در پوشه‌ی backend و با Python محیط خود RedPulse:

```powershell
$env:REDIS_URL = 'redis://localhost:6380/0'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8002
```

راه‌اندازی RedWorld را با دستور فعلی خود پروژه انجام بده؛ snapshot باید نسخه‌ی 2.0.0 برگرداند.
تنظیمات پیش‌فرض این بسته برای workspace به نام red است.

## اجرا
داخل rednexus-ai:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\ECOSYSTEM.ps1 -Action preflight
```

ready=true فقط سلامت قابل‌دسترسی RedPulse و RedWorld را تأیید می‌کند؛ تست workflow نیست.
در دو پنجره‌ی جدا از همین پوشه (در هر پنجره policy بالا را در صورت نیاز تنظیم کن):

```powershell
.\START.ps1
```

```powershell
.\WORKER.ps1
```

هر دو اکنون config/projects-ecosystem.json را می‌خوانند. از اجرای مستقیم CLI با تنظیمات پیش‌فرض دمو استفاده نکن.
اگر NEXUS_DATABASE_URL یا NEXUS_ALLOWED_ORIGINS را قبلاً تنظیم کرده‌ای، مقادیر هر دو پنجره باید یکی باشد.
خطای allowlist را با آدرس دقیق سرویس رفع کن؛ guard را غیرفعال نکن.

## workflow
متن examples/live-maintenance.json را در Workflow builder وارد کن.
مالک باید role=operator یا admin و هر دو grant زیر را داشته باشد:

```
tool:redpulse.analyze
tool:redworld.advance
```

reviewer جدا باید role=reviewer و grant زیر را داشته باشد:

```
review:redworld.advance
```

از مدیریت دسترسی حساب موجود استفاده کن؛ لازم نیست برای هر grant حساب جدید بسازی.
Validate و Queue را بزن. ریسک کمتر از 0.5 مرحله دوم را skip می‌کند؛
ریسک بالاتر یا مساوی 0.5 درخواست تأیید انسانی می‌دهد. قبل از تأیید payload را بررسی کن.
پس از تأیید، یک tick واقعی به جهان اضافه می‌شود. خروجی previous در evidence/context حفظ می‌شود.
این شرط سیاست آزمایشی است، نه مدل علمی نگاشت خرابی موتور به اقتصاد جهان.
API فعلی RedWorld فقط steps می‌گیرد؛ context ریسک وارد مدل داخلی جهان نمی‌شود و
applied_to_world_model=false صریحاً همین محدودیت را ثبت می‌کند.

معیار موفقیت: مرحله اول نتیجه‌ی API واقعی و مرحله دوم approval، advanced_steps=1 و tick معتبر داشته باشد.
اجرای simulated=true دمو است و اتصال واقعی محسوب نمی‌شود. mission قدیمی blocked را دستکاری نکن.
در needs_reconciliation عملیات نوشتنی را خودکار تکرار نکن؛ نتیجه‌ی upstream را بررسی کن.

## بررسی و ادامه
```powershell
python -m pytest -q
git diff --stat
```

این ZIP دیتابیس، حساب‌ها، grantها یا تاریخچه‌ی mission را تغییر نمی‌دهد.
تأیید CI ویندوز، تست زنده لپ‌تاپ، رفع چت ناقص RedPA و تکمیل release gates هنوز باقی است.
