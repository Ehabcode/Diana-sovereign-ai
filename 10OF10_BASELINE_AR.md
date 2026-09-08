# Diana 10/10 — خط الأساس

## النسخة

- الإصدار الحالي: `2.5.4-beta`
- المنصة المستهدفة: Windows Electron
- الواجهة: ClarityIDE recovered baseline
- التشغيل: Electron Forge + Flask على localhost + Ollama محلي

## Backup

تم إنشاء Backup مستقل قبل بداية خطة 10/10:

`/home/ubuntu/Diana_BACKUP_BEFORE_10OF10_20260827_203042.zip`

تم التحقق من سلامة الأرشيف باستخدام `unzip -t`.

## نقاط القبول

1. تشغيل Diana من `npm start` ومن Installer بدون Crash.
2. عدم تشغيل أكثر من نسخة من Diana أو Backend.
3. فتح IDE مرة واحدة وإعادة التركيز عند تكرار الضغط.
4. فتح PowerShell حقيقي من TERMINAL وتشغيل `diana`.
5. عمل DELETE وCLEAR مع وجود بيانات وبدون وجود بيانات.
6. عدم تسريب Private Chat إلى Public History.
7. طلب موافقة قبل إنشاء ملف أو مجلد، ومنع المسارات غير المصرح بها.
8. عمل Health Check بحالات مفهومة عند غياب Ollama أو Python.
9. إلغاء/timeout للطلبات الطويلة وعدم ترك عمليات معلقة عند الإغلاق.
10. نجاح `npm ci` و`npm run package` و`npm run make` على Windows.

## القيود المعروفة قبل المرحلة

- PowerShell لم يثبت بعد بشكل نهائي في Installer عند المستخدم.
- Private Chat مفصول عن العام لكنه غير مشفر حتى الآن.
- البيئة الحالية لا تستطيع إثبات فتح نافذة Windows GUI من داخل Linux.
- Installer لا يضم تلقائيًا Python environment أو Ollama model weights.

لا يتم اعتبار الإصدار 10/10 قبل اجتياز اختبارات Windows النهائية وإغلاق هذه القيود أو توثيقها بوضوح.
