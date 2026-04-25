#!/usr/bin/env bash
set -euo pipefail

PHASE="${1:-}"

if [ -z "$PHASE" ]; then
  echo "Uso: $0 <numero-da-fase>"
  echo "Exemplo: $0 14"
  exit 1
fi



WORKTREE_DIR="../worktrees/phase-${PHASE}"
BRANCH_NAME="gsd/phase-${PHASE}"


echo "==> Criando worktree ${WORKTREE_DIR} na branch gsd/phase-${PHASE}"

git fetch --all --prune

if [ -d "$WORKTREE_DIR" ]; then
  echo "Worktree ${WORKTREE_DIR} já existe, Reutilizando..."
else
  echo "Worktree ${WORKTREE_DIR} não existe, Criando..."

  if git show-ref --verify --quiet "refs/heads/${BRANCH_NAME}"; then
    git worktree add "$WORKTREE_DIR" "gsd/phase-${PHASE}"
  else
    git worktree add -b "gsd/phase-${PHASE}" "$WORKTREE_DIR"
  fi  
fi



cd "$WORKTREE_DIR"


run_gsd() {
  local command="$1"
  shift

  echo "==> Rodando: ${command} $*"
  opencode run -m github-copilot/grok-code-fast-1 --agent build --command "$command" "$@"
}


code-review() {
  
    MAX_REVIEW_ROUNDS=10
    REVIEW_ROUND=1
    REVIEW_APPROVED="false"

    while [ "$REVIEW_ROUND" -le "$MAX_REVIEW_ROUNDS" ]; do
      echo "==> Code review deep - rodada ${REVIEW_ROUND}/${MAX_REVIEW_ROUNDS}"

      run_gsd gsd-code-review ""$@" --depth=deep"

      REVIEW_FILES="$(
  find .planning/phases -maxdepth 2 -type f \
    \( \
      -name "${PHASE}-*-REVIEW.md" \
      -o -name "${PHASE}-REVIEW.md" \
      -o -name "${PHASE}-*-REVIEW-FIX.md" \
      -o -name "${PHASE}-REVIEW-FIX.md" \
    \) \
  | sort
)"

      if [ -z "$REVIEW_FILES" ]; then
        echo "Erro: arquivo de review não encontrado após gsd-code-review"
        exit 1
      fi

      echo "==> Review encontrado: $REVIEW_FILES"

      while IFS= read -r REVIEW_FILE; do
          echo "==> Verificando review: $REVIEW_FILE"

          if grep -Eiq "status: *(clean|all_fixed)" "$REVIEW_FILE"; then
            echo "==> OK: $REVIEW_FILE"
          else
            echo "==> Ainda não aprovado: $REVIEW_FILE"
            REVIEW_APPROVED="false"
          fi
      done <<< "$REVIEW_FILES"

      if [ "$REVIEW_APPROVED" = "true" ]; then
          echo "==> Todos os arquivos de review estão aprovados"
          break
      fi

      if [ "$REVIEW_ROUND" -eq "$MAX_REVIEW_ROUNDS" ]; then
        echo "Erro: review não atingiu qualidade mínima após ${MAX_REVIEW_ROUNDS} rodadas"
        exit 1
      fi

      echo "==> Review ainda possui bloqueios. Rodando fix..."
      run_gsd gsd-code-review-fix ""$@""

      REVIEW_ROUND=$((REVIEW_ROUND + 1))
    done

}

echo "==> Planejando fase ${PHASE}"
run_gsd gsd-plan-phase "$PHASE"


PLAN_FILE="$(find .planning/phases -maxdepth 2 -type f -name "${PHASE}-*-PLAN.md" | head -n 1)"

if [ -n "$PLAN_FILE" ]; then
  echo "==> Plan encontrado: $PLAN_FILE"
  echo "==> Executando fase ${PHASE}..."
  run_gsd gsd-execute-phase "$PHASE --validate"
else
  echo "Erro: Plan não encontrado para a fase ${PHASE}"
  exit 1
fi


SUMMARY_FILE="$(find .planning/phases -maxdepth 2 -type f -name "${PHASE}-*-SUMMARY.md" | head -n 1)"

if [ -n "$SUMMARY_FILE" ]; then
  echo "==> Summary encontrado: $SUMMARY_FILE"
  echo "==> Fase ${PHASE} já executada. Rodando verify-work..."

  code-review "$PHASE"

  run_gsd gsd-verify-work "$PHASE"
else
  echo "==> Summary não encontrado."
  echo "==> Executando fase ${PHASE}..."
  run_gsd gsd-execute-phase "$PHASE --validate"

  SUMMARY_FILE="$(find .planning/phases -maxdepth 2 -type f -name "${PHASE}-*-SUMMARY.md" | head -n 1)"

  if [ -n "$SUMMARY_FILE" ]; then
    echo "==> Summary encontrado após execução: $SUMMARY_FILE"
    echo "==> Verificando trabalho da fase ${PHASE}"

    code-review "$PHASE"
    
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
opencode run -m github-copilot/grok-code-fast-1  <<EOF
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