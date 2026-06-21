# Architecture Notes

## Request Lifecycle

1. `POST /jobs/upload` validates the uploaded CSV headers and creates a pending job.
2. The API stores the CSV in the shared uploads volume and enqueues `process_job`.
3. The Celery worker marks the job processing, reads the file, and executes the pipeline.
4. Cleaned transactions and the job summary are persisted in PostgreSQL.
5. Clients poll `GET /jobs/{job_id}/status` and fetch `GET /jobs/{job_id}/results`.

## Processing Stages

1. Data cleaning normalizes dates, amounts, currency, status, missing category, and duplicate rows.
2. Anomaly detection flags amount outliers and USD domestic-merchant transactions.
3. LLM classification batches rows that had missing categories.
4. LLM summary builds a structured narrative JSON report from aggregate facts.
5. Fallback logic keeps the job completed even when the LLM provider is unavailable.

## Trade-Offs

Celery is slightly heavier than RQ but gives stronger retry and worker scaling behavior. Local upload storage is fine for this assignment, while production should use object storage. In-memory CSV processing is appropriate for the sample file, while large files should be streamed and inserted in batches.
