# Diana — حالة خطة 10/10

## المنفذ في هذه النسخة

تم تثبيت دورة تشغيل Electron الأساسية، ومنع تشغيل أكثر من نسخة، واكتشاف Backend وOllama الموجودين قبل تشغيل نسخ إضافية، وتحسين Health Check، وتنظيف العمليات عند الإغلاق، وإظهار أخطاء renderer وPowerShell بوضوح.

تم إصلاح زر DELETE الخاص بـ Pass Key Profiles. أصبح يعمل مع أكثر من Profile، ومع Profile واحد يقوم بمسح بياناته وإعادته إلى Profile فارغ بعد تأكيد المستخدم بدل أن يكون disabled.

تم تحسين حذف Chat/Code/File History بإضافة تأكيد، ومنع عمليات التنظيف العامة من حذف العناصر الخاصة. كما تم فصل Chat History الخاص عن مفتاح التخزين العام ونقل السجلات القديمة تلقائيًا إلى مفتاح خاص منفصل عند بدء التطبيق.

تم تحسين التحكم في مسارات الملفات، وإضافة موافقة قبل الوصول إلى العناصر المسحوبة، وموافقة قبل إنشاء ملف أو مجلد، ومنع المسارات خارج المجلدات المعتمدة وsymlink escape.

تم رفع الإصدار إلى `2.5.1-beta` وإصلاح إعداد Forge حتى ينجح packaging مع الموارد الموجودة فعليًا.

## ما يحتاج اختبار Windows

يجب بناء Installer من النسخة الحالية باستخدام `npm ci` ثم `npm run make`، وتثبيته في مكان منفصل. بعد ذلك يجب اختبار فتح Diana، تشغيل Ollama، اختيار Folder، سحب File، زر DELETE، وزر TERMINAL.

اختبار TERMINAL الناجح يعني ظهور PowerShell حقيقي وتنفيذ `diana`. إذا ظهر `diana is not recognized` فهذه مشكلة PATH في Windows وليست مشكلة فتح PowerShell.

## الحدود الصادقة

Private storage منفصل عن public storage لكنه ما زال localStorage وغير مشفر. لذلك لا يجب وصفه بأنه حماية تشفيرية كاملة قبل تنفيذ تشفير محلي حقيقي باستخدام Windows Credential Protection أو Electron safeStorage.

كما أن المشروع الحالي ليس Installer Offline مكتملًا بكل Python environment وPyTorch وOllama models وFFmpeg. هذه الموارد تعتمد على إعداد الجهاز إلا إذا تم تجهيزها وتضمينها في إصدار نشر مستقل.
