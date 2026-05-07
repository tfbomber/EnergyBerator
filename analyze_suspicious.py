import sys, json, re
sys.stdout.reconfigure(encoding='utf-8')

with open(r'output\foundation\foundation_structure_results.json', encoding='utf-8') as f:
    foundation = json.load(f)

def range_span(r):
    nums = re.findall(r'\d+', str(r))
    if len(nums) >= 2:
        return abs(int(nums[-1]) - int(nums[0]))
    return 999

rows = []
for c in foundation:
    n = c.get('building_count_total', 0)
    r = c.get('address_range', '')
    span = range_span(r)
    if n < 5:
        continue
    ratio = n / max(span, 1)
    rows.append({
        'street': c['street_name'],
        'plz': c.get('plz', ''),
        'n': n,
        'range': r,
        'span': span,
        'ratio': ratio,
        'sfh_semi': c.get('sfh_semi_detached_count', 0),
        'sfh_row': c.get('sfh_rowhouse_count', 0),
        'sfh_det': c.get('sfh_detached_count', 0),
        'conf': c.get('subtype_confidence', '?'),
    })

rows.sort(key=lambda x: x['ratio'], reverse=True)

print('=== MOST SUSPICIOUS: High building count vs narrow address range ===')
print('  Street                                PLZ    N     Range               Span  N/Span  DHH   RH    Conf')
print('-' * 110)
for r in rows[:14]:
    span_str = str(r['span']) if r['span'] < 999 else '1'
    line = '  {:<38} {:<6} {:<5} {:<20} {:<5} {:<8.1f} {:<5} {:<5} {}'.format(
        r['street'], r['plz'], r['n'], r['range'], span_str,
        r['ratio'], r['sfh_semi'], r['sfh_row'], r['conf'])
    print(line)

print()
print('=== NORMAL baseline: Range and count roughly aligned ===')
print('  Street                                PLZ    N     Range               Span  N/Span  DHH   RH    Conf')
print('-' * 110)
baselines = [r for r in rows if 0.3 <= r['ratio'] <= 1.5 and r['n'] >= 10]
baselines.sort(key=lambda x: x['n'], reverse=True)
for r in baselines[:5]:
    line = '  {:<38} {:<6} {:<5} {:<20} {:<5} {:<8.1f} {:<5} {:<5} {}'.format(
        r['street'], r['plz'], r['n'], r['range'], r['span'],
        r['ratio'], r['sfh_semi'], r['sfh_row'], r['conf'])
    print(line)
