#!/usr/bin/env bash
# Shared devbox environment repairs for reproducible verification.

prepare_cocotb_vvp() {
  local tool_root=/opt/oss-cad-suite
  if [ ! -x "$tool_root/libexec/vvp" ] || [ ! -x "$tool_root/lib/ld-linux-x86-64.so.2" ]; then
    echo "OSS CAD Suite vvp runtime not found under $tool_root" >&2
    return 2
  fi

  CELIUMNEUR_VVP_SHIM=$(mktemp -d /tmp/celiumneur-vvp.XXXXXX)
  cat > "$CELIUMNEUR_VVP_SHIM/vvp" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
tool_root=/opt/oss-cad-suite
if [ -n "${PYGPI_PYTHON_BIN:-}" ]; then
  unset PYTHONHOME
  export PYTHONEXECUTABLE="$PYGPI_PYTHON_BIN"
else
  export PYTHONHOME="$tool_root"
  export PYTHONEXECUTABLE="$tool_root/bin/tabbypy3"
fi
exec "$tool_root/lib/ld-linux-x86-64.so.2" \
  --inhibit-cache --inhibit-rpath "" \
  --library-path "$tool_root/lib" "$tool_root/libexec/vvp" "$@"
EOF
  chmod 0755 "$CELIUMNEUR_VVP_SHIM/vvp"
  export PATH="$CELIUMNEUR_VVP_SHIM:$PATH"
}

cleanup_cocotb_vvp() {
  if [ -n "${CELIUMNEUR_VVP_SHIM:-}" ] && [ -d "$CELIUMNEUR_VVP_SHIM" ]; then
    rm -f -- "$CELIUMNEUR_VVP_SHIM/vvp"
    rmdir -- "$CELIUMNEUR_VVP_SHIM"
  fi
}
