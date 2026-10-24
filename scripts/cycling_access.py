"""Pure WKD bicycle access interpretation; never inherit motor direction."""
def bicycle_direction(row):
    # A missing/unknown field is not permission. Require both explicit J/N fields.
    forward,backward=row.get('FIETS_H'),row.get('FIETS_T')
    if forward not in ('J','N') or backward not in ('J','N'): return 0
    return (1 if forward=='J' else 0)+(2 if backward=='J' else 0)

def eligible_feature(properties,row,snapshot):
    date=(properties.get('wvk_begdat') or '')[:10]
    if not date or date>snapshot: return 0
    if properties.get('bst_code') in {'VDF','VDA','VZ','RP','CADO','DST','BUS','TN'}: return 0
    return bicycle_direction(row)
