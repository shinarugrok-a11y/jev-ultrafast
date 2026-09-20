# Cursor free-reign lab

Cursor may rewrite architecture, add dependencies, benchmarks, adapters, tests, docs, and experiments **in this fork**.

Cursor may not:

- receive relay credentials, production VM credentials, COMPSD secrets, or TypeSafe keys
- embed secrets in the repo, examples, traces, or evals
- push work directly onto an approved/production branch or deployment
- treat a Jev recommendation as authorization, a send, a lane switch, or DONE
- scrape the Kimi TUI; use ACP JSON-RPC (`kimi acp`) only
- make hooks the sole security barrier (they fail open)

Authority remains:

**JEV judges. Kimi thinks and produces. Cursor experiments and builds. Pepper interacts with the computer. Beowulf routes and reconciles. The relay communicates. COMPSD records. Verification proves. Humans authorize.**
