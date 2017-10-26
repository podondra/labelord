import flask
import click
from urllib.parse import urljoin
from .helper import parse_config, get_config_repos, get_webhook_secret, \
                    token_auth, prepare_url, setup_session
from labelord import app
from .cli import cli


@app.before_first_request
def configurate_app():
    """Configurate the application before first request."""
    current_app = flask.current_app
    if app.token is None or app.webhook_secret is None:
        app.reload_config()


@app.template_filter('repo_url')
def repo_url(repo):
    """Flask filter which created link to GitHub repository."""
    return urljoin('https://github.com', repo)


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
