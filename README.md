# DispatchProof V2.40.1 Patch Only

Apply these files over an existing V2.40 installation.

Fixes Operator workspace backup/restore so setup progress is protected even before a job exists. New workspace ZIPs include shared Clients, Projects, Crew, crew unavailability, Client documents, and Project documents in addition to authorized jobs and job files. Restore is additive and does not overwrite existing records.

Important: a zero-job ZIP that was already created by V2.40 cannot contain standalone setup records because V2.40 never wrote those records into that archive. Create a fresh workspace ZIP after deploying V2.40.1.
