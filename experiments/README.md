# سجل التجارب

انسخ `run-template.json` لكل تجربة تدريب، واربطه بـIssue وPR والبيانات والـAdapter. لا ترفع
ملفات تحتوي كود مستخدم خاص أو أسرارًا. تشغيل التدريب الفعلي يكتب أيضًا
`runs/<name>/run-manifest.json` (dataset sha256، resolved model commit، نسخ الحزمة، العتاد،
seed، ذروة الذاكرة، checksum الـAdapter، وsmoke generation بفحص AST فقط).

## مخرجات التقييم الحالية (منفذة فعليًا)

> **تنبيه منهجي مهم (NFR06):** الملفان `evaluation_summary.json` و`dataset_test_summary.json`
> يسجلان نتائج خط الأساس الحتمي **`--baseline mock` (`mock-refactor-v2` على CPU)** وليس نموذج LLM حقيقيًا
> (ويظهر فيهما حقل `base_model: Qwen/Qwen2.5-Coder-1.5B-Instruct` فقط كقيمة التهيئة الافتراضية للمسار وقتها، مع `provider_unavailable` لمجموعتي C وD).
> أما **نتائج الموديل الحقيقي والـAdapter المدرب على GPU** فهي مسجلة في `dataset_test_finetuned_summary.json` و`dataset_test_finetuned_results.csv`.

| الملف | الوصف |
|---|---|
| `dataset_test_finetuned_results.csv` | التقييم الحقيقي الكامل على split الاختبار من `data/curated.jsonl` (48 حالة × 4 مجموعات = 192 صفًا، `0` حالات `provider_unavailable`): المجموعتان A/B بالموديل الأساسي `Qwen/Qwen2.5-Coder-3B-Instruct` (`--baseline base`) والمجموعتان C/D بـ **fp16 LoRA Adapter** (`runs/lora-fp16/adapter`) مع `--candidates 3` واختيار AST فقط. |
| `dataset_test_finetuned_summary.json` | التجميع النهائي للأرقام الحقيقية: Group A (`refactor_success_rate = 0.6042`, findings `0.5312`, clean `0.7500`), Group B (`0.7500`, findings `0.6875`, clean `0.8750`), Group C (`0.4583`, findings `0.1875`, clean `1.0000`), Group D (`0.9167`, findings `0.8750`, clean `1.0000`, `test_pass_rate = 1.0000`). |
| `evaluation_results.csv` | سجل حالة لكل تشغيل على المجموعة المدمجة (4 حالات × 4 مجموعات) باستخدام `--baseline mock` (`mock-refactor-v2` لـ A/B و`provider_unavailable` لـ C/D). |
| `evaluation_summary.json` | تجميع المجموعة المدمجة باستخدام `--baseline mock`؛ قيم `null` في C/D تعني «لم يُقس» لغياب Adapter وقت التشغيل. |
| `dataset_test_results.csv` | سجل مرجعي لـ `--baseline mock` (`mock-refactor-v2` على CPU) على split الاختبار (A وB فقط + `provider_unavailable` لـ C/D) مع `original_code` و`refactored_code`. |
| `dataset_test_summary.json` | تجميع مرجعي لخط الأساس الحتمي `mock-refactor-v2` (`0.4583` إجمالي / `0.1875` findings / `1.0` clean-control). |
| `review/packet.md` | عبوة المراجعة البشرية العمياء (مُعادة التوليد لأربع مرشحين A/B/C/D من `dataset_test_finetuned_results.csv`). |
| `review/score_sheet.csv` | صفوف تقييم فارغة (correctness / readability / maintainability 1–5) يعبّئها المراجعون يدويًا. |
| `review/review_key.csv` | خريطة المرشح → المجموعة الحقيقية؛ للجهة المنسقة فقط. |
| `review/review_summary.json` | يُنشأ فقط بعد تعبئة تقييمات بشرية عبر `scripts/aggregate_blind_review.py`. |

إعادة التوليد:

```bash
uv run python -m evaluation.harness --groups A B C D --include-code --output-dir experiments
uv run python -m evaluation.harness --dataset data/curated.jsonl --split test \
  --name dataset_test --include-code --output-dir experiments
uv run python -m evaluation.harness --dataset data/curated.jsonl --split test \
  --groups A B C D --adapter-path runs/lora-fp16/adapter \
  --base-model Qwen/Qwen2.5-Coder-3B-Instruct --baseline base --candidates 3 \
  --timeout 900 --include-code --name dataset_test_finetuned --output-dir experiments
uv run python scripts/prepare_blind_review.py \
  --results experiments/dataset_test_finetuned_results.csv --output-dir experiments/review --force
```

ملاحظات منهجية:

- المجموعة A تتلقى نفس AST findings التي تتلقاها B؛ الفرق بينهما هو التنظيم والمراجعة، بينما تتلقى Group C قائمة `findings=[]` (دور واحد بلا AnalysisAgent)، ولذلك يتعامل الـAdapter فيها مع الحالات وكأنها clean-control مما يثبت عمليًا أهمية تعدد الأدوار (C `0.4583` مقابل D `0.9167`).
- الحالات الأربع الوحيدة المرفوضة في Group D هي حالات `long-parameter-list` (4/32 = 12.5%): النموذج أنتج تحويل `@dataclass` الصحيح مطابقًا لبيانات التدريب، لكن `ReviewAgent._signature_violations()` يرفض أي تغيير في التوقيع قبل الاختبار. على الأنواع السبعة الحافظة للتوقيع حققت Group D نسبة `28/28` (`100.0%`).
- نجاح clean-control يعني ترك كود نظيف دون تغيير مع الحفاظ على سلوكه، ويُعرض منفصلًا عن نجاح حالات findings.
- `--candidates N` يختار بين المرشحين بتحليل AST فقط، بلا تنفيذ أي مرشح (NFR01).
- التشغيل الفعلي تم بمسار **native fp16 LoRA** (`load_in_4bit=false`, `optim=adamw_torch`) وليس QLoRA 4-bit.
