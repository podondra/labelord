import sys
import functools
import click
import flask
import os
import hmac
import hashlib
import requests
import configparser
from urllib.parse import urljoin


def token_auth(req, token):
    """Token auth handler."""
    req.headers['Authorization'] = 'token ' + token
    return req


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


def get_webhook_secret(cfg):
    """Return secret for GitHub webhook."""
    try:
        webhook_secret = cfg['github']['webhook_secret']
    except KeyError:
        click.echo('No webhook secret has been provided', err=True)
        sys.exit(8)
    return webhook_secret


def get_config_repos(cfg):
    """Return list of repositories configured in configuration file."""
    try:
        repos = {r for r in cfg['repos'] if cfg['repos'].getboolean(r)}
    except KeyError:
        click.echo('No repositories specification has been found', err=True)
        sys.exit(7)
    return repos


def setup_session(ctx):
    """Setup requests' Session object to communicate with GitHub API."""
    s = ctx.obj['session']
    token = ctx.obj['token']
    cfg = ctx.obj['config']
    s.headers = {'User-Agent': 'Python'}
    s.auth = functools.partial(token_auth, token=get_token(cfg, token))


def prepare_url(resource, endpoint='https://api.github.com'):
    """Prepare URL for GitHub API."""
    return urljoin(endpoint, resource)


def get_resource(s, resource):
    """Get resource from GitHub API. It is a generator. Handle pagitation."""
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
    """Check specification of labels and repositories for labelord's run
    command. If error is found exit with approprate code."""
    if template_repo is None and \
       'labels' not in cfg.sections() and \
       cfg.get('others', 'template_repo', fallback=None) is None:
        click.echo('No labels specification has been found', err=True)
        sys.exit(6)

    if not all_repos and 'repos' not in cfg.sections():
        click.echo('No repositories specification has been found', err=True)
        sys.exit(7)


def labels_dict(labels):
    """Return dictionary with lowercase label's names as keys and value is
    tuple of label's name and label's color."""
    return {lbl['name'].lower(): (lbl['name'], lbl['color']) for lbl in labels}


def labels_spec(s, cfg, template_repo):
    """Return labels of a repository as dictionary. Key is lowercase label's
    name and value is tuple of label and color."""
    if template_repo:
        labels = get_resource(s, 'repos/' + template_repo + '/labels')
        return labels_dict(labels)
    elif cfg.get('others', 'template-repo', fallback=False):
        repo = cfg['others']['template-repo']
        labels = get_resource(s, 'repos/' + repo + '/labels')
        return labels_dict(labels)
    else:
        return {l.lower(): (l, c) for l, c in cfg['labels'].items()}


def repos_spec(s, cfg, all_repos):
    """Return list of repositories for labelord's run command. Can be
    specified by '-a/--all-repos' option or in configuration file."""
    if all_repos:
        resource = get_resource(s, 'user/repos')
        return list(repo['full_name'] for repo in resource)
    return [repo for repo in cfg['repos'] if cfg['repos'].getboolean(repo)]


def out_spec(verbose, quiet):
    """Find out what the command line output should be."""
    if verbose and not quiet:
        return 'verbose'
    elif not verbose and quiet:
        return 'quiet'
    else:
        return 'semi'


def change_label(s, act, repo, old_label, new_label, color, dry, out):
    """Add, update or delete label in a repository."""
    l = old_label if act == 'DEL' else new_label
    if not dry:
        url = prepare_url('repos/' + repo + '/labels')
        if act == 'DEL':
            r = s.delete(url + '/' + old_label)

        data = {'name': new_label, 'color': color}
        if act == 'ADD':
            r = s.post(url, json=data)
        elif act == 'UPD':
            r = s.patch(url + '/' + old_label, json=data)

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
    """Change labels in a repository according to new_lbls."""
    err = 0
    labels = get_resource(s, 'repos/' + repo + '/labels')
    old_lbls = labels_dict(labels)

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


def parse_config(path):
    """Parse the configuration file with ConfigParser."""
    # parse config
    cfg = configparser.ConfigParser()
    # make option names case sensitive
    cfg.optionxform = str
    # if config file does not exist 'cfg' will be empty
    cfg.read(path)
    return cfg


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

    cfg = parse_config(config)
    ctx.obj['config'] = cfg
    ctx.obj['token'] = token


