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

    if all_repos == False and 'repos' not in cfg.sections():
        click.echo('No repositories specification has been found', err=True)
        sys.exit(7)


def label_spec(s, cfg, template_repo):
    if template_repo:
        return {l['name']: l['color'] for l in get_resource(s, 'repos/' + template_repo + '/labels')}
    elif cfg.get('others', 'template-repo', fallback=False):
        return {l['name']: l['color'] for l in get_resource(s, 'repos/' + cfg['others']['template-repo'] + '/labels')}
    else:
        return dict(cfg['labels'])


def repos_spec(s, cfg, all_repos):
    if all_repos:
        return list(repo['full_name'] for repo in get_resource(s, 'user/repos'))
    return [repo for repo in cfg['repos'] if cfg['repos'].getboolean(repo)]


def add_label(s, repo, label, color):
    data = json.dumps({'name': label, 'color': color})
    return s.post(prepare_url('repos/' + repo + '/labels'), data=data)


def update_label(s, repo, old_label, new_label, color):
    data = json.dumps({'name': new_label, 'color': color})
    return s.patch(prepare_url('repos/' + repo + '/labels/' + old_label), data=data)


def delete_label(s, repo, label):
    return s.delete(prepare_url('repos/' + repo + '/labels/' + label))


def change_label(s, act, repo, old_label, new_label, color, dry, verbose, quiet):
    if not dry:
        if act == 'ADD':
            r = add_label(s, repo, new_label, color)
        elif act == 'UPD':
            r = update_label(s, repo, old_label, new_label, color)
        else:
            r = delete_label(s, repo, old_label)
        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError:
            if verbose and not quiet:
                click.echo('[{}][ERR] {}; {}; {}; {} - {}'.format(
                    act, repo, old_label if act == 'DEL' else new_label, color, r.status_code, r.json()['message'],
                    err=True))
            elif not (not verbose and quiet):
                click.echo('ERROR: {}; {}; {}; {}; {} - {}'.format(
                    act, repo, old_label if act == 'DEL' else new_label, color, r.status_code, r.json()['message'],
                    err=True))
            return 1

    if verbose and not quiet:
        click.echo('[{}][{}] {}; {}; {}'.format(act, 'DRY' if dry else 'SUC', repo, old_label if act == 'DEL' else new_label, color))
    return 0


def change_labels(s, repo, labels, mode, dry, verbose, quiet):
    err = 0
    old_labels = {l['name']: l['color'] for l in get_resource(s, 'repos/' + repo + '/labels')}

    lower_new = {l.lower(): {'name': l, 'color': c} for l, c in labels.items()}
    lower_old = {l.lower(): {'name': l, 'color': c} for l, c in old_labels.items()}

    # add
    add = set(lower_new) - set(lower_old)
    for l in add:
        err += change_label(s, 'ADD', repo, None, lower_new[l]['name'], lower_new[l]['color'], dry, verbose, quiet)

    # update
    upd = {l.lower() for l, _ in set(labels.items()) - set(old_labels.items())} - add
    for l in upd:
        err += change_label(s, 'UPD', repo, lower_old[l]['name'], lower_new[l]['name'], lower_new[l]['color'], dry, verbose, quiet)

    # delete
    if mode == 'replace':
        for l in set(lower_old) - set(lower_new):
            err += change_label(s, 'DEL', repo, lower_old[l]['name'], None, lower_old[l]['color'], dry, verbose, quiet)

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

    err = 0
    for repo in repos:
        try:
            err += change_labels(s, repo, labels, mode, dry_run, verbose, quiet)
        except requests.exceptions.HTTPError as e:
            if verbose and not quiet:
                click.echo('[LBL][ERR] {}; 404 - Not Found'.format(repo))
            elif not (not verbose and quiet):
                r = e.response
                click.echo('ERROR: LBL; {}; {} - {}'.format(
                    repo, r.status_code, r.json()['message'],
                    err=True))
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
