"""Local inference/control fixtures and domain fakes for four-view tests."""

from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from threading import Event, Thread
from uuid import uuid4

import zmq

from ax3l.entities.ExperimentView import VIEWS
from ax3l.interface.LLM import LLM


class MemoryLog:
    def __init__(self):
        self.events = []

    def log(self, name, category, level, content, **fields):
        event = dict(event_id=len(self.events) + 1, name=name, category=category,
                     log_level=level, content=content, **fields)
        self.events.append(event)
        return event['event_id']

    def update_content(self, event_id, content):
        self.events[event_id - 1]['content'] = content


class MemoryStore:
    def __init__(self, log):
        self.log = log
        self.state = None
        self.snapshots = []

    def load(self):
        return deepcopy(self.state)

    def save(self, state):
        self.state = deepcopy(state)
        self.snapshots.append(deepcopy(state))

    def comparison(self, run_id):
        events = [e for e in self.log.events if e['name'] == 'configuration_compared'
                  and e.get('process_id') == run_id]
        return json.loads(events[-1]['content']) if events else None

    def run_events(self, run_id):
        return {e['name']: e['event_id'] for e in self.log.events if e.get('process_id') == run_id}


class MemoryEvents:
    def __init__(self, log):
        self._log = log

    def log(self, *args, **kwargs):
        return self._log.log(*args, **kwargs)

    def update_content(self, event_id, content):
        self._log.update_content(event_id, content)

    def current_golden_config(self):
        events = [e for e in self._log.events if e['name'] == 'golden_config_created']
        return dict(process_id=events[-1]['process_id']) if events else None


def episodes():
    return [dict(episode=i, score=score, steps=10, epsilon=epsilon, loss=loss,
                 outcome=outcome, epsilon_injections=1, epsilon_nice_injections=2)
            for i, (score, epsilon, loss, outcome) in enumerate(
                ((0, .9, None, 'wall'), (2, .5, .8, 'snake'), (4, 0, .4, 'max_moves')), 1)]


def requested_view(request):
    text = request['messages'][0]['content'][0]['text']
    title = next(line for line in text.splitlines() if line.startswith('## Task: '))
    return title.removeprefix('## Task: ').rsplit(' ', 1)[0].lower().replace(' ', '-')


class FakeSnake:
    def __init__(self, scores=(10, 9, 12, 7)):
        self.scores = iter(scores)
        self.results = {}
        self.submissions = []

    def is_simulation_running(self):
        return False

    def get_all_time_best_run_id(self):
        return max(self.results, key=lambda key: self.results[key]['high_score']) if self.results else None

    def get_run_result(self, run_id):
        return deepcopy(self.results.get(run_id))

    def get_num_sims(self):
        return len(self.results)

    def find_config_run(self, config):
        return next((key for key in reversed(self.results) if self.results[key]['config'] == config), None)

    def submit_simulation(self, config):
        run_id = str(uuid4())
        self.results[run_id] = dict(run_id=run_id, status='completed', high_score=next(self.scores),
                                   config=deepcopy(config))
        self.submissions.append(deepcopy(config))
        return run_id

    def get_simulation_status(self, run_id):
        return self.results[run_id]['status']

    def get_analysis_episodes(self, run_id):
        return episodes()

    def get_episode_scores(self, run_id):
        return [dict(episode=row['episode'], score=row['score']) for row in episodes()]

    def get_exploration_episodes(self, run_id):
        return episodes()

    def get_reward_episodes(self, run_id):
        return episodes()

    def get_training_episodes(self, run_id):
        return episodes()


