# منهج تقييم المنصة والموديل

الحالة: البروتوكول منفذ في `src/evaluation/harness.py` و`src/evaluation/metrics.py`. عُدّل المسار
الأساسي الحالي على المجموعة المدمجة وsplit الاختبار من البيانات (مجموعتا A وB). المجموعتان C
وD تحتاجان Adapter مخصصًا غير موجود بعد على عتاد CUDA، وتُصدَّر صفوفهما بحالة
`provider_unavailable` مع سبب خام وقيم مجمعة `null` — لا أصفار ولا نسب مزيّفة (NFR06).

## مجموعات المقارنة

| المجموعة | الموديل | تنظيم العمل |
|---|---|---|
| A | الأساسي | دور واحد مع نفس أدوات التحقق المتاحة |
| B | الأساسي | تحليل وتعديل ومراجعة |
| C | مخصص في دور التعديل | دور واحد |
| D | مخصص في دور التعديل مع بقية الأدوار الأساسية | تحليل وتعديل ومراجعة |

**عدالة المقارنة A/B:** المجموعة A تتلقى الآن نفس findings التي ينتجها محلل AST وتمررها إلى
المجموعة B. قبل هذا التعديل كانت A تنادي المزود بقائمة findings فارغة، فكانت نسبة قبولها تقيس
ترك الكود دون تغيير لا جودة إعادة الصياغة. الفرق المتبقي بين A وB هو التنظيم (دور واحد مقابل
ثلاثة أدوار مع مراجعة وإعادة محاولة محدودة) لا غياب المعلومات.

**مزود الأساس:** `--baseline mock` (الافتراضي) يستخدم المزود الحتمي على CPU لمقارنة تنظيمية
قابلة لإعادة الإنتاج؛ `--baseline base` يستخدم الموديل الأساسي الحقيقي نفسه الذي يُبنى عليه
الـAdapter، وهو اللازم قبل أي ادعاء بأن التدريب أضاف قيمة. يُمرَّر اسم الموديل عبر
`--base-model` أو يُقرأ من `adapter_config.json` عند وجود Adapter.

المجموعة C وD تُنادي `LocalModelProvider(model_name="fine-tuned-lora-adapter",
adapter_path="runs/lora-first/adapter")` حسب مخرج التدريب في `configs/training.example.json`.
إن غاب `adapter_config.json` أو تعذّر تحميل الموديل، تُسجَّل الحالة `provider_unavailable` ولا
يُستبدل الـAdapter صامتًا بموديل أساسي. نثبت البيانات ونسخة الأدوات وأنواع المهام وسياسة
التوليد، ونقارن تحت سقف إجمالي للاستدعاءات والتوكنز موزع على الأدوار، ولا ننسب فرق الموارد كله
إلى المعمارية.

## المقاييس المنفذة

- `syntax_validity_rate`: نسبة النتائج القابلة للتحليل كـPython من الحالات المنفذة.
- `test_pass_rate`: نسبة اجتياز الاختبارات المتاحة (اختبار المستخدم أو الذهبية المولدة) مع
  إظهار عدد الحالات المغطاة. تكون `null` عند عدم وجود أي حالة قابلة للاختبار، لا `1.0` مزيّفة.
- `smell_rule_resolved` لكل حالة: هل اختفت القاعدة المعلنة (`expected_rule`) من المرشح وفق
  تحليل AST؟ تكون `null` لسجلات clean-control لأنها لا تحمل قاعدة مستهدفة.
- `smell_resolution_rate`: نسبة الحالات التي حُلّت فيها القاعدة المعلنة من بين حالات findings
  المنفذة فقط. لا تُحسب clean-control في مقامها.
- `refactor_success` لكل حالة: `syntax_valid` **و** `preserved_symbols` **و**
  `tests_available` **و** `tests_passed` **و** `smell_rule_resolved is not False`.
  أي أن النجاح يتطلب كودًا صالحًا، وحفظ الرموز العلوية، واختبارات متاحة وناجحة، وعدم ترك
  القاعدة المعلنة قائمة.
- `refactor_success_rate`: نسبة `refactor_success` من الحالات المنفذة.
- `findings_refactor_success_rate`: نفس النسبة على حالات findings وحدها.
- `clean_control_success_rate`: نفس النسبة على clean-control وحدها. النجاح هناك يعني ترك الكود
  النظيف كما هو مع الحفاظ على سلوكه، وليس إصلاح عيب غير موجود. الفصل ضروري لأن clean-control
  لا يجوز أن تتضخم به نسبة نجاح الإصلاح.
