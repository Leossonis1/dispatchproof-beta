DispatchProof V2.45 — Training / Simulation Mode

Apply this patch over V2.44.3.

No new Render environment variables are required.
Database changes are automatic and additive.

First test after deploy:
1. Sign in as Owner/Admin.
2. Open Training.
3. Assign "New PM Basics" to an Operations user.
4. Sign in as that user and confirm Training shows the assigned scenario.
5. Make one intentionally wrong choice and confirm coaching appears without advancing.
6. Choose the correct action and confirm the scenario advances.

Training writes only to training-specific tables and does not send real communications or change production jobs, crew, routes, contractor searches, or reports.
