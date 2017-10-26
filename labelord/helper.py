import click
import functools
import sys
import configparser
from urllib.parse import urljoin


def setup_session(ctx):
    """Setup requests' Session object to communicate with GitHub API."""
    s = ctx.obj['session']
    token = ctx.obj['token']
    cfg = ctx.obj['config']
    s.headers = {'User-Agent': 'Python'}
    s.auth = functools.partial(token_auth, token=get_token(cfg, token))


def get_token(cfg, token):
    """Return GitHub access token. The token is provided as '-t/--token
    parameter, in evironment variable 'GITHUB_TOKEN' or in configuration
    file."""
    try:
        token = token if token else cfg['github']['token']
    except KeyError:
        click.echo('No GitHub token has been provided', err=True)
        sys.exit(3)
    return token


def parse_config(path):
    """Parse the configuration file with ConfigParser."""
    # parse config
    cfg = configparser.ConfigParser()
    # make option names case sensitive
    cfg.optionxform = str
    # if config file does not exist 'cfg' will be empty
    cfg.read(path)
    return cfg


def get_config_repos(cfg):
    """Return list of repositories configured in configuration file."""
    try:
        repos = {r for r in cfg['repos'] if cfg['repos'].getboolean(r)}
    except KeyError:
        click.echo('No repositories specification has been found', err=True)
        sys.exit(7)
    return repos


def get_webhook_secret(cfg):
    """Return secret for GitHub webhook."""
    try:
        webhook_secret = cfg['github']['webhook_secret']
    except KeyError:
        click.echo('No webhook secret has been provided', err=True)
        sys.exit(8)
    return webhook_secret


def token_auth(req, token):
    """Token auth handler."""
    req.headers['Authorization'] = 'token ' + token
    return req


def prepare_url(resource, endpoint='https://api.github.com'):
    """Prepare URL for GitHub API."""
    return urljoin(endpoint, resource)
