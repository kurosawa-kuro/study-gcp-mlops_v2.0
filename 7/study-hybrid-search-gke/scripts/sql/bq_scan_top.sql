-- Cost audit: top 20 BigQuery jobs by bytes scanned in the last 7 days.

SELECT job_id,
       total_bytes_processed / POW(10, 9) AS gb,
       user_email
FROM `region-asia-northeast1`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
WHERE creation_time > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
ORDER BY total_bytes_processed DESC
LIMIT 20
