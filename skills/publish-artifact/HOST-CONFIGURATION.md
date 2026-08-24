# Host configuration

The default configuration is `${XDG_CONFIG_HOME:-$HOME/.config}/faviann-skills/artifacts.json`. `FAVIANN_SKILLS_ARTIFACT_CONFIG` selects another file for one invocation. The JSON object requires:

```json
{
  "directory": "/existing/web/root",
  "baseUrl": "https://artifacts.example.com/files"
}
```

`directory` is an existing absolute publishing root. It may resolve through an infrastructure-owned symlink or mount. Every publisher-owned descendant must remain a real directory or regular file contained beneath the canonical root.

`baseUrl` is an HTTP(S) URL with a hostname, IPv4 address, or bracketed IPv6 authority, an optional port, and no query or fragment. Host and optional userinfo use URI authority characters and complete `%HH` escapes; dotted IPv4 octets and ports stay within their numeric ranges. A trailing slash is accepted and normalized. Unknown configuration fields are ignored.

An absent default file produces `unconfigured`. A selected missing file, an unreadable file, or invalid content produces a `configuration` error.

Publication runs on Linux with Bash and `jq`. A linked worktree also needs Git to derive its primary-checkout group; outside Git, the invocation-directory name is the fallback.

The host owns root creation, modes, ownership, serving, access control, and retention. The publisher leaves those properties unchanged, treats artifact content as opaque, and constructs the URL without checking HTTP reachability.
