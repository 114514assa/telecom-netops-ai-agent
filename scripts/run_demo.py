import argparse
import json
from pathlib import Path
from uuid import uuid4

from langgraph.types import Command

from app.runtime import runtime


CASES = {
    "interface_down": "interface_down.json",
    "no_mac": "no_mac.json",
    "vlan_mismatch": "vlan_mismatch.json",
    "upstream": "upstream.json",
    "resource_mismatch": "resource_mismatch.json",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=CASES, default="vlan_mismatch")
    parser.add_argument("--reject", action="store_true")
    args = parser.parse_args()

    runtime.start()
    try:
        payload = json.loads((Path("data/sample_requests") / CASES[args.case]).read_text(encoding="utf-8"))
        thread_id = uuid4().hex
        result = runtime.graph.invoke(
            {
                "thread_id": thread_id,
                "incident": payload["incident"],
                "raw_evidence": payload["evidence"],
                "status": "created",
            },
            config={"configurable": {"thread_id": thread_id}},
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        if result.get("__interrupt__"):
            result = runtime.graph.invoke(
                Command(resume={"approved": not args.reject, "comment": "CLI demo approval"}),
                config={"configurable": {"thread_id": thread_id}},
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
