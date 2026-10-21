from refactor_ai import task_format as tf

CODE = "def f(x):\n    if x:\n        return 1\n    else:\n        return 2\n"


def test_prompt_contains_code_and_round_trips():
    messages = tf.build_refactor_messages(CODE)
    assert messages[0] == {"role": "system", "content": tf.REFACTOR_SYSTEM_PROMPT}
    assert tf.extract_submitted_code(messages[1]["content"]) == CODE
    assert tf.messages_from_prompt(messages[1]["content"]) == messages


def test_findings_are_rendered_as_notes():
    prompt = tf.build_refactor_user_prompt(
        CODE, [{"start_line": 2, "end_line": 5, "reason": "Else branch returns."}]
    )
    assert "Analysis notes:\n- lines 2-5: Else branch returns." in prompt
    assert tf.extract_submitted_code(prompt) == CODE


def test_completion_renders_and_parses():
    completion = tf.render_refactor_completion("Uses a  guard\nclause.", CODE)
    parsed = tf.parse_refactor_output(completion)
    assert parsed.error is None and not parsed.repaired
    assert parsed.code == CODE
    assert parsed.explanation == "Uses a guard clause."


def test_refactor_v2_puts_the_code_block_first():
    assert tf.PROMPT_VERSION == "refactor-v2"
    prompt = tf.build_refactor_user_prompt(CODE)
    fmt = prompt.split("Respond in exactly this format:\n", 1)[1].split("\n\nCode:", 1)[0]
    assert fmt == (
        "```python\n<the complete refactored function>\n```\nExplanation: <one or two sentences>"
    )
    completion = tf.render_refactor_completion("Guard first.", CODE)
    assert completion == f"```python\n{CODE.rstrip()}\n```\nExplanation: Guard first."


def test_parse_errors_are_typed():
    assert tf.parse_refactor_output("").error == "empty_output"
    assert tf.parse_refactor_output("I cannot help.").error == "no_code_block"
    truncated = tf.parse_refactor_output("Explanation: x\n```python\ndef f(x):\n    if")
    assert truncated.error == "unterminated_code_block"
    assert truncated.explanation == "x"


def test_parse_repairs_are_marked():
    unfenced = tf.parse_refactor_output("Explanation: done\ndef f(x):\n    return x")
    assert unfenced.repaired and unfenced.notes == ["unfenced_code"]
    assert unfenced.code == "def f(x):\n    return x\n"
    multiple = tf.parse_refactor_output(
        "```python\nx = 1\n```\nExplanation: e\n```python\ndef f():\n    return 1\n```"
    )
    assert multiple.repaired and multiple.code.startswith("def f")


def test_parse_keeps_invalid_python_for_verification():
    parsed = tf.parse_refactor_output("Explanation: e\n```python\ndef f(:\n```")
    assert parsed.error is None
    assert parsed.code == "def f(:\n"


def test_explanation_without_label_uses_surrounding_text():
    parsed = tf.parse_refactor_output("Here it is.\n```py\ndef f():\n    return 1\n```\nDone.")
    assert parsed.explanation == "Here it is. Done."


def test_unfenced_repair_stops_at_a_trailing_explanation():
    parsed = tf.parse_refactor_output(
        "def f(x):\n    if x is None:\n        return 0\n    return x + 1\n"
        "Explanation: Uses a guard clause."
    )
    assert parsed.repaired and parsed.notes == ["unfenced_code"]
    assert parsed.code == "def f(x):\n    if x is None:\n        return 0\n    return x + 1\n"
    assert parsed.explanation == "Uses a guard clause."


def test_unfenced_repair_with_leading_explanation_keeps_code_out_of_it():
    parsed = tf.parse_refactor_output("Explanation: done\ndef f(x):\n    return x")
    assert parsed.code == "def f(x):\n    return x\n"
    assert parsed.explanation == "done"
