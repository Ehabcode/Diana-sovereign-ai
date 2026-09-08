# Diana — المرحلة الثانية: استقرار Electron وWindows

تم تنفيذ تحسينات تشغيلية على النسخة الحالية مع الحفاظ على واجهة ClarityIDE.

## التغييرات

- إضافة `single-instance lock` لمنع تشغيل أكثر من نسخة Diana، وتحويل التركيز للنسخة الموجودة.
- اكتشاف Backend صحي يعمل على نفس المنفذ قبل تشغيل Flask جديد.
- اكتشاف Ollama يعمل مسبقًا قبل تشغيل `ollama serve` مرة أخرى.
- وضع نماذج Ollama وTTS في `userData` عند التشغيل packaged بدل الكتابة داخل resources.
- تحسين Health Check مع timeout ومقاومة JSON غير الصالح والردود المتكررة.
- عرض حالة Ollama في شاشة التحميل بدون منع تشغيل الواجهة إذا كان Ollama غير متاح.
- تحسين تشغيل PowerShell الخارجي مع إرجاع خطأ واضح عند فشل فتحه.
- إضافة logs لفشل spawn، renderer غير المستجيب، وخروج renderer بشكل غير متوقع.
- تحسين إغلاق عمليات Flask وOllama وIntegrated Terminal عند الخروج.
- منع نافذة Terminal من التحكم في جلسة Terminal تابعة لنافذة أخرى.
- إصلاح إعداد Forge الذي كان يفشل لأن `backend` و`models` غير موجودين في النسخة الحالية.

## التحقق

تم اجتياز فحوصات syntax لملفات Electron وpreload وIDE وJavaScript المضمن وPython. تم تشغيل Electron فعليًا في بيئة Linux ووصل إلى `/health` وواجهة `/` بنجاح. تم تنفيذ Forge packaging بنجاح وإنتاج حزمة تطبيق.

رسائل GPU وFATAL shutdown التي تظهر في سجل الاختبار مرتبطة بإنهاء التطبيق بالقوة عبر timeout وبيئة Linux الرسومية، وليست دليلًا على خطأ في مسار بدء Diana. اختبار PowerShell الحقيقي وInstaller Windows النهائي يجب أن يتم على Windows.

> هذه النسخة ما زالت مشروعًا يحتاج Python/Ollama والنماذج الخاصة بالجهاز، وليست Installer مكتمل الاعتماديات أو النماذج.
