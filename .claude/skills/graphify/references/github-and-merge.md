# graphify reference: GitHub clone and cross-repo merge

Load this when the user passed one or more `https://github.com/...` URLs, or named several local subfolders to merge into one graph.

### Step 0 - Clone GitHub repo(s) (only if a GitHub URL was given)

**Single repo:**
```bash
LOCAL_PATH=$(graphify clone <github-url> [--branch <branch>])
# Use LOCAL_PATH as the target for all subsequent steps
```

**Multiple repos (cross-repo graph):**
```bash
# Clone each repo, run the full pipeline on each, then merge
graphify clone <url1>   # → ~/.graphify/repos/<owner1>/<repo1>
graphify clone <url2>   # → ~/.graphify/repos/<owner2>/<repo2>
# Run /graphify on each local path to produce their graph.json files
# Then merge:
graphify merge-graphs \
  ~/.graphify/repos/<owner1>/<repo1>/graphify-out/graph.json \
  ~/.graphify/repos/<owner2>/<repo2>/graphify-out/graph.json \
  --out graphify-out/cross-repo-graph.json
```

Graphify clones into `~/.graphify/repos/<owner>/<repo>` and reuses existing clones on repeat runs. Each node in the merged graph carries a `repo` attribute so you can filter by origin.

**Multiple local subfolders (monorepo or multi-service layout):**

The skill pipeline writes all intermediate and final outputs to `graphify-out/` in the current working directory. Running the skill on each subfolder separately will clobber the same output dir. Instead, use the CLI directly for each subfolder — it places `graphify-out/` *inside* the scanned path:

```bash
graphify extract ./core/ --code-only     # → ./core/graphify-out/graph.json
graphify extract ./service/ --code-only  # → ./service/graphify-out/graph.json
graphify extract ./platform/ --code-only # → ./platform/graphify-out/graph.json

# Then merge at the project root:
graphify merge-graphs \
  ./core/graphify-out/graph.json \
  ./service/graphify-out/graph.json \
  ./platform/graphify-out/graph.json \
  --out graphify-out/graph.json
```

Always pass `--code-only`, and never pass `--dedup-llm`. Without `--code-only`, `graphify extract` sends every doc, paper and image in the subfolder to an LLM backend it picks by itself from the environment — any of `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `MOONSHOT_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `AZURE_OPENAI_API_KEY` with its endpoint, `AWS_PROFILE`/`AWS_REGION`/`AWS_DEFAULT_REGION` alone (bedrock), `OLLAMA_BASE_URL`, or the key of a custom provider registered with graphify — with no prompt, billed to that key. `--code-only` indexes code with the local AST only and skips those files, so nothing leaves the machine. Never choose a backend from which key happens to be set. To extract a subfolder's docs, papers and images as well, tell the owner how many such files it holds and which provider would receive them, and ask them to confirm the upload for that subfolder; only on an explicit yes, run that one subfolder with `--backend <name>` for the provider they confirmed and without `--code-only`. On anything else keep `--code-only` (local modification, skill-safety-13ef11d9).

Once `graphify-out/graph.json` exists, the fast path above takes over: any codebase question runs `graphify query` directly on the merged graph — no re-extraction, no size gate.
