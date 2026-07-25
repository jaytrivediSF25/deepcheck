# Security

## Reporting a vulnerability

Open a [private security advisory](https://github.com/jaytrivediSF25/deepcheck/security/advisories/new).
Please do not open a public issue for anything exploitable. Expect an initial
response within 72 hours.

## Threat model

deepcheck reads adversarial input by design. Three sources of it, and what each
one could do if it were not contained:

| Untrusted input | Who controls it | Contained by |
| --- | --- | --- |
| Video ID / URL argument | Whoever runs the tool | `security.is_video_id`, strict character class before it reaches a subprocess |
| Transcript text | Anyone who can upload a video or edit a caption track | Prompt fencing, `security.wrap_untrusted` |
| Retrieved web content | Any page the researcher visits | Prompt fencing + citation allow-listing |
| Model-emitted URLs | Derived from the two above | `security.safe_url` scheme allow-list, retrieval check |

### 1. Prompt injection

The transcript is attacker-controllable — anyone can upload a video, and caption
tracks are text a third party wrote. The research brief is worse: it contains
material pulled from arbitrary web pages, and a page can be authored specifically
to be read by a model.

Both are wrapped in labelled blocks and preceded by an explicit boundary notice
instructing the model to treat the contents as data, never as instruction, and
never to let them change the task, the schema, the verdict, or the citations.

**Prompting is mitigation, not a guarantee.** No instruction reliably survives a
determined injection, which is why the controls below are enforced in code
rather than asked for in a prompt.

### 2. Fabricated and hostile citations

A verification tool that can be talked into citing a URL is worse than no tool,
because the citation is the part the reader trusts.

Two enforcement points, both in code:

- **Retrieval check.** A source is admissible only if the search tool actually
  returned that URL. A URL the model produces from anywhere else — recollection,
  or text embedded in a hostile page — is dropped, whatever the prompt said.
- **Scheme allow-list.** Only `http` and `https` survive `security.safe_url`.

### 3. Script execution in the report

The HTML report is a self-contained file opened from disk, so a script running
inside it executes in a `file://` context.

`html.escape` does **not** make a URL safe: escaping the text of an attribute is
not the same as validating its scheme, and `<a href="javascript:alert(1)">`
survives escaping untouched. Every URL is therefore validated before it reaches
an `href`. Anything that fails is rendered as inert text marked
*link withheld — unsupported scheme*, never silently dropped.

Outbound links carry `rel="noopener noreferrer"`.

Also rejected: URLs with embedded credentials (`https://trusted.com@evil.example`,
which reads as `trusted.com` at a glance), and control, zero-width, and
bidirectional-override characters, which can make a URL display as a domain
other than the one it points to.

### 4. Command execution

Every subprocess call passes an argument list — never a shell string, never
`shell=True`. The only user-controlled component of any command is the video ID,
which must match `[A-Za-z0-9_-]{11}` exactly. `re.match` with a `$` anchor
accepts a trailing newline, so the check uses `fullmatch` after control
characters are stripped.

All subprocess calls carry timeouts.

### 5. Secrets

The API key is read from the environment or an `ant` profile and is never
written to a report, a log line, or an error message. `.env` is gitignored.

Reports contain no credentials, but they do contain the full transcript's claims
and the URLs consulted. Treat a report as you would the recording it came from.

## What is out of scope

- **Verdict accuracy.** Verdicts are model-generated. A wrong verdict is a bug,
  not a vulnerability, unless it results from an injection that bypasses the
  controls above.
- **`DEEPCHECK_UPSTREAM_PATH`.** It is added to `sys.path`, so anyone who can
  set it can already execute code as you.
- **Upstream projects.** Report issues in `youtube-deepsummary` or `yt-dlp` to
  those projects.

## Verifying the controls

```bash
pytest tests/test_security.py -v
```

Covers scheme rejection, credential-embedding URLs, bidi and zero-width
stripping, video-ID validation, prompt-fence integrity, HTML and Markdown
rendering, and citation admissibility.
