import re
import sys
import functools
import click
import requests
import configparser
from urllib.parse import urljoin


def token_auth(req, token):
    req.headers['Authorization'] = 'token ' + token
    return req


def github_get(session, resource, endpoint='https://api.github.com'):
    url = urljoin(endpoint, resource)
    return session.get(url, params={'per_page': 100, 'page': 1})


def github_error(response):
    click.echo('GitHub: ERROR {} - {}'.format(response.status_code,
               response.json()['message']), err=True)
    if response.status_code == requests.codes.unauthorized:
        sys.exit(4)
    elif response.status_code == requests.codes.not_found:
        sys.exit(5)
    else:
        sys.exit(10)


def get_github_resource(session, resource):
    response = github_get(session, resource)
    return_list = list()
    while True:
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError:
            github_error(response)

        return_list += response.json()

        try:
            url = response.links['next']['url']
        except KeyError:
            break
        response = session.get(url)
    return return_list


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


@cli.command(help='List all accessible GitHub repositories.')
@click.pass_context
def list_repos(ctx):
    # https://developer.github.com/v3/repos/
    repos = get_github_resource(ctx.obj['session'], 'user/repos')
    for repo in repos:
        click.echo(repo['full_name'])


@cli.command(help='''List all labels set for a repository. REPOSLUG is
        URL-friendly version of repository name (user/repository).''')
@click.argument('reposlug')
@click.pass_context
def list_labels(ctx, reposlug):
    # https://developer.github.com/v3/issues/labels/
    resource = 'repos/' + reposlug + '/labels'
    labels = get_github_resource(ctx.obj['session'], resource)
    for label in labels:
        click.echo('#{} {}'.format(label['color'], label['name']))


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
    # check labels specification
    if template_repo is None and 'labels' not in cfg.sections() and \
            cfg.get('others', 'template_repo', fallback=None) is None:
        click.echo('No labels specification has been found', err=True)
        sys.exit(6)

    # check repositories specification
    if all_repos == False and 'repos' not in cfg.sections():
        click.echo('No repositories specification has been found', err=True)
        sys.exit(7)


if __name__ == '__main__':
    cli(obj={})
