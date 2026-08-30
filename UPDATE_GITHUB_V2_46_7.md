# DispatchProof V2.46.7 — Training Answer Shuffle

## Fix
- Training now shuffles the visible answer choices, not only the question order.
- Correct answers are deliberately balanced across the available answer positions for each scenario run.
- Prevents obvious three-correct-answers-in-a-row position streaks when possible.
- Incorrect choices are shuffled too.
- Answer positions remain stable on refresh and after an incorrect attempt so choices do not jump around mid-question.
- Reset / Practice Again produces a new question order and therefore a new answer-position pattern.

## Deployment
Deploy over V2.46.6. No database migration and no Render environment changes are required.
