# Privacy Phase 3 — Diana

## ما تم تنفيذه

- أضيفت واجهتا `storage:encrypt` و`storage:decrypt` في main/preload باستخدام Electron `safeStorage`.
- أصبح Private Chat يستخدم مفتاحًا مشفرًا مستقلًا عن Public History.
- أصبح Private Code وPrivate File Memory يستخدمان مفاتيح مشفرة مستقلة.
- السجلات العامة تظل في مفاتيحها العادية ولا تختلط بالمحتوى الخاص.
- السجلات القديمة غير المشفرة يتم قراءتها مرة واحدة ثم نقلها إلى المفاتيح المشفرة عند أول حفظ إذا كانت حماية النظام متاحة.
- عند تشغيل Browser Preview أو نظام لا يدعم safeStorage، يوجد fallback legacy واضح بدل فقدان البيانات.
- حذف Private Memory وZAP يزيل المفاتيح الخاصة المشفرة والقديمة.

## حدود الحماية

التشفير يعتمد على حماية نظام التشغيل وحساب Windows الحالي، وليس على الكود وحده. المستخدم الذي يملك وصولًا كاملًا إلى حساب Windows أو جلسة Diana المفتوحة قد يستطيع الوصول للبيانات. هذا ليس بديلًا عن BitLocker أو حماية حساب Windows.

## التحقق

- `main.cjs` و`preload.cjs` وinline renderer JavaScript اجتازت syntax check.
- تم فصل مفاتيح Public/Private في Chat وCode وFile.
- لم يتم حذف مفاتيح legacy قبل التأكد من نجاح التشفير.
- يلزم اختبار Windows إضافي للتأكد من `safeStorage.isEncryptionAvailable()` في بيئة المستخدم.
