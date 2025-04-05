# -*- coding: utf-8 -*-
{
    'name': 'Advanced Multi-Warehouse Sourcing (Sale & Website)',
    'version': '17.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': """
        Enables multi-warehouse sourcing strategies for Sales Orders,
        integrating with Website selection and configuration.
        Allows direct multi-shipping or collection at a distribution center.
    """,
    'description': """
        Combines website selection of source warehouses with backend logic
        to fulfill Sales Orders based on defined strategies:
        1. Direct Shipping from multiple selected warehouses.
        2. Internal Transfers from multiple selected warehouses to a central
           distribution warehouse before final shipment.
        Configuration available at Website level.
    """,
    'author': 'Generated based on user requirements',
    'depends': [
        'sale_management',
        'stock',
        'website_sale',
        'product',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/website_settings_views.xml',
        'views/product_template_views.xml',
        'views/sale_order_views.xml',
        'views/website_sale_templates.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}