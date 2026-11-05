"""``hermes reddit`` — login, status, logout and a raw API call from the terminal.

Runs the whole OAuth flow without a gateway restart: start the loopback catcher,
print the consent URL, wait for the browser callback, store the refresh token.
"""

from __future__ import annotations

import getpass
import json
import sys
import time

from . import client, login, redaction


def setup_parser(parser) -> None:
    sub = parser.add_subparsers(dest="reddit_command", metavar="<command>")

    do_setup = sub.add_parser(
        "setup",
        help="Save your own Reddit app credentials",
        description="Register an app at https://www.reddit.com/prefs/apps (web app, "
        "redirect uri http://localhost:8080), then store its client id and secret "
        "here. The secret is written to the plugin config file, never to logs.",
    )
    do_setup.add_argument("--client-id", default="", help="App client id.")
    do_setup.add_argument(
        "--client-secret", default="", help="App secret (prompted for when omitted)."
    )
    do_setup.add_argument(
        "--redirect-uri",
        default="",
        help="Redirect URI registered on the app (default http://localhost:8080).",
    )
    do_setup.add_argument(
        "--user-agent", default="", help="User-Agent Reddit requires, e.g. hermes-reddit/0.2 (by /u/you)."
    )
    do_setup.add_argument(
        "--show", action="store_true", help="Print the stored configuration without the secret."
    )
    do_setup.add_argument(
        "--no-validate", action="store_true", help="Skip the read-only credential check."
    )

    do_login = sub.add_parser(
        "login",
        help="Authorize the Reddit account and store a refresh token",
        description="Start the OAuth consent flow, catch the callback on "
        "http://localhost:8080, and store a permanent refresh token.",
    )
    do_login.add_argument("--port", type=int, default=None, help="Callback port (default: configured redirect URI port).")
    do_login.add_argument("--redirect-uri", default="", help="Override the registered redirect URI.")
    do_login.add_argument("--scope", default="", help="Space-separated scopes (default: all).")
    do_login.add_argument(
        "--no-wait",
        action="store_true",
        help="Print the consent URL and exit; finish later with `hermes reddit complete <url>`.",
    )
    do_login.add_argument("--timeout", type=int, default=600, help="Seconds to wait for the callback.")

    do_complete = sub.add_parser(
        "complete", help="Finish login from the full redirect URL with code and state"
    )
    do_complete.add_argument("value", help="Full redirect URL including code and state.")

    sub.add_parser("status", help="Show login state, scopes and account identity")
    sub.add_parser("logout", help="Delete the stored refresh token")
    sub.add_parser(
        "smoke", help="Check app credentials with a read-only public request"
    )

    do_api = sub.add_parser("api", help="Call any Reddit API endpoint")
    do_api.add_argument("method", help="GET, POST, PUT or DELETE")
    do_api.add_argument("path", help="Path on oauth.reddit.com, e.g. /api/v1/me")
    do_api.add_argument("--param", action="append", default=[], metavar="K=V", help="Query parameter.")
    do_api.add_argument("--data", action="append", default=[], metavar="K=V", help="Form field for writes.")
    do_api.add_argument("--app-only", action="store_true", help="Use a read-only application token.")

    lib = sub.add_parser("library", help="Sync, search and manage local Reddit saves")
    lib.add_argument("action", choices=["sync", "capture", "get", "annotate", "remove", "refresh", "stats", "purge", "search", "queue", "read", "unread", "export", "import", "maintain"])
    lib.add_argument("--file", default="", help="Identifier-only bookmark JSON for import/export.")
    lib.add_argument("--target", default="", help="Post/comment fullname or canonical Reddit URL.")
    lib.add_argument("--account", default="", help="Local account namespace; defaults to the stored account.")
    lib.add_argument("--query", default="", help="Literal terms, quoted phrases, -exclusions.")
    lib.add_argument("--pages", type=int, default=1)
    lib.add_argument("--after", default="")
    lib.add_argument("--limit", type=int, default=25)
    lib.add_argument("--offset", type=int, default=0)
    lib.add_argument("--summary", default=None)
    lib.add_argument("--context", default=None)
    lib.add_argument("--notes", default=None)
    lib.add_argument("--tag", action="append", default=None)
    lib.add_argument("--subreddit", default="")
    lib.add_argument("--author", default="")
    lib.add_argument("--kind", choices=["t1", "t3"], default="")
    lib.add_argument("--summary-source", choices=["extractive", "agent_or_user"], default="")
    lib.add_argument("--read", action="store_true", default=None)
    sub.add_parser("secure", help="Encrypt existing Reddit credential files")
    upkeep = sub.add_parser("maintenance", help="Run cleanup and configure bounded background revalidation")
    upkeep.add_argument("--background-refresh", choices=["on", "off"], default=None)

    parser.set_defaults(func=handle)


