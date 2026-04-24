#!/usr/bin/env bash
set -euo pipefail

PHASE="${1:-}"

if [ -z "$PHASE" ]; then
  echo "Uso: $0 <numero-da-fase>"
  echo "Exemplo: $0 14"
  exit 1
fi





PHASE_DIR="$(find .planning/phases -maxdepth 1 -type d -name "${PHASE}-*" | head -n 1)"

if [ -z "$PHASE_DIR" ]; then
  echo "Erro: diretório da fase ${PHASE} não encontrado em .planning/phases"
  exit 1
fi

PHASE_SLUG="$(basename "$PHASE_DIR" | sed "s/^${PHASE}-//")"
BRANCH_NAME="gsd/phase-${PHASE}-${PHASE_SLUG}"
WORKTREE_DIR="../worktrees/phase-${PHASE}-${PHASE_SLUG}"

echo "==> Criando worktree ${WORKTREE_DIR} na branch ${BRANCH_NAME}"

git fetch --all --prune

if [ -d "$WORKTREE_DIR" ]; then
  echo "Worktree ${WORKTREE_DIR} já existe, Reutilizando..."
else
  echo "Worktree ${WORKTREE_DIR} não existe, Criando..."

  if git show-ref --verify --quiet "refs/heads/${BRANCH_NAME}"; then
    git worktree add "$WORKTREE_DIR" "$BRANCH_NAME"
  else
    git worktree add -b "$BRANCH_NAME" "$WORKTREE_DIR"
  fi  
fi



cd "$WORKTREE_DIR"


run_gsd() {
  local command="$1"
  shift

  echo "==> Rodando: ${command} $*"
  opencode run -m github-copilot/grok-code-fast-1 --command "$command" "$@"
}

echo "==> Planejando fase ${PHASE}"
run_gsd gsd-plan-phase "$PHASE"


SUMMARY_FILE="$(find .planning/phases -maxdepth 2 -type f -name "${PHASE}-*-SUMMARY.md" | head -n 1)"

if [ -n "$SUMMARY_FILE" ]; then
  echo "==> Summary encontrado: $SUMMARY_FILE"
  echo "==> Fase ${PHASE} já executada. Rodando verify-work..."
  run_gsd gsd-verify-work "$PHASE"
else
  echo "==> Summary não encontrado."
  echo "==> Executando fase ${PHASE}..."
  run_gsd gsd-execute-phase "$PHASE"

  SUMMARY_FILE="$(find .planning/phases -maxdepth 2 -type f -name "${PHASE}-*-SUMMARY.md" | head -n 1)"

  if [ -n "$SUMMARY_FILE" ]; then
    echo "==> Summary encontrado após execução: $SUMMARY_FILE"
    echo "==> Verificando trabalho da fase ${PHASE}"


    MAX_REVIEW_ROUNDS=10
    REVIEW_ROUND=1
    REVIEW_APPROVED="false"

    while [ "$REVIEW_ROUND" -le "$MAX_REVIEW_ROUNDS" ]; do
      echo "==> Code review deep - rodada ${REVIEW_ROUND}/${MAX_REVIEW_ROUNDS}"

      run_gsd gsd-code-review "$PHASE" "--depth=deep"

      REVIEW_FILE="$(find .planning/phases -maxdepth 2 -type f \( -name "${PHASE}-*-REVIEW.md" -o -name "${PHASE}-REVIEW.md" \) | head -n 1)"

      if [ -z "$REVIEW_FILE" ]; then
        echo "Erro: arquivo de review não encontrado após gsd-code-review"
        exit 1
      fi

      echo "==> Review encontrado: $REVIEW_FILE"

      if grep -Eiq "status: clean" "$REVIEW_FILE"; then
        echo "==> Review aprovado"
        REVIEW_APPROVED="true"
        break
      fi

      if [ "$REVIEW_ROUND" -eq "$MAX_REVIEW_ROUNDS" ]; then
        echo "Erro: review não atingiu qualidade mínima após ${MAX_REVIEW_ROUNDS} rodadas"
        exit 1
      fi

      echo "==> Review ainda possui bloqueios. Rodando fix..."
      run_gsd gsd-code-review-fix "$PHASE"

      REVIEW_ROUND=$((REVIEW_ROUND + 1))
    done

    run_gsd gsd-verify-work "$PHASE"
  else
    echo "Erro: Summary não encontrado após execução da fase ${PHASE} - ele deveria existir se a fase foi executada corretamente. Bloco de execução falhou."
    exit 1
  fi
fi




UAT_FILE="$(find .planning/phases -maxdepth 2 -type f -name "${PHASE}-UAT.md" | head -n 1)"


TMP_DIR=".tmp/uat-phase-${PHASE}"

if [ -z "$UAT_FILE" ]; then
  echo "Erro: arquivo ${PHASE}-UAT.md não encontrado em .planning/phases"
  exit 1
fi

mkdir -p "$TMP_DIR"

echo "==> Executando UAT automatizado da fase ${PHASE}"
opencode run -m github-copilot/grok-code-fast-1 --agent build <<EOF
Execute automatically only the tests from ${UAT_FILE}.
Do not look for UAT.md in the repository root.
Use only paths inside the current repository.

If a test needs temporary files, create them under ${TMP_DIR}, NEVER USE THE /tmp.

Do not run tests that require:
- human interaction
- browser login
- external credentials
- manual validation

Report:
- passed
- failed
- skipped
- exact commands executed
- Keep UAT markdown updated.
EOF


TOTAL="$(awk -F': ' '/^total:/ {print $2}' "$UAT_FILE")"
PASSED="$(awk -F': ' '/^passed:/ {print $2}' "$UAT_FILE")"

if [ "$TOTAL" = "$PASSED" ]; then
  echo "==> Todos os testes UAT passaram. Rodando comando..."
  opencode run -m github-copilot/grok-code-fast-1 --command gsd-ship ${PHASE}

else
  echo "==> UAT ainda não passou totalmente: passed=${PASSED}, total=${TOTAL}"
fi