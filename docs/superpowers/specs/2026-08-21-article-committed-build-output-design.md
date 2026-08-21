# Article Pipeline, Wave C: publishing a committed build output

**Date:** 2026-08-21
**Status:** Approved (design)
**Author:** brainstorming session
**Extends:** [`2026-08-20-article-pipeline-design.md`](2026-08-20-article-pipeline-design.md), [`2026-08-20-article-cross-project-design.md`](2026-08-20-article-cross-project-design.md)

## Problem

Waves A and B publish by committing the paths the writer reported. That is correct for
two of the three projects that actually have a blog, and wrong for the third — and the
third is the one where the user first tried it.

Verified per project:

| Project | Committed | Built by | Wave A/B publish |
|---|---|---|---|
| `mi-code-ai` (landing) | sources only: an entry in `src/data/blog-posts.json`, `blog/<slug>/index.html`, `main.ts`, a line in `vite.config.ts`. `dist` is not tracked | `deploy.yml` in CI | **Correct as is** |
| `accounting-ai-agent` | sources only: 36 tracked files under `packages/web/content/blog/{ru,en,pl}`. `.next` is not tracked | `deploy-production.yml` in CI | **Correct as is** |
| `ai-budget-assistant` | sources **and** the built site: 208 tracked files under `docs/marketing/seo/site/blog` | `build_blog.py`, run locally; `web-deploy.yml` then copies `docs/marketing/seo/site/blog` into the apex tree it deploys | **Publishes nothing that reaches the site** |

That last row is the whole wave. `web-deploy.yml` says it outright — "Committed builds (regenerate then commit)". A new article's markdown can be committed all day and the site will not change, because what the deploy copies is the generated HTML.

The first real run proved it: the writer produced a correct 10 KB Polish article with
frontmatter matching its 21 siblings, and there was no path from that file to
`ai-budget.pl/blog`.

## Decision, and the one it replaces

The obvious design is "publish runs the project's build, then commits". **Rejected.**
`build_blog.py` renders every language, generates OG images with PIL and rebuilds the
sitemap; putting that inside the publish POST means minutes of blocked request on a
hand-pressed button. Wave B rejected the same shape for the verify command, for the
same reason, and it would be inconsistent to accept it here.

The build already has a home: **the verify command, which the session runs.** For
`mi-code-ai` that is `npm run build`; for `ai-budget-assistant` it is
`python docs/marketing/seo/build_blog.py`. The session runs it in the article root,
reports its output, and the publish gate already refuses a red build. For this project
the build *is* the verification in the strongest sense — it proves the article renders
into the site the deploy will copy.

So publishing needs exactly one thing it does not have: the ability to commit the
build's output alongside the writer's own files.

## Architecture

One new per-project setting, read from the **venue** like every other article setting:

| Key | Default | Meaning |
|---|---|---|
| `article_publish_extra_paths` | `""` | Comma- or newline-separated paths, relative to the article root, staged at publish in addition to `draft_ref`. Empty means today's behaviour exactly. |

For `ai-budget-assistant` it is `docs/marketing/seo/site`. For the other two it stays
empty and nothing about their publish changes.

### Why these paths may be directories, and `draft_ref` may not

`article_publish.py` validates every path it stages: no absolute paths, no `..`, no
glob characters, inside the repository, and **an existing regular file, not a
directory**. That last rule stays for `draft_ref`, because `draft_ref` is a
self-reported value from a Claude session over unauthenticated localhost HTTP, and a
directory there would let one report stage a whole subtree.

`article_publish_extra_paths` is different in exactly the way that matters: it is
typed by the operator into project settings, not reported by a session. A build output
*is* a subtree — 208 files for this project — so directories must be allowed. Every
other check still applies, `--literal-pathspecs` still applies, and `-f` is still
never passed, so a gitignored path in that setting still cannot be committed.

The distinction is the point: **paths an operator configured may name a tree; paths a
session reported may not.**

### Staging order and what the commit says

Publish stages `draft_ref` first, then the extra paths, in one `git add` invocation
per group but a single commit. If the extra paths produce nothing staged — the build
changed nothing — that is not an error; the article's own files are still the commit.
If `draft_ref` produces nothing staged and the extra paths do, that is also fine: on a
project whose sources are gitignored the generated output can legitimately be the only
committable artefact.

The commit message gains one line when extra paths were staged, naming how many files
came from the build, so the diff's size is explained rather than surprising.

## Error handling and risk

| Risk | Handling |
|---|---|
| A path in the setting does not exist | Refuse the publish, naming it. A misconfigured output path must not silently publish a source-only commit that never reaches the site |
| A path in the setting escapes the repository | The existing validator refuses it; the directory allowance does not relax containment |
| The build output is gitignored | `git add` without `-f` refuses it, as designed. The publish then fails with git's own message, which names the ignore rule |
| The build was never run (empty verify command) but extra paths are set | Allowed, and the card and commit still say `unverified`. A stale build output is the operator's problem, and lying about verification is not |
| A huge accidental path (`.`) | Containment and existence checks pass, so this commits the working tree. Mitigated only by it being an operator-typed setting shown back on the settings page — the same trust level as `article_publish_mode` |

## Testing

`scripts/smoke_articles.py`, against throwaway git repositories:

- Extra paths stage a directory tree, and the commit contains both the draft file and
  the tree's files.
- An unrelated modified file outside both `draft_ref` and the extra paths stays
  uncommitted — the wave A guarantee, re-asserted with the new setting in play.
- A non-existent extra path refuses the publish and leaves the index clean.
- An extra path containing `..`, an absolute one, and a glob are each refused.
- Empty extra paths reproduce wave A/B behaviour byte for byte.

## Out of scope

- Running the build from the publish route (see Decision).
- Teaching the center what any project's build command is; it stays a setting.
- Pushing to the VPS, or anything past `git push` — `web-deploy.yml` owns that.
- The starter-kit installer's inability to target an article root in a nested
  repository. It is a real gap, worked around by hand for `mi-code-ai`, and it belongs
  to the installer rather than to publishing.
