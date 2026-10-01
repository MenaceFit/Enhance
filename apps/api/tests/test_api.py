"""API integration tests (jobs run synchronously, SQLite, local storage)."""

from __future__ import annotations

import io
import zipfile

from PIL import Image

API = "/api/v1"


def upload(client, data: bytes, n: int = 1, **form):
    files = [("files", (f"photo{i}.jpg", data, "image/jpeg")) for i in range(n)]
    return client.post(f"{API}/uploads", files=files, data=form)


def signup(client, email: str, password: str = "motdepasse123"):
    return client.post(f"{API}/auth/signup", json={"email": email, "password": password, "accept_privacy": True})


def test_guest_journey_upload_to_export(client, jpeg_bytes):
    assert client.get(f"{API}/auth/me").json()["user"] is None
    r = upload(client, jpeg_bytes)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["jobs"][0]["status"] in ("queued", "succeeded")
    photo_id = body["photos"][0]["id"]

    me = client.get(f"{API}/auth/me").json()
    assert me["user"]["is_guest"] is True
    assert me["credits"]["remaining"] == 2  # 3 guest credits − 1

    photo = client.get(f"{API}/photos/{photo_id}").json()
    assert photo["status"] == "ready", photo
    assert photo["latest_job"]["status"] == "succeeded"
    assert photo["analysis"]["clothing"]["category"] == "hoodie"
    v = photo["current_version"]
    assert v["kind"] == "ai"
    assert v["metrics"]["fidelity"]["score"] >= 85
    assert v["metrics"]["structure"]["passed"] is True
    assert photo["checklist"]["cleaned"] and photo["checklist"]["colors"] and photo["checklist"]["framing"]
    after = client.get(v["after_url"])
    assert after.status_code == 200 and after.headers["content-type"] == "image/webp"

    # live preview with other settings, then save as a version and restore the AI one
    settings = {"intensity": "studio", "preserve_article": True, "hue": 3}
    pv = client.post(f"{API}/photos/{photo_id}/preview", json={"settings": settings})
    assert pv.status_code == 200, pv.text
    assert pv.json()["settings"]["background"] == "neutral"
    again = client.post(f"{API}/photos/{photo_id}/preview", json={"settings": settings}).json()
    assert again["metrics"] == pv.json()["metrics"]  # served from cache
    nv = client.post(f"{API}/photos/{photo_id}/versions", json={"settings": settings, "label": "Fond propre"})
    assert nv.status_code == 201
    detail = client.get(f"{API}/photos/{photo_id}").json()
    assert detail["current_version"]["label"] == "Fond propre"
    assert len(detail["versions"]) == 2
    client.post(f"{API}/photos/{photo_id}/versions/{v['id']}/restore")
    assert client.get(f"{API}/photos/{photo_id}").json()["current_version"]["id"] == v["id"]

    # export → job → signed download, named vinted_ai_01.jpg, no metadata
    job = client.post(f"{API}/photos/{photo_id}/exports", json={"format": "jpg", "quality": "standard"}).json()
    job = client.get(f"{API}/jobs/{job['id']}").json()
    assert job["status"] == "succeeded", job
    assert job["result"]["filename"] == "vinted_ai_01.jpg"
    dl = client.get(job["result"]["download_url"])
    assert dl.status_code == 200
    assert "vinted_ai_01.jpg" in dl.headers["content-disposition"]
    im = Image.open(io.BytesIO(dl.content))
    assert im.format == "JPEG" and not im.getexif()
    assert client.get(f"{API}/photos/{photo_id}").json()["current_version"]["kind"] == "final"


