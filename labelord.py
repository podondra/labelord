import re
import sys
import json
import functools
import click
import requests
import configparser
from urllib.parse import urljoin


# TODO add docstrings


def token_auth(req, token):
    req.headers['Authorization'] = 'token ' + token
    return req


def get_token(cfg, token):
    try:
        token = token if token else cfg['github']['token']
    except KeyError:
        click.echo('No GitHub token has been provided', err=True)
        sys.exit(3)
    return token


def prepare_url(resource, endpoint='https://api.github.com'):
    return urljoin(endpoint, resource)


def get_resource(s, resource):
    url = prepare_url(resource)
    r = s.get(url, params={'per_page': 100, 'page': 1})

    while True:
        r.raise_for_status()
        # yield each item
        for item in r.json():
            yield item
        # next page
        try:
            url = r.links['next']['url']
        except KeyError:
            break
        r = s.get(url)


def get_repos(s):
    return (repo['full_name'] for repo in get_resource(s, 'user/repos'))


def get_labels(s, reposlug):
    return ((label['name'], label['color'])
            for label in get_resource(s, 'repos/' + reposlug + '/labels'))


def check_spec(cfg, template_repo, all_repos):
    if template_repo is None and 'labels' not in cfg.sections() and \
            cfg.get('others', 'template_repo', fallback=None) is None:
        click.echo('No labels specification has been found', err=True)
        sys.exit(6)

    if all_repos == False and 'repos' not in cfg.sections():
        click.echo('No repositories specification has been found', err=True)
        sys.exit(7)


def label_spec(s, cfg, template_repo):
    if template_repo:
        return dict(get_labels(s, template_repo))
    elif cfg.get('others', 'template_repo', fallback=False):
        return dict(get_labels(s, cfg['others']['template_repo']))
    else:
        return dict(cfg['labels'])


def repos_spec(s, cfg, all_repos):
    if all_repos:
        return list(get_repos(s))
    return [repo for repo in cfg['repos'] if cfg['repos'].getboolean(repo)]


def add_label(s, repo, label, color):
    data = json.dumps({'name': label, 'color': color})
    return s.post(prepare_url('repos/' + repo + '/labels'), data=data)


def update_label(s, repo, label, color):
    data = json.dumps({'name': label, 'color': color})
    return s.patch(prepare_url('repos/' + repo + '/labels/' + label), data=data)


def delete_label(s, repo, label):
    return s.delete(prepare_url('repos/' + repo + '/labels/' + label))


def change_label(s, act, repo, label, color, dry, verbose, quiet):
    if not dry:
        if act == 'ADD':
            r = add_label(s, repo, label, color)
        elif act == 'UPD':
            r = update_label(s, repo, label, color)
        else:
            r = delete_label(s, repo, label)
        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError:
            if r.status_code == requests.codes.not_found:
                raise
            if verbose and not quiet:
                click.echo('[{}][ERR] {}; {}; {}; {} - {}'.format(
                    act, repo, label, color, r.status_code, r.json()['message'],
                    err=True))
            return 1

    if verbose and not quiet:
        click.echo('[{}][{}] {}; {}; {}'.format(act, 'DRY' if dry else 'SUC', repo, label, color))
    return 0


def change_labels(s, repo, labels, mode, dry, verbose, quiet):
    err = 0
    old_labels = dict(get_labels(s, repo))

    # add
    add = set(labels) - set(old_labels)
    for l in add:
        err += change_label(s, 'ADD', repo, l, labels[l], dry, verbose, quiet)

    # update
    upd = {l[0] for l in set(labels.items()) - set(old_labels.items())} - add
    for l in upd:
        err += change_label(s, 'UPD', repo, l, labels[l], dry, verbose, quiet)

    # delete
    if mode == 'replace':
        for l in set(old_labels) - set(labels):
            err += change_label(s, 'DEL', repo, l, old_labels[l], dry, verbose, quiet)

    return err


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
    session.auth = functools.partial(token_auth, token=get_token(cfg, token))


@cli.command(help='List all accessible GitHub repositories.')
@click.pass_context
def list_repos(ctx):
    # https://developer.github.com/v3/repos/
    try:
        for repo in get_repos(ctx.obj['session']):
            click.echo(repo)
    except requests.exceptions.HTTPError as e:
        r = e.response
        m = 'GitHub: ERROR {} - {}'.format(r.status_code, r.json()['message'])
        click.echo(m)
        if r.status_code == requests.codes.unauthorized:
            sys.exit(4)
        sys.exit(10)


@cli.command(help='''List all labels set for a repository. REPOSLUG is
             URL-friendly version of repository name (user/repository).''')
@click.argument('reposlug')
@click.pass_context
def list_labels(ctx, reposlug):
    # https://developer.github.com/v3/issues/labels/
    try:
        for name, color in get_labels(ctx.obj['session'], reposlug):
            click.echo('#{} {}'.format(color, name))
    except requests.exceptions.HTTPError as e:
        r = e.response
        m = 'GitHub: ERROR {} - {}'.format(r.status_code, r.json()['message'])
        click.echo(m)
        if r.status_code == requests.codes.unauthorized:
            sys.exit(4)
        if r.status_code == requests.codes.not_found:
            sys.exit(5)
        sys.exit(10)


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
    s = ctx.obj['session']

    check_spec(cfg, template_repo, all_repos)
    labels = label_spec(s, cfg, template_repo)
    repos = repos_spec(s, cfg, all_repos)

    err = 0
    for repo in repos:
        try:
            err += change_labels(s, repo, labels, mode, dry_run, verbose, quiet)
        except requests.exceptions.HTTPError:
            if verbose and not quiet:
                click.echo('[LBL][ERR] {}; 404 - Not Found'.format(repo))
            err += 1

    if (verbose and quiet) or (not verbose and not quiet):
        if err:
            click.echo('SUMMARY: {} error(s) in total, please check log above'.format(err), err=True)
            sys.exit(10)
        else:
            click.echo('SUMMARY: {} repo(s) updated successfully'.format(len(repos)))
    elif verbose:
        if err:
            click.echo('[SUMMARY] {} error(s) in total, please check log above'.format(err), err=True)
            sys.exit(10)
        else:
            click.echo('[SUMMARY] {} repo(s) updated successfully'.format(len(repos)))
    elif err:
        sys.exit(10)


if __name__ == '__main__':
    cli()
