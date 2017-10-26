import os
import functools
import requests
import flask
import hmac
import hashlib
from .helper import parse_config, get_config_repos, get_webhook_secret, \
                    token_auth, get_token


class LabelordWeb(flask.Flask):
    session = requests.Session()
    token = None
    webhook_secret = None
    repos = set()
    ignored_events = list()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def inject_session(self, session):
        # inject session for communication with GitHub
        # the tests will call this method to pass the testing session
        # always use session from this call (it will be called before
        # any HTTP request)
        # if this method is not called create new session
        self.session = session

    def reload_config(self):
        """Check envvar LABELORD_CONFIG and reload the config, because there
        are problems with reimporting the app with different configuration,
        this method will be called in order to reload configuration file
        check if everything is correctly set-up."""
        path = os.getenv('LABELORD_CONFIG', default='./config.cfg')
        cfg = parse_config(path)
        self.repos = get_config_repos(cfg)
        self.token = get_token(cfg, token=None)
        self.webhook_secret = get_webhook_secret(cfg)
        self.session.headers = {'User-Agent': 'Python'}
        self.session.auth = functools.partial(token_auth, token=self.token)

    def verify_signature(self, request):
        """Check the request's signature."""
        body = request.get_data()
        signature = request.headers.get('X-Hub-Signature', None)
        if signature is None:
            return False
        h = hmac.new(self.webhook_secret.encode(), body, hashlib.sha1)
        return hmac.compare_digest(('sha1=' + h.hexdigest()).encode(),
                                   signature.encode())

    def should_ignore_event(self, action, repo, label, color):
        """Check if GitHub event should be ignored."""
        item = (action, repo, label, color)
        if action == 'deleted':
            item = (action, repo, label)
        if item in self.ignored_events:
            self.ignored_events.remove(item)
            return True
        return False
