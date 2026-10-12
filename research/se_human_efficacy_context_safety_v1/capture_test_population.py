"""Capture existing test reader calls before any behavioral change."""
import hashlib
import json
from pathlib import Path
import pytest
from bve.se.evidence import human_poc as hp

OUT = Path('/tmp/human_efficacy_context_safety_v1')
calls = {}
current = ''
original_prose = hp.efficacy_statements
original_result = hp.result_supports_human_poc

def store_call(route, inputs, outputs):
    key = hashlib.sha256(json.dumps([route, inputs], sort_keys=True).encode()).hexdigest()
    row = calls.setdefault(key, {'id': key, 'route': route, 'inputs': inputs,
                                 'baseline_outputs': outputs, 'tests': []})
    if current not in row['tests']:
        row['tests'].append(current)

def prose(text, *, asset_names, document_id=''):
    asset_names = list(asset_names)
    result = original_prose(text, asset_names=asset_names, document_id=document_id)
    store_call('prose', {'text': text, 'asset_names': asset_names, 'document_id': document_id},
               [x.model_dump(mode='json') for x in result])
    return result

def structured(result):
    value = original_result(result)
    store_call('structured', result.model_dump(mode='json'), value)
    return value

hp.efficacy_statements = prose
hp.result_supports_human_poc = structured

class Capture:
    def pytest_runtest_setup(self, item):
        global current
        current = item.nodeid

code = pytest.main(['tests/se', '-q', '-p', 'no:cacheprovider',
                    '--junitxml=/tmp/human_efficacy_context_safety_v1/baseline_tests.xml'],
                   plugins=[Capture()])
(OUT/'existing_test_population.json').write_text(json.dumps(list(calls.values()), indent=2)+'\n')
(OUT/'baseline_test_result.json').write_text(json.dumps({'exit_code':code,'reader_calls':len(calls)},indent=2)+'\n')
raise SystemExit(code)
