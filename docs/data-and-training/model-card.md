# بطاقة الموديل المخصص

الحالة: **تم تنفيذ التدريب والتقييم الفعلي على Kaggle Tesla T4** باستخدام **native fp16 LoRA** (`load_in_4bit=false`, `optim=adamw_torch`) على `Qwen/Qwen2.5-Coder-3B-Instruct`. مسار QLoRA 4-bit لا يزال غير مثبت على صورة الحاوية المستخدمة ولا يُنسب إلى هذا النموذج.

## المزودات ونتيجة التخصيص الفعلية (`experiments/training/lora-fp16/run-manifest.json`)

| الحقل | القيمة الفعلية المقاسة |
|---|---|
| المهمة | Refactoring محدود لكود Python: long-function، deep-nesting، high-complexity، async، mutable-default، duplicate-code، long-parameter-list، broad-exception |
| مزود الاختبار الحتمي | `mock` — تحويلات AST حتمية (`mock-refactor-v2`)، متاح دائمًا كمرجع CPU (`dataset_test_summary.json`) |
| المزود الآمن على CPU | `smart_ast` — تحويلات AST→AST مضمونة البنية |
| خادم محلي مرشح | `ollama` — نموذج افتراضي `qwen2.5-coder:1.5b`؛ التوفّر يُفحص لحظيًا في `GET /api/v1/providers` |
| مسار LoRA الفعلي | `local_lora` — **fp16 LoRA** (`runs/lora-fp16/adapter` محليًا؛ الأوزان نفسها ليست في Git لأنها dataset خاص على Kaggle، `load_in_4bit=false`, `optim=adamw_torch`) |
| سلوك غياب الـAdapter | `ProviderUnavailableError` صريح — لا استبدال صامت بموديل أساسي (NFR06) |
| الموديل الأساسي وrevision | `Qwen/Qwen2.5-Coder-3B-Instruct` @ `488639f1ff808d1d3d0ba301aef8c11461451ec5` (Apache-2.0) |
| بيانات التدريب ومصدرها | `data/curated.jsonl` (416 سجلًا مؤلفًا/قوالب بارامترية: 320 train / 48 val / 48 test؛ 224 findings + 192 clean-control، CC0-1.0، SHA-256 `e5b782bf584b331cfe11daeca2356041fcd79de3db61f5f4205ba50c73805756`) |
| طريقة التخصيص | native fp16 LoRA: rank 16، alpha 32، dropout 0.05، `target_modules="all-linear"`، `max_length=2048`، 3 epochs، cosine، gradient checkpointing؛ المعاملات المدربة `29,933,568 / 3,115,872,256` (`0.9607%`) |
| الجهاز ومدة التدريب | Kaggle `Tesla T4` (`15 GB` VRAM)، المدة `7157.5` ثانية (`1:57:24` حلقة التدريب)، ذروة الذاكرة المخصصة `9997977600` بايت (~9.31 GiB) |
| التحقق على validation | 48/48 سجلًا، `eval_loss = 0.005797240417450666` عند epoch 3.0؛ وفحص smoke generation (`long-function-validation-01`) صالح تركيبيًا بلا تنفيذ (`executed=false`) |
| النتائج على split الاختبار (`48` حالة، `--baseline base --candidates 3`) | **Group A (Base Single):** `0.6042` (`findings=0.5312`, `clean=0.7500`)؛ **Group B (Base MultiAgent):** `0.7500` (`findings=0.6875`, `clean=0.8750`)؛ **Group C (LoRA Single):** `0.4583` (`findings=0.1875`, `clean=1.0000`)؛ **Group D (LoRA MultiAgent):** **`0.9167`** (44/48؛ `findings=0.8750`, `clean=1.0000`, `test_pass_rate=1.0000` على 44 حالة قابلة للاختبار؛ `execution_pass_at_1=0.9773` على نفس الـ44، أي `43/48 = 0.8958` على كل الـ48) |
| artifact وchecksum | `adapter_model.safetensors` (`119,801,528` B) SHA-256 `42ae18e5eb26976143077051824e97719222103d4352ca70a24ef1089bb8405f`؛ `adapter_config.json` SHA-256 `dd09bc613a1aaa0a9ad2d5f40021fc6caa59e97cde02f3090ef9c3f884ed329e` |

## حدود الاستخدام المعلنة والقيود

- **نطاق القوالب:** بيانات التدريب والاختبار مؤلفة من 2–3 قوالب بارامترية لكل نوع؛ التفوق المقاس يثبت إتقان المهمة داخل نفس التوزيع ولا يثبت تعميمًا عامًا على مستودعات إنتاجية عشوائية.
- **اعتماد Group D على تعدد الأدوار:** في Group C (دور واحد بلا `AnalysisAgent`) يمرّر الـharness `findings=[]`، فيفسر الموديل المدرب الكود كـ clean-control (`0.1875` findings)، بينما يحقق وجود `AnalysisAgent` + `ReviewAgent` في Group D نسبة `28/28` (`100%`) في الأنواع السبعة الحافظة للتوقيع.
- **قيد `long-parameter-list`:** الحالات الأربع المرفوضة في Group D أنتجت تحويل `@dataclass` الصحيح لكنها رُفضت بقيد حفظ التوقيع الصارم في `ReviewAgent._signature_violations()`.
- **عدم إثبات التكافؤ الكامل:** نجاح اختبارات التكافؤ الآلية على عينات داخل sandbox لا يعادل برهانًا دلاليًا كاملًا (NFR06)، والمراجعة البشرية العمياء لا تزال بانتظار تعبئة `score_sheet.csv`.
