# Draft Part B classifications (Claude), 5 Nov 2026, pending Nick's review.
# C = checkable (specific entity, number or structural feature decides it)
# P = pattern-checkable (synonym list / small set of keywords)
# J = judge-only
C = {3:"entity",6:"entity",15:"number",22:"entity",24:"number",28:"entity",30:"number",51:"entity",52:"number",54:"number",58:"entity",
     90:"entity",110:"entity",119:"number",160:"entity",172:"entity+number",181:"structure",182:"structure",183:"length",191:"structure",
     192:"structure",193:"structure",194:"length",196:"entity",207:"structure",212:"structure",217:"structure",223:"structure",230:"structure",
     237:"entity",249:"entity",261:"entity",262:"entity",271:"entity",282:"structure",286:"number",293:"entity"}
P = [4,9,11,13,14,16,18,19,21,62,63,64,65,72,73,74,76,79,82,85,91,94,96,98,100,102,103,104,105,109,111,112,113,114,115,117,118,
     121,124,126,127,133,134,135,136,138,139,140,141,142,143,144,145,146,151,157,158,161,167,170,171,184,188,195,210,211,226,
     241,242,243,244,248,252,254,256,257,259,268,274,277,278,281,284,285,290,291]
NEGATION = [34,36,43,44,53,55,57,59,177]   # judge-only mainly because the response may mention the item to warn against it
