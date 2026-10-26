# Host configuration

`publish.sh` and `render-check.sh` read `${XDG_CONFIG_HOME:-$HOME/.config}/faviann-skills/artifact-server.json`. The JSON object has two required keys:

```json
{
  "server": "https://artifact-server.example.com",
  "tokenFile": "/home/me/.agents/artifact-server/api-key"
}
```

`server` is the artifact-server origin, an `http://` or `https://` URL with no path. `tokenFile` is the absolute path of a file holding one API key. Both scripts read the file on every run, so replacing the key needs no other change. Unknown fields are ignored.

The key needs the scopes `artifact:create`, `artifact:publish:any`, `artifact:read`, `content-session:issue`, `comment:write`, and `artifact:manage:any`. The last two let it reply to comments and change visibility. The `:any` scopes reach every artifact on the server, including deletion.

An absent file makes `publish.sh` print `{"status":"unconfigured"}` and exit 0. The old `artifacts.json` is no longer read, so a host that only has that file is unconfigured. An unreadable or invalid file, or a missing token file, is a `configuration` error with exit 3.

## What else the host provides

- `artifactserver` on `PATH` (Node 24.12 or later), the CLI that `publish.sh` runs. A missing one is a `dependency` error with exit 4.
- `jq`.
- For `render-check.sh`, which exits 1 when the page breaks and 2 or 3 when the check cannot run, Node with `npx`, network access to fetch Playwright 1.64.1, and `chromium` on `PATH` with a font installed. Without a font, the screenshot shows empty boxes where text belongs.
- For comments and visibility, the server's `/mcp` endpoint registered in the agent's harness as `artifact-server`, authenticated with the same key as a bearer header that a helper reads from `tokenFile` when the harness connects, so no copy of the key sits in the harness config.

The server owns storage, versions, access control, and retention. Every artifact starts private, and only `artifact_set_visibility` over MCP makes one public.
