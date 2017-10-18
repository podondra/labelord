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


def setup_session(ctx):
    s = ctx.obj['session']
    token = ctx.obj['token']
    cfg = ctx.obj['config']
    s.headers = {'User-Agent': 'Python'}
    s.auth = functools.partial(token_auth, token=get_token(cfg, token))


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


def check_spec(cfg, template_repo, all_repos):
    if template_repo is None and \
       'labels' not in cfg.sections() and \
       cfg.get('others', 'template_repo', fallback=None) is None:
        click.echo('No labels specification has been found', err=True)
        sys.exit(6)

    if not all_repos and 'repos' not in cfg.sections():
        click.echo('No repositories specification has been found', err=True)
        sys.exit(7)


def label_spec(s, cfg, template_repo):
    if template_repo:
        labels = get_resource(s, 'repos/' + template_repo + '/labels')
        return {l['name'].lower(): (l['name'], l['color']) for l in labels}
    elif cfg.get('others', 'template-repo', fallback=False):
        repo = cfg['others']['template-repo']
        labels = get_resource(s, 'repos/' + repo + '/labels')
        return {l['name'].lower(): (l['name'], l['color']) for l in labels}
    else:
        return {l.lower(): (l, c) for l, c in cfg['labels'].items()}


def repos_spec(s, cfg, all_repos):
    if all_repos:
        resource = get_resource(s, 'user/repos')
        return list(repo['full_name'] for repo in resource)
    return [repo for repo in cfg['repos'] if cfg['repos'].getboolean(repo)]


def out_spec(verbose, quiet):
    if verbose and not quiet:
        return 'verbose'
    elif not verbose and quiet:
        return 'quiet'
    else:
        return 'semi'


def change_label(s, act, repo, old_label, new_label, color, dry, out):
    l = old_label if act == 'DEL' else new_label
    if not dry:
        url = prepare_url('repos/' + repo + '/labels')
        if act == 'DEL':
            r = s.delete(url + '/' + old_label)

        data = json.dumps({'name': new_label, 'color': color})
        if act == 'ADD':
            r = s.post(url, data=data)
        elif act == 'UPD':
            r = s.patch(url + '/' + old_label, data=data)

        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError:
            if out == 'verbose':
                m = '[{}][ERR] {}; {}; {}; {} - {}'
            elif out == 'semi':
                m = 'ERROR: {}; {}; {}; {}; {} - {}'
            if out != 'quiet':
                error = r.json()['message']
                st = r.status_code
                click.echo(m.format(act, repo, l, color, st, error), err=True)
            return 1

    if out == 'verbose':
        res = 'DRY' if dry else 'SUC'
        click.echo('[{}][{}] {}; {}; {}'.format(act, res, repo, l, color))

    return 0


def change_labels(s, repo, new_lbls, mode, dry, out):
    err = 0
    resource = get_resource(s, 'repos/' + repo + '/labels')
    old_lbls = {l['name'].lower(): (l['name'], l['color']) for l in resource}

    # add
    add = set(new_lbls) - set(old_lbls)
    for l in add:
        err += change_label(s, 'ADD', repo, None, new_lbls[l][0],
                            new_lbls[l][1], dry, out)
    # update
    upd = {l for l, _ in set(new_lbls.items()) - set(old_lbls.items())} - add
    for l in upd:
        err += change_label(s, 'UPD', repo, old_lbls[l][0], new_lbls[l][0],
                            new_lbls[l][1], dry, out)
    # delete
    if mode == 'replace':
        for l in set(old_lbls) - set(new_lbls):
            err += change_label(s, 'DEL', repo, old_lbls[l][0], None,
                                old_lbls[l][1], dry, out)

    return err


@click.group('labelord')
@click.option('-c', '--config', default='./config.cfg', type=click.Path(),
              help='Configuration file in INI format.')
@click.option('-t', '--token', envvar='GITHUB_TOKEN',
              help='Access token for GitHub API.')
@click.version_option(0.1)
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
    ctx.obj['token'] = token


@cli.command(help='List all accessible GitHub repositories.')
@click.pass_context
def list_repos(ctx):
    setup_session(ctx)
    s = ctx.obj['session']

    # https://developer.github.com/v3/repos/
    try:
        for repo in get_resource(s, 'user/repos'):
            click.echo(repo['full_name'])
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
    setup_session(ctx)
    s = ctx.obj['session']

    # https://developer.github.com/v3/issues/labels/
    try:
        for label in get_resource(s, 'repos/' + reposlug + '/labels'):
            click.echo('#{} {}'.format(label['color'], label['name']))
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
    setup_session(ctx)
    s = ctx.obj['session']
    cfg = ctx.obj['config']

    check_spec(cfg, template_repo, all_repos)
    labels = label_spec(s, cfg, template_repo)
    repos = repos_spec(s, cfg, all_repos)
    out = out_spec(verbose, quiet)

    err = 0
    for repo in repos:
        try:
            err += change_labels(s, repo, labels, mode, dry_run, out)
        except requests.exceptions.HTTPError as e:
            err += 1
            if out == 'verbose':
                click.echo('[LBL][ERR] {}; 404 - Not Found'.format(repo))
            elif out == 'semi':
                r = e.response
                click.echo('ERROR: LBL; {}; {} - {}'.format(repo,
                           r.status_code, r.json()['message'], err=True))

    if err:
        m = 'error(s) in total, please check log above'
        if out == 'verbose':
            click.echo('[SUMMARY] {} {}'.format(err, m), err=True)
        elif out == 'semi':
            click.echo('SUMMARY: {} {}'.format(err, m), err=True)
        sys.exit(10)

    m = 'repo(s) updated successfully'
    if out == 'verbose':
        click.echo('[SUMMARY] {} {}'.format(len(repos), m))
    elif out == 'semi':
        click.echo('SUMMARY: {} {}'.format(len(repos), m))


if __name__ == '__main__':
    cli()
