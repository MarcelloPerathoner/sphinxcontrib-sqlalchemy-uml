# -*- coding: utf-8 -*-

import importlib
import inspect
import os
import re
import sys
import textwrap

import sqlalchemy

DOT_ATTRS = ('graph', 'node', 'edge', 'table', 'td')

def get_pg_pass (url):
    """Get the password from :file:`~/.pgpass` and paste it into the url.

    If you write Sphinx documentation you don't want your passwords in the
    source.  Also works for non-Postgres passwords if you put them into
    :file:`~/.pgpass`.

    """

    URL = sqlalchemy.engine.url.make_url (url)

    if not URL.password:
        try:
            params = ('host', 'port', 'database', 'username') # order must match ~/.pgpass
            pgpass = os.path.expanduser ('~/.pgpass')
            with open (pgpass, 'r') as f:
                for line in f.readlines ():
                    line = line.strip ()
                    if line == '' or line.startswith ('#'):
                        continue
                    # format: hostname:port:database:username:password
                    fields = line.split (':')
                    if all ([field == '*' or field == getattr (URL, param)
                             for field, param in zip (fields, params)]):
                        URL.password = fields[4]
                        break

        except IOError:
            sys.stderr.write ('Error: could not open %s for reading\n' % pgpass)

    return URL


def filter_regexp (regexes, item, negate = False):
    """ Return true if item matches any regex in regexes. """

    for regex in regexes:
        if negate != bool (re.fullmatch (regex, item)):
            return True
    return False


def filter_regexp_list (regexes, items, negate = False):
    """ Return any item in items that matches any regex in regexes.

    Respects the order of the regex list.

    Negate: return those items that *don't* match.
    """

    for regex in regexes:
        for item in items:
            if negate != bool (re.fullmatch (regex, item)):
                yield item


def inspect_urls (args):
    """ Inspect databases. """

    objects = []
    relations = []

    for url in args.urls:
        engine = sqlalchemy.create_engine (get_pg_pass (url))

        meta = sqlalchemy.MetaData ()
        meta.reflect (bind = engine, schema = args.schema)

        tables = meta.tables.keys ()

        if args.include:
            tables = filter_regexp_list (args.include, tables)

        if args.exclude:
            tables = filter_regexp_list (args.exclude, tables, True)

        insp = sqlalchemy.inspection.inspect (engine)

        for item in tables:
            if '.' in item:
                schema, table = item.split ('.')
            else:
                schema = None
                table = item

            pks = set (insp.get_pk_constraint (table, schema = schema)['constrained_columns'])
            fks = set (col for fk in insp.get_foreign_keys (table, schema = schema) for col in fk['constrained_columns'])

            def format_column (col):
                name = col['name']
                try:
                    type_ = str (col['type'])
                except sqlalchemy.exc.CompileError:
                    type_ = 'unknown'
                role = '◦'
                if name in fks:
                    role = '☆'
                if name in pks:
                    role = '★'
                return {
                    'name' : name,
                    'type' : type_,
                    'role' : role,
                }

            def format_index (index):
                return {
                    'name' : index['name'],
                    'type' : 'INDEX({0})'.format (', '.join (index['column_names'])),
                    'role' : '»',
                }

            objects.append ({
                'name'    : item,
                'cols'    : [ format_column (col) for col in insp.get_columns (table, schema = schema)
                              if not args.include_fields or filter_regexp (args.include_fields, col['name'])],
                'indexes' : [ format_index (index) for index in insp.get_indexes (table, schema = schema)
                              if not args.include_fields or filter_regexp (args.include_fields, index['name'])],
            })

            for fkc in insp.get_foreign_keys (table, schema = schema):
                if fkc['referred_schema']:
                    ref_table = fkc['referred_schema'] + '.' + fkc['referred_table']
                else:
                    ref_table = fkc['referred_table']
                if args.include:
                    if not filter_regexp (args.include, fkc['referred_table']):
                        continue
                if args.exclude:
                    if filter_regexp (args.exclude, fkc['referred_table']):
                        continue
                label = []
                for source, target in zip (fkc['constrained_columns'], fkc['referred_columns']):
                    label.append (source if source == target else "%s->%s" % (source, target))

                if label:
                    relations.append ({
                        'from' : item,
                        'by'   : r',\n'.join (label),
                        'to'   : ref_table,
                    })

    return objects, relations


