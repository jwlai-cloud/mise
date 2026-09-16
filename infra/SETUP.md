# AWS setup

Four steps, ordered so each unblocks the next. Run the preflight between them —
it names the exact missing IAM action rather than making you guess.

```bash
pip install -e '.[aws]'
python3 infra/preflight.py          # tells you what is still blocked
```

Current state of account `034355008385`, user `mimir-bedrock`: **10 of 11 checks
blocked**. Only ECR is reachable.

---

## Step 1 — the Anthropic use-case form  ·  *you, in the console*

**No IAM policy works around this, and it gates every model call in every
region.** It is the long pole, so do it first.

1. Console → **Amazon Bedrock** → **Model access** (left nav)
2. Find any Anthropic model → **Available to request** / **Manage model access**
3. Fill in the use-case details form. For this project, truthfully:
   *"A cooking assistant that judges pan readiness from a camera frame and
   declines to answer when the view is obscured. Personal hackathon project;
   no end users; no data stored beyond a local threshold file."*
4. Submit, then wait. The console says 15 minutes; it can be longer.

**How you know it worked.** Before: the preflight's first line reads
`Anthropic use-case form not submitted`. That comes from Bedrock returning
`ResourceNotFoundException` with a message about the form — a confusing error
code for an entitlement gap, which is why the preflight translates it.

---

## Step 2 — attach the deployer policy  ·  *needs an admin principal*

`mimir-bedrock` cannot grant itself these. Use the account root or an admin user.

```bash
aws iam create-policy \
  --policy-name MiseDeployer \
  --policy-document file://infra/deployer-policy.json

aws iam attach-user-policy \
  --user-name mimir-bedrock \
  --policy-arn arn:aws:iam::034355008385:policy/MiseDeployer
```

Or console → **IAM** → **Policies** → **Create policy** → **JSON** tab → paste
`infra/deployer-policy.json` → attach to the user.

**What it grants, and why each part:**

| Statement | Why |
|---|---|
| `bedrock-agentcore:*`, region-scoped | Memory, Runtime, Policy, **Evaluations** and Datasets. Wildcarded because AWS publishes no minimum deployer policy — the action names have to be reverse-engineered from denial messages one call at a time. Tighten from CloudTrail after the first successful deploy. |
| Bedrock invoke + list | Model discovery is gated **separately** from invocation, so an identity can hold `InvokeModel` and still be unable to find out which model ids are valid. |
| ECR, CodeBuild, Logs, X-Ray | `agentcore deploy` packages code, builds a container and pushes it. |
| S3, prefix-scoped | Deployment artifacts. Scoped to `bedrock-agentcore-*` and `mise-*` rather than every bucket. |
| Cognito | Inbound OAuth on the Runtime — its MCP hosting path wants a `CUSTOM_JWT` authorizer. |
| IAM on `role/mise-*` only | Creating the execution role in step 3, with `PassRole` restricted to `bedrock-agentcore.amazonaws.com`. |

> `iam:*` on a deployer is privilege escalation in principle. The `role/mise-*`
> path constraint plus the `PassedToService` condition is what keeps it honest —
> this identity can only create and pass roles that AgentCore can assume.

---

## Step 3 — create the runtime execution role  ·  *after step 2*

**This is the step people miss.** Two IAM principals are needed, not one: your
deployer identity, and a separate role that AgentCore Runtime *assumes* when it
runs your container. The MCP walkthrough covers Cognito in detail and never
mentions this, so you meet it via a deploy failure.

```bash
aws iam create-role --role-name mise-runtime \
  --assume-role-policy-document file://infra/runtime-trust-policy.json

aws iam put-role-policy --role-name mise-runtime \
  --policy-name mise-runtime --policy-document file://infra/runtime-execution-policy.json

aws iam get-role --role-name mise-runtime --query Role.Arn --output text
```

The trust policy names `bedrock-agentcore.amazonaws.com` and pins
`aws:SourceAccount`, so no other account can assume it.

---

## Step 4 — verify, then run for real

```bash
python3 infra/preflight.py          # expect: All clear
```

Then the graph runs against real models with no code change:

