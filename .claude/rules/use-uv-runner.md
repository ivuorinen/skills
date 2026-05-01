# Script Execution

Always invoke Python scripts with `uv run --quiet <script>`, never `python3 <script>`.
New scripts must begin with `#!/usr/bin/env -S uv run --quiet` and include the `# /// script` inline metadata block.