def inspect_modules (args):
    """ Inspect Python modules. """

    objects = []
    relations = []

    classes = [] # list of (name, object)
    for name in args.modules:
        module = importlib.import_module (name)
        classes += inspect.getmembers (module, inspect.isclass)

    if args.include:
        # respect order of include list
        classes = [ x for x in classes if x[0] in args.include ]

    if args.exclude:
        classes = [ x for x in classes if x[0] not in args.exclude ]

    for name, item in classes:
        try:
            table = sqlalchemy.inspection.inspect (item).mapped_table
        except sqlalchemy.exc.NoInspectionAvailable:
            continue

        pks = set (col.name for col in table.primary_key)
        fks = set (col for fk in table.foreign_key_constraints for col in fk.column_keys)

        def format_column (col):
            name = col.name
            role = '◦'
            if name in fks:
                role = '☆'
            if name in pks:
                role = '★'
            return {
                'name' : name,
                'type' : str (col.type),
                'role' : role,
            }

        def format_index (index):
            return {
                'name' : index.name,
                'type' : 'INDEX({0})'.format (', '.join (col.name for col in index.columns)),
                'role' : '»',
            }

        objects.append ({
            'name'    : table.name,
            'cols'    : [ format_column (col) for col in table.columns
                          if not args.include_fields or filter_regexp (args.include_fields, col.name)],
            'indexes' : [ format_index (index) for index in table.indexes
                          if not args.include_fields or filter_regexp (args.include_fields, index.name)],
        })

        for fkc in table.foreign_key_constraints:
            label = []
            for col, fk in zip (fkc.columns, fkc.elements):
                label.append (col.name if col.name == fk.column.name else "%s->%s" % (col.name, fk.column.name))

            relations.append ({
                'from' : table.name,
                'by'   : r',\n'.join (label),
                'to'   : fkc.referred_table,
            })

    return objects, relations


def format_as_plantuml (data, args, **kw):
    """Generate a plantuml UML diagram"""

    objects, relations = data

    def format_class (item, indent = '    ', col_delimiter = ' '):
        """ Format one class object for plantuml output. """

        tab = []
        tab.append ('Class {name} {{'.format (**item))

        fields = ('name', 'role', 'type')

        # calculate column widths from data
        col_widths = {}
        for f in fields:
            col_widths[f] = 0
            for row in item['cols']:    # cols is a list of dicts
                col_widths[f] = max (col_widths[f], len (row[f]))

        # tabulate
        for row in item['cols']:
            t = [ u'{:{}}'.format (row[f], col_widths[f]) for f in fields ]
            tab.append (indent + col_delimiter.join (t))

        tab.append ('}')
        return '\n'.join (tab)

    result = [
        '@startuml',
        'skinparam defaultFontName Courier',
    ]

    for item in objects:
        result.append (format_class (item))

    for item in relations:
        result.append ("{from} <--o {to}: {by}".format (**item))

    result += [
        '@enduml',
    ]

    return '\n\n'.join (result)


