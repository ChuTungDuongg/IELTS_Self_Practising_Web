#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

printf 'Starting IELTS development environment...\n\n'
printf 'Frontend: http://localhost:3000\n'
printf 'Backend:  http://localhost:8000\n\n'
printf 'Press Ctrl+C to stop both.\n\n'

# Give each service its own process group so its child processes stop together.
set -m
"$repo_root/dev-frontend.sh" &
frontend_pid=$!
"$repo_root/dev-backend.sh" &
backend_pid=$!

cleanup() {
  trap - EXIT INT TERM
  kill -TERM -- "-$frontend_pid" "-$backend_pid" 2>/dev/null || true
  wait "$frontend_pid" "$backend_pid" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

status=0
wait -n "$frontend_pid" "$backend_pid" || status=$?
# A development server returning successfully still means the stack stopped.
if (( status == 0 )); then
  status=1
fi
exit "$status"
