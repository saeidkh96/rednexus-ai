# اتصال پروژه‌های واقعی — RedNexus 1.0.0-rc.2

این بسته سورس کامل Nexus است. repoهای پنج پروژه مستقل می‌مانند و در ZIP Nexus کپی نشده‌اند. فایل `config/projects-ecosystem.json` اتصال HTTP واقعی را فعال می‌کند؛ `config/projects.json` همچنان دمو است. اجرای START.ps1 معمولی به‌تنهایی اتصال واقعی را فعال نمی‌کند.

## ۱. ارتقا

API و worker قبلی را متوقف کن. ZIP را در یک پوشه جدا استخراج کن و از داخل پوشه جدید `rednexus-ai` اجرا کن:

```powershell
.\scripts\UPGRADE.ps1 -Target 'C:\Users\saeed\Desktop\rednexus-ai'
cd C:\Users\saeed\Desktop\rednexus-ai
.\SETUP.ps1
```

اسکریپت از کد قبلی نسخه پشتیبان می‌گیرد؛ دیتابیس، `.env` و محیط نصب قبلی را جایگزین نمی‌کند. تنظیمات سفارشی manifest را پس از ارتقا دوباره اعمال کن. workflowهای نیمه‌تمام قبلی ممکن است به دلیل تغییر قرارداد متوقف شوند؛ workflow تازه بساز.

## ۲. اجرای پروژه‌ها

هر backend باید در محیط Python و با وابستگی‌های خودش اجرا شود. backendها فقط روی `127.0.0.1` گوش دهند؛ برخی از آن‌ها احراز هویت داخلی ندارند. frontendهای پروژه‌ها برای اتصال Nexus لازم نیستند.

| پروژه | پورت پیشنهادی | فرمان uvicorn در محیط همان پروژه | مسیر اجرای فرمان |
|---|---:|---|---|
| RedPA | 8111 | `python -m uvicorn app.main:app --host 127.0.0.1 --port 8111` | `redpa-ai/backend` |
| RedGuard | 8112 | `python -m uvicorn redguard.api.app:app --host 127.0.0.1 --port 8112` | ریشه پروژه، پس از نصب package |
| RedPulse | 8113 | `python -m uvicorn app.main:app --host 127.0.0.1 --port 8113` | `redpulse-ai/backend` |
| RedForge | 8114 | `python -m uvicorn redforge.main:app --host 127.0.0.1 --port 8114` | ریشه پروژه، پس از نصب package |
| RedWorld | 8100 | `python -m uvicorn redworld.api.main:app --host 127.0.0.1 --port 8100` | ریشه پروژه، پس از نصب package |

این فرمان‌ها جایگزین نصب و migration پروژه‌ها نیستند. RedPA و RedPulse پیش‌نیازهای سرویس و دیتابیس خودشان را دارند؛ راهنمای همان repo را اجرا کن. RedForge به Python **3.14 یا بالاتر** نیاز دارد. Nexus محیط Python مستقل خودش را نگه می‌دارد.

در ترمینال RedForge، قبل از اجرای backend، محدوده دسترسی را تعیین کن:

```powershell
$env:REDFORGE_WORKSPACE_ROOT = 'C:\Users\saeed\Desktop\redforge-ai'
```

مقدار `resource_binding` مربوط به `redforge.scan` در `config/projects-ecosystem.json` نیز باید همین مسیر را داشته باشد. این مسیر روی دستگاه backend تفسیر می‌شود. کاربر workflow نمی‌تواند با JSON مسیر دیگری برای scan انتخاب کند. لینک‌های فایل به بیرون از محدوده را در مخزن مورد اسکن قرار نده؛ اجرای مسیر scan به معنای اجرای کد مخزن نیست.

## ۳. RedPA

با یک حساب اختصاصی در RedPA وارد شو. توکن دسترسی همان حساب را در محیط worker Nexus قرار بده:

```powershell
$env:NEXUS_REDPA_TOKEN = '<access token from your RedPA login>'
```

توکن را در فایل پروژه یا manifest ننویس. این توکن ممکن است منقضی شود؛ پس از جایگزینی، worker را با محیط تازه اجرا کن. برای `redpa.chat` ابتدا در RedPA یک conversation متعلق به همین حساب بساز و شناسه واقعی آن را در ورودی قرار بده. اتصال از تنظیمات مدل و RAG خود RedPA استفاده می‌کند؛ کیفیت یا فعال بودن بازیابی اسناد را Nexus تضمین نمی‌کند.

