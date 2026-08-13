#!/usr/bin/env bash
# CeliumNeUR build box bootstrap (idempotent).
# Target: Ubuntu 24.04, dedicated-CPU droplet. Installs:
#   - base deps (curl, tmux, git)
#   - OSS CAD Suite (pinned daily build 2026-08-12) into /opt/oss-cad-suite
#   - uv (Astral) for user 'build' + Python 3.12 + venv ~/venvs/neuro
#   - cocotb + pytest inside that venv
# Run as root on the fresh droplet. Safe to re-run.
set -euo pipefail

OCS_TARBALL_URL="https://github.com/YosysHQ/oss-cad-suite-build/releases/download/2026-08-12/oss-cad-suite-linux-x64-20260812.tgz"
BUILD_USER="build"

echo "==> apt basics"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq curl ca-certificates tmux git rsync >/dev/null

echo "==> user ${BUILD_USER}"
if ! id -u "${BUILD_USER}" >/dev/null 2>&1; then
    useradd -m -s /bin/bash "${BUILD_USER}"
    mkdir -p "/home/${BUILD_USER}/.ssh"
    cp /root/.ssh/authorized_keys "/home/${BUILD_USER}/.ssh/authorized_keys"
    chown -R "${BUILD_USER}:${BUILD_USER}" "/home/${BUILD_USER}/.ssh"
    chmod 700 "/home/${BUILD_USER}/.ssh"
    chmod 600 "/home/${BUILD_USER}/.ssh/authorized_keys"
fi

echo "==> OSS CAD Suite"
if [ ! -x /opt/oss-cad-suite/bin/yosys ]; then
    tmp=$(mktemp -d)
    curl -sSL -o "${tmp}/ocs.tgz" "${OCS_TARBALL_URL}"
    mkdir -p /opt
    tar -xzf "${tmp}/ocs.tgz" -C "${tmp}"
    mv "${tmp}/oss-cad-suite" /opt/oss-cad-suite
    rm -rf "${tmp}"
fi
chmod -R a+rX /opt/oss-cad-suite
cat > /etc/profile.d/oss-cad-suite.sh <<'EOF'
export PATH=/opt/oss-cad-suite/bin:$PATH
EOF

echo "==> uv + venv for ${BUILD_USER}"
su - "${BUILD_USER}" <<'EOSU'
set -euo pipefail
if [ ! -x "$HOME/.local/bin/uv" ]; then
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
fi
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.12 >/dev/null
if [ ! -d "$HOME/venvs/neuro" ]; then
    uv venv "$HOME/venvs/neuro" --python 3.12 >/dev/null
fi
uv pip install --python "$HOME/venvs/neuro/bin/python" -q -r "$HOME/celiumneur/requirements-lock.txt" 2>/dev/null || \
  uv pip install --python "$HOME/venvs/neuro/bin/python" -q cocotb==2.0.1 pytest==9.1.1
EOSU

# Convenience env for build shells (written BEFORE the smoke so a smoke
# hiccup never leaves the box half-configured).
cat > "/home/${BUILD_USER}/.neuro_env" <<'EOF'
export PATH=/opt/oss-cad-suite/bin:$HOME/.local/bin:$PATH
export LD_LIBRARY_PATH=/home/build/.local/share/uv/python/cpython-3.12.13-linux-x86_64-gnu/lib
EOF
chown "${BUILD_USER}:${BUILD_USER}" "/home/${BUILD_USER}/.neuro_env"

echo "==> smoke (non-fatal: report and continue)"
export PATH=/opt/oss-cad-suite/bin:$PATH
yosys -V | head -1 || true
iverilog -V 2>&1 | head -1 || true
sby --version 2>&1 | head -1 || true
su - "${BUILD_USER}" -c 'venvs/neuro/bin/python -c "import cocotb, pytest; print(\"cocotb\", cocotb.__version__, \"| pytest\", pytest.__version__)"' || true
echo "==> DONE bootstrap"
