"""Create one *synthetic* request to test the local read-only collector."""
import json
from pathlib import Path
from app.core.config import get_settings


def main():
    root=Path('data/sample_requests/vlan_mismatch.json')
    source=json.loads(root.read_text(encoding='utf-8'))
    payload={'incident':source['incident'],'evidence':{'evidence_mode':'simulated_collection'}}
    out=get_settings().runtime_dir/'mock_collection_request.json'
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Wrote synthetic demo request:',out)

if __name__=='__main__':main()
