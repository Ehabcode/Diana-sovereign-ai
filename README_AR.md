# Diana Project

هذا هو المشروع الموحد بعد إعادة الهيكلة. تم فصل تطبيق سطح المكتب، خادم Diana، terminal agent، الواجهة، المكتبات المحلية، النماذج، الاختبارات، والملفات القديمة.

## الهيكل

```text
DianaProject/
├─ app/                 Electron main.cjs و preload.cjs
├─ renderer/            واجهة Diana وواجهة IDE
├─ python/              Flask + Ollama + XTTS-v2
├─ terminal/            Diana Coding terminal agent وأدوات ADB/USB
├─ vendor/              Monaco وxterm محليان بدون CDN
├─ ollama/              Modelfile وملفات إنشاء النماذج
├─ memory/              ملفات الذاكرة المحلية
├─ assets/audio/        عينات ونتائج الصوت
├─ tests/               اختبارات وفحوصات المشروع
├─ models/              ضع cache الخاص بـ XTTS-v2 هنا
├─ wheels/              ضع Python wheels هنا للتثبيت الأوفلاين
├─ legacy/              ملفات قديمة أو مرجعية غير مستخدمة في التشغيل
└─ package.json         إعداد Electron Forge
```

## التشغيل على Windows

افتح PowerShell داخل مجلد `DianaProject`:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\python\requirements-offline.txt
python -m pip install -r .\terminal\requirements.txt
npm install
```

شغّل Ollama في نافذة منفصلة:

```powershell
ollama serve
ollama create diana-texty -f .\ollama\Modelfile.texty
ollama create diana-coding -f .\ollama\Modelfile.coding
```

اضبط XTTS-v2 قبل التشغيل الأول:

```powershell
$env:TTS_HOME = "$PWD\models\tts"
$env:DIANA_TTS_DEVICE = "cuda"   # استخدم cpu إذا لم توجد NVIDIA CUDA
python -c "from TTS.api import TTS; TTS('tts_models/multilingual/multi-dataset/xtts_v2')"
```

بعد تثبيت الاعتماديات والنماذج، شغّل:

```powershell
npm start
```

تفتح واجهة Diana الرئيسية أولًا. زر `OPEN IDE` أو الاختصار `Ctrl+Alt+I` يفتح IDE القديم بعد دمجه، مع Monaco وxterm من `vendor/`.

## Terminal agent

لتشغيل terminal agent مباشرة:

```powershell
cd .\terminal
..\.venv\Scripts\python.exe .\diana_coding.py
```

أو استخدم:

```powershell
.\terminal\diana.bat
```

يستخدم terminal agent نموذج `qwen2.5-coder:7b` افتراضيًا، ويستطيع استخدام `diana-coding` عبر:

```powershell
$env:DIANA_MODEL = "diana-coding"
```

## فحص الجاهزية

```powershell
python .\prepare_offline.py
```

الفحص يتحقق من الملفات المحلية، مكتبات Python، خدمة Ollama على localhost، وأحد النموذجين الأساسيين أو المخصصين لكل شخصية. لا ينزّل شيئًا.

## بناء التطبيق

بعد نجاح التشغيل:

```powershell
python .\build_backend.py
npm run make
```

سيضع Electron Forge المخرجات داخل `out/`. يجب بناء نسخة Windows على Windows للحصول على نتيجة Windows أصلية.

## شاشة التحميل وفحص جاهزية الخادم

يبدأ Electron الآن بفتح `app/splash.html` فورًا، ثم يشغّل خادم Python ويفحص `http://127.0.0.1:5000/health` كل نصف ثانية. لا تظهر نافذة Diana الرئيسية إلا بعد أن يعيد الخادم حالة HTTP ناجحة. توجد ملفات `app/splash.html` و`app/splash.css` لتعديل الألوان والحركة والنصوص بسهولة. عند فشل الخادم تبقى شاشة التحميل ظاهرة برسالة الخطأ بدل فتح نافذة بيضاء.

## ما لم يتم تضمينه كتشغيل مباشر

