#!/usr/bin/env python3
"""Add two host routes with graceful Caddy reload; preserve existing host routes."""
import json
import pathlib
import subprocess
import sys
import urllib.request

from prepare_pilot import fingerprint, write

root = pathlib.Path(sys.argv[1])
old = pathlib.Path('/home/ubuntu/unreal-auditor/review-service')
binary = old / 'deps/caddy-2.11.4/caddy'
config = old / 'public-deployment-20260911/Caddyfile'
original = config.read_text()
addition = '''

# BEGIN bug-finding single-case pilot
explore.150-230-45-149.sslip.io {
    @internal path /internal/*
    respond @internal 404
    reverse_proxy 127.0.0.1:8102
}
evaluate.150-230-45-149.sslip.io {
    @internal path /internal/*
    respond @internal 404
    reverse_proxy 127.0.0.1:8103
}
# END bug-finding single-case pilot
'''
assert '# BEGIN bug-finding single-case pilot' not in original, 'Routes already installed'
candidate = root / 'verification/Caddyfile.candidate'
backup = root / 'verification/Caddyfile.before'
write(backup, original)
write(candidate, original + addition)


def live():
    return json.load(urllib.request.urlopen('http://127.0.0.1:2019/config/'))


def legacy_routes(config):
    found = []
    def walk(value):
        if isinstance(value, dict):
            if any('review.150-230-45-149.sslip.io' in item.get('host', []) for item in value.get('match', [])):
                found.append(value)
            else:
                for item in value.values(): walk(item)
        elif isinstance(value, list):
            for item in value: walk(item)
    walk(config)
    return found


before = live()
expected = legacy_routes(before)
assert expected, 'Original review host route not found'
adapted = subprocess.run([str(binary), 'adapt', '--config', str(candidate), '--adapter', 'caddyfile'], capture_output=True, text=True, check=True)
assert legacy_routes(json.loads(adapted.stdout)) == expected, 'Existing review routes would change'
subprocess.run([str(binary), 'validate', '--config', str(candidate), '--adapter', 'caddyfile'], capture_output=True, check=True)
before_services = fingerprint(old)
try:
    config.write_text(candidate.read_text())
    subprocess.run([str(binary), 'reload', '--config', str(config), '--adapter', 'caddyfile'], capture_output=True, check=True)
    assert legacy_routes(live()) == expected
    after = fingerprint(old)
    assert before_services == after, 'Legacy service fingerprint changed'
    write(root / 'verification/public-routing.json', {'legacy_routes_unchanged': True, 'legacy_services_unchanged': True, 'added_hosts': ['explore.150-230-45-149.sslip.io', 'evaluate.150-230-45-149.sslip.io']})
    print('Added two host routes. Existing review routes and service PIDs are unchanged.')
except Exception:
    config.write_text(original)
    subprocess.run([str(binary), 'reload', '--config', str(config), '--adapter', 'caddyfile'], capture_output=True, check=True)
    raise
