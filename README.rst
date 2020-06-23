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
        'arguments' : [
            'postgresql+psycopg2://user@localhost:5432/database',
            'url2',
            ...
        ],
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

:copyright: Copyright 2019-20 by Marcello Perathoner <marcello@perathoner.de>
:license: BSD, see LICENSE for details.