```bash
export MISE_VISION_BACKEND=graph
export AWS_REGION=us-east-1                  # see ADR-0004
export MISE_VISION_MODEL=us.anthropic.claude-haiku-4-5-20251001-v1:0
PYTHONPATH=src uvicorn mise.app:app --port 8000
```

Point a phone at `<https-tunnel>/dev/camera` and the first accepted frame stands
the scripted pan down automatically.

### Region

ADR-0004: develop in the US, decide residency from the spike's numbers. `au.*`
profiles give Australian data residency on 4.5-generation models; `us.*` gives
frontier models without it. The deployer policy allows `us-east-1`, `us-west-2`
and `ap-southeast-2` so you can compare without editing IAM.

### Tracing

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=<your collector>
```

`mise.agents.enable_tracing()` emits a span per graph node. That waterfall is the
evidence the critic is conditional rather than decorative — it should be absent
on clear frames and present near the gate.

---

## Cost

The hot graph is one perception call per frame at ~0.3 Hz, plus a risk call, plus
a critic call only near the gate. A 90-second demo step is roughly 30 perception
+ 30 risk + a handful of critic calls on a 4.5-generation model at 640×480
(~400 visual tokens). Cents, not dollars. The `$150` hackathon credit is ample.

**Set a budget alarm anyway** — a loop left running overnight is the classic way
to find out otherwise. Console → **Billing** → **Budgets** → a $20 monthly alert
costs nothing and takes two minutes.

---

## Step 5 — the evaluators  ·  *after step 4, optional but this is the AWS Builder story*

Two evals, two objects. They are **not** alternatives and neither replaces the other:

| | scores | needs AWS |
|---|---|---|
| `evals/abstention.py` | the **pan** — one labelled corpus, offline. "Does this model read the pan to ±0.15, and decline when it can't see?" | no |
| `evals/trajectory.py` | the **agent** — real traces. "Did `perceive → critique → risk → arbitrate` fire in the right shape, and did the critic run only where a mistake was expensive?" | yes |

AgentCore Evaluations does the second and **cannot do the first**:
`StartBatchEvaluation`'s `dataSourceConfig` accepts CloudWatch log groups or an
online-eval config — never a JSONL corpus — and `Evaluate` takes OTEL
`sessionSpans`. Its `level` enum is `TOOL_CALL | TRACE | SESSION`. It is a trace
product, so the perception corpus stays where it is.

### Deploy the codeBased evaluator

`codeBased` takes a **`lambdaArn`**, not inline code, so the trajectory rules ship
as a Lambda. They are plain functions in `evals/trajectory.py` and
`tests/test_trajectory.py` exercises them offline, so the Lambda is a wrapper
rather than the only copy.

```bash
cd evals && zip -q /tmp/mise-trajectory.zip trajectory.py && cd ..

aws lambda create-function --function-name mise-trajectory \
  --runtime python3.12 --handler trajectory.lambda_handler \
  --role arn:aws:iam::034355008385:role/mise-runtime \
  --zip-file fileb:///tmp/mise-trajectory.zip --timeout 30

export MISE_TRAJECTORY_LAMBDA_ARN=$(aws lambda get-function \
  --function-name mise-trajectory --query Configuration.FunctionArn --output text)
```

`evals/trajectory.py::evaluator_definitions()` returns the two `CreateEvaluator`
bodies — the codeBased one above, and an `llmAsAJudge` for the one genuinely
judgement-shaped question ("could a cook verify that evidence sentence by
glancing at the pan?"). Their shapes are asserted against the real API enums in
`tests/test_trajectory.py`.

### Feed it traces

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=<AgentCore Observability endpoint>
```

`mise.agents.enable_tracing()` turns on the exporter. The graph emits a
`mise.frame` span carrying `doneness`, `confidence_in`, `confidence_out`, `risk`
and `wrote` — **Strands itself emits only `gen_ai.*` mechanics (tokens, tool
names), none of the domain values**, so without that span the evaluator can see
the shape of a run and none of its meaning. Then `StartBatchEvaluation` over the
log group, or `CreateOnlineEvaluationConfig` to score continuously.
