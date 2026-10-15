# Host configuration

The default configuration is `${XDG_CONFIG_HOME:-$HOME/.config}/faviann-skills/artifacts.json`. `FAVIANN_SKILLS_ARTIFACT_CONFIG` selects another file for one invocation. The JSON object requires `directory` and `baseUrl`; `gallery` is optional:

```json
{
  "directory": "/existing/web/root",
  "baseUrl": "https://artifacts.example.com/files",
  "gallery": "3f9c2a7d0b6e4f18a5c1d2e3b4a59687"
}
```

`directory` is an existing absolute publishing root. It may resolve through an infrastructure-owned symlink or mount. Every publisher-owned descendant must remain a real directory or regular file contained beneath the canonical root.

`baseUrl` is an HTTP(S) URL with a hostname, IPv4 address, or bracketed IPv6 authority, an optional port, and no query or fragment. Host and optional userinfo use URI authority characters and complete `%HH` escapes; dotted IPv4 octets and ports stay within their numeric ranges. A trailing slash is accepted and normalized. Unknown configuration fields are ignored.

`gallery`, when present, is one path segment of at least 16 letters, digits, underscores, or hyphens. Every publication rebuilds a page at `<baseUrl>/<gallery>/` that lists the versioned artifacts under the root. Anyone holding that URL can reach every listed artifact, so use a random value such as `openssl rand -hex 16`. A repository group with the same name is refused.

An absent default file produces `unconfigured`. A selected missing file, an unreadable file, or invalid content produces a `configuration` error.

Publication runs on Linux with Bash, `jq`, util-linux `flock`, and GNU coreutils 9.5 or later, whose `mv --exchange` swaps `latest/` atomically; the root's filesystem must support that exchange. A linked worktree also needs Git to derive its primary-checkout group; outside Git, the invocation-directory name is the fallback.

## Layout

```text
<directory>/<repository>/<producer>/<slug>-<24 hex>/
  index.html      viewer page, identical for every artifact
  artifact.json   title and version list
  v1/ v2/ ...     immutable copy of each publication
  latest/         copy of the newest version
<directory>/<gallery>/index.html and gallery.json
```

The random suffix is the access control for each artifact: every artifact URL contains it. Publications serialize on a lock on the canonical root. Earlier timestamped publications at `<producer>/<UTC timestamp>-<24 hex>/` stay where they are and stay out of the gallery.

## Serving

Serve `index.html` for a directory URL. Directory listings and symlink following are not required. Raw files are byte-identical copies, so serving `.md` as `text/plain` keeps them readable to web fetchers.

The viewer and gallery pages never change between publications, so long cache lifetimes are safe for them. They read `artifact.json` and `gallery.json` with a cache-busting query, so a new version appears without revalidation. Files under `v<n>/` never change. Files under `latest/` change in place, so a client that caches by URL can see an older copy until its cache expires.

The host owns root creation, modes, ownership, serving, access control, and retention. The publisher leaves those properties unchanged, treats artifact content as opaque, and constructs the URL without checking HTTP reachability.
