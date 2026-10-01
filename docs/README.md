# Documentation

## Run the benchmark

1. [Reproduce the paper](reproduction.md): the evaluation set, model settings, and protocols.
2. [Prepare external resources](resources.md): environments, demonstration images, and recordings.
3. [Run native agents](native-agent-mcp.md): client setup, commands, and MCP tools.
4. [Evaluate reports](binary-judge.md): the binary judgment protocol.

## Understand the code

- [Repository map](repository-layout.md): where to find each component and why there are separate agent and environment directories.
- [Script entry points](../scripts/README.md): episode, batch, and VLA launchers.
- [Environment HTTP API](environment-http-api.md): the Unreal bridge interface.
- [Human baseline judging](human-baseline-judge.md): evaluation of human submissions.
- [Validation](validation.md): tested behavior and known limitations.

## Source history

- [Migration record](migration/README.md): source locations and checksums.
- [Historical research notes](history/README.md): earlier plans and handoffs.
- [Historical scripts](../scripts/legacy/README.md): original pilots and machine-specific reruns.