def _pairs(items: list[str]) -> dict:
    out = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"expected K=V, got {item!r}")
        key, value = item.split("=", 1)
        out[key] = value
    return out


def _print(payload) -> None:
    print(json.dumps(redaction.safe(payload), indent=2, ensure_ascii=False, default=str))


def _setup(args) -> int:
    creds = client.load_credentials()
    if args.show:
        config = client.load_config()
        _print(
            {
                "config_file": str(client.config_path()),
                "config_present": bool(config),
                "source": creds["source"] or None,
                "client_id": creds["client_id"] or None,
                "client_secret_set": bool(creds["client_secret"]),
                "redirect_uri": creds["redirect_uri"],
                "user_agent": creds["user_agent"],
                "logged_in": bool(client.load_token().get("refresh_token")),
            }
        )
        return 0

    client_id = (args.client_id or "").strip()
    secret = (args.client_secret or "").strip()
    redirect = (args.redirect_uri or "").strip()
    user_agent = (args.user_agent or "").strip()

    interactive = not client_id and sys.stdin.isatty()
    if interactive:
        print("Create an app at https://www.reddit.com/prefs/apps (web app).")
        print("Set its redirect uri to exactly the value you enter below.\n")
        client_id = input("Client id (under the app name): ").strip()
        if not redirect:
            redirect = input(f"Redirect uri [{client.DEFAULT_REDIRECT_URI}]: ").strip()
        if not user_agent:
            user_agent = input(
                "User agent, e.g. hermes-reddit/0.2 (by /u/yourname) []: "
            ).strip()

    client_id = client_id or creds["client_id"]
    secret = secret or creds["client_secret"]
    if not client_id:
        print(client.SETUP_HINT, file=sys.stderr)
        return 1
    if not secret:
        if not sys.stdin.isatty():
            print("✗ client secret missing; pass --client-secret.", file=sys.stderr)
            return 1
        secret = getpass.getpass("Client secret (hidden): ").strip()
    if not secret:
        print("✗ client secret is required.", file=sys.stderr)
        return 1

    redirect = redirect or creds["redirect_uri"] or client.DEFAULT_REDIRECT_URI
    user_agent = user_agent or creds["user_agent"] or client.DEFAULT_USER_AGENT

    validation = None
    if not args.no_validate:
        validation = client.validate_app(client_id, secret, user_agent)
        print(f"✓ credentials accepted (app scopes: {validation.get('scopes')})")

    path = client.save_config(
        {
            "client_id": client_id,
            "client_secret": secret,
            "redirect_uri": redirect,
            "user_agent": user_agent,
        }
    )
    _print(
        {
            "saved": str(path),
            "client_id": client_id,
            "redirect_uri": redirect,
            "user_agent": user_agent,
            "validation": validation,
            "next": f"hermes reddit login   (the app's redirect uri must equal {redirect})",
        }
    )
    return 0


