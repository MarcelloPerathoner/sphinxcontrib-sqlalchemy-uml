"""
    sphinxcontrib.sqlalchemy-uml
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Builds UML diagrams from SQLAlchemy introspection.

    Inspect an SQLAlchemy model or database and generate an UML graph to be included
    in Sphinx-generated documents.

    The UML graph is generated in graphviz .dot format and then passed to the sphinx
    graphviz directive.

    Inspect an SQLAlchemy model in one or more Python modules::

        .. sauml:: myapp.module [myapp.module2 ...]

    Inspect one or more databases::

        .. sauml:: postgresql+psycopg2://user:password@localhost:5432/database [url2 ...]

    Use it this way and it will read the password from :file:`~/.pgpass`::

        .. sauml:: postgresql+psycopg2://user@localhost:5432/database

    This also works for non-Postgres databases.  Enter the password in
    :file:`~/.pgpass` in the same way as you would for Postgres databases.

    To avoid having to repeat the same urls for every diagram default urls can
    be set (as list) in the conf.py directive: sauml_arguments::

        sauml_arguments = [postgresql+psycopg2://user@localhost:5432/database, url2, ...]

    :param string include: Whitespace-separated list of tables to include.  Use
                           either include or exclude, not both.  If none is
                           given, all tables are included.

    :param string exclude: Whitespace-separated list of tables to exclude.

    :param string include-fields: Whitespace-separated list of table fields to
                                  include.  If none is given all fields are
                                  included.

    :param bool include-indices: Include database indices.

    All parameters of the graphviz directive (alt, align, caption, ...) are also
    supported.

    Parameters that will be passed verbatim to the graphviz .dot file (all
    parameters must be entered as strings in in :rfc:`3986` query format)::

    :param string dot-graph: Parameters for the graph, eg. :code:`bgcolor=transparent&rankdir=RL`
    :param string dot-node: Parameters for nodes
    :param string dot-edge: Parameters for edges
    :param string dot-table: Parameters for tables, eg. :code:`bgcolor=#e7f2fa&color=#41799e`
    :param string dot-td: Parameters for table cells

    Defaults for these parameters can be set in the conf.py directives:
    sauml_dot_graph, sauml_dot_node, sauml_dot_edge, sauml_dot_table, and
    sauml_dot_td::

       sauml_dot_graph = 'bgcolor=transparent'
       sauml_dot_node  = 'margin=0.5'
       sauml_dot_table = 'bgcolor=#e7f2fa&color=#2980B9'

    :copyright: Copyright 2019 by Marcello Perathoner <marcello@perathoner.de>
    :license: BSD, see LICENSE for details.
"""

import sys
import traceback
import types
import urllib.parse

from docutils import nodes
from docutils.parsers.rst import directives, Directive
from sphinx.errors import SphinxWarning, SphinxError, ExtensionError
from sphinx.util.osutil import ensuredir, ENOENT
from sphinx.ext import graphviz

import pbr.version

from . import sagraph

NAME = 'sauml'

if False:
    # For type annotations
    from typing import Any, Dict  # noqa
    from sphinx.application import Sphinx  # noqa

__version__ = pbr.version.VersionInfo ('sqlalchemy-uml').version_string ()


def setup (app):
    # type: (Sphinx) -> Dict[unicode, Any]

    app.add_config_value (NAME + '_arguments', [], False)

    for attr in sagraph.DOT_ATTRS:
        app.add_config_value (NAME + '_dot_' + attr, '', False)

    app.add_directive (NAME, SaUmlDirective)

    app.add_node (
        SaUmlNode,
        html    = (html_visit_graphviz, None),
        latex   = (graphviz.latex_visit_graphviz, None),
        texinfo = (graphviz.texinfo_visit_graphviz, None),
        text    = (graphviz.text_visit_graphviz, None),
        man     = (graphviz.man_visit_graphviz, None)
    )

    return {'version': __version__, 'parallel_read_safe': True}


class SaUmlError (SphinxError):
    category = NAME + ' error'


class SaUmlNode (graphviz.graphviz):
    pass


class SaUmlDirective (graphviz.Graphviz):
    """Directive to display SQLAlchemy Uml Models"""

    required_arguments = 0
    optional_arguments = 999
    has_content = True

    option_spec = graphviz.Graphviz.option_spec.copy ()
    del option_spec['graphviz_dot']
    option_spec.update ({
        'schema'          : directives.unchanged,
        'exclude'         : directives.unchanged,
        'include'         : directives.unchanged,
        'include-fields'  : directives.unchanged,
        'include-indices' : directives.flag,
    })
    for attr in sagraph.DOT_ATTRS:
        option_spec['dot-' + attr] = directives.unchanged


    def run (self):
        node = SaUmlNode ()
        env = self.state.document.settings.env
        args = types.SimpleNamespace ()

        node['args'] = args
        node['content'] = self.content
        node['options'] = {}
        node['alt'] = 'UML Database Graph'
        if 'alt' in self.options:
            node['alt'] = self.options['alt']
        if 'align' in self.options:
            node['align'] = self.options['align']

        args.arguments       = self.arguments or env.config.sauml_arguments
        args.schema          = self.options.get ('schema', None)
        args.include         = self.options.get ('include', '').split ()
        args.exclude         = self.options.get ('exclude', '').split ()
        args.include_fields  = self.options.get ('include-fields', '').split ()
        args.include_indices = self.options.get ('include-indices', False)

        if args.include and args.exclude:
            raise SaUmlError ('Use either :include: or :exclude:')

        kw = {}
        kw['content'] = '\n'.join (node['content'])
        for attr in sagraph.DOT_ATTRS:
            kw[attr]  = urllib.parse.parse_qsl (getattr (env.config, 'sauml_dot_' + attr, ''))
            kw[attr] += urllib.parse.parse_qsl (self.options.get ('dot-' + attr, ''))

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

            node['code'] = sagraph.format_as_dot (data, args, **kw)

        except Exception:
            traceback.print_exc ()
            sys.stderr.write (kw['content'])
            raise nodes.SkipNode

        caption = self.options.get ('caption')
        if caption:
            node = graphviz.figure_wrapper (self, node, caption)

        self.add_name (node)
        return [node]


def html_visit_graphviz (self, node):
    # type: (nodes.NodeVisitor, graphviz) -> None
    graphviz.render_dot_html (self, node, node['code'], node['options'], imgcls='sauml')
