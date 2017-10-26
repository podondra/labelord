from .cli import cli
from .web import LabelordWeb


__all__ = [cli]

# http://flask.pocoo.org/docs/0.12/patterns/packages/
# instantiate LabelordWeb app
# be careful with configs this is module-wide variable
# you want to be able to run CLI app as it was in task 1
app = LabelordWeb(__name__)


import labelord.views
