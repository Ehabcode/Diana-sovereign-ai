# Diana 10/10 — Release Candidate

## المنفذ في هذه التجميعة

تضم التجميعة تحسينات دورة حياة Electron وFlask وHealth Check وOllama، منع النسخ المكررة، تشغيل `.venv` تلقائيًا عند وجودها، وحماية مسارات IPC. كما تضم إصلاحات DELETE وCLEAR والتأكيدات والـ overlays، وفصل Public History عن Private History.

تستخدم Private Chat وPrivate Code وPrivate File Memory تشفير Electron `safeStorage` عند توفر حماية نظام التشغيل، مع migration للبيانات القديمة وfallback واضح للمتصفح أو الأنظمة التي لا توفر مخزن مفاتيح.

أضيف timeout للردود الطويلة وإلغاء آمن للطلبات وfallback للنماذج المحلية. أزرار الذاكرة الفارغة تظهر الآن كـ disabled بدل أن تبدو غير مستجيبة.

## قرار TERMINAL

لم تُحذف ميزة TERMINAL بناءً على قرار المستخدم. تم إبقاء كودها وملفاتها كما هي وتأجيل إصلاح PowerShell. لذلك لا يُعتبر TERMINAL ضمن الوظائف المغلقة في تقييم هذا الإصدار.

## ما يجب اختباره على Windows

يجب بناء Installer من المصدر، تثبيته في بيئة منفصلة، ثم اختبار DELETE وCLEAR مع بيانات فعلية، Private History، تشغيل Ollama، الإغلاق، وإعادة فتح التطبيق. يجب اختبار TERMINAL بشكل منفصل أو تركه مؤجلًا.

## حدود صريحة

التشفير مرتبط بحساب ونظام التشغيل الحالي وليس بديلًا عن حماية حساب Windows أو BitLocker. الـ Installer لا يضم تلقائيًا Python virtual environment أو أوزان Ollama أو PyTorch وFFmpeg. الإصدار الحالي Release Candidate وليس ضمانًا أن كل الحالات وصلت 10/10 قبل اختبار Windows النهائي.
