#!/bin/bash
# Runs every scenario of the debate panel (4 at a time). Output: d_<name>.json
cd "$(dirname "$0")"
WELF='[{"kind":"cash","audience":"low_income","share":0.3,"budget":60000},{"kind":"service","need":"health","audience":"in_need","budget":40000}]'
run() { python scen2.py "$1" "$2" "$3" "${4:-[]}" > "d_$1.json"; }
run baseline_s11 11 '{}' &
run baseline_s12 12 '{}' &
run baseline_s13 13 '{}' &
run light_touch 11 '{"tax_profit":0.05,"benefit_rate":0,"gov_policies":[]}' &
wait
run institutions 11 '{"firms_enabled":true,"expectations_enabled":true,"inheritance_enabled":true,"min_contract_days":90,"severance_rate":0.5}' &
run stakeholder 11 "{\"tax_profit\":0.35,\"gov_policies\":$WELF,\"min_contract_days\":90,\"severance_rate\":0.5}" &
run shocks 11 '{}' '[[90,"epidemic",{}],[180,"shortage",{"goods":["grain","water"],"severity":0.5,"days":60}]]' &
run light_touch_s12 12 '{"tax_profit":0.05,"benefit_rate":0,"gov_policies":[]}' &
wait
# Replications on seed 12 (added after Round 4 asked for them)
run stakeholder_s12 12 "{\"tax_profit\":0.35,\"gov_policies\":$WELF,\"min_contract_days\":90,\"severance_rate\":0.5}" &
run institutions_s12 12 '{"firms_enabled":true,"expectations_enabled":true,"inheritance_enabled":true,"min_contract_days":90,"severance_rate":0.5}' &
wait
