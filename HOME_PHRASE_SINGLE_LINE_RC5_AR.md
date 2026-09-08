# Home Phrase Single-Line RC5

تم تحديث صندوق العبارات في Home حسب الملاحظة البصرية الأخيرة.

أصبحت العبارة الأساسية تُعرض في سطر واحد فقط باستخدام `white-space: nowrap` مع `overflow` آمن وellipsis عند الحاجة. لون العبارة الأساسي أصبح فضيًا/رماديًا، وتم تخصيص خط Pixel-style واضح ومختلف عن بقية الواجهة عبر fallback مرتب يبدأ بخطوط Pixel المعروفة ثم Cascadia Mono وCourier New عند عدم توفرها.

أثناء كل دورة typewriter يتم اختيار كلمة واحدة عشوائيًا من العبارة، وتُرسم داخل span مستقل باسم `home-phrase-accent` بلون بنفسجي فاتح مع glow خفيف. الاختيار يتغير مع كل عبارة ولا يكرر نمطًا ثابتًا.

تمت إزالة نقطة الحالة من markup ومن تحديث JavaScript. بقي اسم الفترة نصيًا فقط مثل `MIDNIGHT` أو `AFTERNOON` أو `EARLY BIRD`.

نجحت static phrase test، وinline JavaScript syntax، وElectron main/preload/IDE renderer checks، وPython compile، وElectron package، وZIP integrity. لم يتم تعديل chat logic أو IPC أو Terminal.
