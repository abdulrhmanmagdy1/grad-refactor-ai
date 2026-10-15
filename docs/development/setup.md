# إعداد بيئة التطوير

البيئة الأساسية تعمل على CPU ولا تحتاج تنزيل موديل. التدريب بيئة منفصلة تُضبط حسب GPU المتاح. حافظ على مفاتيح الوصول والبيانات المحلية خارج Git.

## المتطلبات

Git، Python 3.11، وuv من [المصدر الرسمي](https://docs.astral.sh/uv/getting-started/installation/). الحسابات الخمسة تحتاج صلاحية المستودع. Node مطلوب عند بدء الواجهة فقط؛ لا يوجد Frontend منتج في حزمة التأسيس الحالية.

## الخطوات

```bash
git clone https://github.com/abdulrhmanmagdy1/grad-refactor-ai.git
cd grad-refactor-ai
uv sync --frozen
uv run python scripts/doctor.py
uv run pytest
uv run uvicorn refactor_ai.api:app --reload --host 127.0.0.1
```

نفس أوامر uv تعمل على Windows PowerShell دون تفعيل يدوي للـvenv. افتح http://127.0.0.1:8000/docs. جرّب `/api/v1/analyze` بكود Python بسيط. الخدمة تحلل البنية فقط ولا تنفذ المدخلات.

## فحوصات قبل PR

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python scripts/check_docs.py
```

## بيئة التدريب

ابدأ بـ[خطة التدريب](../data-and-training/training-plan.md). تحقق من NVIDIA GPU/VRAM أو موارد الكلية. مواصفات CUDA وPyTorch تتحدد من الجهاز قبل تثبيت بيئة التدريب؛ لا تثبت نسخة CUDA عشوائية على Mac أو جهاز CPU. ملف `training/requirements.in` قائمة مرشحة، وبعد تجربة الجهاز تُثبت النسخ الناجحة في ملف قفل منفصل. لا تستخدم ملف قفل البيئة الأساسية كدليل على قابلية إعادة التدريب.

## الملفات المحلية

`data/` و`models/` و`runs/` و`.env` و`.venv/` مستبعدة من Git. سجل التجربة المنقح يرفع في `experiments/`، والمرفقات المسموح بها في Releases. لا ترفع Base Model متاحًا أصلًا؛ سجل معرفه وrevision وترخيصه.

## مشاكل شائعة

عدم الوصول للمستودع: تأكد من الحساب وقبول الدعوة. فشل uv بسبب إصدار Python: ثبّت 3.11 أو استخدم إدارة Python في uv. فشل التدريب بسبب الذاكرة: قصّر السياق وقلل batch وحجم الموديل قبل تغيير عدة إعدادات معًا. بطء الجهاز لا يبرر استخدام API مدفوع خارج الاتفاق.
