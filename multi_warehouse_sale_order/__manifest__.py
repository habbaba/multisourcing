{
    'name': 'Multi Warehouse Sale Order',
    'summary': 'Choose one or multiple warehouses on the sale order line.',
    'description': 'Choose one or multiple warehouses on the sale order line.',
    'author': "Sonny Huynh",
    'category': 'Sales',
    'version': '0.1',
    'depends': ['sale', 'sale_stock', 'website_sale'],

    'data': [
        'security/ir.model.access.csv',
        'views/template_report.xml',
        'views/form_view.xml',
        'wizard/select_warehouse_views.xml',
    ],
    'qweb': [],
    # only loaded in demonstration mode
    'demo': [],
    'images': [
        'static/description/banner.png',
    ],
    'license': 'OPL-1',
    'price': 110.00,
    'currency': 'EUR',
}