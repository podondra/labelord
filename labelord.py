import re
import sys
import functools
import click
import requests
import configparser
from urllib.parse import urljoin, urlencode


# TODO add docstrings


def token_auth(req, token):
    req.headers['Authorization'] = 'token ' + token
    return req


def prepare_url(resource, endpoint='https://api.github.com'):
    return urljoin(endpoint, resource)


def handle_error(response):
    click.echo('GitHub: ERROR {} - {}'.format(response.status_code,
               response.json()['message']), err=True)
    if response.status_code == requests.codes.unauthorized:
        sys.exit(4)
    elif response.status_code == requests.codes.not_found:
        sys.exit(5)
    else:
        sys.exit(10)


def get_resource(session, resource):
    url = prepare_url(resource)
    response = session.get(url, params={'per_page': 100, 'page': 1})

    while True:
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            handle_error(response)

        for item in response.json():
            yield item

        try:
            url = response.links['next']['url']
        except KeyError:
            break
        response = session.get(url)


def get_token(token, cfg):
    try:
        token = token if token else cfg['github']['token']
    except KeyError:
        click.echo('No GitHub token has been provided', err=True)
        sys.exit(3)
    return token


@click.group('labelord')
@click.option('-c', '--config', default='./config.cfg', type=click.Path(),
              help='Configuration file in INI format.')
@click.option('-t', '--token', envvar='GITHUB_TOKEN',
              help='Access token for GitHub API.')
@click.pass_context
def cli(ctx, config, token):
    # with 'setup.py' the ctx.obj might be None
    ctx.obj = ctx.obj if ctx.obj else {}

    # use this session for communication with GitHub
    session = ctx.obj.get('session', requests.Session())
    ctx.obj['session'] = session

    # parse config
    cfg = configparser.ConfigParser()
    # make option names case sensitive
    cfg.optionxform = str
    # if config file does not exist 'cfg' will be empty
    cfg.read(config)
    ctx.obj['config'] = cfg

    session.headers = {'User-Agent': 'Python'}
    session.auth = functools.partial(token_auth, token=get_token(token, cfg))


def get_repos(session):
    repos = get_resource(session, 'user/repos')
    return (repo['full_name'] for repo in repos)


@cli.command(help='List all accessible GitHub repositories.')
@click.pass_context
def list_repos(ctx):
    # https://developer.github.com/v3/repos/
    for repo in get_repos(ctx.obj['session']):
        click.echo(repo)


def get_labels(session, reposlug):
    labels = get_resource(session, 'repos/' + reposlug + '/labels')
    return ((label['name'], label['color']) for label in labels)


@cli.command(help='''List all labels set for a repository. REPOSLUG is
        URL-friendly version of repository name (user/repository).''')
@click.argument('reposlug')
@click.pass_context
def list_labels(ctx, reposlug):
    # https://developer.github.com/v3/issues/labels/
    for name, color in get_labels(ctx.obj['session'], reposlug):
        click.echo('#{} {}'.format(color, name))


def check_specification(cfg, template_repo, all_repos):
    # check labels specification
    if template_repo is None and 'labels' not in cfg.sections() and \
            cfg.get('others', 'template_repo', fallback=None) is None:
        click.echo('No labels specification has been found', err=True)
        sys.exit(6)

    # check repositories specification
    if all_repos == False and 'repos' not in cfg.sections():
        click.echo('No repositories specification has been found', err=True)
        sys.exit(7)


@cli.command(help='Update labels. MODE can be \'update\' or \'replace\'.')
@click.argument('mode', type=click.Choice(['update', 'replace']))
@click.option('-a', '--all-repos', is_flag=True, default=False,
              help='''Act on all repositories listed by \'list_repos\'
              subcommand.''')
@click.option('-d', '--dry-run', is_flag=True, default=False,
              help='Print actions but do not apply them on GitHub.')
@click.option('-r', '--template-repo', metavar='REPOSLUG',
              help='Template repository to specify labels.')
@click.option('-v', '--verbose', is_flag=True, default=False,
              help='Print actions to standart ouput.')
@click.option('-q', '--quiet', is_flag=True, default=False,
              help='Do not write anything to stdout or stderr.')
@click.pass_context
def run(ctx, mode, all_repos, dry_run, verbose, quiet, template_repo):
    # TODO: implement the 'run' command
    cfg = ctx.obj['config']
    session = ctx.obj['session']

    check_specification(cfg, template_repo, all_repos)

    if template_repo:
        labels = get_labels(session, template_repo)
    elif cfg.get('others', 'template_repo', fallback=False):
        labels = get_labels(session, cfg['others']['template_repo'])
    else:
        labels = ((name, color) for name, color in cfg['labels'].items())

    if all_repos:
        repos = get_repos(session)
    else:
        cfg_repos = cfg['repos']
        repos = (repo for repo in cfg_repos if cfg_repos.getboolean(repo))


if __name__ == '__main__':
    cli(obj={})
