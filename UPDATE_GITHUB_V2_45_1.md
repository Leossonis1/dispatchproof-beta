# DispatchProof V2.45.1 — Training Feedback + Shuffle

Targeted training-mode polish on top of V2.45.

- 8 questions per scenario / 56 total questions.
- Question order is randomized per assignment and reshuffled on Reset / Practice Again.
- Strong green Correct and orange/red Not Quite feedback banners appear directly above the simulation.
- Incorrect answers keep the trainee on the same question with coaching.
- Existing training assignments migrate automatically via the new nullable `question_order` column.
- No production job, crew, email, routing, contractor-search, or client-report workflow was changed.
