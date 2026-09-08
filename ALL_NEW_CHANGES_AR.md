# Diana // كل التغييرات الجديدة

هذه الحزمة مبنية فوق آخر نسخة سليمة من Diana، وتضم التغييرات الجديدة مجمعة في نسخة واحدة.

## Chat Engine

تمت إضافة زر `+ NEW CHAT` داخل رأس المحادثة، وهو يبدأ جلسة جديدة فعلية ويعيد العنوان والتاريخ والحالة إلى وضع الاستعداد. تمت إضافة حركة دخول منفصلة لرسائل المستخدم وردود Diana، ومؤشر typing، وحالة مرئية أثناء THINKING وCONNECTED، وتحسين حالة الإدخال والزر عند التركيز أو الإرسال.

## Levers

تم تغيير ترتيب levers بحيث تظهر Texty/Coding وSound/Mute جنبًا إلى جنب داخل بطاقات متوازنة، مع أيقونات أوضح وحركة hover هادئة واستجابة أفضل للشاشات الصغيرة.

## Agents

أصبحت اختيارات `PERSONA` و`ROUTE / MODE` واضحة وقابلة للاختيار. تشمل الخيارات Texty وCoding وAuto Route وLocal Only وWeb Research وKnowledge Note. يظهر الاختيار في حالة الشات، ويتحول RUN TASK إلى RUNNING مع حركة أثناء الإرسال، وتظهر بطاقات المهام بحركات مختلفة حسب running أو done أو error.

## D-Saturn

شاشة التحميل تحتوي D كبيرة بكسلية بداخلها Saturn، والحلقة محصورة داخل الحرف. وفي Home يظهر D-Saturn على اليسار مع حلقة كاملة وثلاثة أسطر terminal عشوائية متحركة بجانبه.

## Private Chat

تظل وظائف Pass Key وPrivate Chat وHistory وLOCK وZAP موجودة، مع فتح الخاص من Pass Key باستخدام Shift وكتابة الكود، وفصل history الخاص عن العام في العرض.

## IDE

تم حذف زر `OPEN IDE` العائم من أسفل الواجهة، مع الإبقاء على فتح IDE من خيار `IDE` في الشريط الجانبي.

## التشغيل

هذه حزمة مصدر قابلة للتركيب وليست Offline Bundle تحتوي على `node_modules` و`.venv` ونماذج Ollama. بعد فك الضغط في مجلد جديد، شغّل:

```powershell
cd "D:\coding\diana-project\DianaProject"
npm install
python -m pip install -r .\python\requirements-offline.txt
npm start
```

لا تفك الحزمة فوق نسخة قديمة. احتفظ بالنسخة الحالية كـ backup حتى تتأكد من التشغيل على Windows.
