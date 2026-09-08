# Diana Liquid Glass Rework RC4

## نطاق التعديل

تم تنفيذ إعادة تصميم بصرية واسعة فوق النسخة المستقرة، مع الحفاظ على DOM والمنطق الحاليين قدر الإمكان. أصبح Liquid Glass هو اللغة الموحدة: بنفسجي داكن شفاف، حدود Orchid خفيفة، فضي للحالات، وطمس على الأسطح فقط وليس على Monaco أو النصوص.

## Home والشات والـ levers

تم توسيع مساحة الشات على سطح المكتب إلى تخطيط أعرض، مع إبقاء عمود levers مستقلًا حتى لا تبدو controls مدفوسة داخل الشات. أزيلت pseudo-rings والهالات القديمة حول levers، وأصبحت Persona وVoice داخل controls صغيرة نظيفة بخلفية شفافة وhandle فضي.

على الشاشات الصغيرة يتحول العمود إلى صف مستقل فوق الشات، ويأخذ الشات عرض الشاشة بدل القص الأفقي.

## Hide Slide

تم استبدال إحساس CRT القديم بـ dock زجاجي شفاف. أضيفت بطاقات موحدة للـ Chat History وCode History وVRAM وPass Key وAgents وIDE وTERMINAL وInfo، مع hover بنفسجي هادئ، active state فضي، وأيقونات grayscale. تمت إعادة رسم الأزرار، meters، summaries، cards، typography، والـ status states داخل panels.

## IDE

تم تنفيذ Liquid Glass rework للـ topbar وExplorer وeditor panel وtabs وDiana Chat وterminal drawer وcommand palette وopen files وsettings. الأزرار والحالات أصبحت بنفسجية/فضية، ومساحة Monaco بقيت داكنة واضحة مع منع backdrop blur على سطح الكود.

ميزة Terminal بقيت محفوظة ومؤجلة كما طلب المستخدم؛ لم يتم الادعاء بإصلاح تشغيل PowerShell.

## الاختبارات

نجح static layout test، ونجحت فحوص inline JavaScript وElectron main/preload وIDE renderer وPython syntax. نجح `npm run package`، كما نجح اختبار ZIP integrity.

بقيت بعض declarations الخضراء القديمة داخل ملفات CSS المتراكمة، لكن طبقات override النهائية تغطي العناصر المرئية ذات الصلة وتحوّلها إلى silver/gray أو violet. لم يتم حذفها wholesale لتقليل خطر regression.

## حدود النسخة

الأرشيف Source ZIP وليس Installer Windows نهائيًا. يجب فكّه في مجلد مستقل ثم تشغيل `npm ci` و`npm run make` على Windows. لا يحتوي الأرشيف على Python virtual environment أو Ollama model weights أو PyTorch/TTS/FFmpeg كاملة.
