#!/usr/bin/env bash
# Download the OCR text of the four Swarupananda scans from archive.org into $1 (default: /tmp/scans).
# Uses archive.org's text viewer, which serves the OCR text from archive.org itself.
set -euo pipefail
out="${1:-/tmp/scans}"; mkdir -p "$out"
fetch() {  # identifier, output name
  local file
  file=$(curl -s "https://archive.org/metadata/$1/files" | python3 -c "import sys,json;print(next(x['name'] for x in json.load(sys.stdin)['result'] if x['name'].endswith('_djvu.txt')))")
  curl -s "https://archive.org/stream/$1/$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$file")" \
    | python3 -c "import sys,re,html;s=sys.stdin.read();m=re.search(r'<pre[^>]*>(.*?)</pre>',s,re.S);sys.stdout.write(html.unescape(m.group(1)))" > "$out/$2"
  echo "$2: $(wc -c < "$out/$2") bytes"
}
fetch in.ernet.dli.2015.237563 swarupananda-1909-a.txt   # primary (numbered translations)
fetch in.ernet.dli.2015.386852 swarupananda-1909-b.txt   # same edition, second scan
fetch in.ernet.dli.2015.20768  swarupananda-1926.txt
fetch in.ernet.dli.2015.20770  swarupananda-1933.txt
echo "next: python scripts/ingest_swarupananda.py $out/swarupananda-1909-a.txt $out/swarupananda-1909-b.txt $out/swarupananda-1926.txt $out/swarupananda-1933.txt"
