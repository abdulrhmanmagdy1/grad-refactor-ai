# Reference runner safety

The reference runner executes server-owned reference tests against a proposed function so that behavior can be checked (T20). It is a hardening layer for **trusted demonstration cases and model-generated candidates**, not a sandbox for arbitrary or hostile code. The API offers only the cases in `src/refactor_ai/fixtures/demo_cases.json`; callers choose a case by id and cannot submit paths, tests, commands or URLs. Code: [src/refactor_ai/verification/runner.py](../../src/refactor_ai/verification/runner.py), [runner_child.py](../../src/refactor_ai/verification/runner_child.py), [policy.py](../../src/refactor_ai/verification/policy.py) and [_winjob.py](../../src/refactor_ai/verification/_winjob.py).

## How one run works

1. **Static admission** (in the service process, syntax trees only): the candidate must parse as exactly one top-level function inside the [task constraints](../requirements/task-scope.md). The runner also refuses any reference to a denied builtin (for example `f = eval`, unless the name is a local variable) and `getattr`/`hasattr`/`setattr`/`delattr` unless the attribute name is a string literal that does not start with an underscore. Refused candidates are `not_run`; a candidate that does not parse is a `fail` (`missing_function`) without starting a process.
2. **Process start**: the base interpreter (not the virtual environment's launcher) runs `runner_child.py` with `-I -S -B -X utf8`: isolated mode, no site packages, no bytecode writes. The environment is empty except `SYSTEMROOT` on Windows. The working directory is a new temporary directory. The case's tests and the candidate are sent once over stdin as JSON.
3. **Operating-system limits**. Windows: the process is created suspended and without a console, assigned to a Job Object (committed memory, user CPU time, one active process, UI restrictions, kill on close, no error dialog), membership is confirmed, and only then are its threads resumed; if any step fails the suspended process is killed. Linux: the child applies `RLIMIT_AS` (memory), `RLIMIT_CPU`, `RLIMIT_NPROC` = 0, `RLIMIT_FSIZE` = 0 and `RLIMIT_CORE` = 0 before any candidate code and refuses to run if that fails; the process starts in a new session so the whole group can be killed.
4. **Audit hook** (first statement in the child). Always refused: sockets, process creation and signalling (`subprocess`, `os.system`, `os.exec*`, `os.spawn*`, `os.posix_spawn`, `os.fork`, `os.kill`, `os.startfile`), `ctypes`, the Windows API (`_winapi`), registry and `msvcrt`, file system changes, environment changes, new audit hooks and threads. Once candidate code can run: imports of network, process, native-code and introspection modules, every file write (inside the temporary directory too), file reads and listings outside the interpreter's library directories and the temporary directory, frame and code access (`sys._getframe`, `tb_frame`, `gi_frame`, tracing, `gc`), and resource-limit changes.
5. **Execution**: the candidate is compiled and the test literals are parsed (`ast.literal_eval`) before the hook switches to its strict phase. The function runs in a namespace without `open`, `exec`, `eval`, `compile`, `print`, `input` and the other denied builtins. Each test compares the return value by type and value (floats and complex numbers with `math.isclose`, relative tolerance 1e-9, recursively in lists, tuples and dicts) or the raised exception by its type name.
6. **Result channel**: results are lines tagged with a random per-run nonce, written to a private copy of the stdout descriptor; descriptor 1 points to the null device before candidate code runs. Output is capped (256 KiB) and lines without the nonce are ignored.
7. **Limits and cleanup**: a wall-clock timeout (10 s by default, lowered to the time left in the workflow run) terminates the job or process group. Afterwards the runner confirms that no process of the job or group is left and removes the temporary directory. A timeout at the runner's own wall-clock or CPU limit counts against the candidate (`fail`, kind `timeout`). A timeout at the lowered limit means the run's time ran out, not the candidate's: the result is `not_run` (disposition `uncertain`), unless a test that already finished failed (`fail`) or could not be evaluated (`error`).

Defaults (`RunnerLimits`): 10 s wall clock, 5 s CPU, 256 MB memory, one process, at most 200 tests, 20,000 candidate characters.

## Isolation checklist

`SubprocessReferenceRunner.info()` runs these probes once per runner (about 5 s on the demonstration laptop, 10 s when the laptop was busy) and caches the result. Execution is enabled only when every check passes; otherwise every run returns `not_run` with the names of the failed checks, and `/health` shows the same `isolation` dictionary. `REFACTOR_AI_RUNNER=disabled` disables execution without running the probes.

| Check | What the probe does | Windows | Linux |
|---|---|---|---|
| `basic_execution` | A small function passes four tests, including keyword arguments and an expected exception | child process | child process |
| `os_limits_applied` | The limits are in place before candidate code runs | Job Object membership confirmed | child reports `rlimit` |
| `audit_hook_installed` | The child reports its hook | audit hook | audit hook |
| `environment_scrubbed` | The child's environment holds no other variable | `SYSTEMROOT` only | at most `LC_CTYPE`, which the interpreter itself sets when it coerces the C locale (PEP 538) |
| `working_directory_isolated` | The child runs in the new temporary directory | yes | yes |
| `workdir_removed` | The temporary directory is gone afterwards | yes | yes |
| `network_blocked` | `socket.create_connection` to a local listener and `import _socket` are refused, and the listener received nothing | audit hook | audit hook |
| `file_write_blocked` | `io.open(path, "w")` and `os.open(path, O_WRONLY or O_CREAT)` outside the temporary directory are refused and no file appears | audit hook | audit hook (and `RLIMIT_FSIZE`) |
| `host_read_blocked` | Reading a file outside the library directories is refused | audit hook | audit hook |
| `subprocess_blocked` | `subprocess.run` and `os.system` are refused and the would-be child leaves no marker file | audit hook | audit hook |
| `process_limit_enforced` | With the hook switched off, `subprocess.run` fails and no marker file appears | Job active-process limit | `RLIMIT_NPROC` |
| `native_code_blocked` | `import ctypes` is refused | audit hook | audit hook |
| `introspection_blocked` | `sys._getframe` is refused | audit hook | audit hook |
| `memory_limit_enforced` | Allocating the limit plus 64 MB raises `MemoryError` inside the child | Job process memory limit | `RLIMIT_AS` |
| `timeout_enforced` | An endless loop is stopped at the 1 s wall-clock limit | job terminated | process group killed |
| `process_cleanup` | No process of the job or group is left after a timeout | job accounting | `killpg(0)` |
| `cpu_limit_enforced` | A busy loop is stopped by a 1 s CPU limit | job user-time limit | `SIGXCPU` |
| `platform_supported`, `interpreter_found` | Windows or Linux, and the base interpreter exists | yes | yes |

**Result on the demonstration laptop** (Windows 11 Home, Python 3.11.9, no administrator rights, no Docker; 2026-10-20): all 19 checks passed and execution is enabled. All six demonstration cases' original and reference code passed their 52 tests in the runner. The Linux column is covered by the same tests: the Ubuntu job of GitHub Actions run 39418314923 (2026-10-20, commit 5549a77) passed `tests/test_runner.py` and `tests/test_runner_child.py` as a non-root user. If a check fails on a host, the runner disables itself rather than running without that layer.

The probes and the refusal of each attack are also covered by `tests/test_runner.py` (real processes, Windows and Linux) and `tests/test_runner_child.py` (the hook's policy table and the result mapping, without installing a hook in the test process):

```
python -m uv run pytest tests/test_runner.py tests/test_runner_child.py
python -m uv run python -c "from refactor_ai.verification import create_runner; print(create_runner().info())"
```

## Honest limits

- **Not a security boundary for hostile code.** The audit hook and the comparison code run in the same interpreter as the candidate. Python-level defenses can be bypassed by code that reaches interpreter internals; the static admission policy closes the usual routes (imports, dunder access, computed attribute names, denied builtins), but there is no proof that it closes all of them. This is acceptable only because the executed functions are model proposals for server-owned demonstration cases.
- **No operating-system network or file system boundary.** Network access is refused by the audit hook only; there are no firewall rules, AppContainer, network namespace or container (the laptop has no administrator rights and no Docker). File reads outside the library directories and all writes are refused by the hook, not by the operating system.
- **No privilege boundary.** The test process runs as the same user as the service, with the same access token on Windows and the same user id on Linux. NFR02's privilege limit is met only by the job or resource limits and the audit hook. A restricted token or AppContainer on Windows, and a separate user with user and network namespaces or a rootless container on Linux, would add a real boundary; they are future work.
- **Linux process limit and root.** `RLIMIT_NPROC` does not apply to root. When the service runs as root (for example in a container or a Kaggle session), the runner starts the test process as the unprivileged user and group 65534 (`nobody`) with no supplementary groups and hands it the temporary directory, so the process limit applies again. A first Kaggle evaluation run on 2026-10-20, before this change, reported `process_limit_enforced` as failed and therefore ran no reference tests.
- **Result integrity.** Results carry a random nonce on a private descriptor, and frame access is refused, so candidate code that stays inside the policy cannot forge results. Code that escaped the static policy could tamper with the comparison inside its own process.
- **Limit precision.** Windows enforces the CPU-time limit with a delay (a 1 s limit stopped a busy loop after about 1.5 s of CPU time). Windows limits committed memory and Linux limits address space, so the same number does not mean exactly the same thing on both.
- **Resource use.** Each run starts an interpreter (about 0.3 s on the laptop). The self-checks cost about 5 to 10 s on first use of a runner; the service should call `info()` at startup.
- **Prompts are not affected by the runner**, but reference-test failure details (inputs, expected and actual values) are shown to the model in the correction prompt; see [the workflow](../architecture/workflow.md).
