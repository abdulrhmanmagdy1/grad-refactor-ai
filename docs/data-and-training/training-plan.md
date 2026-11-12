# خطة تخصيص الموديل

الحالة: مسار QLoRA منفذ في `training/train_lora.py`، لكن **لم يبدأ تدريب ولم يُعتمد Adapter**. الهدف الأول تخصيص دور التعديل على أنواع Refactoring ضيقة، مع الحفاظ على baseline مستقل.

## تجربة الجدوى في الأسبوع الأول

حصر الأجهزة، اختيار مرشحين صغيرين وفق الترخيص وجودة المهمة، قياس inference على جهاز العرض، ثم تجربة تدريب على عينة صغيرة للتأكد من الذاكرة والزمن والحفظ والاستئناف. الهدف الأساسي `Qwen/Qwen2.5-Coder-3B-Instruct`، مع `1.5B` بديلًا محليًا و`7B` اختياريًا على Colab؛ تبقى البنية قابلة للتغيير بعد فحص العتاد. نسجل revision الفعلي للموديل والتوكنيزر بعد اعتمادهما، ويسجل المانيفست resolved commit hash حتى لو كان الطلب `main`.

## المسار

PyTorch وTransformers وDatasets وPEFT وbitsandbytes هي حزمة التدريب. المسار الافتراضي هو QLoRA 4-bit NF4 مع `bfloat16`/`float16` compute، rank 16، alpha 32، `target_modules="all-linear"`، `max_length=2048`، ثلاث epochs، cosine schedule، gradient checkpointing، وeffective batch 16 (batch 1 × gradient accumulation 16). يُختار أفضل checkpoint حسب validation loss. التدريب يتطلب CUDA؛ لا نستخدم CPU لتدريب طويل ولا نفترض توافر GPU مجاني دائمًا. `--dry-run` يعمل على CPU ويستخدم tokenizer الحقيقي لفحص الأطوال قبل حجز GPU.

## عقد الـprompt والـEOS

التدريب والاستدلال يستخدمان `src/models/prompting.py` نفسه: system prompt موحد، صياغة findings موحدة، `apply_chat_template`، و`<|im_end|>` كنهاية دور المساعد. يُدرَّب الـcompletion فقط مع إخفاء الـprompt من loss. هذا يمنع الفجوة التي كانت تجعل الـAdapter يتدرب على code block خام بينما يقيس على chat template مختلف. الفحص في `--dry-run` يطبع أطوال prompt/completion الفعلية لكل split ويفشل إذا تجاوز أي سجل `max_length`.

## التجهيز والتنفيذ

البيانات المطلوبة JSONL وفق [الخطة](data-plan.md). تحقق أولًا:

```bash
uv run python scripts/validate_dataset.py data/curated.jsonl
uv run python scripts/audit_tokens.py data/curated.jsonl --max-length 2048
```

في بيئة التدريب المنفصلة، بعد تثبيت تبعيات متوافقة وتثبيت نسخها، املأ `configs/training.local.json` بمعرف وrevision معتمدين ومسارات البيانات ثم شغّل:

```bash
python training/train_lora.py --config configs/training.example.json --dry-run
python training/train_lora.py --config configs/training.local.json
python training/train_lora.py --config configs/training.local.json \
  --resume-from-checkpoint runs/lora-first/checkpoint-42
```

يرفض السكريبت الإعدادات غير المحسومة، والبيانات غير الصالحة، والسجلات الأطول من `max_length`، وبيئة بلا CUDA عند التدريب الفعلي. يستبعد test من Trainer ويستخدم validation للاختيار. يكتب `run-manifest.json` مع dataset sha256، resolved model commit، نسخ الحزمة، العتاد، seed، عدد المعاملات القابلة للتدريب، ذروة ذاكرة GPU، مدة التدريب، checksum للـAdapter، ونتيجة smoke generation تفحص syntax فقط عبر AST ولا تنفذ الكود المولّد (NFR01). لا يكفي loss وحده للحكم؛ يبقى تقييم `refactor_success` على test المجمد هو المرجع.

## سجل كل تجربة

معرف التجربة؛ SHA الكود؛ dataset hash وتقسيماته؛ الموديل وrevision؛ نسخ التبعيات وCUDA؛ العتاد والذاكرة؛ seed؛ LoRA targets/rank؛ batch وgradient accumulation؛ LR وepochs والسياق؛ الزمن وذروة الذاكرة؛ نتائج validation؛ مكان الـAdapter والـchecksum؛ وأي توقف أو فشل. النموذج في `experiments/run-template.json`.

## اختيار النسخة

اختيار النموذج على validation وفق مقياس معلن، ثم تشغيل test مرة للمقارنة المعتمدة. loss وحده لا يقيس نجاح Refactoring. إذا لم يتحسن النموذج، نحلل البيانات والإعدادات ونبلغ النتيجة؛ لا نخفي حالات الفشل أو نعيد الضبط على test.

## الموارد المجانية والتخزين

يمكن تجربة Colab ضمن حدوده للاستخدام التفاعلي، لكنه ليس خادم استضافة دائمًا أو موردًا مضمونًا. احفظ Adapter وcheckpoints القابلة للاستئناف وفق الحصة المتاحة. GitHub يحتفظ بالـAdapter الصغير المعتمد وmetadata، لا بنسخة أخرى من الموديل الأساسي إذا كان متاحًا من مصدره.