def test_credits_are_enforced_and_refunded(client, jpeg_bytes):
    r = upload(client, jpeg_bytes, n=4)
    assert r.status_code == 402
    assert client.get(f"{API}/auth/me").json()["credits"]["remaining"] == 3
    # an unreadable file is rejected up-front and costs nothing
    bad = client.post(f"{API}/uploads", files=[("files", ("x.jpg", b"not an image", "image/jpeg"))])
    assert bad.status_code == 415
    assert client.get(f"{API}/auth/me").json()["credits"]["remaining"] == 3
    # a corrupted JPEG passes the header probe, fails in the job and is refunded
    corrupted = jpeg_bytes[:2000]
    r = client.post(f"{API}/uploads", files=[("files", ("c.jpg", corrupted, "image/jpeg"))])
    if r.status_code == 201:
        pid = r.json()["photos"][0]["id"]
        assert client.get(f"{API}/photos/{pid}").json()["status"] == "failed"
        assert client.get(f"{API}/auth/me").json()["credits"]["remaining"] == 3


def test_users_are_isolated(client, app, jpeg_bytes):
    from fastapi.testclient import TestClient

    pid = upload(client, jpeg_bytes).json()["photos"][0]["id"]
    with TestClient(app) as other:
        upload(other, jpeg_bytes)
        assert other.get(f"{API}/photos/{pid}").status_code == 404
        assert other.post(f"{API}/photos/{pid}/preview", json={"settings": {}}).status_code == 404
        assert other.delete(f"{API}/photos/{pid}").status_code == 404
    assert client.get(f"{API}/photos/{pid}").status_code == 200


def test_signed_urls_cannot_be_forged(client, jpeg_bytes):
    pid = upload(client, jpeg_bytes).json()["photos"][0]["id"]
    url = client.get(f"{API}/photos/{pid}").json()["current_version"]["after_url"]
    assert client.get(url).status_code == 200
    assert client.get(url.replace("sig=", "sig=0")).status_code == 403
    other_key = url.replace("after.webp", "before.webp")
    assert client.get(other_key).status_code == 403


def test_signup_keeps_guest_photos_and_extends_retention(client, jpeg_bytes):
    pid = upload(client, jpeg_bytes).json()["photos"][0]["id"]
    guest_exp = client.get(f"{API}/photos/{pid}").json()["expires_at"]
    r = signup(client, "seller@example.com")
    assert r.status_code == 201, r.text
    me = r.json()
    assert me["user"]["is_guest"] is False and me["credits"]["plan_code"] == "free"
    photo = client.get(f"{API}/photos/{pid}").json()
    assert photo["expires_at"] > guest_exp
    assert signup(client, "seller@example.com").status_code == 409
    client.post(f"{API}/auth/logout")
    assert client.get(f"{API}/auth/me").json()["user"] is None
    assert client.post(f"{API}/auth/login", json={"email": "seller@example.com", "password": "wrong-password"}).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": "seller@example.com", "password": "motdepasse123"}).status_code == 200
    assert client.get(f"{API}/photos/{pid}").status_code == 200


def test_project_enhance_all_with_consistency(client, jpeg_bytes):
    signup(client, "multi@example.com")
    r = upload(client, jpeg_bytes, n=2)
    project_id = r.json()["project"]["id"]
    job = client.post(f"{API}/projects/{project_id}/enhance", json={"settings": {"intensity": "premium"}}).json()
    assert client.get(f"{API}/jobs/{job['id']}").json()["status"] == "succeeded"
    project = client.get(f"{API}/projects/{project_id}").json()
    assert project["ready_count"] == 2
    for p in project["photos"]:
        detail = client.get(f"{API}/photos/{p['id']}").json()
        assert detail["analysis"]["consistency"]["group_size"] == 2
        assert detail["current_version"]["kind"] == "edited"
    zjob = client.post(f"{API}/projects/{project_id}/exports", json={"format": "webp", "quality": "standard"}).json()
    zjob = client.get(f"{API}/jobs/{zjob['id']}").json()
    assert zjob["status"] == "succeeded"
    z = zipfile.ZipFile(io.BytesIO(client.get(zjob["result"]["download_url"]).content))
    assert sorted(z.namelist()) == ["vinted_ai_01.webp", "vinted_ai_02.webp"]