- `overall_acceptance_rate`: نسبة الحالات المقبولة (حكم مراجعة `approved` على الأقل).
- `execution_pass_at_1`: نجاح المحاولة الأولى قبل أي إعادة — نسبة مرجحة بالحالات القابلة للاختبار.
- `codebleu_score_mean`: صيغة CodeBLEU بأوزان متساوية (0.25): n-gram BLEU بتنعيم add-1،
  n-gram مرجح بالكلمات المفتاحية (وزن 5.0)، تطابق AST بنيوي، وتشابه Data-Flow Dice —
  نسخة Python موثقة في `src/evaluation/metrics.py`.
- `ast_similarity_mean`: نسبة LCS على عقد AST المعلّقة (preorder) — نسخة Python موثقة.
- `mi_improvement_mean`: فرق Maintainability Index (بعد − قبل) من لقطات دور المراجعة.
- `complexity_reduction_pct_mean`: نسبة خفض التعقيد الأقصى للمهمة، وقد تكون سالبة عند إضافة
  بنية جديدة (مثل استخراج دالة)؛ الانخفاض وحده ليس نجاحًا كافيًا.
- الزمن والاستدعاءات والتوكنز وعدد إعادات المحاولة: من `metrics` كل تشغيل.

المقام يشمل المحاولات الفاشلة والمنتهية بالوقت ولا يحذفها. عند صفر حالات منفذة تكون القيم
المجمعة `null` مع حقول `executed_cases` و`provider_unavailable_cases` لبيان السبب.

## Best-of-N والاختيار بلا تنفيذ

`--candidates N` يطلب من المزود المحلي N مرشحين لكل حالة. الاختيار بينهم في
`src/core/candidate_selection.py` يعتمد على تحليل AST فقط: صلاحية syntax، حفظ الرموز العلوية،
اختفاء القواعد المعلنة، وانخفاض عدد findings — **لا يُنفَّذ أي مرشح أثناء الاختيار** (NFR01).
الاختبارات المعزولة تعمل بعد الاختيار فقط وعلى المرشح الفائز، وتُسجل `candidates_generated`
و`selected_candidate` في CSV. عند تعذر توليد أكثر من مرشح (مزود حتمي) تبقى القيمة 1.

## تحميل المزود وتوقيت التوليد

على عتاد CUDA الحقيقي يُحمَّل الموديل مرة واحدة لكل مزود (أساسي ومخصص) ويُعاد استخدامه في كل
الحالات؛ إعادة التحميل لكل حالة كانت ستضاعف زمن التشغيل وتستهلك ذاكرة GPU بلا داعٍ. سقف توقيت
التوليد يُضبط عبر `--timeout` (بالثواني، الافتراضي 900) ويغطي كل مرشحي best-of-N في الاستدعاء
الواحد. انتهاء المهلة لا يُحوَّل إلى `provider_unavailable` ولا يُحذف من المقام: يُسجل صف بحالة
`executed` ونوع فشل `generation_timeout` و`refactor_success=false` حتى تبقى النسبة محسوبة على
كل ما جرى فعليًا (NFR06).

## التصدير وسجل الحالة

كل تشغيل ينتج `experiments/<name>_results.csv` (سجل حالة لكل سطر: knowledge case وgroup
وrefactoring_type وvariant والقاعدة المتوقعة والحالة ونوع الفشل وحكم المراجعة و
`syntax_valid` و`preserved_symbols` و`smell_rule_resolved` و`refactor_success` و`tests_*`
ونِسب المقاييس و`candidates_generated`/`selected_candidate`) و
`experiments/<name>_summary.json` (تجميع لكل مجموعة مع فصل findings/clean). أوامر إعادة الإنتاج:

```bash
# المجموعة المدمجة
uv run python -m evaluation.harness --groups A B C D --output-dir experiments

# split الاختبار من البيانات (48 سجلًا: 32 findings + 16 clean-control)
uv run python -m evaluation.harness --dataset data/curated.jsonl --split test \
  --name dataset_test --include-code --output-dir experiments

# مقارنة مع الموديل الأساسي الحقيقي وBest-of-N عند توفر Adapter
uv run python -m evaluation.harness --baseline base \
  --base-model Qwen/Qwen2.5-Coder-3B-Instruct --candidates 4 \
  --adapter-path runs/lora-first/adapter --groups C D --output-dir experiments
```

`--load-in-4bit` يفعّل تحميل الموديل بـNF4 عبر bitsandbytes عند توفر CUDA. نتائج test تحفظ دون
تعديل انتقائي، ونذكر إصدار الكود والبيانات في manifest البيانات (`data/manifest.json` يحمل
sha256 للسجلات وطريقة تحقق كل سجل وعدّادات findings/clean).

