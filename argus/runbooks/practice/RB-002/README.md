# RB-002 hands-on practice lab

This lab is a disposable local exercise for `RB-002 - Service/container health check failure`.

## The problem in simple terms

A service can fail a health check in several different ways. The process might be stopped, the application might be
stuck, a dependency might be unavailable, the network path might be broken, or the health check itself might not
match the real service. Docker's health state is therefore evidence about one configured test, not proof that the
whole service works or fails.

The analyst's job is to separate three questions:

1. Is the container process present and running?
2. What exact check is Docker running, and what did that check observe?
3. Does the real application route work from the path that matters to a user?

This fixture intentionally makes those observations disagree. The exact cause is not stated here because finding it
is the exercise.

## Safety boundary

The lab creates only a disposable image, one container, and one bridge network with names beginning in
`argus-lab-rb002` or `argus-rb002`. It stores no persistent data, runs as a non-root user with dropped capabilities,
limits CPU, memory, and process count, and publishes only a loopback port on the laptop. It does not use either Argus
VM and does not touch the production-style `argus-v18-*` objects.

## How the exercise works

Use only the current step in `code.bash`; do not inspect the fixture source yet. Run the block in the terminal named
by its `Where` line. Return the complete output without secrets, either in chat or in the ignored `output.bash` file.
The next diagnostic command will be selected from that evidence. We will observe before changing anything and will
not restart or alter the container merely because Docker reports it as unhealthy.
