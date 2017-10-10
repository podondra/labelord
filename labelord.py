import re
import sys
import functools
import click
import requests
import configparser


def token_auth(req, token):
    req.headers['Authorization'] = 'token ' + token
    return req


@click.group('labelord')
@click.option('-c', '--config', default='./config.cfg', type=click.Path())
@click.option('-t', '--token', envvar='GITHUB_TOKEN')
@click.pass_context
def cli(ctx, config, token):
    # use this session for communication with GitHub
    session = ctx.obj.get('session', requests.Session())
    # save session in context
    # if the session already exists reassign the same session
    ctx.obj['session'] = session

    cfg = configparser.ConfigParser()
    # if config file does not exist 'cfg' will be empty
    cfg.read(config)

    try:
        the_token = token if token else cfg['github']['token']
    except KeyError:
        click.echo('No GitHub token has been provided')
        sys.exit(3)

    session.headers = {'User-Agent': 'Python'}
    session.auth = functools.partial(token_auth, token=the_token)


@cli.command()
@click.pass_context
def list_repos(ctx):
    # TODO: add required options/arguments
    # TODO: implement the 'list_repos' command
    session = ctx.obj['session']

    # TODO url creation
    url = 'https://api.github.com/user/repos?per_page=100&page=1'
    while True:
        r = session.get(url)

        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError:
            # TODO separate function
            click.echo('GitHub: ERROR {} - {}'.format(r.status_code,
                r.json()['message']))
            if r.status_code == 401:
                sys.exit(4)
            else:
                sys.exit(10)

        for repo in r.json():
            click.echo(repo['full_name'])

        # TODO control statements and url matching
        link = r.headers.get('link', None)
        if link is None:
            break
        else:
            next_page = re.match('<(.*)>; rel="next"', link)
            if next_page is None:
                break
            url = next_page.group(1)



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
