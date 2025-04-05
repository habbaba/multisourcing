from odoo import api, SUPERUSER_ID

def create_rules(cr, registry):
    """Create company-specific procurement rules for all companies"""
    env = api.Environment(cr, SUPERUSER_ID, {})

    # For each company that has warehouses
    companies = env['res.company'].search([])
    for company in companies:
        # Skip if no warehouses for this company
        warehouses = env['stock.warehouse'].search([('company_id', '=', company.id)])
        if not warehouses:
            continue

        # Get MTO route for this company
        mto_route = env['stock.route'].search([
            ('name', '=', 'Make To Order'),
            ('company_id', '=', company.id)
        ], limit=1)

        if not mto_route:
            continue

        # Create the priority rule for this company
        priority_vals = {
            'name': 'Multi-Warehouse: Priority-based sourcing',
            'action': 'pull_push',
            'active': False,
            'group_propagation_option': 'propagate',
            'procure_method': 'make_to_stock',
            'route_id': mto_route.id,
            'picking_type_id': warehouses[0].out_type_id.id,
            'location_src_id': warehouses[0].lot_stock_id.id,
            'location_dest_id': env.ref('stock.stock_location_customers').id,
            'warehouse_id': warehouses[0].id,
            'company_id': company.id,
        }
        env['stock.rule'].create(priority_vals)

        # Create the nearest rule for this company
        nearest_vals = {
            'name': 'Multi-Warehouse: Proximity-based sourcing',
            'action': 'pull_push',
            'active': False,
            'group_propagation_option': 'propagate',
            'procure_method': 'make_to_stock',
            'route_id': mto_route.id,
            'picking_type_id': warehouses[0].out_type_id.id,
            'location_src_id': warehouses[0].lot_stock_id.id,
            'location_dest_id': env.ref('stock.stock_location_customers').id,
            'warehouse_id': warehouses[0].id,
            'company_id': company.id,
        }
        env['stock.rule'].create(nearest_vals)