import json, os, sys, tempfile
from pathlib import Path

with tempfile.TemporaryDirectory() as tmp:
    os.environ['DIANA_DATA_DIR'] = tmp
    sys.path.insert(0, str(Path(__file__).parents[1] / 'python'))
    import server
    server.model_call = lambda persona, messages, timeout=240: 'TEST RESPONSE'
    client = server.app.test_client()
    assert client.get('/health').json['status'] == 'ok'
    assert client.get('/health').headers['Access-Control-Allow-Origin'] == '*'
    public = client.post('/chat', json={'message':'hello','persona':'texty'})
    assert public.status_code == 200 and public.json['response'] == 'TEST RESPONSE'
    public_file = Path(tmp) / 'diana_texty_memory.json'
    assert public_file.exists()
    private = client.post('/chat', json={'message':'secret','persona':'texty','private':True})
    assert private.status_code == 200 and private.json['private'] is True
    assert not any(x.get('content') == 'secret' for x in json.loads(public_file.read_text()))
    created = client.post('/agents/run', json={'command':'test task','mode':'local'})
    assert created.status_code == 202
    task_id = created.json['task']['id']
    assert client.get('/agents/tasks/' + task_id).status_code == 200
    assert client.post('/agents/tasks/' + task_id + '/cancel').status_code in (200,409)
    routine = client.post('/agents/schedules', json={'name':'test','command':'repeat','frequency':'interval'})
    assert routine.status_code == 201 and routine.json['schedule']['interval_minutes'] == 5
    rid = routine.json['schedule']['id']
    assert client.patch('/agents/schedules/' + rid, json={'enabled':False}).status_code == 200
    assert client.delete('/agents/schedules/' + rid).status_code == 200
print('FULL_SUITE_API_OK')