def format_as_dot (data, args, **kw):
    """Generate graphviz dot UML diagram"""

    objects, relations = data

    fontname = '"DejaVu Sans Mono"'
    fontsize = '10'

    def setdefault (kw, key, defaults):
        defaults.update (kw[key])
        kw[key] = defaults

    def setdefault_html (kw, key, defaults):
        d = kw[key]
        for k, v in d.items ():
            defaults[k.upper ()] = '"%s"' % v.strip ('"')
        kw[key] = defaults

    setdefault (kw, 'graph', {
        'fontname' : fontname,
        'fontsize' : fontsize,
        'pad'      : '0',
    })
    setdefault (kw, 'node', {
        'fontname' : fontname,
        'fontsize' : fontsize,
        'shape'    : 'none',
        'width'    : '0',
        'height'   : '0',
        'margin'   : '0',
    })
    setdefault (kw, 'edge', {
        'fontname'  : fontname,
        'fontsize'  : fontsize,
        'arrowhead' : 'ediamond',
        'arrowtail' : 'open',
    })
    setdefault_html (kw, 'table', {
        'BGCOLOR'     : '"#fefece"',
        'BORDER'      : '"2"',
        'COLOR'       : '"#a80036"',
        'CELLBORDER'  : '"0"',
        'CELLSPACING' : '"0"',
    })
    setdefault_html (kw, 'td', {
        'ALIGN'  : '"LEFT"',
        'BORDER' : '"0"',
    })

    def as_attrs (kw, item, table_name = None):
        d = dict ()
        for k, v in kw[item].items ():
            k = k.split ('.')
            if len (k) == 1:
                d[k[0]] = v
        if table_name:
            for k, v in kw[item].items ():
                k = k.split ('.')
                if len (k) >= 2 and k[1].upper () == table_name.upper ():
                    d[k[0]] = v

        return ' '.join (["%s=%s" % (k, v) for k, v in d.items ()])

    result = ["""
    /* generated by sagraph.py */

    digraph G {{
        graph [{graph}]
        node [{node}]
        edge [{edge}]
    """.format (
        graph = as_attrs (kw, 'graph'),
        node  = as_attrs (kw, 'node'),
        edge  = as_attrs (kw, 'edge')
    )]

    for item in objects:
        result.append ("""
        "{name}" [label=<
          <TABLE {table}>
            <TR>
              <TD COLSPAN="3" CELLPADDING="4" ALIGN="CENTER" BORDER="2" SIDES="B">
                <B><FONT COLOR="black">{name}</FONT></B>
              </TD>
            </TR>
        """.format (table = as_attrs (kw, 'table', item['name']), **item))

        for i in item['cols'] + (item['indexes'] if args.include_indices else []):
            result.append ("""
            <TR>
              <TD {td}>{name}</TD>
              <TD {td}>{role}</TD>
              <TD {td}>{type}</TD>
            </TR>
            """.format (td = as_attrs (kw, 'td'), **i))

        result.append ("""
          </TABLE>
        >]
        """)

    for item in relations:
        result.append ("""
        "{from}" -> "{to}" [label="{by}"]
        """.format (**item))

    result.append ("""
        {content}
    }}
    """.format (**kw))

    # print (textwrap.dedent (''.join (result)).strip ())
    return textwrap.dedent (''.join (result)).strip ()


if __name__ == '__main__':
    import argparse
    import urllib.parse

    parser = argparse.ArgumentParser (description='Generate UML graph of database.')

    parser.add_argument (
        'args', nargs='+',
        help='The urls or modules to inspect.',
    )

    parser.add_argument (
        '-r', '--render', default='dot',
        choices=['dot', 'plantuml'],
        help='Output format (default: %(default)s)',
    )

    group = parser.add_argument_group (
        title='dot attributes',
        description='Set dot attributes. Use RFC3986 query string format.'
    )

    for attr in DOT_ATTRS:
        group.add_argument (
            '--dot-%s' % attr, dest=attr, default='',
            help='dot %s attributes' % attr,
        )

    parser.add_argument (
        '-i', '--include', action='append',
        help='Name of table to include (regex)',
    )

    parser.add_argument (
        '-e', '--exclude', action='append',
        help='Name of table to exclude (regex)',
    )

    parser.add_argument (
        '--include-fields', dest='include_fields', action='append',
        help='Name of field to include (regex)',
    )

    parser.add_argument (
        '--include-indices', dest='include_indices', action='store_true',
        help='Include the database indices.',
    )

    args = parser.parse_args ()

    args.urls    = [ arg for arg in args.args if '//' in arg]
    args.modules = [ arg for arg in args.args if '//' not in arg]

    if args.urls and args.modules:
        sys.stderr.write ('Error: use either urls or modules\n')
        sys.exit (1)

    if args.urls:
        data = inspect_urls (args)
    if args.modules:
        data = inspect_modules (args)

    kw = {}
    if args.render == 'plantuml':
        print (format_as_plantuml (data, args, **kw))
    else:
        for attr in DOT_ATTRS:
            kw[attr] = urllib.parse.parse_qsl (getattr (args, attr))
        print (format_as_dot (data, args, **kw))
