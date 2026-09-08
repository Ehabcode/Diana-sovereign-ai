# Diana Terminal

وكيل طرفية محلي يعمل مع Ollama، ويستطيع قراءة وتعديل ملفات المشروع بعد تأكيد المستخدم، مع دعم اختياري لهاتف Android عبر ADB، وجرد وسائط USB، وجرد محلي لمحولات الشبكة.

## التشغيل من أي مكان على Windows

يمكن استدعاء الملف من أي مجلد عبر `diana.bat` أو PowerShell. لا يغيّر البرنامج مجلد البداية تلقائيًا؛ استخدم `/cwd` لاختيار مجلد المشروع الذي ستعمل عليه:

```text
/cwd D:\coding\my-project
```

بعد اختيار `/cwd`، تصبح حدود أدوات الملفات وshell هي ذلك المجلد فقط. تغيير `/cwd` متاح من أي مكان ولا يعتمد على مكان تشغيل Python.

## المتطلبات

ثبّت المتطلبات على نفس Python الذي يستخدمه ملف التشغيل:

```powershell
$python = "C:\Users\<your-username>\AppData\Local\Programs\Python\Python311\python.exe"
& $python -m pip install -r "D:\coding\diana-project\diana-terminal\requirements.txt"
```

يجب تشغيل Ollama محليًا، ثم تنزيل النموذج:

```powershell
ollama pull qwen2.5-coder:7b
```

## Android / ADB

نزّل Android SDK Platform-Tools من Google، ثم حدّد مسار `adb.exe`:

```powershell
[Environment]::SetEnvironmentVariable(
  "DIANA_ADB_PATH",
  "D:\Android\platform-tools\adb.exe",
  "User"
)
```

افتح PowerShell جديدًا، فعّل USB Debugging على هاتفك، ثم وافق على نافذة RSA. اختبر:

```powershell
adb version
adb devices -l
```

الأدوات المخصصة `adb_device_info`, `adb_list_user_apps`, و`adb_read_only_check` قراءة فقط. عمليات `push` وفتح التطبيقات تحتاج تأكيدًا. لا تستخدم Wireless ADB أو shell عامًا في البداية.

## USB Storage وNetwork

`list_removable_drives` يعرض الوسائط القابلة للإزالة التي يتعرف عليها النظام. `usb_list_directory` يقرأ مجلدًا داخل الجذر الحالي فقط. `network_inventory` يعرض محولات الشبكة والعناوين والإحصاءات المحلية فقط؛ لا ينفذ scanning ولا يغير IP أو DNS أو routes.

## الاختبارات

من داخل مجلد المشروع:

```powershell
& $python -m py_compile diana_coding.py android_adb.py usb.py network.py
& $python test_diana_safety.py
& $python test_diana_features.py
& $python test_shell_execution.py
```

## ملاحظات أمنية

الموافقة اليدوية وAllowlist تقللان المخاطر، لكنهما ليستا Sandbox لنظام التشغيل. لا تشغّل Diana بامتيازات Administrator إلا عند الضرورة، ولا تضع مفاتيح أو كلمات مرور داخل `DIANA.md` أو ملفات الذاكرة، واستخدم هاتفًا وفلاشًا مخصصين للتجارب. كل أوامر الشبكات يجب أن تبقى في مختبر تملكه أو لديك تصريح لاختباره.
