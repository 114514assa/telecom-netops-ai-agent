"""Windows-friendly PDF API smoke test using the project's existing httpx dependency.

Usage:
  python -m scripts.demo_pdf_input --pdf tests/fixtures/documented_interface_excerpt.pdf
  python -m scripts.demo_pdf_input --pdf ... --incident data/...json --kind interface --start
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx


def main() -> None:
    p = argparse.ArgumentParser(description="Test read-only PDF text extraction or submit explicitly scoped CLI evidence")
    p.add_argument("--pdf", type=Path, required=True)
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--token", default="", help="Demo reader token; omit when local auth is off")
    p.add_argument("--start", action="store_true", help="Start diagnosis from a CLI PDF instead of extract-only")
    p.add_argument("--kind", choices=["terminal", "interface", "mac", "arp", "vlan"], default="interface")
    p.add_argument("--incident", type=Path, help="UTF-8 JSON file containing incident object or {'incident':{...}}")
    p.add_argument("--port", default="", help="Observed port, e.g. GE0/0/15")
    args = p.parse_args()
    if not args.pdf.is_file():
        p.error(f"PDF file not found: {args.pdf}")
    if args.start and args.incident is None:
        p.error("--start requires --incident")
    data = {}
    if args.start:
        loaded = json.loads(args.incident.read_text(encoding="utf-8"))
        incident = loaded.get("incident", loaded)
        data["incident_json"] = json.dumps(incident, ensure_ascii=False)
        data["evidence_kind"] = args.kind
        if args.port:
            data["observed_port"] = args.port
    endpoint = "/api/v1/incidents/from-pdf" if args.start else "/api/v1/documents/pdf/extract"
    headers = {"X-Demo-Token": args.token} if args.token else {}
    with args.pdf.open("rb") as f:
        with httpx.Client(timeout=120) as client:
            response = client.post(args.base_url.rstrip("/") + endpoint,
                                   files={"file": (args.pdf.name, f, "application/pdf")},
                                   data=data, headers=headers)
    print(f"HTTP status: {response.status_code}")
    print(json.dumps(response.json(), ensure_ascii=False, indent=2)[:5000])
    response.raise_for_status()


if __name__ == "__main__":
    main()