لم يتم اعتماد ملفات `Scripts/` و`share/` و`pyvenv.cfg` القديمة كبيئة تشغيل؛ فهي تحتوي على executable paths مرتبطة بجهاز ومسار سابقين. تم حفظ snapshot مرجعي لها تحت `legacy/venv_snapshot/`، لكن البيئة الصحيحة يعاد إنشاؤها داخل `.venv` على الجهاز المستهدف.

لم يتم تضمين أوزان Ollama أو cache XTTS-v2 داخل الحزمة؛ ضعها في Ollama و`models/tts` بعد تنزيلها مرة واحدة. بعد ذلك يعمل التطبيق محليًا، مع بقاء أي وظائف ADB أو USB معتمدة على توصيل الجهاز وتثبيت أدواته.

## ملاحظة أمان

خادم Diana مربوط على `127.0.0.1` فقط. لا تغيّر ذلك إلى `0.0.0.0`. Endpoint تشغيل الكود مخصص للاستخدام المحلي وليس sandbox أمنيًا كاملًا؛ لا تشغّل كودًا غير موثوق.

## Private Chat

لإنشاء جلسة خاصة من داخل الشات، استخدم `Shift + Click` على خيار `Pass Key` من الـ sidebar ليظهر المنشن، ثم اكتب كود Pass Key الخاص بك (اضبطه في إعدادات البيئة، لا تستخدم الكود الافتراضي) وأرسل الرسالة. يتم فتح جلسة `PRIVATE // LOCAL` ولا يتم إرسال رسائلها إلى ملفات `diana_texty_memory.json` أو `diana_coding_memory.json`؛ تبقى ذاكرتها داخل عملية الخادم المحلية فقط.

لن تظهر المحادثة الخاصة في `CHAT HISTORY` العادي. لا تُستعاد الجلسة الخاصة إلا بعد التحقق من Pass Key مرة أخرى من لوحة Pass Key أو من خلال منشن Pass Key وكتابة الكود في الشات. بدء `NEW CHAT` يقفل الجلسة الخاصة، وإعادة تشغيل الخادم تمسح ذاكرتها المؤقتة من RAM.

مهم: Private Chat عزل محلي عن ذاكرة Diana العامة، لكنه ليس تشفيرًا جنائيًا للقرص؛ فالسجل المحلي داخل واجهة Electron قد يحتوي على نسخة تاريخية خاصة، لذلك استخدم زر الحذف إذا أردت إزالتها من الجهاز.

## Agent Workbench

افتح `AGENTS` من الـ sidebar لكتابة أمر مباشر. تختار Diana تلقائيًا بين Planner وWriter/Coder وResearcher وReviewer، وتظهر حالة المهمة ونسبة التقدم والنتيجة داخل البطاقة مباشرة. يمكنك أيضًا كتابة `/agent` أو `@agent` في الشات لتشغيل المهمة من نفس المحادثة.

وضع `LOCAL ONLY` يعمل بدون إنترنت. وضع `WEB RESEARCH` أو أمر مثل `ابحث من الإنترنت ولخص...` يستخدم مصادر عامة عند الطلب فقط، ثم يعرض روابط المصادر مع النتيجة. وضع `KNOWLEDGE NOTE` يحفظ النتيجة التي تمت مراجعتها داخل `agent_knowledge.json` للرجوع إليها محليًا.

قسم `ROUTINES` يسمح بحفظ أمر يومي أو متكرر. يعمل المجدول داخل خادم Diana المحلي أثناء تشغيله، ولا ينفذ أوامر shell أو حذف ملفات أو إرسال رسائل تلقائيًا؛ هذه الآثار الجانبية تظل بحاجة إلى إجراء صريح.

## Diana 2.5 beta وIDE

الإصدار الظاهر داخل لوحة INFO هو `DIANA // 2.5 {beta}`، ورقم حزمة Electron هو `2.5.0-beta`. زر `IDE` في الـ sidebar يفتح مباشرة واجهة Diana Terminal/IDE المدمجة عبر Electron، وتظل واجهة `OPEN IDE` السفلية متاحة أيضًا.
