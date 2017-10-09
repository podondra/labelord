import sys, os
import betamax
import pytest
import requests


ABS_PATH = os.path.abspath(os.path.dirname(__file__))
FIXTURES_PATH = ABS_PATH + '/fixtures'
CASSETTES_PATH = FIXTURES_PATH + '/cassettes'
CONFIGS_PATH = FIXTURES_PATH + '/configs'
DATA_PATH = FIXTURES_PATH + '/data'

sys.path.insert(0, ABS_PATH + '/../')

with betamax.Betamax.configure() as config:
    config.cassette_library_dir = CASSETTES_PATH
    token = os.environ.get('GITHUB_TOKEN', '<TOKEN>')
    if 'GITHUB_TOKEN' in os.environ:
        config.default_cassette_options['record_mode'] = 'once'
    else:
        config.default_cassette_options['record_mode'] = 'none'
    config.define_cassette_placeholder('<TOKEN>', token)


class Utils:

    @staticmethod
    def config(name):
        return CONFIGS_PATH + '/' + name + '.cfg'

    @staticmethod
    def load_data(name):
        with open(DATA_PATH + '/' + name + '.json') as f:
            return f.read()

    @staticmethod
    def create_auth(username, password):
        import base64
        return {
            'Authorization': 'Basic ' + base64.b64encode(
                bytes(username + ":" + password, 'ascii')
            ).decode('ascii')
        }


@pytest.fixture
def utils():
    return Utils()


class LabelordInvocation:

    def __init__(self, runner, result, session):
        self.runner = runner
        self.result = result
        self.session = session


@pytest.fixture
def invoker(betamax_session):
    from click.testing import CliRunner
    from flexmock import flexmock
    from labelord import cli

    def invoker_inner(*args, isolated=False, session_expectations=None):
        session_mock = flexmock(betamax_session or requests.Session())
        if session_expectations is not None:
            for what, count in session_expectations.items():
                session_mock.should_call(what).times(count)
        runner = CliRunner()
        args = [a for a in args if a is not None]
        if isolated:
            with runner.isolated_filesystem():
                result = runner.invoke(cli, args,
                                       obj={'session': session_mock})
        else:
            result = runner.invoke(cli, args,
                                   obj={'session': session_mock})
        return LabelordInvocation(runner, result, session_mock)
    return invoker_inner


@pytest.fixture
def invoker_norec():
    return invoker(None)


@pytest.fixture
def client_maker(betamax_session):
    def inner_maker(config, own_config_path=False,
                    session_expectations=None):
        from flexmock import flexmock

        if not own_config_path:
            config = Utils.config(config)

        session_mock = flexmock(betamax_session or requests.Session())
        if os.environ.get('LABELORD_SESSION_SPY', '').lower() != 'off' and \
           session_expectations is not None:
            for what, count in session_expectations.items():
                session_mock.should_call(what).times(count)

        os.environ['LABELORD_CONFIG'] = config
        from labelord import app
        app.inject_session(betamax_session)
        app.reload_config()
        client = app.test_client()
        return client
    return inner_maker
