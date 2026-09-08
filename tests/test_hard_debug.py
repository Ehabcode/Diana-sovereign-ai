import json
import os
import tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as tmp:
    os.environ['DIANA_DATA_DIR'] = tmp
    import sys
    sys.path.insert(0, str(Path(__file__).parents[1] / 'python'))
    import server

    server.model_call = lambda persona, messages, timeout=240: 'TEST RESPONSE'
    client = server.app.test_client()

    health = client.get('/health')
    assert health.status_code == 200
    assert health.json['status'] == 'ok'
    assert health.headers['Access-Control-Allow-Origin'] == '*'

    public = client.post('/chat', json={'message': 'hello', 'persona': 'texty'})
    assert public.status_code == 200 and public.json['response'] == 'TEST RESPONSE'
    assert (Path(tmp) / 'diana_texty_memory.json').exists()

    private = client.post('/chat', json={'message': 'secret', 'persona': 'texty', 'private': True})
    assert private.status_code == 200 and private.json['private'] is True
    public_memory = json.loads((Path(tmp) / 'diana_texty_memory.json').read_text())
    assert not any(item.get('content') == 'secret' for item in public_memory)

    created = client.post('/agents/run', json={'command': 'test task', 'mode': 'local'})
    assert created.status_code == 202
    task_id = created.json['task']['id']
    cancelled = client.post(f'/agents/tasks/{task_id}/cancel')
    assert cancelled.status_code in (200, 409)
    assert client.get(f'/agents/tasks/{task_id}').status_code == 200

    schedule = client.post('/agents/schedules', json={'name': 'test', 'command': 'repeat', 'frequency': 'interval'})
    assert schedule.status_code == 201
    schedule_id = schedule.json['schedule']['id']
    assert schedule.json['schedule']['interval_minutes'] == 5
    assert client.patch(f'/agents/schedules/{schedule_id}', json={'enabled': False}).status_code == 200
    assert client.delete(f'/agents/schedules/{schedule_id}').status_code == 200

print('HARD_DEBUG_API_OK')
