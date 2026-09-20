"""Ask a running Beowulf gateway to route one task packet. Start it first: uv run jev-gateway

uv run --env-file .env python examples/gateway_client.py --token <printed token> \
  --goal 'The world selector is broken. Figure out the problem, fix it, and show me it works.'

This makes one paid TypeSafe request through the gateway. The response is a recommendation; nothing is executed.
"""

import argparse
import json
import os

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--goal", required=True)
parser.add_argument("--token", default=os.environ.get("JEV_GATEWAY_TOKEN"))
parser.add_argument("--port", type=int, default=int(os.environ.get("JEV_GATEWAY_PORT", "8767")))
parser.add_argument(
    "--executors",
    default="deterministic,kimi_explore,kimi_plan,kimi_coder,cursor,pepper,human,park",
    help="Executors that are actually available right now.",
)
args = parser.parse_args()
if not args.token:
    raise SystemExit("Pass --token or set JEV_GATEWAY_TOKEN; the gateway prints its token on start.")

host = f"127.0.0.1:{args.port}"
response = httpx.post(
    f"http://{host}/decision",
    headers={"Host": host, "X-Gateway-Token": args.token},
    json={
        "domain": "agent_router",
        "input": {"packet": {"goal": args.goal, "source": "example"}, "available_executors": args.executors.split(",")},
        "policy_context": {},
    },
    timeout=30,
)
response.raise_for_status()
body = response.json()
rec = body["recommendation"]
print(f"decision {body['decision_id']}  model {body['model_version']}  {body['latency_ms']} ms")
print(f"route -> {rec['target']}  ({rec['candidate']['task_class']}, confidence {rec['confidence']:.2f})")
print(f"policy: {body['policy']['verdict']}  {'; '.join(body['policy']['reasons']) or 'no gates tripped'}")
print(json.dumps({k: round(v, 2) for k, v in rec["flags"].items()}, indent=2))
print(json.dumps(rec["scores"], indent=2))
