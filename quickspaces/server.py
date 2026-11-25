"""HTTP Server & AWS CloudFront `/api/*` Origin Handler for QuickSpaces."""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import platform
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Tuple
from urllib.parse import parse_qs, urlparse

from .spaces_catalog import QuickSpacesWorkspace

ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"
DOCS_DIR = ROOT_DIR / "docs"

WORKSPACE = QuickSpacesWorkspace()

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
}


def route_api_request(
    method: str,
    path: str,
    query: Dict[str, str],
    body: Dict[str, Any],
    request_id: str = "local",
) -> Tuple[int, Dict[str, Any]]:
    """Pure router shared by local HTTP server and AWS Lambda `/api/*` origin behind CloudFront."""
    try:
        if method == "GET" and path == "/api/health":
            return 200, {
                "status": "ok",
                "service": "quickspaces-ai",
                "delivery": os.environ.get("QUICKSPACES_DELIVERY", "cloudfront-s3-oac + api-origin"),
                "aws_region": os.environ.get("AWS_REGION", "us-west-2"),
                "bedrock_model": os.environ.get("QUICKSPACES_BEDROCK_MODEL", "us.amazon.nova-lite-v1:0"),
                "python_version": platform.python_version(),
                "request_id": request_id,
                "spaces_count": len(WORKSPACE.spaces),
                "assets_count": len(WORKSPACE.assets),
            }

        if method == "GET" and path == "/api/state":
            space_id = query.get("space_id") or "space-q3-cloud-arr"
            role_id = query.get("role") or "vp_admin"
            snap = WORKSPACE.get_workspace_snapshot(space_id=space_id, role_id=role_id)
            snap["request_id"] = request_id
            return 200, snap

        if method == "GET" and path.startswith("/api/assets/"):
            asset_id = path.split("/api/assets/", 1)[1].strip("/")
            role_id = query.get("role") or "vp_admin"
            return 200, WORKSPACE.get_asset_detail(asset_id=asset_id, role_id=role_id)

        if method == "POST" and path.endswith("/favorite") and path.startswith("/api/assets/"):
            asset_id = path[len("/api/assets/") : -len("/favorite")].strip("/")
            return 200, WORKSPACE.toggle_favorite(asset_id=asset_id)

        if method == "GET" and path.startswith("/api/spaces/") and path.endswith("/search"):
            space_id = path[len("/api/spaces/") : -len("/search")].strip("/")
            q = query.get("q") or ""
            role_id = query.get("role") or "vp_admin"
            modality = query.get("modality") or "all"
            fav = query.get("favorites_only") == "true"
            return 200, WORKSPACE.search(
                space_id=space_id,
                query=q,
                role_id=role_id,
                modality=modality,
                favorites_only=fav,
            )

        if method == "POST" and path.startswith("/api/spaces/") and path.endswith("/ask"):
            space_id = path[len("/api/spaces/") : -len("/ask")].strip("/")
            question = str(body.get("question") or "").strip()
            if not question:
                return 400, {"error": "Question is required"}
            role_id = str(body.get("role") or "vp_admin")
            out = WORKSPACE.ask(space_id=space_id, question=question, role_id=role_id)
            out["request_id"] = request_id
            return 200, out

        if method == "POST" and path.startswith("/api/spaces/") and path.endswith("/ingest"):
            space_id = path[len("/api/spaces/") : -len("/ingest")].strip("/")
            title = str(body.get("title") or "").strip()
            raw_content = str(body.get("raw_content") or "").strip()
            if not title or not raw_content:
                return 400, {"error": "Both title and raw_content are required"}
            res = WORKSPACE.ingest_custom_asset(
                space_id=space_id,
                title=title,
                filename=str(body.get("filename") or ""),
                modality=str(body.get("modality") or "document"),
                classification=str(body.get("classification") or "INTERNAL"),
                regions=list(body.get("regions") or ["NA", "EMEA"]),
                raw_content=raw_content,
                owner=str(body.get("owner") or "workspace-upload@acmecloud.io"),
                tags=list(body.get("tags") or ["custom-upload"]),
            )
            return 200, res

        if method == "POST" and path.startswith("/api/spaces/") and path.endswith("/governance/remediate"):
            space_id = path[len("/api/spaces/") : -len("/governance/remediate")].strip("/")
            finding_id = body.get("finding_id")
            return 200, WORKSPACE.remediate_governance(space_id=space_id, finding_id=finding_id)

        if method == "POST" and path == "/api/reset":
            WORKSPACE.reset()
            return 200, {"status": "reset_complete"}

        return 404, {"error": f"Unknown API route: {method} {path}"}
    except KeyError as exc:
        return 404, {"error": str(exc)}
    except Exception as exc:
        return 500, {"error": str(exc)}


