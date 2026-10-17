---
name: ark-linux
description: Work on an installed Ark Linux system, its immutable OS deployment, or its persistent agent workspace. Use when choosing where to install tools, locate state, or change Ark system configuration.
---

Ark deploys its host OS through bootc/OSTree. Install development dependencies in the agent environment; host pacman is removed. Host updates use Alga or bootc and take effect through a new deployment.

`~/Work` is a bind mount from `/agents/users/<host-uid>/Work`. Changes through either path affect the same files. Workspace data survives OS rollback. Inside the agent environment, the workspace is `/home/agent/Work`; the container UID may differ from the host UID.

Tool configuration and home state persist independently of the container root filesystem. Record project dependencies in the project so the environment can be rebuilt. `ark-agent status` reports the environment identity.

Skills shipped by Ark live in `/usr/share/agents/skills`. Personal skill directories and project instructions may contain additional instructions. A skill does not grant host privileges or authorization to deploy, publish, or send messages.

Use host integration only when the task requires changing the host; verify the active deployment and relevant service before acting. `/agents` is storage, while the runtime and its mounts define process access. Snapshots cover the Work subvolume, not nested subvolumes or remote services.
