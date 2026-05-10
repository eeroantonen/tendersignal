# Sales Territory Mapping

`config/sales_territory_mapping.csv` is intentionally empty except for headers.

Add only real internal K Group/Onninen account or territory rules. Do not add invented buyers, fake owners, or placeholder customers.

Columns:

- `buyer_contains`: substring match against the public buyer name.
- `country`: exact buyer country code, for example `FIN`.
- `region_contains`: substring match against TED/Hilma region or NUTS field.
- `category_contains`: substring match against TenderSignal category.
- `cpv_prefix`: CPV prefix match.
- `account_segment`: internal segment label.
- `sales_territory`: internal territory label.
- `territory_owner`: real owner/team name.

Rules can combine multiple match columns. If a rule has `country=FIN` and `category_contains=HVAC`, both must match.