def lambda_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """AWS Lambda handler mounted behind Amazon CloudFront `/api/*` origin."""
    req_ctx = event.get("requestContext") or {}
    method = ((req_ctx.get("http") or {}).get("method") or event.get("httpMethod") or "GET").upper()
    raw_path = event.get("rawPath") or event.get("path") or "/"
    query_params = {k: str(v) for k, v in (event.get("queryStringParameters") or {}).items() if v is not None}
    req_id = getattr(context, "aws_request_id", "cloudfront-api")

    if method == "OPTIONS":
        return {"statusCode": 204, "headers": CORS_HEADERS, "body": ""}

    if raw_path.startswith("/api/"):
        body: Dict[str, Any] = {}
        raw_body = event.get("body")
        if raw_body:
            if event.get("isBase64Encoded") and isinstance(raw_body, str):
                raw_body = base64.b64decode(raw_body).decode("utf-8")
            body = json.loads(raw_body) if isinstance(raw_body, str) else dict(raw_body)
        status, payload = route_api_request(method, raw_path, query_params, body, request_id=req_id)
        return {
            "statusCode": status,
            "headers": {
                **CORS_HEADERS,
                "Content-Type": "application/json; charset=utf-8",
                "Cache-Control": "no-store",
            },
            "body": json.dumps(payload, default=str),
        }

    # Fallback static serving if someone hits the origin directly during diagnostics
    target = WEB_DIR / ("index.html" if raw_path in ("/", "") else raw_path.lstrip("/"))
    if not target.is_file() and raw_path.endswith(".svg"):
        target = DOCS_DIR / Path(raw_path).name
    if target.is_file():
        ctype = mimetypes.guess_type(str(target))[0] or "text/html; charset=utf-8"
        return {
            "statusCode": 200,
            "headers": {**CORS_HEADERS, "Content-Type": ctype},
            "body": target.read_text(encoding="utf-8"),
        }
    return {
        "statusCode": 404,
        "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps({"error": "Not found", "path": raw_path}),
    }


class LocalQuickSpacesHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = {k: v[0] for k, v in parse_qs(parsed.query).items() if v}

        if path.startswith("/api/"):
            status, payload = route_api_request("GET", path, query, {}, request_id="local-dev")
            raw = json.dumps(payload, indent=2, default=str).encode("utf-8")
            self.send_response(status)
            for k, v in CORS_HEADERS.items():
                self.send_header(k, v)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        candidate = (WEB_DIR / rel).resolve()
        if not candidate.is_file() and path.endswith(".svg"):
            candidate = (DOCS_DIR / Path(path).name).resolve()
        if not candidate.is_file():
            candidate = WEB_DIR / "index.html"

        data = candidate.read_bytes()
        ctype = mimetypes.guess_type(str(candidate))[0] or "text/html"
        if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
            ctype += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or "0")
        raw_body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        body = json.loads(raw_body) if raw_body.strip() else {}
        status, payload = route_api_request("POST", parsed.path, {}, body, request_id="local-dev")
        raw = json.dumps(payload, indent=2, default=str).encode("utf-8")
        self.send_response(status)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def run_local_server(port: int = 3095) -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", port), LocalQuickSpacesHandler)
    print(f"QuickSpaces live workspace running at http://localhost:{port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    port_num = int(os.environ.get("PORT", "3095"))
    run_local_server(port=port_num)
