# Diana Project — Manifest

## الحالة

تم إنشاء مشروع موحد من الملفات المرفقة، مع فصل التشغيل عن الملفات القديمة. النسخة المعتمدة للتشغيل هي `app/main.cjs` و`app/preload.cjs` و`python/server.py` و`renderer/`.

## الإصلاحات المنفذة

| المجال | الإصلاح |
|---|---|
| Electron | تحديث `package.json` ليستخدم `app/main.cjs` من جذر المشروع |
| المسارات | جعل resource root يشير إلى جذر Diana Project بعد فصل app |
| الصوت | جعل استيراد PyTorch وTTS وsoundfile اختياريًا وتحميل XTTS-v2 عند أول طلب فقط |
| الجهاز | اختيار CUDA تلقائيًا عند توفرها والعودة إلى CPU عند غيابها |
| الذاكرة | توحيد ملفات الذاكرة في `memory/` والسجلات في `logs/` |
| terminal | نقل agent القديم إلى `terminal/` وربطه بجذر المشروع |
| الأوفلاين | الاحتفاظ بـ Monaco وxterm داخل `vendor/` وإزالة CDN من الواجهة |
| Ollama | الاحتفاظ بـ Modelfile وscripts داخل `ollama/` |
| البيئة الافتراضية | حفظ snapshot مرجعي فقط داخل `legacy/venv_snapshot/` وعدم اعتباره بيئة قابلة للنقل |

## الاختبارات الناجحة

تم اجتياز فحص Python syntax لجميع الملفات التشغيلية، وفحص JavaScript لـ Electron وpreload وIDE renderer، وفحص JSON لـ `package.json` و`package-lock.json`، وفحص استيراد الخادم مع lazy TTS، واختبارات terminal للسلامة وتنفيذ الأوامر والخصائص.

## ما يحتاج جهاز Windows فعليًا

يجب تنفيذ `npm install` وتهيئة `.venv` على Windows. ويجب تثبيت PyTorch/Torchaudio المناسبين للجهاز، ثم تنزيل XTTS-v2 مرة واحدة وترك Ollama مع النموذجين المحليين. لا يمكن اختبار CUDA أو PyTorch Windows من بيئة Linux الحالية.

## مصادر قديمة محفوظة

تم الاحتفاظ بالأرشيفات الأصلية والـ virtualenv snapshot تحت `legacy/archives/` و`legacy/venv_snapshot/` للرجوع إليها فقط، وليست ضمن مسار التشغيل.