def handle(args) -> int:
    command = getattr(args, "reddit_command", None)
    try:
        if command == "secure":
            _print(client.protect_credentials())
            return 0
        if command == "maintenance":
            from . import maintenance
            if args.background_refresh is not None:
                client.save_config({"background_refresh": args.background_refresh == "on"})
            _print(maintenance.run_once())
            return 0
        if command == "library":
            from . import tools
            values = {key: getattr(args, key) for key in ("action", "target", "account", "query", "pages", "after", "limit", "offset", "subreddit", "author", "kind")}
            if args.action == "search":
                values.update(summary_source=args.summary_source, read=args.read)
                if args.tag:
                    values["tag"] = args.tag[0]
                result = tools.reddit_library_search(values)
            else:
                if args.action == "import":
                    from pathlib import Path
                    if not args.file:
                        raise client.RedditError("Supply --file with a bookmark export")
                    path = Path(args.file)
                    if path.stat().st_size > 2000000:
                        raise client.RedditError("Bookmark import exceeds 2 MB")
                    values["bookmarks"] = json.loads(path.read_text(encoding="utf-8"))
                for key in ("summary", "context", "notes"):
                    if getattr(args, key) is not None:
                        values[key] = getattr(args, key)
                if args.tag is not None:
                    values["tags"] = args.tag
                result = tools.reddit_library(values)
            payload = json.loads(result)
            if args.action == "export" and args.file and payload.get("ok"):
                from pathlib import Path
                client._atomic_write(Path(args.file), json.dumps(payload["result"], indent=2))
                _print({"exported": len(payload["result"]["items"]), "file": str(Path(args.file).resolve())})
                return 0
            _print(payload)
            return 0 if payload.get("ok") else 1
        if command == "setup":
            return _setup(args)
        if command == "login":
            return _login(args)
        if command == "complete":
            code, state = login.parse_code(args.value)
            _print(login.finish(code, state=state))
            return 0
        if command == "status":
            session = client.session()
            if session.has_refresh_token:
                _print(session.identity())
            else:
                _print({"logged_in": False, "token_file": str(client.token_path()),
                        "hint": "hermes reddit login"})
            return 0
        if command == "logout":
            _print(login.logout())
            return 0
        if command == "smoke":
            session = client.session()
            listing = session.request(
                "GET", "/r/hermesagent/new", params={"limit": 3}, app_only=True
            )
            items = [
                child["data"].get("title")
                for child in (listing.get("data", {}).get("children") or [])
            ]
            _print({"app_token": "ok", "titles": items, "rate": session.last_rate})
            return 0
        if command == "api":
            session = client.session()
            payload = session.request(
                args.method.upper(),
                args.path,
                params=_pairs(args.param) or None,
                data=_pairs(args.data) or None,
                app_only=bool(args.app_only),
            )
            _print(payload)
            return 0
        print(
            "usage: hermes reddit {setup|login|complete|status|logout|smoke|api}",
            file=sys.stderr,
        )
        return 2
    except (client.RedditError, OSError) as exc:
        print(redaction.safe(f"✗ {exc}"), file=sys.stderr)
        return 1


def _login(args) -> int:
    started = login.start(
        port=args.port, redirect_uri=args.redirect_uri, scope=args.scope
    )
    print("Open this URL in a browser logged in to Reddit and approve access:\n")
    print(started["authorize_url"])
    print(f"\nWaiting for the callback on {started['listening_on']} …")
    if args.no_wait:
        print("\nRerun with `hermes reddit complete <redirect-url>` after approving.")
        return 0

    deadline = time.time() + max(30, args.timeout)
    while time.time() < deadline:
        state = login.result()
        if state["status"] == "logged_in":
            _print(state)
            return 0
        if state["status"] == "failed":
            print(redaction.safe(f"✗ login failed: {state.get('error')}"), file=sys.stderr)
            return 1
        time.sleep(1)
    print("✗ OAuth callback timed out. Check the configured redirect URI and finish with the full redirect URL.", file=sys.stderr)
    return 1
