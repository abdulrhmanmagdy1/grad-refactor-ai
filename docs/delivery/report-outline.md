
# مخطط التقرير الأكاديمي وربط كل قسم بدليله

هذا الملف ليس التقرير نفسه؛ هو خريطة كتابته. لكل قسم: ما يُكتب، ومن أين يُؤخذ الدليل داخل
المستودع. القاعدة الحاكمة (NFR06): لا رقم في التقرير بلا ملف مصدر، ولا ادعاء نجاح بلا اختبار أو
سجل تشغيل يمكن فتحه.

## قبل الكتابة

- شغّل `python scripts/tasks.py all` واحفظ ناتجه (البوابات الثماني) كملحق.
- أعد توليد `RELEASE_MANIFEST.json` بعد أي تغيير في البيانات أو التجارب أو حزمة الواجهة، ثم
  `python scripts/verify_release.py`.
- ثبّت إصدار الأدوات المستخدم في التجارب (`python --version`، `node --version`، إصدار الموديل)
  من ناتج `python scripts/doctor.py`.

## الأقسام

| # | القسم | المحتوى | الدليل في المستودع |
|---|---|---|---|
| 1 | المقدمة والمشكلة | صيانة كود Python وتكلفة الـRefactoring اليدوي، ولماذا التحقق الآلي شرط لا رفاهية | `docs/proposal/project-proposal.md`, `docs/research/related-work.md` |
| 2 | الأهداف والنطاق | FR01–FR10 وNFR01–NFR07 كما هي، مع تمييز المنفَّذ عن المؤجَّل | `docs/requirements/srs.md`, `docs/requirements/traceability.md` |
| 3 | العمل المرتبط | المقارنة بالموديلات العامة وأدوات الـRefactoring، والفجوة التي يعالجها المشروع | `docs/research/related-work.md` |
| 4 | التصميم | الأدوار الأربعة، حدود الثقة، قرارات ADR01–ADR19 وبدائلها | `docs/architecture/system-design.md`, `docs/architecture/decisions.md` |
| 5 | التنفيذ | المحلل AST، الوكلاء، سجل المزودات، Runner المعزول، واجهة React الواحدة، ومسار QLoRA المشترك مع الاستدلال | `src/`, `frontend/src/`, `training/train_lora.py`, `docs/architecture/system-design.md` |
| 6 | مجموعة البيانات | 416 سجلًا مولّدًا ومتحقَّقًا آليًا (224 findings + 192 clean-control)، التقسيم 320/48/48، وبصمة الملف | `data/curated.jsonl`, `data/manifest.json`, `docs/data-and-training/data-plan.md` |
| 7 | التقييم | المقارنة الحقيقية A–D بين الموديل الأساسي 3B و`fp16 LoRA` مع `refactor_success` و`smell_resolution_rate` وفصل findings/clean، ومرجع `--baseline mock`، والمراجعة العمياء | `experiments/*.csv`, `experiments/*_summary.json`, `docs/evaluation/protocol.md` |
| 8 | الاختبارات والتحقق | 104 اختبار خلفي، اختبارات واجهة Vitest، اختبار الدخان (8 فحوص)، وبوابات CI | `tests/`, `frontend/src/**/*.test.tsx`, `docs/development/testing.md` |
| 9 | النتائج والمناقشة | ما أثبتته الأرقام، وما لم تثبته (نجاح الاختبارات ≠ تكافؤ سلوكي كامل) | `experiments/`, `docs/requirements/traceability.md` (NFR06) |
| 10 | القيود والعمل المستقبلي | غياب Adapter مدرَّب، المراجعة البشرية غير المكتملة، جهاز التحقق الثاني | `docs/planning/risks.md`, `docs/delivery/checklist.md` |
| 11 | الخاتمة | إسهام المشروع ومقاييس نجاحه كما هي معلنة | البنود أعلاه |
| — | الملاحق | أوامر التشغيل، بصمات الإصدار، ناتج البوابات، جدول تتبع المتطلبات | `README.md`, `RELEASE_MANIFEST.json`, `docs/agent-execution/execution-state.json` |

## قواعد الصدق في الكتابة

1. **الأرقام من الملفات**: كل نسبة في القسم 7 تُنسخ من `experiments/*_summary.json`؛ لا يُعاد
   حسابها يدويًا ولا تُقرَّب لتبدو أفضل.
2. **C وD والتفريق المنهجي:** نتائج C وD في `experiments/dataset_test_finetuned_summary.json` هي نتائج **native fp16 LoRA** (`load_in_4bit=false`) لا QLoRA، بينما تبقى ملفات `dataset_test_summary.json` و`evaluation_summary.json` موثقة كمرجع `--baseline mock` (`provider_unavailable` لـ C/D وقتها).
3. **المراجعة العمياء**: تبقى «غير مكتملة» حتى تُملأ `experiments/review/score_sheet.csv` بشريًا؛
   `scripts/aggregate_blind_review.py` يرفض التجميع قبل ذلك، وهذا سلوك مقصود يُذكر كدليل نزاهة.
4. **الاختبارات**: تُذكر أعداد الاختبارات كما يطبعها المشغّل في تاريخ التشغيل، لا من الذاكرة.
5. **المقارنة بالموديلات العامة**: تُنسخ من مصادرها مع تاريخ الوصول؛ لا أرقام من الذاكرة.
6. **الاقتباسات**: كل اقتباس له مرجع في `docs/references.md` وأثر في النص.
7. **findings وclean-control**: تُفصل نسب النجاح دائمًا؛ نجاح clean-control يعني ترك كود نظيف
   دون تغيير، ولا يُضاف إلى `findings_refactor_success_rate`. و`test_pass_rate = null` تعني
   «لا حالات قابلة للاختبار»، لا «كل الاختبارات نجحت».

## ما لا يُكتب

- «النظام يعادل سلوكيًا الكود الأصلي» — يُكتب: «اجتاز التحقق ثلاثي الطبقات (syntax، رموز،
  اختبارات) وهذا ليس برهانًا على التكافؤ الدلالي الكامل».
- «الموديل المخصص أفضل» — يُكتب فقط بعد تدريب Adapter فعلي ونتائج C/D حقيقية.
- «جاهز للإنتاج» — يُكتب: «جاهز للعرض المحلي بحدود معلنة» وفق `docs/delivery/checklist.md`.
