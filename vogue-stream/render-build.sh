#!/usr/bin/env bash
set -o errexit

CURRENT_DIR=$(pwd)
STORAGE_DIR=/opt/render/project/.render

# 1. Instalace systémových knihoven pro Chrome (nutné pro headless mód)
echo "...Installing system dependencies"
apt-get update && apt-get install -y \
  wget \
  curl \
  gnupg \
  libnss3 \
  libatk1.0-0 \
  libatk-bridge2.0-0 \
  libcups2 \
  libdrm2 \
  libxkbcommon0 \
  libxcomposite1 \
  libxdamage1 \
  libxfixes3 \
  librandr2 \
  libgbm1 \
  libasound2

# 2. Instalace Chrome
if [[ ! -d $STORAGE_DIR/chrome ]]; then
  echo "...Downloading Chrome"
  mkdir -p $STORAGE_DIR/chrome
  cd $STORAGE_DIR/chrome
  wget -P ./ https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  dpkg -x ./google-chrome-stable_current_amd64.deb $STORAGE_DIR/chrome
  rm ./google-chrome-stable_current_amd64.deb
  cd $CURRENT_DIR
else
  echo "...Using Chrome from cache"
fi

export PATH="${PATH}:/opt/render/project/.render/chrome/opt/google/chrome"

# 3. Instalace Python balíčků
pip install -r requirements.txt
