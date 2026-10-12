"""Expected retrieval requests using already-supported biological query surfaces."""
import json
import socket
from datetime import date
from pathlib import Path
from unittest.mock import patch

from bve.se.acquisition import connectors as c

packet = Path('/tmp/target_reference_identity_surface_diagnosis_v1')
baseline = json.loads((packet / 'consumer_baseline.json').read_text())
rows = []
with patch.object(socket.socket, 'connect', side_effect=AssertionError('network prohibited')) as guard:
    for case in baseline['reference_cases']:
        if not case['reference'].startswith('TARGET:'):
            continue
        row = {'entity_id': case['reference'], 'surface': case['surface'],
               'aliases': case['targets'][0]['aliases'],
               'attribution': case['attribution'], 'policy_expected': 'ACCEPT', 'requests': {}}
        target = c.TargetQuery(canonical_id=row['surface'], aliases=row['aliases'])
        for name in case['connectors']:
            requests = []
            def capture(*args):
                requests.append(list(args))
                return []
            connector = (
                c.CrossrefConferenceConnector(c.ConferenceVenue(
                    source_family='conference_asco', publisher='Fixture',
                    container_titles=['Fixture Journal']), search_fn=capture)
                if name == 'CrossrefConferenceConnector' else getattr(c, name)(search_fn=capture)
            )
            health = connector.acquire(None, targets=[target], modality_terms=['antibody'],
                                       as_of_date=date(2026, 10, 12))
            assert health.connector_succeeded
            assert all('TARGET:' not in str(request) for request in requests)
            row['requests'][name] = requests
        rows.append(row)
    assert guard.call_count == 0
(packet / 'surface_request_oracle.json').write_text(json.dumps({
    'basis': 'Existing connector behavior with biological canonical surface and the exact aliases already returned by the certified ontology ID. Not a new resolver or source implementation.',
    'rows': rows, 'network_calls': 0}, indent=2, sort_keys=True, default=str) + '\n')
print('frozen', len(rows), 'entities across', sum(len(r['requests']) for r in rows), 'connector cases')
