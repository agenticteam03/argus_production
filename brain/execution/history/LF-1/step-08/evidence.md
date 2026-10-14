# LF-1 step 08 - native OTLP cold-request timeout

Ready in 242 seconds; all six services running. The first OTLP request exceeded the 10-second client timeout. No ingestion or read success is claimed. Minimum available RAM was 2385 MiB; no Argus API health failures or core state changes. Cleanup removed all dedicated containers/volumes; NO INTERFERENCE.

Details: [measurements](measurements.json); [guarded invocation](code.bash). The next retry allows up to 60 seconds per Langfuse request while retaining the independent Argus monitor and total deadline.
