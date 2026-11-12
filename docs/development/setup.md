# إعداد بيئة التطوير

البيئة الأساسية تعمل على CPU ولا تحتاج تنزيل موديل. التدريب بيئة منفصلة تُضبط حسب GPU المتاح. حافظ على مفاتيح الوصول والبيانات المحلية خارج Git.

## المتطلبات

Git، Python 3.11، وuv من [المصدر الرسمي](https://docs.astral.sh/uv/getting-started/installation/). الحسابات الخمسة تحتاج صلاحية المستودع. Node مطلوب فقط لإعادة بناء واجهة الويب (React/TypeScript)؛ البناء الجاهز محفوظ في `frontend/dist` وتُقدَّمه الخدمة تلقائيًا.

## الخطوات

```bash
git clone https://github.com/abdulrhmanmagdy1/grad-refactor-ai.git
cd grad-refactor-ai
uv sync --frozen
uv run python scripts/doctor.py
uv run pytest
uv run uvicorn refactor_ai.api:app --reload --host 127.0.0.1
```

نفس أوامر uv تعمل على Windows PowerShell دون تفعيل يدوي للـvenv. افتح http://127.0.0.1:8000
لواجهة الويب (Monaco وتبويبات النتائج ورسم AST)، وhttp://127.0.0.1:8000/docs
لمرجع API. جرّب `/api/v1/analyze` بكود Python بسيط. الخدمة تحلل البنية فقط ولا تنفذ المدخلات.

## إعادة بناء واجهة الويب

```bash
cd frontend
npm install
npm run build
```

البناء يكتب إلى `frontend/dist` (outDir محلي مع `emptyOutDir`)، وتقرأه الخدمة على `/` عند
بدء uvicorn التالي. عند غياب البناء تُقدَّم صفحة placeholder بتعليمة البناء بدل الفشل.
خلال التطوير يمكن تشغيل `npm run dev` على منفذ 5173 مع proxy إلى الخدمة على 8000.

## فحوصات قبل PR

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python scripts/check_docs.py
```

## بيئة التدريب

ابدأ بـ[خطة التدريب](../data-and-training/training-plan.md). تحقق من NVIDIA GPU/VRAM أو موارد الكلية. مواصفات CUDA وPyTorch تتحدد من الجهاز قبل تثبيت بيئة التدريب؛ لا تثبت نسخة CUDA عشوائية على Mac أو جهاز CPU. ملف `training/requirements.in` قائمة مرشحة (وتشمل `bitsandbytes` لـQLoRA)، وبعد تجربة الجهاز تُثبت النسخ الناجحة في ملف قفل منفصل. لا تستخدم ملف قفل البيئة الأساسية كدليل على قابلية إعادة التدريب. على جهاز CPU يمكن تشغيل `python training/train_lora.py --config configs/training.example.json --dry-run` لفحص الأطوال بالـtokenizer الحقيقي قبل حجز GPU.

## الملفات المحلية

`data/` و`models/` و`runs/` و`.env` و`.venv/` مستبعدة من Git. سجل التجربة المنقح يرفع في `experiments/`، والمرفقات المسموح بها في Releases. لا ترفع Base Model متاحًا أصلًا؛ سجل معرفه وrevision وترخيصه.

## مشاكل شائعة

عدم الوصول للمستودع: تأكد من الحساب وقبول الدعوة. فشل uv بسبب إصدار Python: ثبّت 3.11 أو استخدم إدارة Python في uv. فشل التدريب بسبب الذاكرة: قصّر السياق وقلل batch وحجم الموديل قبل تغيير عدة إعدادات معًا. بطء الجهاز لا يبرر استخدام API مدفوع خارج الاتفاق.
