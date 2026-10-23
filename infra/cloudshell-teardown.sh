#!/usr/bin/env bash
# Undo infra/cloudshell-setup.sh. Paste into AWS CloudShell as an ADMIN of
# account 034355008385. Removes the mise-runtime role and the MiseDeployer
# policy (detaching it from mimir-bedrock first). Safe to re-run.
set -uo pipefail
ACCT=034355008385
POLICY=arn:aws:iam::$ACCT:policy/MiseDeployer
[ "$(aws sts get-caller-identity --query Account --output text)" = "$ACCT" ] \
  || { echo "Wrong account - sign in to $ACCT first"; exit 1; }

echo "1/2 role mise-runtime"
for p in $(aws iam list-role-policies --role-name mise-runtime --query PolicyNames --output text 2>/dev/null); do
  aws iam delete-role-policy --role-name mise-runtime --policy-name "$p"
done
for a in $(aws iam list-attached-role-policies --role-name mise-runtime --query "AttachedPolicies[].PolicyArn" --output text 2>/dev/null); do
  aws iam detach-role-policy --role-name mise-runtime --policy-arn "$a"
done
aws iam delete-role --role-name mise-runtime 2>/dev/null && echo "  deleted" || echo "  already gone"

echo "2/2 policy MiseDeployer"
aws iam detach-user-policy --user-name mimir-bedrock --policy-arn "$POLICY" 2>/dev/null && echo "  detached from mimir-bedrock" || echo "  not attached"
for v in $(aws iam list-policy-versions --policy-arn "$POLICY" --query "Versions[?!IsDefaultVersion].VersionId" --output text 2>/dev/null); do
  aws iam delete-policy-version --policy-arn "$POLICY" --version-id "$v"
done
aws iam delete-policy --policy-arn "$POLICY" 2>/dev/null && echo "  deleted" || echo "  already gone"

echo "verify (both should say gone)"
aws iam get-role --role-name mise-runtime >/dev/null 2>&1 && echo "  role STILL EXISTS" || echo "  role gone"
aws iam get-policy --policy-arn "$POLICY" >/dev/null 2>&1 && echo "  policy STILL EXISTS" || echo "  policy gone"
