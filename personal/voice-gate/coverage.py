"""Map catalog patterns to mechanical indicators and contextual review checks."""
from . import mechanics

MECHANICAL = {
    1: ('significance_inflation',), 3: ('tier1a', 'tier1b', 'tier2'),
    5: ('marketing_adjectives',), 7: ('em_dashes',), 8: ('rule_of_three',),
    9: ('negation_positive',), 10: ('copula_avoidance',), 11: ('same_openers',),
    12: ('hedges', 'hedge_stacked'), 13: ('gerund_openings',), 15: ('trailing_qualifiers',),
    16: ('negation_triads',), 18: ('transitions',), 21: ('signposting',),
    56: ('hedge_stacked',), 57: ('real_actual',), 60: ('future_narrative',),
    62: ('hashtag_stuffing',), 63: ('bare_bullet_runs',), 64: ('vague_authority',),
    66: ('parenthetical_hedge',), 67: ('number_inflation',), 73: ('candor_frames',),
    75: ('wh_openers',), 76: ('negative_listing',), 77: ('staccato_runs',),
    79: ('objection_frames',), 81: ('rhetorical_setup',), 84: ('negation_triads',),
    86: ('rhetorical_setup',), 88: ('dev_slogans',), 89: ('question_runs',),
    90: ('same_openers',), 93: ('launch_copy',), 109: ('over_compression',),
}
for key, (ids, _severity, _pattern, _floor, _repair) in mechanics.SPECS.items():
    for number in ids:
        MECHANICAL[number] = (*MECHANICAL.get(number, ()), key)


def review_check(number):
    if number in {2, 4, 108, 110}: return 'voice'
    if 22 <= number <= 43 and number not in {34, 38}: return 'narrative'
    if number in {1, 3, 5, 6, 38, 55, 57, 58, 59, 60, 61, 64, 65, 69, 72, 73, 74, 79, 80, 83, 95, 96, 97, 100, 101}: return 'claims'
    if number in {34, 71, 82, 107}: return 'reader'
    return 'movement'
