#!/bin/bash
# Watch for changes in src/vastai/*.py and remake docs when modified.

if [ "$(which inotifywait)" == "" ]; then 
  echo "inotifywait not installed. Enter admin password to install with 'sudo apt-get install'";
  sudo apt-get install inotify-tools; 
fi

while inotifywait -e modify src/vastai/*.py; do
  [ -d html ] && rm -rf html/; pdoc --config sort_identifiers=False --html src/vastai; echo "Finished rebuilding docs in html/."
done
