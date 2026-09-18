> نسخه جدید: **1.0.0-rc.2** — برای اتصال پروژه‌های واقعی ابتدا [راهنمای اکوسیستم](docs/ECOSYSTEM_SETUP_FA.md) را اجرا کن. بخش‌های RC1 پایین، راهنمای پایه و سابقه نسخه قبلی‌اند.

# RedNexus AI — شروع نسخه‌ی جدید

نسخه‌ی تحویلی: **1.0.0-rc.1**، پلتفرم اجرایی با Studio، API، حساب کاربری، workflow پایدار و review انسانی.

راهنمای کامل نصب و جایگزینی روی پروژه‌ی قبلی:

[docs/UPGRADE_AND_RUN_FA.md](docs/UPGRADE_AND_RUN_FA.md)

manifest پیش‌فرض demo است. اتصال واقعی snapshot/advance به RedWorld v1.4.0 هم تست شده و با manifest جدا قابل فعال‌سازی است؛ راهنما در `docs/REDWORLD_INTEGRATION.md` قرار دارد. چهار پروژه‌ی دیگر هنوز اتصال واقعی تأییدشده ندارند. وضعیت دقیق هر مرحله‌ی roadmap:

[docs/RELEASE_STATUS.md](docs/RELEASE_STATUS.md)

برای اجرای تست:

```powershell
.\.venv\Scripts\python.exe scripts/validate.py
```

این بسته بدون API key در حالت demo اجرا می‌شود. برای اتصال واقعی، سورس یا OpenAPI فعلی پروژه‌های Red لازم است.