class LocalLLM:
    def __init__(self, respond=None):
        self.requests = []
        self.status = 200
        self.respond = respond or self.proposal
        self.stream_chunks = self.chunks
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                fixture.requests.append(request)
                response = fixture.respond(request)
                try:
                    self.send_response(fixture.status)
                    if request.get('stream') and fixture.status < 400:
                        self.send_header('Content-Type', 'text/event-stream')
                        self.end_headers()
                        for chunk in fixture.stream_chunks(response):
                            self.wfile.write(b'data: ' + json.dumps(chunk, ensure_ascii=False).encode() + b'\n\n')
                            self.wfile.flush()
                        self.wfile.write(b'data: [DONE]\n\n')
                        self.wfile.flush()
                    else:
                        body = json.dumps(response).encode()
                        self.send_header('Content-Type', 'application/json')
                        self.send_header('Content-Length', str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    # A timed-out client can close before its fixture reply arrives.
                    pass

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.llm = LLM(f'http://127.0.0.1:{self.server.server_port}')

    @staticmethod
    def chunks(response):
        message = response['choices'][0]['message']
        yield dict(choices=[dict(index=0, delta={key: value for key, value in message.items()
                                                if key != 'tool_calls'})])
        for index, call in enumerate(message.get('tool_calls', [])):
            function = call['function']
            yield dict(choices=[dict(index=0, delta=dict(tool_calls=[dict(
                index=index, id=call['id'], type=call['type'],
                function=dict(name=function['name'], arguments=''))]))])
            for offset in range(0, len(function['arguments']), 17):
                yield dict(choices=[dict(index=0, delta=dict(tool_calls=[dict(
                    index=index, function=dict(arguments=function['arguments'][offset:offset + 17]))]))])
        yield dict(choices=[dict(index=0, delta={}, finish_reason='tool_calls')])
        if 'usage' in response:
            yield dict(choices=[], usage=response['usage'])

    @staticmethod
    def proposal(request):
        if request['tools'][0]['function']['name'] == 'submit_observations':
            content = request['messages'][0]['content'][0]['text']
            title = content.splitlines()[0].removeprefix('## Task: ').removesuffix(' Evaluation')
            arguments = dict(observations=f'{title}: recorded training results evaluated.')
            return dict(choices=[dict(message=dict(role='assistant', tool_calls=[dict(
                id='observations', type='function', function=dict(
                    name='submit_observations', arguments=json.dumps(arguments)),
            )]))])
        properties = request['tools'][0]['function']['parameters']['properties']['values']['properties']
        view = next(view for view in VIEWS.values() if set(properties) <= set(view.parameters))
        changed = {'reward-signals': {'game.rewards.food': 12},
                   'architecture': {'model.hidden_size': 72},
                   'training': {'training.learning_rate': .002},
                   'exploration': {'epsilon.initial': .9}}[view.name]
        content = request['messages'][0]['content']
        text = content if isinstance(content, str) else content[0]['text']
        tuning = text.split('## Parameters to tune', 1)[1]
        parameters = json.loads(re.findall(r'```json\n(.*?)\n```', tuning, re.S)[0])
        primary = next(iter(changed))
        current = parameters[primary]['value']
        if current == changed[primary] or text.startswith('This configuration is a duplicate,'):
            changed[primary] = {'reward-signals': current + 1,
                               'architecture': current + 8,
                               'training': current / 2,
                               'exploration': current - .05}[view.name]
        changed.update({name: value for name, value in {
            'training.sequence_length': 8, 'training.gamma': .95,
        }.items() if name in properties})
        arguments = dict(hypothesis=f'Hypothesis for {view.name}.',
                         values=changed)
        return dict(choices=[dict(message=dict(role='assistant', content=None, tool_calls=[dict(
            id='proposal', type='function', function=dict(name='submit_view', arguments=json.dumps(arguments)),
        )]))], usage=dict(prompt_tokens=100, completion_tokens=50, total_tokens=150))

    def close(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()



class LocalSnakeControl:
    """Speak the actual SnakeLab wire protocol over a local ZeroMQ socket."""
    def __init__(self, handle):
        self.handle = handle
        self.ready, self.stop = Event(), Event()
        self.error = None
        self.endpoint = None
        self.thread = Thread(target=self.serve, daemon=True)
        self.thread.start()
        if not self.ready.wait(5):
            raise RuntimeError('Control fixture did not bind')
        if self.error:
            raise self.error

    def serve(self):
        try:
            with zmq.Context() as context, context.socket(zmq.REP) as socket:
                socket.setsockopt(zmq.LINGER, 0)
                socket.bind('tcp://127.0.0.1:*')
                self.endpoint = socket.getsockopt_string(zmq.LAST_ENDPOINT)
                self.ready.set()
                while not self.stop.is_set():
                    if socket.poll(50):
                        request = socket.recv_json()
                        result = self.handle(request['method'], request['payload'])
                        socket.send_json(dict(protocol_version=1, request_id=request['request_id'],
                                              status='ok', payload=result))
        except BaseException as error:
            self.error = error
        finally:
            self.ready.set()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise RuntimeError('Control fixture did not stop')
        if self.error:
            raise self.error


class FixtureLLM:
    """Use native tool responses without a listener for state-machine tests."""
    url = 'http://fixture/v1/chat/completions'

    def __init__(self):
        self.requests = []
        self.respond = LocalLLM.proposal

    def complete(self, payload, *, on_progress=None):
        request = json.loads(payload)
        self.requests.append(request)
        response = self.respond(request)
        if on_progress is not None:
            on_progress(response)
        return 200, '', json.dumps(response).encode()
