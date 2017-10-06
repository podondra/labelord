import click
import requests


@click.group('labelord')
@click.pass_context
def cli(ctx):
    # TODO: add and process required app-wide options
    # you can/should use context 'ctx' for passing
    # data and objects to commands

    # use this session for communication with github
    session = ctx.obj.get('session', requests.Session())


@cli.command()
@click.pass_context
def list_repos(ctx):
    # TODO: add required options/arguments
    # TODO: implement the 'list_repos' command
    ...


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
