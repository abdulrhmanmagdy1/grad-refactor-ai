# Python Multi Agent Refactoring Platform

منصة مشروع تخرج لتحليل كود Python واقتراح Refactoring باستخدام عدة Agents، مع تخصيص موديل مفتوح الأوزان بالتدريب وتقييم النتائج.

**الحالة الحالية:** بيئة تأسيس وتوثيق v0.1. الموديل لم يُختَر أو يُدرَّب بعد. المسار المتاح حاليًا تحليل بنيوي للكود دون تشغيله؛ ليس نظام الـAgents النهائي.

## ابدأ من هنا

- [فهرس التوثيق](docs/README.md)
- [المقترح للدكتورة](docs/proposal/project-proposal.md)
- [الخطة خلال ثمانية أسابيع](docs/planning/roadmap.md)
- [تشغيل البيئة](docs/development/setup.md)
- [طريقة الشغل والتاسكات](CONTRIBUTING.md)
- [التيم والمسؤوليات](docs/planning/team.md)
- [لوحة العمل والروابط](docs/planning/github-workspace.md)
- [تاسكات المشروع](docs/planning/task-index.md)
- [خطوات أول يوم](docs/development/first-day.md)

## تشغيل سريع

ثبّت Git وPython 3.11 وuv من مصادرهم الرسمية، ثم:

```bash
uv sync --frozen
uv run uvicorn refactor_ai.api:app --reload --host 127.0.0.1
```

افتح http://127.0.0.1:8000/docs لتجربة API، أو http://127.0.0.1:8000/health لفحص الخدمة.

```bash
uv run python scripts/doctor.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python scripts/check_docs.py
```

## حدود النسخة المستهدفة

Python فقط، ومدخلات صغيرة موثوقة في النسخة التجريبية، وأنواع Refactoring يتم اعتمادها بعد تجربة الجدوى. لا تعتمد الخطة على API مدفوع أو GPU مضمون. مراجعة الدكتورة مطلوبة عند نهاية كل مرحلة، وتُسجل ملاحظاتها كتاسكات.

## المحتويات

`src/` للخدمة، `tests/` للاختبارات، `training/` للتدريب، `configs/` للإعدادات، `experiments/` لسجلات التجارب، `docs/` للتوثيق و`planning/` لقائمة العمل الأولية.

يحفظ GitHub الكود والتوثيق والخطة وسجلات التجارب. تُحفظ المخرجات الصغيرة في المستودع أو GitHub Releases حسب طبيعتها. تُحسم أحجام الأوزان والبيانات وحدود GitHub المجانية في مرحلة الجدوى قبل اعتماد التخزين؛ لا توجد خدمة تخزين مدفوعة ضمن الخطة.
