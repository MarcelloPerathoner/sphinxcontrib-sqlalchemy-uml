"""
    sphinxcontrib.sqlalchemy-uml
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Builds UML diagrams from SQLAlchemy introspection.

    Inspect an SQLAlchemy model or database and generate an UML graph to be included
    in Sphinx-generated documents.

    The UML graph is generated in graphviz .dot format and then passed to the
    sphinxcontrib-pic directive.

    Inspect an SQLAlchemy model in one or more Python modules::

        .. sauml:: myapp.module [myapp.module2 ...]

    Inspect one or more databases::

        .. sauml:: postgresql+psycopg2://user:password@localhost:5432/database [url2 ...]

    Use it this way and it will read the password from :file:`~/.pgpass`::

        .. sauml:: postgresql+psycopg2://user@localhost:5432/database

    This also works for non-Postgres databases.  Enter the password in
    :file:`~/.pgpass` in the same way as you would for Postgres databases.

    To avoid having to repeat the same urls for every diagram default urls can
    be set (as list) in the conf.py directive: sauml_option['arguments']::

        sauml_options = {
            'arguments' : ['postgresql+psycopg2://user@localhost:5432/database', 'url2', ...],
        }

    :param string include: Whitespace-separated list of tables to include.  Use
                           either include or exclude, not both.  If none is
                           given, all tables are included.

    :param string exclude: Whitespace-separated list of tables to exclude.

    :param string include-fields: Whitespace-separated list of table fields to
                                  include.  If none is given all fields are
                                  included.

    :param bool include-indices: Include database indices.

    All parameters of the sphinxcontrib-pic directive (alt, align, caption, ...) are also
    supported.

    Parameters that will be passed verbatim to the graphviz .dot file (all
    parameters must be entered as strings in in :rfc:`3986` query format)::

    :param string dot-graph: Parameters for the graph, eg. :code:`bgcolor=transparent&rankdir=RL`
    :param string dot-node: Parameters for nodes
    :param string dot-edge: Parameters for edges
    :param string dot-table: Parameters for tables, eg. :code:`bgcolor=#e7f2fa&color=#41799e`
    :param string dot-td: Parameters for table cells

    Defaults for these parameters can be set in the conf.py directive sauml_options,
    keys: dot-graph, dot-node, dot-edge, dot-table, and dot-td::

       sauml_options = {
          'dot_graph' : { 'bgcolor' : 'transparent' },
          'dot_node'  : { 'margin'  : '0.5' },
          'dot_table' : { 'bgcolor' : '#e7f2fa', 'color' : '#2980B9' },
       }

    :copyright: Copyright 2019 by Marcello Perathoner <marcello@perathoner.de>
    :license: BSD, see LICENSE for details.

"""

import sys
import traceback
import types
import urllib.parse

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.errors import SphinxWarning, ExtensionError
from sphinx.util.osutil import ensuredir, ENOENT
from sphinx.util.docutils import SphinxDirective
from sphinx.util.logging import getLogger

import pic

import pbr.version

from . import sagraph

NAME = 'sauml'
logger = getLogger (__name__)

if False:
    # For type annotations
    from typing import Any, Dict  # noqa
    from sphinx.application import Sphinx  # noqa

__version__ = pbr.version.VersionInfo ('sqlalchemy-uml').version_string ()


class SaUmlError (ExtensionError):
    category = 'SQLAlchemy-UML error'


class SaUmlDirective (pic.PicDirective):
    """Directive to display SQLAlchemy UML Models"""

    required_arguments = 0
    optional_arguments = 999
    has_content = True

    name = NAME

    option_spec = {
        'schema'          : directives.unchanged,
        'exclude'         : directives.unchanged,
        'include'         : directives.unchanged,
        'include-fields'  : directives.unchanged,
        'include-indices' : directives.flag,
    }
    for attr in sagraph.DOT_ATTRS:
        option_spec['dot-' + attr] = directives.unchanged

    option_spec.update (pic.PicDirective.base_option_spec)

    def get_opt (self, name, default = None, required = False, parse = False):
        options = getattr (self.env.config, self.name + '_options')

        if parse:
            opt = dict (options.get (name) or {})
            opt.update (urllib.parse.parse_qsl (self.options.get (name) or ''))
        else:
            opt = self.options.get (name) or options.get (name)

        if required and opt is None:
            raise PicError (
                ':%s: option required in directive (or set %s_%s in conf.py).' % (name, self.name, name)
            )
        return opt or default


    def get_code (self):
        # env = self.state.document.settings.env
        args = types.SimpleNamespace ()

        args.arguments       = self.arguments if self.arguments else self.get_opt ('arguments', [])
        args.schema          = self.get_opt ('schema')
        args.include         = self.get_opt ('include', '').split ()
        args.exclude         = self.get_opt ('exclude', '').split ()
        args.include_fields  = self.get_opt ('include-fields', '').split ()
        args.include_indices = self.get_opt ('include-indices', False)

        if args.include and args.exclude:
            raise SaUmlError ('Use either :include: or :exclude:')

        kw = {}
        kw['content'] = '\n'.join (self.content)
        for attr in sagraph.DOT_ATTRS:
            kw[attr] = self.get_opt ('dot-' + attr, {}, parse = True)

        args.urls = []
        args.modules = []

        for argument in args.arguments:
            if '//' in argument:
                args.urls.append (argument)
            else:
                args.modules.append (argument)

        if not (args.urls or args.modules):
            raise SaUmlError ('Either :url: or :module: directive required (or conf.py).')
        if args.urls and args.modules:
            raise SaUmlError ('Both :url: and :module: directives specified.')

        try:
            if args.urls:
                data = sagraph.inspect_urls (args)
            else:
                data = sagraph.inspect_modules (args)

            return sagraph.format_as_dot (data, args, **kw)

        except Exception as e:
            raise SaUmlError ('Cannot open database: %s (%s)' % self.arguments, e)


def setup (app):
    # type: (Sphinx) -> Dict[unicode, Any]

    app.add_config_value (NAME + '_options', {}, 'env')

    for attr in sagraph.DOT_ATTRS:
        app.add_config_value (NAME + '_dot_' + attr, '', False)

    app.add_directive (NAME, SaUmlDirective)

    return {'version': __version__, 'parallel_read_safe': True}
