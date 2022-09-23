# -*- coding: utf-8 -*-
{

    'name': 'CFS - Automated Kickstart App',
    'author': 'Odoo Inc, PS',

    'website': 'https://www.odoo.com',
    'category': 'Sales/Sales',
    'sequence': 1,
    'summary': """
        Install all licensed Apps
    """,

    'license': 'OEEL-1',
    'version': '1.0',

    'description': """
        Installs core Odoo Apps:
    """,

    'depends': [
        'base','mail',
    ],
    'data': [
        'data/translations.xml',
        'data/ir.actions.server.xml',
    ],
    'auto_install': False,
    'application': True,
    "cloc_exclude": ["./**/*"],  # exclude all files in a module recursively
}