این اتصال نماینده یک **حساب سرویس مشترک در workspace red** است؛ هویت تک‌تک کاربران Nexus به حساب مستقل RedPA تبدیل نمی‌شود. دسترسی به این ابزارها را فقط به کاربران مجاز آن حساب بده.

## ۴. دسترسی‌های Nexus

برای دیتابیس جدید فقط یک بار:

```powershell
.\ECOSYSTEM.ps1 -Action bootstrap
```

اگر حساب `saeid` و workspace `red` قبلاً ساخته شده‌اند، bootstrap را تکرار نکن. دسترسی قابلیت‌های جدید را به همان مدیر اضافه کن:

```powershell
.\ECOSYSTEM.ps1 -Action sync-admin-grants
```

این فرمان محلی فقط مدیر فعال موجود را می‌پذیرد و افزودن دسترسی‌ها را در audit ثبت می‌کند. رمز یا نقش را عوض نمی‌کند. اگر نام مدیر متفاوت است، نام آن را در ECOSYSTEM.ps1 تنظیم کن.

## ۵. اجرای Nexus

ترمینال اول در پوشه Nexus:

```powershell
.\ECOSYSTEM.ps1 -Action serve
```

ترمینال دوم در همان پوشه، پس از تنظیم توکن RedPA:

```powershell
.\ECOSYSTEM.ps1 -Action worker
```

Studio: `http://127.0.0.1:8000`. هر دو فرآیند باید manifest یکسان داشته باشند. این wrapper متغیرهای لازم را تنظیم می‌کند؛ فایل `.env` به‌صورت خودکار توسط Nexus خوانده نمی‌شود.

## ۶. اولین مأموریت

در New mission ابتدا فقط `redpulse.analyze` را انتخاب کن. JSON نمونه همان قابلیت را از `config/ecosystem-inputs.json` در کادر ورودی آن کپی کن. سپس `redforge.scan` و `redworld.snapshot` را جداگانه امتحان کن؛ ورودی آن‌ها `{}` است.

هر مرحله ورودی مستقل خودش را دارد. خروجی Pulse خودکار به امتیازهای Guard تبدیل نمی‌شود؛ چنین تبدیل معنایی هنوز تعریف نشده است. API عمومی workflow و eventها موجود است، ولی پروژه‌های دیگر بدون نصب producer رویداد، خودکار رویدادی برای Nexus نمی‌فرستند.

برای `redguard.inspect`، `redpa.chat` و `redworld.advance` یک reviewer مستقل در Team بساز و به او دسترسی‌های مورد نیاز بده:

```text
review:redguard.inspect
review:redpa.chat
review:redworld.advance
```

با حساب reviewer وارد شو و ورودی دقیق را تأیید کن. درخواست‌کننده نمی‌تواند کار خودش را تأیید کند. RedGuard امتیازهای تحلیل تصویر را می‌گیرد و نتیجه بازرسی را ذخیره می‌کند؛ آپلود عکس در این اتصال پیاده نشده است. RedForge فقط موجودی مخزن را می‌خواند؛ patch، اجرای تست و انتشار PR فعال نیست.

## محدودیت‌های قابل مشاهده

- `redforge.scan` تعداد کل فایل‌ها و پیش‌نمایش حداکثر ۵۰ فایل را برمی‌گرداند؛ `files_preview_truncated` ناقص بودن پیش‌نمایش را نشان می‌دهد. پاسخ backend حداکثر ۱ MiB دریافت می‌شود؛ مخزن بزرگ‌تر ممکن است رد شود.
- پاسخ سایر اتصال‌ها حداکثر ۶۴ KiB است. فهرست بسیار بزرگ اسناد یا گفت‌وگوی طولانی ممکن است رد شود.
- backendهای بدون احراز هویت باید خصوصی و مختص همین workspace باشند. هدرهای Nexus به‌تنهایی احراز هویت backend محسوب نمی‌شوند.
- در قطع ارتباط عملیات نوشتن، وضعیت ممکن است `needs_reconciliation` شود؛ قبل از اجرای مجدد، نتیجه را در پروژه مبدأ بررسی کن.
- تست ویندوز، مرورگر، PostgreSQL/Redis و RedPA با سرویس‌های واقعی هنوز انجام نشده؛ بنابراین نام نسخه **rc.2** است، نه نسخه پایدار نهایی.
