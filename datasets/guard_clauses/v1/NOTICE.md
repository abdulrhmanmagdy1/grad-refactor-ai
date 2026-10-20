# Notices for guard_clauses-v1

This dataset (`records.jsonl`, `metadata.jsonl`, `manifest.json`) is built by `python -m uv run python scripts/curate_dataset.py`; see the [data plan](../../../docs/data-and-training/data-plan.md). Each record's `license`, `source`, `source_url` and `provenance` fields identify where its code comes from.

## Team-authored records (795 records, license `LicenseRef-team-authored-pending`)

The functions were produced by the template families in `src/refactor_ai/data/families/`, written for this project by the coding agent on behalf of the team. They contain no third-party code. A redistribution license has not been chosen yet; this is pending a team decision, and until then these records should not be redistributed outside the project.

## MBPP (3 records, license `CC-BY-4.0`)

Records `gc1-mbpp-task-47`, `gc1-mbpp-task-113` and `gc1-mbpp-task-605` contain code from the Mostly Basic Python Problems dataset, licensed under the Creative Commons Attribution 4.0 International license (CC-BY-4.0) as declared on the Hugging Face dataset card google-research-datasets/mbpp (<https://huggingface.co/datasets/google-research-datasets/mbpp>). The file used is `mbpp/mbpp.jsonl` from google-research/google-research at commit f82046ba5aabbbb427dbfd38a254d26bff08b533. Changes: line endings normalized, trailing spaces removed (syntax tree unchanged); the target code is our reference transformation of that function; the test inputs include the task's own test calls plus derived variations.

Citation: Austin, J., Odena, A., Nye, M., Bosma, M., Michalewski, H., Dohan, D., Jiang, E., Cai, C., Terry, M., Le, Q. and Sutton, C. (2021). Program Synthesis with Large Language Models. arXiv:2108.07732.

## HumanEval (1 record, license `MIT`)

Record `gc1-humaneval-95` contains the prompt and canonical solution of HumanEval/95 from openai/human-eval at commit 463c980b59e818ace59f6f9803cd92c749ceae61 (`data/HumanEval.jsonl.gz`), used under the MIT License reproduced below. Changes: line endings normalized and leading blank lines removed; the target code is our reference transformation.

Citation: Chen, M., Tworek, J., Jun, H., Yuan, Q., Pinto, H. P. de O., Kaplan, J., et al. (2021). Evaluating Large Language Models Trained on Code. arXiv:2107.03374.

```text
The MIT License

Copyright (c) OpenAI (https://openai.com)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```
