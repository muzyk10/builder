#!/bin/bash
# runs given python commands inside a Builder container.
# just like `.project.py`, the contents of stdout will be read by a YAML parser

set -e

# errcho() { echo "$@" 1>&2; } # writes to stderr, will not be interpreted as YAML
# errcho "debug"

if [ -e .use-python-3.flag ]; then
    image=py3
else
    image=py2
fi

# skips building image each time
#if ! docker inspect --type=image "elifesciences/builder:$image" > /dev/null; then
    time docker build \
        -f "Dockerfile.${image}" \
        -t "elifesciences/builder:${image}" \
        . \
        1>&2
#fi

mkdir -p .cfn/stacks .cfn/keypairs .cfn/contexts .cfn/terraform logs
touch logs/app.log

docker run \
  -v "$(pwd)":/srv/builder \
  -w /srv/builder \
  "elifesciences/builder:${image}" \
  /venv/bin/python -B "$@"
