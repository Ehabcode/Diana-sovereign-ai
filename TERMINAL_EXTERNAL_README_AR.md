# TERMINAL خارجي

خيار `TERMINAL` في الشريط الجانبي يفتح نافذة PowerShell الحقيقية على Windows بدل فتح Terminal داخل Diana.

عند الضغط على:

```text
Sidebar → TERMINAL
```

يتم تشغيل:

```powershell
diana
```

في PowerShell جديد مع إبقائه مفتوحًا. يجب أن يكون أمر `diana` متاحًا في Windows PATH أو موجودًا كملف `diana.cmd` داخل أحد مجلدات PATH.

إذا ظهر الخطأ `diana is not recognized`، فهذا يعني أن PowerShell فُتح بنجاح لكن أمر Diana غير مضاف إلى PATH. أغلق النسخة القديمة من الاختصار، أضف ملف `diana.cmd` إلى مجلد مثل `$HOME\bin`، ثم أضف المجلد إلى User PATH وافتح PowerShell جديدًا.

المعاينة المباشرة لملفات HTML لا تستطيع فتح PowerShell؛ التشغيل الخارجي يعمل من تطبيق Electron بعد `npm start` فقط.
