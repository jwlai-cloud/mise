#!/usr/bin/env python3
"""Tell me exactly what is still blocking AWS, and nothing else.

Run it before and after each setup step. Every check is read-only and costs
nothing; the model invocation uses a 1-token response.

    python3 infra/preflight.py                    # default region from ADR-0004
    AWS_REGION=ap-southeast-2 python3 infra/preflight.py

Exit code is the number of blocked checks, so it also works in a shell guard:

    python3 infra/preflight.py && echo "ready to deploy"
"""
from __future__ import annotations

import os
import sys

REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL = os.getenv("MISE_VISION_MODEL",
                  "us.anthropic.claude-haiku-4-5-20251001-v1:0" if REGION.startswith("us")
                  else "au.anthropic.claude-haiku-4-5-20251001-v1:0")
ROLE = os.getenv("MISE_RUNTIME_ROLE", "mise-runtime")

OK, BLOCKED, WARN = "  ok  ", "BLOCKED", " warn "
results: list[tuple[str, str, str]] = []


def check(label: str, fn) -> None:
    try:
        detail = fn()
        results.append((OK, label, detail or ""))
    except Exception as exc:
        name = type(exc).__name__
        msg = str(exc)
        code = ""
        if hasattr(exc, "response"):
            code = exc.response.get("Error", {}).get("Code", "")
        # An entitlement gap is not a permissions gap, and the difference is the
        # whole point of this script - they need different fixes.
        if "use case details" in msg or "use case" in msg.lower():
            results.append((BLOCKED, label, "Anthropic use-case form not submitted (step 1)"))
        elif code in ("AccessDeniedException", "AccessDenied") or "not authorized" in msg:
            action = ""
            if "perform: " in msg:
                action = msg.split("perform: ")[1].split()[0]
            results.append((BLOCKED, label, f"missing IAM action: {action or code}"))
        elif code in ("ResourceNotFoundException",) and "runtime" in label.lower():
            results.append((WARN, label, "nothing created yet — expected before first deploy"))
        else:
            results.append((BLOCKED, label, f"{code or name}: {msg[:90]}"))


def main() -> int:
    try:
        import boto3
    except ImportError:
        print("boto3 not installed.  pip install -e '.[aws]'")
        return 1

    sts = boto3.client("sts", region_name=REGION)
    ident = sts.get_caller_identity()
    print(f"\nidentity   {ident['Arn']}")
    print(f"region     {REGION}")
    print(f"model      {MODEL}\n")

    br = boto3.client("bedrock", region_name=REGION)
    brt = boto3.client("bedrock-runtime", region_name=REGION)
    acc = boto3.client("bedrock-agentcore-control", region_name=REGION)
    iam = boto3.client("iam")

    # --- step 1: the account-level entitlement, which no policy fixes ---
    check("bedrock: invoke a model", lambda: (
        brt.converse(modelId=MODEL,
                     messages=[{"role": "user", "content": [{"text": "hi"}]}],
                     inferenceConfig={"maxTokens": 1}),
        "the form is cleared and the model answers")[1])

    # --- step 2: the deployer policy ---
    check("bedrock: list models", lambda:
          f"{len(br.list_foundation_models()['modelSummaries'])} models visible")
    check("bedrock: list inference profiles", lambda:
          f"{len(br.list_inference_profiles()['inferenceProfileSummaries'])} profiles")
    check("agentcore: memory", lambda:
          f"{len(acc.list_memories().get('memories', []))} memories")
    check("agentcore: runtimes", lambda:
          f"{len(acc.list_agent_runtimes().get('agentRuntimes', []))} runtimes")
    check("agentcore: evaluators", lambda:
          f"{len(acc.list_evaluators().get('evaluators', []))} evaluators")
    check("agentcore: datasets", lambda:
          f"{len(acc.list_datasets().get('datasets', []))} datasets")

    # --- step 3: the runtime execution role ---
    check(f"iam: role {ROLE} exists", lambda:
          iam.get_role(RoleName=ROLE)["Role"]["Arn"])

    # --- the deploy substrate, usually already present ---
    check("ecr", lambda: "reachable" if boto3.client(
        "ecr", region_name=REGION).describe_repositories(maxResults=1) else "")
    check("s3", lambda: f"{len(boto3.client('s3').list_buckets()['Buckets'])} buckets")
    check("cloudwatch logs", lambda: "reachable" if boto3.client(
        "logs", region_name=REGION).describe_log_groups(limit=1) else "")

    width = max(len(l) for _, l, _ in results)
    blocked = 0
    print("─" * (width + 46))
    for status, label, detail in results:
        print(f"[{status}] {label:<{width}}  {detail}")
        blocked += status == BLOCKED
    print("─" * (width + 46))

    if blocked:
        print(f"\n{blocked} blocked. See infra/SETUP.md — the steps are ordered so that "
              "each one unblocks the next.")
    else:
        print("\nAll clear. MISE_VISION_BACKEND=graph will run against real models.")
    return blocked


if __name__ == "__main__":
    sys.exit(main())
