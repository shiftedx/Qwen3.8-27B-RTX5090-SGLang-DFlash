#!/usr/bin/env bash
set -Eeuo pipefail

# Installs Docker and NVIDIA Container Toolkit only. The Windows host driver is
# exposed through WSL; this script intentionally never installs a Linux NVIDIA driver.
if [[ "${EUID}" -ne 0 ]]; then exec sudo bash "$0" "$@"; fi
export DEBIAN_FRONTEND=noninteractive

install -m 0755 -d /etc/apt/keyrings /usr/share/keyrings
if [[ ! -s /etc/apt/keyrings/docker.gpg ]]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
fi
if [[ ! -s /etc/apt/sources.list.d/docker.list ]]; then
  . /etc/os-release
  arch="$(dpkg --print-architecture)"
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu %s stable\n' "$arch" "$VERSION_CODENAME" > /etc/apt/sources.list.d/docker.list
fi
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
if [[ ! -s /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg ]]; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
fi
if [[ ! -s /etc/apt/sources.list.d/nvidia-container-toolkit.list ]]; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' > /etc/apt/sources.list.d/nvidia-container-toolkit.list
fi
if ! dpkg-query -W -f='${Status}' nvidia-container-toolkit 2>/dev/null | grep -q 'ok installed'; then
  apt-get update
  apt-get install -y nvidia-container-toolkit
fi
nvidia-ctk runtime configure --runtime=docker
systemctl enable --now docker
systemctl restart docker
install_user="${SUDO_USER:-${USER:-}}"
if [[ -n "$install_user" && "$install_user" != root ]]; then usermod -aG docker "$install_user"; fi
docker info >/dev/null
docker run --rm --gpus all ubuntu:24.04 nvidia-smi
printf 'Docker and NVIDIA Container Toolkit are ready. Start a new WSL session before using docker without sudo.\n'