@cli.command(help='List all accessible repositories.')
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
        click.echo(m, err=True)
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
        click.echo(m, err=True)
        if r.status_code == requests.codes.unauthorized:
            sys.exit(4)
        if r.status_code == requests.codes.not_found:
            sys.exit(5)
        sys.exit(10)


@cli.command(help='Run labels processing.')
@click.argument('mode', type=click.Choice(['update', 'replace']),
                metavar='<update|replace>')
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
              help='No output at all')
@click.pass_context
def run(ctx, mode, all_repos, dry_run, verbose, quiet, template_repo):
    setup_session(ctx)
    s = ctx.obj['session']
    cfg = ctx.obj['config']

    check_spec(cfg, template_repo, all_repos)
    labels = labels_spec(s, cfg, template_repo)
    repos = repos_spec(s, cfg, all_repos)
    out = out_spec(verbose, quiet)

    err = 0
    for repo in repos:
        try:
            err += change_labels(s, repo, labels, mode, dry_run, out)
        except requests.exceptions.HTTPError as e:
            err += 1
            if out == 'verbose':
                m = '[LBL][ERR] {}; {} - {}'
            elif out == 'semi':
                m = 'ERROR: LBL; {}; {} - {}'
            if out != 'quiet':
                r = e.response
                code = r.status_code
                click.echo(m.format(repo, code, r.json()['message'], err=True))

    if err:
        m = '{} {} error(s) in total, please check log above'
        if out == 'verbose':
            click.echo(m.format('[SUMMARY]', err, m), err=True)
        elif out == 'semi':
            click.echo(m.format('SUMMARY:', err), err=True)
        sys.exit(10)

    m = '{} {} repo(s) updated successfully'
    if out == 'verbose':
        click.echo(m.format('[SUMMARY]', len(repos)))
    elif out == 'semi':
        click.echo(m.format('SUMMARY:', len(repos)))


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


# instantiate LabelordWeb app
# be careful with configs this is module-wide variable
# you want to be able to run CLI app as it was in task 1
app = LabelordWeb(__name__)


@app.before_first_request
def configurate_app():
    """Configurate the application before first request."""
    current_app = flask.current_app
    if app.token is None or app.webhook_secret is None:
        app.reload_config()


@app.route('/', methods=['GET', 'POST'])
def index():
    current_app = flask.current_app
    request = flask.request
    if request.method == 'GET':
        return flask.render_template('index.html', repos=current_app.repos)

    # POST method
    if not current_app.verify_signature(request):
        return '', 401

    # check event
    event = request.headers.get('X-GitHub-Event', None)
    if event == 'ping':
        return '', 200
    elif event != 'label':
        # not allowed event
        return '', 400

    response = request.get_json()

    # check repository validity
    repo = response['repository']['full_name']
    if repo not in current_app.repos:
        return '', 400

    action = response['action']
    label = response['label']['name']
    color = response['label']['color']

    if current_app.should_ignore_event(action, repo, label, color):
        return '', 200

    data = {'name': label, 'color': color}
    for r in current_app.repos - {repo}:
        url = prepare_url('repos/' + r + '/labels')

        if action == 'created':
            current_app.session.post(url, json=data)

        elif action == 'edited':
            current_app.ignored_events.append((action, r, label, color))
            try:
                label = response['changes']['name']['from']
            except KeyError:
                pass
            current_app.session.patch(url + '/' + label, json=data)

        elif action == 'deleted':
            current_app.ignored_events.append((action, r, label))
            current_app.session.delete(url + '/' + label)

        else:
            return '', 500

    return '', 200


@app.template_filter('repo_url')
def repo_url(repo):
    """Flask filter which created link to GitHub repository."""
    return urljoin('https://github.com', repo)


@cli.command(help='Run server for master-to-master replication.')
@click.option('-h', '--host', default='127.0.0.1', help='Hostname.')
@click.option('-p', '--port', default=5000, help='Server port.')
@click.option('-d', '--debug', is_flag=True, default=False, help='Debug mode.')
@click.pass_context
def run_server(ctx, host, port, debug):
    app.repos = get_config_repos(ctx.obj['config'])
    setup_session(ctx)
    app.webhook_secret = get_webhook_secret(ctx.obj['config'])
    app.inject_session(ctx.obj['session'])
    app.run(host=host, port=port, debug=debug)


if __name__ == '__main__':
    cli()
