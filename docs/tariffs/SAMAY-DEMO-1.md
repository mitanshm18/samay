# SAMAY-DEMO-1 (SYNTHETIC: not UP rates)

Every number below is made up for development and tests. None of it is a UPERC rate or
rule, and a bill computed with it is not a real bill. Every result carries status
SYNTHETIC and a banner saying so.

Source: `backend/src/samay/tariffs/samay_demo_1.py`.

| Code | Component | Rule |
| --- | --- | --- |
| C1 | Billing demand | max(recorded MD, 75% of contract demand), exact kVA, never rounded |
| C2 | Demand charge | ₹400 per kVA per billing period x billing demand |
| C3 | Excess demand charge | max(MD - CD, 0) x ₹400 x 1.5, in addition to C2 |
| C4 | Energy charge | ₹9.00 per kVAh x total kVAh |
| C5 | Time-of-day adjustment | peak (18:00-22:00) +₹1.50, off-peak (22:00-06:00) -₹1.00, normal (06:00-18:00) ₹0.00 per kVAh |
| C6 | Electricity duty | 5% of the rounded C2 + C3 + C4 + C5 |
| C7 | Other printed lines | taken as printed, not recalculated, included in the total |
| C8 | Subtotal | C2 + ... + C7 (not a line) |
| C9 | Rounding off | half-up to the rupee of C8, minus C8 |
| | Payable total | C8 + C9 = the sum of all money lines |

Rounding: C2 to C6 are each computed exactly and rounded once, half-up to the paisa.
C5 is the exact sum of the three zone amounts, rounded once.

Time-of-day zones: the three zone kVAh readings must add up exactly to total kVAh. If any
zone is missing, C5 is MISSING (never zero), and so are C6, C8, C9 and the total.

Power factor is shown for information only; this tariff has no power factor charge or
rebate. Charges are not prorated; a period shorter than 28 or longer than 31 days gives a
warning.

## Worked example (from the tests)

CD 500 kVA, MD 412.345 kVA, 100,000 kVAh (peak 25,000, off-peak 30,000, normal 45,000).

| Line | Working (paise) | Amount |
| --- | --- | --- |
| C2 | 40,000 x 412.345 = 16,493,800 | ₹1,64,938.00 |
| C3 | MD below CD | ₹0.00 |
| C4 | 900 x 100,000 = 90,000,000 | ₹9,00,000.00 |
| C5 | 150 x 25,000 - 100 x 30,000 = 750,000 | ₹7,500.00 |
| C6 | 5% x 107,243,800 = 5,362,190 | ₹53,621.90 |
| C8 | 112,605,990 | ₹11,26,059.90 |
| C9 | 112,606,000 - 112,605,990 | ₹0.10 |
| Total | | ₹11,26,060.00 |
