"""Rebuild TRANSCRIPT.md from the logs of the last `run_demo.sh` run."""

import datetime
import pathlib
import platform
import re
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
LOGS = HERE / "logs"


def _hardware() -> str:
    try:
        cpu = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
        mem = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout.strip()) // (1 << 30)
        return f"{cpu}, {mem} GB unified memory, macOS"
    except Exception:  # noqa: BLE001
        return platform.platform()


def _versions() -> str:
    import torch
    import transformers

    device = "MPS, float16" if torch.backends.mps.is_available() else "CPU"
    return f"Python {platform.python_version()}, torch {torch.__version__} ({device}), transformers {transformers.__version__}, kbnf grammar-guard fork"


def main() -> None:
    client = (LOGS / "client.log").read_text().rstrip()
    server_lines = [l for l in (LOGS / "server.log").read_text().splitlines() if "grammar_guard_demo.server" in l or "Uvicorn running" in l]
    proxy_lines = [l for l in (LOGS / "proxy.log").read_text().splitlines() if "formatron.proxy" in l or re.search(r'"(POST|GET) /', l)]
    today = datetime.date.today().isoformat()
    out = f"""# Transcript of one full run

Verbatim output of `./run_demo.sh` on {today}: {_hardware()},
{_versions()}.
Nothing below was edited; the model output is exactly what `Qwen/Qwen2.5-0.5B-Instruct`
produced under the grammar, and the rejection bodies are exactly what the proxy returned.
Regenerate with `python transcript.py` after a run.

- Client transcript: `client.py` talking to the proxy on `:8080` (`logs/client.log`).
- Server timing lines: the `grammar_guard_demo.server` logger on `:8000` (`logs/server.log`).
- Proxy decisions: the `formatron.proxy` logger on `:8080` (`logs/proxy.log`).

## Client transcript

```text
{client}
```

## Server timing lines

```text
{chr(10).join(server_lines)}
```

## Proxy decisions

```text
{chr(10).join(proxy_lines)}
```
"""
    (HERE / "TRANSCRIPT.md").write_text(out)
    print(f"wrote {HERE / 'TRANSCRIPT.md'} ({len(out):,} chars)")


if __name__ == "__main__":
    main()