def test_defects_can_be_acknowledged_not_erased(client, jpeg_bytes):
    pid = upload(client, jpeg_bytes).json()["photos"][0]["id"]
    photo = client.get(f"{API}/photos/{pid}").json()
    defects = [d for d in photo["analysis"]["defects"] if d["kind"] != "speck"]
    assert defects, "the synthetic hoodie has a stain"
    r = client.patch(f"{API}/photos/{pid}/defects/{defects[0]['id']}", json={"status": "acknowledged"})
    assert r.json()["defect_state"][defects[0]["id"]] == "acknowledged"
    # retouching specks is refused in preserve mode: the guard drops them
    s = {"preserve_article": True, "retouch_specks": [1, 2]}
    pv = client.post(f"{API}/photos/{pid}/preview", json={"settings": s}).json()
    assert pv["settings"]["retouch_specks"] == [1, 2]  # stored as asked...
    assert "retouch_specks" in pv["metrics"]["capped"]  # ...but not applied


def test_gdpr_export_and_erasure(client, jpeg_bytes):
    from app.core.config import get_settings

    signup(client, "gdpr@example.com")
    me = client.get(f"{API}/auth/me").json()["user"]
    upload(client, jpeg_bytes)
    job = client.post(f"{API}/account/export").json()
    job = client.get(f"{API}/jobs/{job['id']}").json()
    assert job["status"] == "succeeded"
    z = zipfile.ZipFile(io.BytesIO(client.get(job["result"]["download_url"]).content))
    names = z.namelist()
    assert "donnees.json" in names and any(n.endswith("original.jpg") for n in names)
    assert client.post(f"{API}/account/delete", json={"confirm": "non"}).status_code == 422
    assert client.post(f"{API}/account/delete", json={"confirm": "SUPPRIMER"}).json() == {"deleted": True}
    assert client.get(f"{API}/auth/me").json()["user"] is None
    assert not (get_settings().local_storage_path / "users" / me["id"]).exists()


def test_admin_metrics_and_benchmark(client, jpeg_bytes):
    assert client.get(f"{API}/admin/metrics").status_code == 401
    signup(client, "admin@example.com")
    upload(client, jpeg_bytes)
    m = client.get(f"{API}/admin/metrics?days=7").json()
    assert m["photos"]["processed"] >= 1
    assert any(row["provider"] == "local" for row in m["ai_cost"]["models"])
    assert "mrr_cents" in m["revenue"]
    prov = client.get(f"{API}/admin/providers").json()
    assert {p["name"] for p in prov["providers"]} >= {"local", "anthropic", "rembg", "replicate"}
    r = client.post(f"{API}/admin/benchmarks", json={"profiles": ["local"], "synthetic_count": 2}).json()
    run = client.get(f"{API}/admin/benchmarks/{r['run']['id']}").json()
    assert run["status"] == "succeeded", run
    assert run["summary"][0]["profile"] == "local" and run["summary"][0]["error_rate"] == 0
    plan = client.patch(f"{API}/admin/plans/starter", json={"monthly_credits": 150}).json()
    assert plan["monthly_credits"] == 150


def test_non_admin_forbidden_and_billing(client, jpeg_bytes):
    signup(client, "user@example.com")
    assert client.get(f"{API}/admin/metrics").status_code == 403
    plans = client.get(f"{API}/billing/plans").json()["plans"]
    assert [p["code"] for p in plans] == ["free", "starter", "pro", "business"]
    r = client.post(f"{API}/billing/checkout", json={"plan_code": "pro"}).json()
    assert r["mode"] == "activated"  # no payment provider in development
    me = client.get(f"{API}/auth/me").json()
    assert me["credits"]["plan_code"] == "pro" and me["credits"]["remaining"] == 500


def test_foreign_origin_is_rejected(client):
    r = client.post(f"{API}/auth/guest", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post(f"{API}/auth/guest", headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 200


def test_listing_draft_is_honest(client, jpeg_bytes):
    pid = upload(client, jpeg_bytes).json()["photos"][0]["id"]
    listing = client.get(f"{API}/photos/{pid}/listing").json()
    assert listing["title"].startswith("Hoodie")
    assert listing["size_visible"] == ""  # never invented
    assert "À noter" in listing["condition_notes"]  # the stain is disclosed