## المراجعة البشرية

اثنان يراجعان عينة دون معرفة المجموعة إن أمكن، باستخدام rubric واحد، ويسجلان الخلاف وتسويته.
التكافؤ الآلي (اختبارات + CodeBLEU + تشابه AST) مؤشر مرجعي وليس حكمًا دلاليًا كاملًا، ومخرجات
نفس الموديل ليست حكمًا مرجعيًا تلقائيًا.

الأداة المنفذة لهذا البروتوكول: صدّر نتائج split الاختبار مع الكود `--include-code`، ثم:

```bash
uv run python -m evaluation.harness --dataset data/curated.jsonl --split test \
  --name dataset_test --include-code --output-dir experiments
uv run python scripts/prepare_blind_review.py --results experiments/dataset_test_results.csv \
  --output-dir experiments/review
# المراجعون يعبّئون score_sheet.csv يدويًا: correctness / readability / maintainability (1–5)
uv run python scripts/aggregate_blind_review.py --review-dir experiments/review
```

`experiments/review/packet.md` يعرض الأصل والمرشحين بترتيب مبهم لكل حالة؛ الترتيب يُشتق من بذرة
ثابتة فيُعاد إنتاج نفس العبوة بالضبط، و`review_key.csv` للجهة المنسقة فقط. المجمّع لا يختلق شيئًا:
بلا تقييمات بشرية يفشل برسالة صريحة (NFR06)، والصفوف الفارغة أو خارج المقياس تُحصى وتُتخطى، ويطبع
متوسطات كل مجموعة ومدى الخلاف بين المراجعين (mean max-min range، ويحتاج تقييمين على الأقل لكل
عنصر). العينة الحالية 48 حالة × مرشحَين (A وB) لأن C/D غير متاحتين؛ لا يُدّعى ثبات إحصائي من
عينة بهذا الحجم، والمنهج يُناقش مع الدكتورة قبل أي استنتاج.

## شروط اعتماد النسخة

المتطلبات P0 P1 المتفق عليها تعمل على جهاز العرض؛ سجل نتائج قابل للإعادة بالملفات أعلاه؛ تحليل
للأخطاء؛ شرح القيود (بما فيها غياب المجموعتين C وD حتى توفر Adapter)؛ وموافقة الدكتورة على
تفسير النتيجة قبل أي ادعاء تفوق. لا نختلق دلالة إحصائية من عينة صغيرة، والأهداف العددية النهائية
تُثبَّت قبل فتح الاختبار النهائي.

## ضوابط التنفيذ على عتاد T4 وعزل الاختبارات

بطاقة T4 بذاكرة 15 GB لا تتسع لتحميل موديل 3B fp16 أساسي وموديل 3B ثانٍ مع Adapter في الوقت نفسه. لذلك ينفّذ `harness.py` مجموعتي A/B أولًا ثم يحرر النموذج الأساسي صراحةً عبر `_release_baseline_provider` (`gc.collect()` و`torch.cuda.empty_cache()`) قبل تحميل الـAdapter لمجموعتي C/D. كما يضع `LocalModelProvider` نماذج fp16 على GPU مباشرةً عبر `device_map="auto"` مع `torch.float16` بدل التحميل على CPU أو الاعتماد على نقل `pipeline(device=...)`، حتى لا تتضاعف الذاكرة أو ينزلق التوليد إلى CPU.

داخل `src/runner/sandbox.py` تُعطَّل إضافات `pytest` الخارجية عبر `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` لإزالة تأخير الإقلاع ومنع تسرب إضافات البيئة المضيفة إلى بيئة الاختبار المعزولة (NFR02)، مع بقاء إضافات `pytest` الأساسية وبوابة حظر الشبكة (`conftest.py`) فعّالة.

## التجربة الاستكشافية وتقسيم الجلسات عند الحاجة

يدعم `evaluation.harness` معامل `--limit N` لتشغيل أول N حالات فقط من split الاختبار. في بيئة Kaggle نبدأ بتجربة استكشافية (`--limit 2`) قبل دفع الحالات الـ48 الكاملة: نتحقق من أن المجموعات الأربع A/B/C/D تعمل جميعها بحالة `executed` (لا `provider_unavailable`) مع مطابقة SHA-256 للـAdapter، ونقيس الزمن المتوقع للتشغيل الكامل. إذا تجاوز الزمن المتوقع حد الجلسة الآمن (~8 ساعات على GPU)، نقسّم المجموعات على جلسات منفصلة (`A B` ثم `C D`) ثم ندمج المخرجات بدون المساس بالمقاييس المقاسة.

