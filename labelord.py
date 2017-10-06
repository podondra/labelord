import sys
import click
import requests
import configparser


@click.group('labelord')
@click.option('-c', '--config', default='./config.cfg',
        type=click.Path())
@click.option('-t', '--token', envvar='GITHUB_TOKEN')
@click.pass_context
def cli(ctx, config, token):
    # TODO: add and process required app-wide options
    # you can/should use context 'ctx' for passing
    # data and objects to commands

    # use this session for communication with GitHub
    session = ctx.obj.get('session', requests.Session())

    ctx.obj['session'] = session

    cfg = configparser.ConfigParser()
    cfg.read(config)

    if token is None:
        try:
            token = cfg['github']['token']
        except KeyError:
            click.echo('No GitHub token has been provided')
            sys.exit(3)

    def token_auth(req):
        req.headers['Authorization'] = 'token ' + token
        return req

    session.headers = {'User-Agent': 'Python'}
    session.auth = token_auth


@cli.command()
@click.pass_context
def list_repos(ctx):
    # TODO: add required options/arguments
    # TODO: implement the 'list_repos' command
    session = ctx.obj['session']
    payload = {'per_page': 100, 'page': 1}
    r = session.get('https://api.github.com/user/repos',
            params=payload)
    for repo in r.json():
        click.echo(repo['full_name'])


@cli.command()
@click.pass_context
def list_labels(ctx):
    # TODO: add required options/arguments
    # TODO: implement the 'list_labels' command
    ...


@cli.command()
@click.pass_context
def run(ctx):
    # TODO: add required options/arguments
    # TODO: implement the 'run' command
    ...


if __name__ == '__main__':
    cli(obj={})
