"""Tests for the QLoRA training helpers and offline token audit (NFR05/NFR06)."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def load_script(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


train_lora = load_script("train_lora", "training/train_lora.py")
audit_tokens = load_script("audit_tokens", "scripts/audit_tokens.py")


def test_config_requires_a_real_model_id(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"model_id": "CHOOSE_AFTER_FEASIBILITY", "model_revision": "main"}),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        train_lora._load_config(config)


def test_config_defaults_match_the_accuracy_plan(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"model_id": "Qwen/Qwen2.5-Coder-3B-Instruct", "model_revision": "main"}),
        encoding="utf-8",
    )
    loaded = train_lora._load_config(config)
    assert loaded["max_length"] == 2048
    assert loaded["lora_rank"] == 16
    assert loaded["lora_alpha"] == 32
    assert loaded["load_in_4bit"] is True
    assert loaded["target_modules"] == "all-linear"


class FakeTokenizer:
    pad_token_id = 0
    eos_token_id = 2
    eos_token = "<eos>"
    pad_token = "<pad>"
    unk_token_id = 0

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        text = "\n".join(message["content"] for message in messages)
        if add_generation_prompt:
            return f"PROMPT {text} ASSISTANT"
        return f"PROMPT {text} ASSISTANT RESPONSE END"

    def __call__(self, text, add_special_tokens=False):
        return {"input_ids": [len(word) for word in text.split()]}

    def convert_tokens_to_ids(self, token):
        return 5 if token == "<|im_end|>" else 0


def test_training_example_uses_chat_template_and_masks_the_prompt():
    row = {
        "prompt": "def f(items):\n    return items\n",
        "completion": "def f(items):\n    return list(items)\n",
    }
    input_ids, labels = train_lora._tokenize_example(FakeTokenizer(), row, 5)
    assert len(input_ids) == len(labels)
    assert -100 in labels
    assert labels[-1] != -100
    assert labels[0] == -100


def test_proxy_audit_passes_and_flags_over_limit(tmp_path):
    row = {
        "id": "r1",
        "split": "train",
        "prompt": "def f(x):\n    return x\n",
        "completion": "def f(x):\n    return x\n",
    }
    report = audit_tokens.audit([row], max_length=10_000)
    assert report["exact"] is False
    assert report["status"] == "pass"

    failing = audit_tokens.audit([row], max_length=1)
    assert failing["status"] == "fail"
    assert failing["over_limit"][0]["id"] == "r1"
