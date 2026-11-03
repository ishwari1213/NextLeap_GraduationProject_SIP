# How to label Data/eval/human_labels.csv

Read each post and fill the six columns from what the text states. Leave a cell empty when the text does not state it. Do not look at the engine's tags first.

- about_sip: yes or no (is the post about SIPs or mutual-fund instalments?)
- stage: before_starting, onboarding, first_instalment, months_2_6, months_7_12, after_year_1 (empty = not stated)
- event: started, continued, paused, reduced, stopped, considering_stopping (empty = not stated)
- trigger: switching_platform_or_plan, goal_or_wealth, market_fall_or_losses, rule_change, charges_or_tax, habit_discipline, app_bug, fund_issue, cash_flow_or_life (empty = not stated)
- theme: goals_and_motivation, platform_and_plan_choice, payments_and_mandates, returns_and_progress, sip_controls, support_and_service, app_experience, charges_and_tax, learning (empty = not stated)
- failure_mode: instalment_failed, debited_after_cancel_or_twice, confusing_returns_or_progress, losses_shake_confidence, cannot_pause_or_change_amount, amount_too_high, app_bug, withdrawal_problem, support_not_resolving (empty = not stated)

Then run: python -m src.phase6_retrieval_testing.agreement score
