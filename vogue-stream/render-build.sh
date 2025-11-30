#!/usr/bin/env bash
# exit on error
set -o errexit

# Uložíme si aktuální cestu, abychom se neztratili
CURRENT_DIR=$(pwd)
STORAGE_DIR=/opt/render/project/.render

if [[ ! -d $STORAGE_DIR/chrome ]]; then
  echo "...Downloading Chrome"
  mkdir -p $STORAGE_DIR/chrome
  cd $STORAGE_DIR/chrome
  wget -P ./ https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  dpkg -x ./google-chrome-stable_current_amd64.deb $STORAGE_DIR/chrome
  rm ./google-chrome-stable_current_amd64.deb
  
  # VRACÍME SE PŘESNĚ TAM, ODKUD JSME VYŠLI
  cd $CURRENT_DIR
else
  echo "...Using Chrome from cache"
fi

# Add Chrome to path
export PATH="${PATH}:/opt/render/project/.render/chrome/opt/google/chrome"

# Install Python dependencies
pip install -r requirements.txt
