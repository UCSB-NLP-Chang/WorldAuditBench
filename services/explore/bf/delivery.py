"""Retryable HTTP handoff between independent services."""
import json
import urllib.request
from .common import canonical, require


def request_json(url, data, secret, timeout=30):
    req = urllib.request.Request(url, data=canonical(data).encode(), headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + secret})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def deliver_pending(store, config):
    for row in store.delivery_batch():
        try:
            result = request_json(config['evaluation_internal'] + '/internal/submissions', json.loads(row['payload']), config['transfer_secret'])
            require(result.get('id') == row['id'] and result.get('status') == 'complete', 'Import not complete', 502)
            store.delivery_result(row['id'])
        except Exception:
            store.delivery_result(row['id'], 'Evaluation import unavailable; will retry')


def evidence_fetcher(config):
    def fetch(sid, fid):
        # Both IDs have been validated by the import contract. No arbitrary URL fetching.
        url = config['exploration_internal'] + '/internal/submissions/' + sid + '/evidence/' + fid
        req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + config['transfer_secret']})
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.read(5 * 1024 * 1024 + 1)
    return fetch
