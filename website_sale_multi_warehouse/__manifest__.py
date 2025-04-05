{
    'name': 'Website Sale Multi-Warehouse Delivery',
    'version': '1.0',
    'category': 'Website/Sales',
    'summary': 'Enable multi-warehouse fulfillment for online orders with distribution center consolidation',
    'description': """
        This module enables online orders to be fulfilled from multiple warehouses:
        - Products are sourced from different warehouses based on availability
        - Items are consolidated at a distribution center
        - Final delivery to customer is done from the distribution center
        - Works only for online sales without affecting standard workflows
    """,
    'depends': ['sale_stock', 'website_sale', 'stock', 'delivery'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'views/stock_warehouse_views.xml',
        'views/sale_order_views.xml',
        'views/res_config_settings_views.xml',
    ],
    # Change this line:
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}